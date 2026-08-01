"""Cache và chia sẻ danh sách dropdown của form Apparel Style.

Snapshot được quét read-only từ WFX tối đa một lần mỗi 30 ngày. App ưu tiên
snapshot GitHub Raw để nhiều máy dùng chung, giữ cache local khi offline và chỉ
ghi GitHub khi máy quản trị đã cấu hình token có quyền Contents.
"""

from __future__ import annotations

import json
import os
import time
from base64 import b64encode
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from wfx_panel.atomic_io import write_json_atomic

SCHEMA_VERSION = 1
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
ENV_LIBRARY_URL = "WFX_STYLE_OPTIONS_LIBRARY_URL"
ENV_GITHUB_TOKEN = "WFX_STYLE_OPTIONS_GITHUB_TOKEN"
ENV_GITHUB_REPOSITORY = "WFX_STYLE_OPTIONS_GITHUB_REPOSITORY"
ENV_GITHUB_BRANCH = "WFX_STYLE_OPTIONS_GITHUB_BRANCH"
DEFAULT_GITHUB_REPOSITORY = "sieuxuan/WFX-APP"
DEFAULT_GITHUB_BRANCH = "main"
GITHUB_SNAPSHOT_PATH = "data/style-options.json"
DEFAULT_LIBRARY_URL = (
    "https://raw.githubusercontent.com/sieuxuan/WFX-APP/main/"
    "data/style-options.json"
)
FIELD_KEYS = (
    "material_type",
    "buyer",
    "division",
    "product_group",
    "color_card",
    "size_range",
    "season",
)


def _cache_path(base_dir: Path) -> Path:
    return Path(base_dir) / "style-options.json"


def _values(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = str(item.get("label") or item.get("value") or "").strip()
        else:
            value = str(item or "").strip()
        identity = value.casefold()
        if not value or identity in seen:
            continue
        seen.add(identity)
        result.append(value[:300])
    return result[:10_000]


def normalise_snapshot(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    fields_raw = raw.get("fields")
    if not isinstance(fields_raw, Mapping):
        return None
    fields = {key: _values(fields_raw.get(key)) for key in FIELD_KEYS}
    if not fields["material_type"]:
        fields["material_type"] = ["KNIT", "WOVEN"]
    if not fields["buyer"] or not fields["product_group"] or not fields["season"]:
        return None
    dependencies_raw = raw.get("subcategories_by_product_group")
    dependencies: dict[str, list[str]] = {}
    if isinstance(dependencies_raw, Mapping):
        for product_group, raw_values in dependencies_raw.items():
            key = str(product_group or "").strip()[:300]
            values = _values(raw_values)
            if key and values:
                dependencies[key] = values
    if not dependencies:
        return None
    generated_at = float(raw.get("generated_at") or 0)
    saved_at = float(raw.get("saved_at") or generated_at or time.time())
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or saved_at,
        "saved_at": saved_at,
        "source": str(raw.get("source") or "cache")[:80],
        "company_id": str(raw.get("company_id") or "")[:80],
        "division_key": str(raw.get("division_key") or "")[:160],
        "group_id": str(raw.get("group_id") or "")[:80],
        "fields": fields,
        "subcategories_by_product_group": dependencies,
    }


def load_cached(base_dir: Path, *, allow_expired: bool = True) -> dict[str, Any] | None:
    try:
        raw = json.loads(_cache_path(base_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    snapshot = normalise_snapshot(raw)
    if snapshot is None:
        return None
    if not allow_expired and time.time() - snapshot["generated_at"] >= CACHE_TTL_SECONDS:
        return None
    return snapshot


def save_snapshot(base_dir: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    normalised = normalise_snapshot(snapshot)
    if normalised is None:
        raise ValueError("Danh sách dropdown Style không hợp lệ.")
    normalised["saved_at"] = time.time()
    target = _cache_path(base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(target, normalised, separators=(",", ":"))
    return normalised


def status(base_dir: Path) -> dict[str, Any]:
    snapshot = load_cached(base_dir)
    if snapshot is None:
        return {"available": False, "fresh": False, "generated_at": 0}
    return {
        "available": True,
        "fresh": time.time() - snapshot["generated_at"] < CACHE_TTL_SECONDS,
        "generated_at": snapshot["generated_at"],
        "source": snapshot["source"],
        "field_count": sum(len(values) for values in snapshot["fields"].values()),
        "dependency_count": len(snapshot["subcategories_by_product_group"]),
    }


def sync_remote(base_dir: Path) -> dict[str, Any] | None:
    url = os.getenv(ENV_LIBRARY_URL, "").strip() or DEFAULT_LIBRARY_URL
    if not url.casefold().startswith("https://"):
        return None
    try:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "WFX-Smart-Style-Options/1"})
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            return None
        remote = normalise_snapshot(json.loads(payload.decode("utf-8-sig")))
        if remote is None:
            return None
        local = load_cached(base_dir)
        if local is None or remote["generated_at"] > local["generated_at"]:
            remote["source"] = "github"
            return save_snapshot(base_dir, remote)
        return local
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError):
        return None


def publish_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """Ghi snapshot lên GitHub Contents API khi máy quản trị có token."""
    token = (
        os.getenv(ENV_GITHUB_TOKEN, "").strip()
        or os.getenv("GH_TOKEN", "").strip()
    )
    repository = (
        os.getenv(ENV_GITHUB_REPOSITORY, "").strip()
        or DEFAULT_GITHUB_REPOSITORY
    )
    branch = os.getenv(ENV_GITHUB_BRANCH, "").strip() or DEFAULT_GITHUB_BRANCH
    if not token or repository.count("/") != 1 or not branch:
        return False
    normalised = normalise_snapshot(snapshot)
    if normalised is None:
        return False
    url = (
        f"https://api.github.com/repos/{repository}/contents/"
        f"{GITHUB_SNAPSHOT_PATH}"
    )
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "WFX-Smart-Style-Options/1",
    }
    sha = ""
    try:
        request = Request(
            f"{url}?ref={quote(branch, safe='')}",
            headers=headers,
        )
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            existing = json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
        if isinstance(existing, Mapping):
            sha = str(existing.get("sha") or "").strip()
    except HTTPError as error:
        if error.code != 404:
            return False
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError):
        return False

    content = json.dumps(
        normalised,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    body: dict[str, str] = {
        "message": "chore: refresh Style options snapshot",
        "content": b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    try:
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="PUT",
        )
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status) in (200, 201)
    except OSError:
        return False
