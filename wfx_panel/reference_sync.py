"""Đồng bộ dữ liệu tham chiếu Article/Style qua n8n + PostgreSQL.

User chỉ đọc snapshot đã publish và giữ cache offline 30 ngày. Máy quản trị có
thể publish cache Article/Style hiện tại; admin key chỉ được đọc từ DPAPI/env,
không bao giờ trả về WebView hoặc ghi vào log.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from wfx_panel import article_library, prefs, style_options
from wfx_panel.atomic_io import write_json_atomic

DEFAULT_READ_URL = "https://n8n.itx.io.vn/webhook/wfx-sync-latest"
DEFAULT_PUBLISH_URL = "https://n8n.itx.io.vn/webhook/wfx-sync-publish"
DEFAULT_COMPANY_ID = "77400"
DEFAULT_DIVISION_KEY = "01"
SYNC_TTL_SECONDS = 30 * 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 60
MAX_RESPONSE_BYTES = 35 * 1024 * 1024
ENV_READ_KEY = "WFX_SYNC_READ_KEY"
ENV_READ_URL = "WFX_SYNC_READ_URL"
ENV_PUBLISH_URL = "WFX_SYNC_PUBLISH_URL"
ENV_COMPANY_ID = "WFX_SYNC_COMPANY_ID"
ENV_DIVISION_KEY = "WFX_SYNC_DIVISION_KEY"


def _safe_https_url(value: str) -> str:
    """Chỉ cho phép HTTPS, giống article_library và style_options.

    Hai URL này đến từ env hoặc `sync-config.json` rồi đi thẳng vào
    ``urlopen``. Không kiểm scheme thì một cấu hình nhầm ``http://`` đủ để đẩy
    read key và admin key qua mạng dưới dạng rõ, còn ``file://`` biến chính
    ``_request_json`` thành trình đọc file cục bộ.
    """
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Địa chỉ máy chủ đồng bộ phải là HTTPS.")
    return url


def _state_path(base_dir: Path) -> Path:
    return Path(base_dir) / "reference-sync.json"


def _private_config_paths(base_dir: Path) -> tuple[Path, ...]:
    return (
        Path(base_dir) / "sync-config.json",
        prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "sync-config.json",
    )


def _load_private_config(base_dir: Path) -> dict[str, str]:
    for path in _private_config_paths(base_dir):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, Mapping):
            return {
                str(key): str(value or "").strip()
                for key, value in raw.items()
            }
    return {}


def _config(base_dir: Path) -> dict[str, str]:
    private = _load_private_config(base_dir)
    return {
        "read_url": os.getenv(ENV_READ_URL, "").strip()
        or private.get("read_url", "")
        or DEFAULT_READ_URL,
        "publish_url": os.getenv(ENV_PUBLISH_URL, "").strip()
        or private.get("publish_url", "")
        or DEFAULT_PUBLISH_URL,
        "read_key": os.getenv(ENV_READ_KEY, "").strip()
        or private.get("read_key", ""),
        "company_id": os.getenv(ENV_COMPANY_ID, "").strip()
        or private.get("company_id", "")
        or DEFAULT_COMPANY_ID,
        "division_key": os.getenv(ENV_DIVISION_KEY, "").strip()
        or private.get("division_key", "")
        or DEFAULT_DIVISION_KEY,
    }


def _load_state(base_dir: Path) -> dict[str, Any]:
    try:
        raw = json.loads(_state_path(base_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _save_state(base_dir: Path, **updates: Any) -> dict[str, Any]:
    state = {**_load_state(base_dir), **updates}
    target = _state_path(base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(target, state, separators=(",", ":"))
    return state


def status(base_dir: Path) -> dict[str, Any]:
    state = _load_state(base_dir)
    last_success = float(state.get("last_success") or 0)
    article_state = article_library.status(base_dir)
    style_state = style_options.status(base_dir)
    config = _config(base_dir)
    return {
        "configured": bool(config["read_key"]),
        "admin_configured": bool(prefs.load_sync_admin_key(base_dir=base_dir)),
        "version": str(state.get("version") or ""),
        "published_at": str(state.get("published_at") or ""),
        "last_success": last_success,
        "fresh": bool(last_success and time.time() - last_success < SYNC_TTL_SECONDS),
        "company_id": str(state.get("company_id") or config["company_id"]),
        "division_key": str(state.get("division_key") or config["division_key"]),
        "article_count": int(article_state.get("article_count") or 0),
        "style_option_count": int(style_state.get("field_count") or 0),
        "subcategory_group_count": int(style_state.get("dependency_count") or 0),
    }


def _request_json(request: Request) -> dict[str, Any]:
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Dữ liệu đồng bộ vượt giới hạn dung lượng.")
    decoded = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(decoded, Mapping):
        raise ValueError("Server đồng bộ trả dữ liệu không hợp lệ.")
    return dict(decoded)


def sync_latest(
    base_dir: Path,
    log: Callable[[str], None] = print,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Tải snapshot mới; lỗi mạng không xóa cache cuối cùng."""
    current = status(base_dir)
    if not force and current["fresh"]:
        return {
            "ok": True,
            "code": "REFERENCE_SYNC_CURRENT",
            "message": "Dữ liệu Article/Style vẫn còn hạn trong tháng này.",
            **current,
        }
    config = _config(base_dir)
    if not config["read_key"]:
        return {
            "ok": False,
            "code": "REFERENCE_SYNC_NOT_CONFIGURED",
            "message": "Bản app chưa có khóa đọc dữ liệu đồng bộ.",
            **current,
        }
    state = _load_state(base_dir)
    query = {
        "company_id": config["company_id"],
        "division_key": config["division_key"],
    }
    version = str(state.get("version") or "").strip()
    if version:
        query["client_version"] = version
    try:
        # Dựng Request bên trong try: read key nằm trong header nên URL phải
        # được xác thực HTTPS trước khi có bất kỳ lời gọi mạng nào, và lỗi cấu
        # hình phải trả về kết quả thân thiện thay vì ném ra bridge.
        request = Request(
            f"{_safe_https_url(config['read_url'])}?{urlencode(query)}",
            headers={
                "Accept": "application/json",
                "User-Agent": "WFX-Smart-Reference-Sync/1",
                "x-wfx-read-key": config["read_key"],
            },
        )
        response = _request_json(request)
        if not response.get("ok"):
            raise ValueError(str(response.get("message") or "Server chưa có dữ liệu."))
        now = time.time()
        remote_version = str(response.get("version") or version).strip()
        published_at = str(response.get("published_at") or "").strip()
        if response.get("not_modified") is True:
            _save_state(
                base_dir,
                version=remote_version,
                published_at=published_at,
                last_success=now,
                company_id=config["company_id"],
                division_key=config["division_key"],
            )
        else:
            articles = response.get("articles")
            options = response.get("style_options")
            dependencies = response.get("style_subcategories")
            if not isinstance(articles, list) or not isinstance(options, list):
                raise ValueError("Snapshot server thiếu Article hoặc Style options.")
            article_library.save_server_articles(
                base_dir,
                articles,
                version=remote_version,
                generated_at=published_at,
            )
            style_options.save_server_options(
                base_dir,
                options,
                dependencies if isinstance(dependencies, list) else [],
                version=remote_version,
                published_at=published_at,
                company_id=config["company_id"],
                division_key=config["division_key"],
            )
            _save_state(
                base_dir,
                version=remote_version,
                published_at=published_at,
                last_success=now,
                company_id=config["company_id"],
                division_key=config["division_key"],
            )
        result = status(base_dir)
        log(
            "[REFERENCE SYNC] Đã cập nhật "
            f"{result['article_count']} Article và "
            f"{result['style_option_count']} lựa chọn Style."
        )
        return {
            "ok": True,
            "code": "REFERENCE_SYNC_UPDATED",
            "message": "Đã đồng bộ dữ liệu Article/Style từ server.",
            **result,
        }
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        log(f"[REFERENCE SYNC] Dùng cache hiện có: {type(error).__name__}.")
        return {
            "ok": False,
            "code": "REFERENCE_SYNC_FAILED",
            "message": "Chưa đồng bộ được; app tiếp tục dùng cache gần nhất.",
            "error_type": type(error).__name__,
            **status(base_dir),
        }


