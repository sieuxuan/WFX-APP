"""Báo lỗi tối giản qua webhook, không để lộ endpoint trong giao diện.

Webhook mặc định nhận góp ý và báo lỗi nằm ở ``DEFAULT_WEBHOOK_URL``. Khi cần
chạy thử có thể ghi đè bằng ``WFX_ERROR_WEBHOOK_URL`` trong environment hoặc
file .env của app. Payload có thể chứa User ID/Company/Division để hỗ trợ,
nhưng tuyệt đối không chứa password, cookie, URL WFX, query hay ảnh chụp màn hình.
"""

from __future__ import annotations

import json
import os
import platform
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wfx_panel.atomic_io import write_json_atomic
from wfx_panel.telemetry_labels import (  # noqa: F401
    _DIVISION_LABELS,
    _FILTER_LABELS,
    _METHOD_DEFAULT_FILTERS,
    _METHOD_MODULES,
    _MODULE_NAMES_BY_ID,
    ERROR_CODE_INFO,
    METHOD_LABELS,
)

DEFAULT_WEBHOOK_URL = "https://n8n.itx.io.vn/webhook/wfx-app"
ENV_NAME = "WFX_ERROR_WEBHOOK_URL"
MAX_OUTBOX = 100
SCHEMA_VERSION = 1
_LOCK = threading.Lock()
_FLUSH_LOCK = threading.Lock()



_URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(
        password|passwd|pwd|cookie|session[_\s-]?id|login[_\s-]?id|
        query|article[_\s-]?code|buyer[_\s-]?reference|style[_\s-]?code
    )\b
    \s*[:=]\s*
    ("[^"]*"|'[^']*'|[^\s,;]+)
    """
)
_EXACT_CODE_PATTERN = re.compile(
    r"(?i)\bcode\s+(?:chính\s+xác|cần\s+tìm)\s*:\s*[^\s,;]+"
)


def redact_telemetry_text(value: object) -> str:
    """Loại URL, secret và query nghiệp vụ khỏi mô tả gửi ra ngoài."""
    text = str(value or "").strip()
    text = _URL_PATTERN.sub("[URL đã ẩn]", text)
    text = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=[đã ẩn]",
        text,
    )
    return _EXACT_CODE_PATTERN.sub("Code [đã ẩn]", text)




def _error_operation_context(
    method: str,
    result: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, str, str]:
    module_id = str(request.get("module_id") or "").strip()
    module = (
        str(result.get("module") or "").strip()
        or _MODULE_NAMES_BY_ID.get(module_id, "")
        or _METHOD_MODULES.get(method, "")
    )
    raw_filter = str(
        result.get("filter_kind")
        or request.get("filter_kind")
        or ""
    ).strip()
    filter_kind = (
        _FILTER_LABELS.get(method, {}).get(raw_filter, raw_filter)
        or _METHOD_DEFAULT_FILTERS.get(method, "")
    )
    division_key = str(request.get("division_key") or "").strip().casefold()
    division_label = _DIVISION_LABELS.get(division_key, "")
    return module, filter_kind, division_label


def _fallback_error_detail(
    method: str,
    code: str,
    method_label: str,
    module: str,
    filter_kind: str,
    division_label: str,
) -> str:
    if code in {"MODULE_SEARCH_NOT_READY", "MODULE_LIST_NOT_OPEN"}:
        target = f"ô {filter_kind}" if filter_kind else "ô tìm kiếm"
        location = f" trong {module}" if module else ""
        if code == "MODULE_SEARCH_NOT_READY":
            return (
                f"Không tìm thấy {target}{location} sau khi app tự mở List."
            )
        return f"Không tìm thấy {target}{location}; màn List chưa sẵn sàng."
    if code == "MODULE_SEARCH_NOT_CONFIRMED":
        target = f" theo {filter_kind}" if filter_kind else ""
        location = f" trong {module}" if module else ""
        return f"WFX chưa xác nhận kết quả tìm kiếm{target}{location}."
    if method in {"open_module", "open_module_new"}:
        target = module or "module được chọn"
        return (
            f"Không thể mở {target}; menu hoặc frame WFX chưa sẵn sàng "
            f"(mã {code})."
        )
    if method == "switch_division":
        target = f" sang Division {division_label}" if division_label else ""
        return f"WFX chưa hoàn tất chuyển Division{target} (mã {code})."
    return f"{method_label} trả về mã {code} nhưng không kèm lỗi gốc."


def automation_error_context(
    method: str,
    result: dict[str, Any],
    request: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Tạo mô tả webhook rõ nghĩa, chỉ lấy dữ liệu đã whitelist."""
    method = str(method or "")
    safe_request = request if isinstance(request, dict) else {}
    code = str(result.get("code") or "UNKNOWN")
    method_label = METHOD_LABELS.get(method, method or "Tác vụ WFX")
    default_title = f"{method_label} chưa hoàn tất"
    title, suggestion = ERROR_CODE_INFO.get(
        code,
        (
            default_title,
            "Mở Log kỹ thuật và dùng Run ID để đối chiếu bước bị lỗi.",
        ),
    )
    module, filter_kind, division_label = _error_operation_context(
        method,
        result,
        safe_request,
    )
    if code == "MODULE_FAILED" and module:
        title = f"Không thể thao tác module {module}"
    detail = redact_telemetry_text(result.get("message"))
    if not detail:
        detail = _fallback_error_detail(
            method,
            code,
            method_label,
            module,
            filter_kind,
            division_label,
        )
    return {
        "method_label": method_label,
        "error_title": title,
        "error_detail": detail[:2_000],
        "suggestion": suggestion,
        "message": f"{title}: {detail}"[:4_000],
        "module": module,
        "filter_kind": filter_kind,
    }


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
        except OSError:
            pass
        return
    write_json_atomic(path, rows[-MAX_OUTBOX:], indent=2)


