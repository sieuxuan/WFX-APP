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

DEFAULT_WEBHOOK_URL = "https://n8n.itx.io.vn/webhook/wfx-app"
ENV_NAME = "WFX_ERROR_WEBHOOK_URL"
MAX_OUTBOX = 100
SCHEMA_VERSION = 1
_LOCK = threading.Lock()

METHOD_LABELS = {
    "login": "Đăng nhập WFX",
    "check_session": "Kiểm tra phiên WFX",
    "open_chrome": "Mở trình duyệt automation",
    "open_module": "Mở module",
    "prepare_catalog": "Chuẩn bị Catalog",
    "browse_catalog": "Mở Catalog List",
    "catalog_action": "Tìm trong Catalog",
    "find_code": "Tìm Style Code",
    "find_buyer_reference": "Tìm Buyer Reference",
    "open_catalog_destination": "Mở Costing/BOM",
    "download_catalog_file": "Tải file Catalog",
    "open_sale_asn_new": "Mở Sale ASN mới",
    "open_sample_new": "Mở Sample Order mới",
    "search_oc": "Tìm trong OC List",
    "search_sample": "Tìm trong Sample List",
    "search_sale_asn": "Tìm trong Sale ASN List",
    "open_supplier_category": "Mở Supplier List",
    "find_supplier": "Tìm Supplier",
    "find_supplier_in_category": "Tìm Supplier theo Category",
    "find_buyer": "Tìm Buyer",
    "toggle_company_foc": "Đổi FOC trong Company Setup",
    "switch_division": "Đổi Division",
}

ERROR_CODE_INFO = {
    "DIVISION_CHANGE_NOT_CONFIRMED": (
        "WFX chưa xác nhận đổi Division",
        "Kiểm tra menu Division trên WFX rồi thử lại.",
    ),
    "MODULE_FAILED": (
        "Không thể thao tác module WFX",
        "Mở Log kỹ thuật để xem bước và lỗi gốc cuối cùng.",
    ),
    "MODULE_SEARCH_NOT_READY": (
        "Ô tìm kiếm của module chưa sẵn sàng",
        "Bấm List, chờ danh sách tải xong rồi thử tìm lại.",
    ),
    "MODULE_SEARCH_NOT_CONFIRMED": (
        "WFX chưa xác nhận kết quả tìm kiếm",
        "Kiểm tra màn List và thử lại sau khi grid tải xong.",
    ),
    "MODULE_SEARCH_FAILED": (
        "Không thể thao tác ô tìm kiếm",
        "Mở Log kỹ thuật để xem lỗi gốc rồi thử lại.",
    ),
    "FLOATING_FILTER_NOT_READY": (
        "Floating Filter chưa sẵn sàng",
        "Chờ danh sách tải xong, bật Floating Filter rồi thử lại.",
    ),
    "PANEL_ERROR": (
        "Ứng dụng gặp lỗi khi chạy tác vụ",
        "Mở Log kỹ thuật và dùng Run ID để đối chiếu.",
    ),
}