def _current_bundle(base_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    article_cache = article_library.load_cached(base_dir)
    style_cache = style_options.load_cached(base_dir)
    if article_cache is None or style_cache is None:
        raise ValueError("Cần có cache Article và Style trước khi publish.")
    articles = [
        {
            "article_code": str(option.get("article_code") or ""),
            "article_name": str(option.get("article_name") or ""),
            "buyer_reference": str(option.get("buyer_reference") or ""),
        }
        for section in article_cache.get("sections") or []
        for option in section.get("options") or []
    ]
    flat_options = [
        {
            "material_type": "",
            "field_name": field_name,
            "option_value": value,
            "option_label": value,
        }
        for field_name, values in style_cache["fields"].items()
        for value in values
    ]
    dependencies = [
        {
            "material_type": "",
            "product_group": product_group,
            "sub_category": value,
        }
        for product_group, values in style_cache[
            "subcategories_by_product_group"
        ].items()
        for value in values
    ]
    return articles, flat_options, dependencies


def publish_current(
    base_dir: Path,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Publish cache hiện tại bằng admin key đã lưu cục bộ."""
    admin_key = prefs.load_sync_admin_key(base_dir=base_dir)
    if not admin_key:
        return {
            "ok": False,
            "code": "REFERENCE_ADMIN_KEY_REQUIRED",
            "message": "Hãy lưu Admin key trên máy này trước khi publish.",
            **status(base_dir),
        }
    try:
        articles, options, dependencies = _current_bundle(base_dir)
        config = _config(base_dir)
        version = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        body = json.dumps(
            {
                "company_id": config["company_id"],
                "division_key": config["division_key"],
                "version": version,
                "articles": articles,
                "style_options": options,
                "style_subcategories": dependencies,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            _safe_https_url(config["publish_url"]),
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "WFX-Smart-Reference-Sync/1",
                "x-wfx-admin-key": admin_key,
            },
        )
        response = _request_json(request)
        if not response.get("ok"):
            raise ValueError(str(response.get("message") or "Publish thất bại."))
        published_version = str(response.get("version") or version)
        published_at = str(response.get("published_at") or "")
        _save_state(
            base_dir,
            version=published_version,
            published_at=published_at,
            last_success=time.time(),
            company_id=config["company_id"],
            division_key=config["division_key"],
        )
        log(
            "[REFERENCE SYNC] Admin đã publish "
            f"{len(articles)} Article và {len(options)} lựa chọn Style."
        )
        return {
            "ok": True,
            "code": "REFERENCE_SYNC_PUBLISHED",
            "message": "Đã publish dữ liệu hiện tại lên PostgreSQL.",
            "published_counts": dict(response.get("counts") or {}),
            **status(base_dir),
            "version": published_version,
        }
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        log(f"[REFERENCE SYNC] Publish lỗi: {type(error).__name__}.")
        return {
            "ok": False,
            "code": "REFERENCE_SYNC_PUBLISH_FAILED",
            "message": "Chưa publish được dữ liệu lên server.",
            "error_type": type(error).__name__,
            **status(base_dir),
        }