def _json_safe(value: Any) -> Any:
    """Chỉ giữ giá trị JSON hóa được.

    Payload góp ý nhúng cả ``get_status()`` và diagnostics; một object lạ lọt
    vào sẽ làm ``json.dumps`` raise TypeError — mà TypeError không nằm trong
    danh sách except của flush(), nên nó bay thẳng ra bridge.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def enqueue(base_dir: Path, event: dict[str, Any]) -> int:
    envelope = {
        "schema": SCHEMA_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **_json_safe(event),
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
    account = event.get("account")
    if isinstance(account, dict):
        for key in (
            "user_id",
            "company_id",
            "division_label",
            "division_name",
        ):
            value = account.get(key)
            if value in (None, ""):
                continue
            fields.append(
                {
                    "name": key.replace("_", " ").title(),
                    "value": str(value)[:1000],
                    "inline": key != "division_name",
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


def flush(
    base_dir: Path,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Gửi outbox qua endpoint đã chốt tại lúc lên lịch, nếu được truyền vào."""
    url = (
        webhook_url(base_dir)
        if endpoint is None
        else str(endpoint or "").strip()
    )
    if not url.startswith(("https://", "http://")):
        return {
            "ok": True,
            "code": "WEBHOOK_NOT_CONFIGURED",
            "sent": 0,
            "queued": len(_load_outbox(base_dir)),
        }
    # _FLUSH_LOCK tuần tự hóa phần GỬI, _LOCK chỉ bảo vệ đọc/ghi file.
    # Vì sao tách: mỗi lỗi automation spawn một thread flush, nên hai flush có
    # thể chồng nhau. Nếu chúng cùng snapshot outbox thì cùng POST một event —
    # webhook nhận trùng. Còn nếu giữ _LOCK suốt lúc gửi (bản cũ) thì 100 event
    # × timeout 5 s chặn cả enqueue, và submit_feedback đứng im trên UI thread.
    if not _FLUSH_LOCK.acquire(blocking=False):
        return {
            "ok": True,
            "code": "WEBHOOK_BUSY",
            "sent": 0,
            "queued": len(_load_outbox(base_dir)),
        }
    try:
        with _LOCK:
            rows = _load_outbox(base_dir)
        sent = 0
        failed = False
        for event in rows:
            try:
                _post(url, event)
            except (OSError, HTTPError, URLError, ValueError, TypeError):
                failed = True
                break
            sent += 1
        if sent:
            with _LOCK:
                # Chỉ bỏ đúng số event ĐÃ gửi ở đầu hàng đợi, không ghi đè cả
                # file bằng snapshot cũ: event mới xếp vào trong lúc đang gửi
                # phải còn nguyên. Cũng không xóa outbox trước khi gửi — bị kill
                # giữa lúc POST thì gửi lại vài event vẫn tốt hơn là mất chúng.
                _write_outbox(base_dir, _load_outbox(base_dir)[sent:])
        queued = len(_load_outbox(base_dir))
    finally:
        _FLUSH_LOCK.release()
    # Trạng thái phải phản ánh việc GỬI có lỗi hay không, không phải độ sâu hàng
    # đợi: một event vừa được enqueue giữa lúc flush làm queued > 0 nhưng webhook
    # vẫn hoàn toàn bình thường.
    return {
        "ok": not failed,
        "code": "WEBHOOK_UNAVAILABLE" if failed else "REPORTS_FLUSHED",
        "sent": sent,
        "queued": queued,
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