ERROR_CODE_INFO.update(
    {
        "BUYER_EDIT_NOT_CONFIRMED": (
            "WFX chưa xác nhận màn Edit Buyer",
            "Mở Buyer List, tìm lại Buyer rồi thử mở Edit.",
        ),
        "BUYER_EDIT_NOT_FOUND": (
            "Không tìm thấy nút Edit của Buyer",
            "Kiểm tra quyền chỉnh sửa Buyer và cấu trúc dòng kết quả.",
        ),
        "BUYER_SEARCH_FAILED": (
            "Không thể tìm Buyer",
            "Mở Log kỹ thuật và kiểm tra Buyer List đang hiển thị.",
        ),
        "BUYER_SEARCH_NOT_READY": (
            "Buyer List chưa sẵn sàng",
            "Chờ danh sách tải xong rồi thử tìm lại.",
        ),
        "CATALOG_DESTINATION_FAILED": (
            "Không thể mở Costing/BOM",
            "Mở lại style từ Catalog rồi thử lại.",
        ),
        "CATALOG_FILES_SCAN_FAILED": (
            "Không thể đọc file đính kèm Catalog",
            "Mở lại Article và kiểm tra tab file đính kèm.",
        ),
        "CATALOG_FILE_DOWNLOAD_FAILED": (
            "Không thể tải file Catalog",
            "Kiểm tra phiên WFX và quyền tải file rồi thử lại.",
        ),
        "CATALOG_FILE_SAVE_FAILED": (
            "Không thể lưu file Catalog",
            "Kiểm tra quyền ghi thư mục tải xuống và dung lượng ổ đĩa.",
        ),
        "CATALOG_FILE_TABS_NOT_FOUND": (
            "Không tìm thấy tab file của Article",
            "Mở lại Article rồi kiểm tra tab Images/Documents.",
        ),
        "CATALOG_FILE_URL_INVALID": (
            "WFX trả về liên kết file không hợp lệ",
            "Mở Log kỹ thuật và kiểm tra cấu hình file trên WFX.",
        ),
        "CATALOG_FOLDER_OPEN_FAILED": (
            "Không thể mở folder Catalog",
            "Quét lại cây folder rồi thử mở lại.",
        ),
        "CATALOG_FOLDER_OPEN_TIMEOUT": (
            "WFX phản hồi chậm khi mở folder Catalog",
            "Chờ Catalog tải xong rồi thử lại.",
        ),
        "CATALOG_FOLDER_SCAN_FAILED": (
            "Không thể quét cây folder Catalog",
            "Kiểm tra quyền Catalog của tài khoản rồi thử lại.",
        ),
        "CATALOG_FOLDER_SCAN_TIMEOUT": (
            "WFX phản hồi chậm khi tải cây Catalog",
            "Chờ cây Catalog hiển thị rồi quét lại.",
        ),
        "CATALOG_NOT_OPEN": (
            "Catalog Master chưa sẵn sàng",
            "Bấm Mở Catalog và chờ Master/Floating Filter hiển thị.",
        ),
        "CATALOG_SEARCH_FAILED": (
            "Không thể tìm trong Catalog",
            "Mở lại Catalog Master rồi thử tìm lại.",
        ),
        "CATEGORY_FAILED": (
            "Không thể chọn Category",
            "Mở lại module và kiểm tra quyền Category của tài khoản.",
        ),
        "CHROME_OPEN_FAILED": (
            "Không thể mở trình duyệt automation",
            "Kiểm tra cài đặt Chrome/Edge và quyền chạy ứng dụng.",
        ),
        "CODE_FILTER_FAILED": (
            "Không thể thao tác Code Filter",
            "Mở lại Catalog Master và Floating Filter rồi thử lại.",
        ),
        "CODE_FILTER_TIMEOUT": (
            "Code Filter phản hồi quá chậm",
            "Chờ grid Catalog ổn định rồi thử lại.",
        ),
        "COMPANY_FOC_FAILED": (
            "Không thể đổi cấu hình FOC",
            "Mở lại Company Setup và kiểm tra quyền chỉnh sửa.",
        ),
        "COMPANY_FOC_NOT_READY": (
            "Màn cấu hình FOC chưa sẵn sàng",
            "Chờ Miscellaneous Settings tải xong rồi thử lại.",
        ),
        "COMPANY_FOC_SAVE_NOT_CONFIRMED": (
            "WFX chưa xác nhận lưu cấu hình FOC",
            "Kiểm tra trạng thái checkbox và bấm Save lại trên WFX.",
        ),
        "DIVISION_CHANGE_FAILED": (
            "Không thể đổi Division",
            "Kiểm tra menu Division và phiên đăng nhập rồi thử lại.",
        ),
        "DIVISION_DETECT_FAILED": (
            "Không thể nhận diện Division hiện tại",
            "Kiểm tra màn Home WFX và đăng nhập lại nếu cần.",
        ),
        "FILTER_RESULTS_NOT_READY": (
            "Kết quả filter chưa ổn định",
            "Chờ grid tải xong rồi thử tìm lại.",
        ),
        "FILTER_VALUE_NOT_CONFIRMED": (
            "WFX chưa nhận giá trị filter",
            "Mở lại Floating Filter rồi nhập lại.",
        ),
        "LOGIN_FAILED": (
            "Đăng nhập WFX thất bại",
            "Kiểm tra tài khoản, Company và trạng thái trang đăng nhập.",
        ),
        "LOGIN_TIMEOUT": (
            "WFX phản hồi quá chậm khi đăng nhập",
            "Kiểm tra mạng và thử đăng nhập lại.",
        ),
        "MASTER_FAILED": (
            "Không thể mở Master",
            "Mở lại Category rồi thử Master lần nữa.",
        ),
        "MASTER_NOT_FOUND": (
            "Không tìm thấy mục Master",
            "Kiểm tra quyền truy cập và cây menu của Category.",
        ),
        "MODULE_ACCESS_CHECK_FAILED": (
            "Không thể kiểm tra quyền module",
            "Đăng nhập lại và tải lại danh sách quyền.",
        ),
        "MODULE_NOT_FOUND": (
            "Không tìm thấy module trên menu WFX",
            "Kiểm tra quyền tài khoản và menu module.",
        ),
        "QUICK_SEARCH_FAILED": (
            "Quick Search gặp lỗi",
            "Mở module thủ công và thử lại từng bước.",
        ),
        "QUICK_SEARCH_TIMEOUT": (
            "Quick Search phản hồi quá chậm",
            "Chờ WFX tải xong rồi thử lại.",
        ),
        "RESULT_DETACHED": (
            "Dòng kết quả đã thay đổi trước khi mở",
            "Tìm lại để lấy dòng kết quả mới.",
        ),
        "SALE_ASN_NEW_FAILED": (
            "Không thể tạo màn Sale ASN mới",
            "Mở lại Sale ASN và kiểm tra quyền tạo mới.",
        ),
        "SALE_ASN_NEW_NOT_READY": (
            "Màn Sale ASN mới chưa sẵn sàng",
            "Chờ form tải xong rồi thử lại.",
        ),
        "SAMPLE_NEW_FAILED": (
            "Không thể tạo màn Sample Order mới",
            "Mở lại Sample List và kiểm tra quyền tạo mới.",
        ),
        "SAMPLE_NEW_NOT_READY": (
            "Màn Sample Order mới chưa sẵn sàng",
            "Chờ form tải xong rồi thử lại.",
        ),
        "SESSION_CHECK_FAILED": (
            "Không thể kiểm tra phiên WFX",
            "Kiểm tra trình duyệt automation và đăng nhập lại.",
        ),
        "SUPPLIER_MASTER_NOT_READY": (
            "Supplier Master chưa sẵn sàng",
            "Chờ Supplier List và Category tải xong rồi thử lại.",
        ),
        "SUPPLIER_OPEN_FAILED": (
            "Không thể mở Supplier List",
            "Kiểm tra quyền Supplier và menu WFX.",
        ),
        "SUPPLIER_SEARCH_FAILED": (
            "Không thể tìm Supplier",
            "Mở Log kỹ thuật và kiểm tra Category đang thao tác.",
        ),
        "SUPPLIER_SEARCH_NOT_READY": (
            "Ô tìm Supplier chưa sẵn sàng",
            "Chờ Supplier Master tải xong rồi thử lại.",
        ),
        "SUPPLIER_SEARCH_PARTIAL": (
            "Chưa kiểm tra được toàn bộ Category Supplier",
            "Thử lại để kiểm tra các Category bị lỗi hoặc mở từng Category riêng.",
        ),
    }
)

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


def automation_error_context(
    method: str,
    result: dict[str, Any],
) -> dict[str, str]:
    """Tạo mô tả webhook rõ nghĩa, chỉ lấy dữ liệu đã whitelist."""
    method = str(method or "")
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
    module = str(result.get("module") or "").strip()
    if code == "MODULE_FAILED" and module:
        title = f"Không thể thao tác module {module}"
    detail = redact_telemetry_text(result.get("message"))
    if not detail:
        detail = "Automation không trả về mô tả chi tiết."
    return {
        "method_label": method_label,
        "error_title": title,
        "error_detail": detail[:2_000],
        "suggestion": suggestion,
        "message": f"{title}: {detail}"[:4_000],
        "module": module,
        "filter_kind": str(result.get("filter_kind") or "").strip(),
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
