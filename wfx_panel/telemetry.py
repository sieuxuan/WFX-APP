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
import traceback
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
# Chỉ tên trang WFX (``WFXSalesASN.aspx``) được giữ lại: biết frame đang ở
# trang nào là manh mối chẩn đoán chính, còn host, thư mục, query và fragment
# vẫn bị bỏ hẳn. Đoạn cuối không có dạng tên trang (REST path có thể mang mã
# Style) thì ẩn cả URL như cũ.
_PAGE_NAME_PATTERN = re.compile(
    r"(?i)^[\w-]{1,80}\.(?:aspx|ashx|asmx|axd|html?|svc)$"
)


def _redact_url(match: re.Match[str]) -> str:
    address = re.split(r"[?#]", match.group(0), maxsplit=1)[0]
    segments = address.split("://", 1)[-1].split("/")[1:]
    name = segments[-1].rstrip(".,;:)]}") if segments else ""
    if _PAGE_NAME_PATTERN.match(name):
        return f"[URL đã ẩn: {name}]"
    return "[URL đã ẩn]"


def redact_telemetry_text(value: object) -> str:
    """Loại URL, secret và query nghiệp vụ khỏi mô tả gửi ra ngoài."""
    text = str(value or "").strip()
    text = _URL_PATTERN.sub(_redact_url, text)
    text = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=[đã ẩn]",
        text,
    )
    return _EXACT_CODE_PATTERN.sub("Code [đã ẩn]", text)


MAX_REPORT_LOG_LINES = 40
# Lỗi Playwright gốc kèm "Call log" (selector đang chờ) thường dài hơn 300
# ký tự; cắt ở đó là mất đúng phần cho biết automation kẹt ở đâu.
_REPORT_LOG_LINE_CHARS = 500


def redact_log_lines(lines: object) -> list[str]:
    """Đuôi log của một lần chạy, đã qua đúng lớp che của mô tả lỗi.

    Log trên máy đã qua ``sanitize_log_text`` nhưng lớp đó giữ phần host của
    URL; thứ đi ra webhook phải ẩn hẳn URL như mọi ``error_detail``.
    """
    if not isinstance(lines, (list, tuple)):
        return []
    redacted = [
        redact_telemetry_text(line)[:_REPORT_LOG_LINE_CHARS]
        for line in lines
        if isinstance(line, str) and line.strip()
    ]
    return redacted[-MAX_REPORT_LOG_LINES:]


