"""Báo lỗi tối giản qua webhook, không để lộ endpoint trong giao diện.

Webhook mặc định sẽ được điền sau vào ``DEFAULT_WEBHOOK_URL``. Trong lúc phát
triển có thể đặt ``WFX_ERROR_WEBHOOK_URL`` trong environment hoặc file .env
của app. Payload tự động tuyệt đối không chứa credential, URL WFX, query hay
ảnh chụp màn hình.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_WEBHOOK_URL = ""
ENV_NAME = "WFX_ERROR_WEBHOOK_URL"
MAX_OUTBOX = 100
SCHEMA_VERSION = 1
_LOCK = threading.Lock()


def _outbox_path(base_dir: Path) -> Path:
    return Path(base_dir) / "telemetry-outbox.json"


def _read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip()
        try:
            parsed = json.loads(value)
            return str(parsed).strip()
        except (json.JSONDecodeError, TypeError):
            return value.strip("\"' ")
    return ""


def webhook_url(base_dir: Path) -> str:
    """Resolve endpoint mà không bao giờ trả nó qua PanelAPI/UI."""
    return (
        os.getenv(ENV_NAME, "").strip()
        or _read_env_value(Path(base_dir) / ".env", ENV_NAME)
        or DEFAULT_WEBHOOK_URL.strip()
    )


def is_configured(base_dir: Path) -> bool:
    return webhook_url(base_dir).startswith(("https://", "http://"))


def outbox_count(base_dir: Path) -> int:
    return len(_load_outbox(base_dir))


def _load_outbox(base_dir: Path) -> list[dict[str, Any]]:
    path = _outbox_path(base_dir)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_outbox(base_dir: Path, rows: list[dict[str, Any]]) -> None:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = _outbox_path(base_dir)
    if not rows:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(rows[-MAX_OUTBOX:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def enqueue(base_dir: Path, event: dict[str, Any]) -> int:
    envelope = {
        "schema": SCHEMA_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **event,
    }
    with _LOCK:
        rows = _load_outbox(base_dir)
        rows.append(envelope)
        rows = rows[-MAX_OUTBOX:]
        _write_outbox(base_dir, rows)
        return len(rows)


def _discord_payload(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "event")
    title = "WFX Smart · Báo lỗi" if event_type == "automation_error" else "WFX Smart · Góp ý"
    fields = []
    for key in ("kind", "code", "method", "run_id", "elapsed_ms", "app_version"):
        value = event.get(key)
        if value in (None, ""):
            continue
        fields.append(
            {
                "name": key.replace("_", " ").title(),
                "value": str(value)[:1000],
                "inline": key not in {"run_id"},
            }
        )
    description = str(event.get("message") or "Báo lỗi tự động (không kèm dữ liệu nghiệp vụ).")
    return {
        "username": "WFX Smart Reporter",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "description": description[:4000],
                "fields": fields[:20],
            }
        ],
    }


def _post(url: str, event: dict[str, Any], timeout: float = 5.0) -> None:
    payload = (
        _discord_payload(event)
        if "discord.com/api/webhooks/" in url
        or "discordapp.com/api/webhooks/" in url
        else event
    )
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "WFX-Smart-Reporter/1",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= int(response.status) < 300:
            raise HTTPError(url, response.status, "Webhook rejected", {}, None)


def flush(base_dir: Path) -> dict[str, Any]:
    url = webhook_url(base_dir)
    if not url.startswith(("https://", "http://")):
        return {
            "ok": True,
            "code": "WEBHOOK_NOT_CONFIGURED",
            "sent": 0,
            "queued": len(_load_outbox(base_dir)),
        }
    sent = 0
    with _LOCK:
        rows = _load_outbox(base_dir)
        remaining: list[dict[str, Any]] = []
        for index, event in enumerate(rows):
            try:
                _post(url, event)
                sent += 1
            except (OSError, HTTPError, URLError, ValueError):
                remaining.extend(rows[index:])
                break
        _write_outbox(base_dir, remaining)
    return {
        "ok": not remaining,
        "code": "REPORTS_FLUSHED" if not remaining else "WEBHOOK_UNAVAILABLE",
        "sent": sent,
        "queued": len(remaining),
    }


def submit(base_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    queued = enqueue(base_dir, event)
    outcome = flush(base_dir)
    if outcome["sent"] > 0 and outcome["queued"] == 0:
        return {
            "ok": True,
            "code": "REPORT_SENT",
            "delivery": "sent",
            "queued": 0,
        }
    return {
        "ok": True,
        "code": "REPORT_QUEUED",
        "delivery": "queued",
        "queued": outcome.get("queued", queued),
    }


def system_summary() -> dict[str, str]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
    }