_STAGE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_DIAGNOSTIC_STATUS_KEYS = (
    "chrome_alive",
    "browser_available",
    "browser_name",
    "session_active",
    "last_login_at",
    "current_division",
    "division_label",
    "division_name",
)


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def failure_stage(
    result: dict[str, Any],
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bước hỏng của flow, chỉ lấy định danh bước, không lấy câu progress.

    Ưu tiên ``failed_stage``/``failed_step`` do chính flow trả (GDN), rồi
    progress cuối cùng mà engine thấy trong lượt chạy. Câu progress có thể
    chứa số PO/Invoice nên không bao giờ đi ra webhook; tên bước là hằng số
    trong code (``report``, ``po``…) nên an toàn.
    """
    progress = progress if isinstance(progress, dict) else {}
    stage = str(result.get("failed_stage") or progress.get("stage") or "")
    if not _STAGE_PATTERN.match(stage):
        return {}
    context: dict[str, Any] = {"failed_stage": stage}
    step = _positive_int(result.get("failed_step") or progress.get("step"))
    total = _positive_int(progress.get("total"))
    if step is not None:
        context["failed_step"] = step
    if total is not None and stage == progress.get("stage"):
        context["progress_total"] = total
    return context


def diagnostics(
    status: dict[str, Any],
    recent_jobs: list[dict[str, Any]],
    *,
    include_system: bool = True,
) -> dict[str, Any]:
    """Trạng thái máy/trình duyệt/phiên cho người hỗ trợ, theo whitelist.

    Dùng chung cho lỗi tự động và Báo lỗi một chạm để hai loại tin mang cùng
    một bộ trường; ``get_status()`` có thêm khóa mới cũng không tự lọt ra.
    """
    status = status if isinstance(status, dict) else {}
    return {
        **(system_summary() if include_system else {}),
        **{key: status[key] for key in _DIAGNOSTIC_STATUS_KEYS if key in status},
        "recent_jobs": [
            {
                "run_id": row.get("run_id"),
                "method": row.get("method"),
                "ok": row.get("ok"),
                "code": row.get("code"),
                "elapsed_ms": row.get("elapsed_ms"),
            }
            for row in recent_jobs
            if isinstance(row, dict)
        ],
    }


def exception_frames(error: BaseException, limit: int = 8) -> str:
    """Vị trí lỗi dạng ``file.py:12 in hàm``, frame trong cùng đứng trước.

    Chỉ tên file + số dòng + tên hàm: không đường dẫn (lộ tên tài khoản
    Windows), không giá trị biến. Đủ để biết exception bật ra ở đâu khi một
    flow trả ``PANEL_ERROR`` mà message chỉ còn ``KeyError: 'x'``.
    """
    frames = traceback.extract_tb(error.__traceback__)[-limit:]
    return " ← ".join(
        f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
        for frame in reversed(frames)
    )




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


def _repeat_key(event: dict[str, Any]) -> tuple[str, ...] | None:
    if event.get("event_type") != "automation_error":
        return None
    if not event.get("method") or not event.get("code"):
        return None
    account = event.get("account")
    user_id = account.get("user_id") if isinstance(account, dict) else ""
    return (
        str(event.get("method") or ""),
        str(event.get("code") or ""),
        str(event.get("app_version") or ""),
        str(user_id or ""),
    )


def enqueue(base_dir: Path, event: dict[str, Any]) -> int:
    envelope = {
        "schema": SCHEMA_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **_json_safe(event),
    }
    key = _repeat_key(envelope)
    with _LOCK:
        rows = _load_outbox(base_dir)
        # Cùng một lỗi tự động lặp lại khi offline (hoặc user bấm lại liên tục)
        # thì gộp vào event đang chờ thay vì xếp thêm một tin: kênh hỗ trợ
        # nhận một thông báo kèm số lần lặp, và trần MAX_OUTBOX còn chỗ cho
        # lỗi khác và cho góp ý của người dùng.
        pending = next(
            (row for row in reversed(rows) if key and _repeat_key(row) == key),
            None,
        )
        if pending is not None:
            pending["repeat_count"] = int(pending.get("repeat_count") or 1) + 1
            pending["last_run_id"] = envelope.get("run_id")
            pending["last_timestamp"] = envelope["timestamp"]
            _write_outbox(base_dir, rows)
            return len(rows)
        rows.append(envelope)
        rows = rows[-MAX_OUTBOX:]
        _write_outbox(base_dir, rows)
        return len(rows)


def _discord_payload(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "event")
    title = "WFX Smart · Báo lỗi" if event_type == "automation_error" else "WFX Smart · Góp ý"
    fields = []
    for key in (
        "kind",
        "code",
        "method",
        "run_id",
        "repeat_count",
        "elapsed_ms",
        "failed_stage",
        "app_version",
    ):
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
    log_tail = [
        line for line in event.get("log_tail") or () if isinstance(line, str)
    ]
    if log_tail:
        # Embed field tối đa 1.024 ký tự: giữ các dòng CUỐI, nơi có lỗi gốc.
        kept: list[str] = []
        for line in reversed(log_tail):
            if sum(len(item) + 1 for item in kept) + len(line) > 1000:
                break
            kept.insert(0, line)
        fields.append(
            {
                "name": "Log cuối",
                "value": "\n".join(kept) or log_tail[-1][-1000:],
                "inline": False,
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
