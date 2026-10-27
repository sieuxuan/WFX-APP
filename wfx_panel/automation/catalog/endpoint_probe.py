"""Dò request mà Catalog Grid gọi để nạp dữ liệu Article — CHỈ ĐỌC.

Mục tiêu dài hạn là gọi thẳng nguồn dữ liệu đó bằng ``fetch`` trong trang đã
đăng nhập thay vì scrape DOM. Bước này chỉ quan sát: gắn listener
``request``/``response`` lên context, chạy lại đúng luồng Mở Catalog
(Category → Master → grid settled) rồi ghi "hình dạng" từng request ra một file
JSON cục bộ trong ``DATA_DIR/diagnostics``. Không click gì ngoài đường mở
Catalog, không Save, không gửi telemetry nội dung file.

File kết quả có thể được chuyển cho người phát triển nên mọi chuỗi đều qua
``redact_telemetry_text``: không ghi header (cookie nằm ở đó), không ghi query
string thô, tên tham số nhạy cảm và giá trị trông như GUID/mã phiên bị ẩn, dòng
mẫu chỉ giữ vài ký tự đầu của mỗi giá trị.
"""

from __future__ import annotations

import math
import time as _time
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from wfx_panel.atomic_io import write_json_atomic
from wfx_panel.automation._common import (
    Any,
    Callable,
    Playwright,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    json,
    re,
    sync_playwright,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.catalog.grid import _show_catalog_floating_filter
from wfx_panel.automation.catalog.navigation import (
    _click_catalog_master,
    _open_catalog_tree_on_page,
)
from wfx_panel.automation.session import _session_is_active
from wfx_panel.telemetry import redact_telemetry_text

PROBE_SCHEMA_VERSION = 1
HIDDEN = "[đã ẩn]"
MAX_ENTRIES = 200
MAX_PARAMS = 40
MAX_SHAPE_KEYS = 40
MAX_SHAPE_DEPTH = 5
MAX_SAMPLE_ROWS = 2
MAX_SAMPLE_FIELDS = 30
MAX_PARAM_VALUE_CHARS = 40
MAX_BODY_BYTES = 30 * 1024 * 1024
# Request cuối của grid có thể tới sau khi DOM đã ổn định (đếm tổng, cấu hình
# cột). Chờ thêm một nhịp ngắn để không bỏ lỡ chúng.
TRAILING_CAPTURE_MS = 2_000

_CAPTURED_RESOURCE_TYPES = frozenset({"xhr", "fetch"})
_SENSITIVE_NAME = re.compile(
    r"(?i)(pass|pwd|cookie|session|sid$|^sid|login|user|token|auth|secret|"
    r"guid|ticket|viewstate|eventvalidation|csrf|xsrf|signature|hash|key|"
    r"email|phone|createdby|modifiedby|updatedby|owner)"
)
_GUID = re.compile(
    r"(?i)\b[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}\b"
)
_OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9+/=_\-%.]{24,}$")
# ASP.NET cookieless session nhét mã phiên ngay trong path: /(S(abc...))/.
_COOKIELESS_SEGMENT = re.compile(r"\([A-Z]\([^)]*\)\)")

# Tên cột Article ứng với từng vai trò, so trên tên key đã bỏ ký tự phân cách.
_ROLE_PATTERNS = {
    "article_code": re.compile(r"^(code|articlecode|lnkarticlecode|articleno|stylecode|styleno)$|articlecode"),
    "article_name": re.compile(r"^(name|articlename|stylename|description)$|articlename"),
    "buyer_reference": re.compile(r"buyerref"),
    "category": re.compile(r"category"),
}
_HTML_FIELD_HINT = re.compile(
    r"""(?i)["']?(articlecode|article_code|articlename|buyerreference|buyer_reference|articlecategory)["']?\s*:"""
)


def _key_token(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").casefold())


def is_sensitive_name(name: object) -> bool:
    return bool(_SENSITIVE_NAME.search(_key_token(name)))


def looks_opaque(value: object) -> bool:
    """Giá trị trông như GUID, mã phiên hoặc chuỗi mã hóa dài."""
    text = str(value or "").strip()
    return bool(_GUID.search(text) or _OPAQUE_VALUE.match(text))


def safe_text(value: object, limit: int = 120) -> str:
    return redact_telemetry_text(value)[:limit]


def mask_value(value: object) -> str:
    """Che giá trị mẫu: giữ vài ký tự đầu để còn nhận ra định dạng (F…, T…)."""
    text = safe_text(value, 200)
    if not text:
        return ""
    if looks_opaque(text):
        return HIDDEN
    if len(text) <= 3:
        return text
    return f"{text[:3]}…(len={len(text)})"


def safe_path(path: str) -> str:
    """Path đã bỏ mã phiên/GUID nhúng trong segment."""
    path = _COOKIELESS_SEGMENT.sub(HIDDEN, path or "/")
    segments = [
        HIDDEN if looks_opaque(segment) else segment
        for segment in path.split("/")
    ]
    return safe_text("/".join(segments) or "/", 300)


def describe_params(pairs: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict]:
    """Tên tham số luôn được ghi; giá trị chỉ khi chắc chắn không nhạy cảm."""
    described: list[dict] = []
    for name, value in list(pairs)[:MAX_PARAMS]:
        entry: dict[str, Any] = {"name": safe_text(name, 80)}
        value_text = str(value or "")
        if (
            is_sensitive_name(name)
            or looks_opaque(value_text)
            or len(value_text) > MAX_PARAM_VALUE_CHARS
        ):
            entry["value"] = HIDDEN if value_text else ""
        else:
            entry["value"] = safe_text(value_text, MAX_PARAM_VALUE_CHARS)
        described.append(entry)
    return described


def describe_url(url: str) -> dict:
    """Host + path, không có query thô; query chỉ còn danh sách tham số."""
    parts = urlsplit(str(url or ""))
    return {
        "host": safe_text(parts.hostname or "", 120),
        "path": safe_path(parts.path),
        "query_params": describe_params(parse_qsl(parts.query, keep_blank_values=True)),
    }


def _json_pairs(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, dict):
        return []
    pairs: list[tuple[str, str]] = []
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            pairs.append((str(key), f"<{type(item).__name__}>"))
        else:
            pairs.append((str(key), "" if item is None else str(item)))
    return pairs


# Header không bao giờ ghi: cookie/xác thực mang thẳng phiên đăng nhập. Header
# chuẩn của trình duyệt chỉ gây nhiễu (referer còn chứa URL có query).
_DROPPED_HEADERS = frozenset(
    {
        "cookie",
        "authorization",
        "proxy-authorization",
        "referer",
        "origin",
        "host",
        "user-agent",
        "connection",
        "content-length",
        "pragma",
        "cache-control",
        "priority",
    }
)
_DROPPED_HEADER_PREFIXES = ("sec-", "accept", ":")


def _json_array_pairs(items: list[dict]) -> list[tuple[str, str]]:
    """Mảng ``[{ParamName, ParamValue}]`` của WFX thành cặp tên → giá trị.

    Nhờ vậy luật che áp theo chính tên tham số (``UserID`` bị ẩn,
    ``ProductCatCode`` thì không). Mảng dạng khác giữ chỉ số ``[i].key``.
    """
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        keys = {_key_token(key): key for key in item}
        if "paramname" in keys and "paramvalue" in keys:
            value = item[keys["paramvalue"]]
            pairs.append(
                (
                    str(item[keys["paramname"]]),
                    f"<{type(value).__name__}>"
                    if isinstance(value, (dict, list))
                    else "" if value is None else str(value),
                )
            )
            continue
        pairs.extend((f"[{index}].{key}", value) for key, value in _json_pairs(item))
    return pairs


def describe_headers(headers: dict | None) -> list[dict]:
    """Header tùy biến của WFX: tên luôn ghi, giá trị theo luật tham số.

    API ``WFXCommon/GetData`` không có query lẫn body, nên tham số chỉ có thể
    nằm trong header. Header có giá trị JSON được tách thành từng key thay vì
    bị ẩn nguyên khối vì dài.
    """
    described: list[dict] = []
    for name, value in sorted((headers or {}).items()):
        lowered = str(name).casefold()
        if lowered in _DROPPED_HEADERS or lowered.startswith(_DROPPED_HEADER_PREFIXES):
            continue
        text = str(value or "")
        # WFX gửi JSON đã URL-encode (`searchparams: %5B%5D`).
        decoded = unquote(text) if text.startswith("%") else text
        parsed = _maybe_json_string(decoded) if not is_sensitive_name(name) else None
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            described.append(
                {
                    "name": safe_text(name, 80),
                    "value": "<json-array>",
                    "params": describe_params(_json_array_pairs(parsed)),
                    "shape": json_shape(parsed, depth=MAX_SHAPE_DEPTH - 2),
                }
            )
            continue
        if isinstance(parsed, dict):
            described.append(
                {
                    "name": safe_text(name, 80),
                    "value": "<json>",
                    "params": describe_params(_json_pairs(parsed)),
                    "shape": json_shape(parsed, depth=MAX_SHAPE_DEPTH - 2),
                }
            )
            continue
        described.extend(describe_params([(str(name), text)]))
        if len(described) >= MAX_PARAMS:
            break
    return described


def describe_body(post_data: str | None, content_type: str) -> dict:
    if not post_data:
        return {"format": "none", "params": []}
    content_type = (content_type or "").casefold()
    text = post_data.strip()
    if "json" in content_type or text[:1] in {"{", "["}:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            return {
                "format": "json",
                "params": describe_params(_json_pairs(parsed)),
                "shape": json_shape(parsed, depth=MAX_SHAPE_DEPTH - 2),
            }
    if "x-www-form-urlencoded" in content_type or "=" in text:
        return {
            "format": "form",
            "params": describe_params(parse_qsl(text, keep_blank_values=True)),
        }
    return {"format": "text", "params": [], "length": len(post_data)}


def _maybe_json_string(value: str) -> Any:
    """ASP.NET WebMethod hay bọc kết quả thành chuỗi JSON trong ``{"d": "..."}``."""
    text = value.strip()
    if len(text) < 2 or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def json_shape(value: Any, depth: int = 0) -> Any:
    if depth > MAX_SHAPE_DEPTH:
        return {"type": "…"}
    if isinstance(value, dict):
        keys = list(value)[:MAX_SHAPE_KEYS]
        return {
            "type": "object",
            "key_count": len(value),
            "keys": {
                safe_text(key, 80): json_shape(value[key], depth + 1)
                for key in keys
            },
        }
    if isinstance(value, list):
        shape: dict[str, Any] = {"type": "array", "length": len(value)}
        if value:
            shape["item"] = json_shape(value[0], depth + 1)
        return shape
    if isinstance(value, str):
        nested = _maybe_json_string(value)
        if nested is not None:
            return {"type": "json_string", "parsed": json_shape(nested, depth + 1)}
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def find_row_lists(value: Any, path: str = "$", depth: int = 0) -> list[tuple[str, list[dict]]]:
    """Mọi mảng object trong JSON, kể cả mảng nằm trong chuỗi JSON lồng."""
    if depth > MAX_SHAPE_DEPTH + 2:
        return []
    found: list[tuple[str, list[dict]]] = []
    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        if rows and len(rows) == len(value):
            found.append((path, rows))
        for item in value[:1]:
            found.extend(find_row_lists(item, f"{path}[0]", depth + 1))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(find_row_lists(item, f"{path}.{key}", depth + 1))
    elif isinstance(value, str):
        nested = _maybe_json_string(value)
        if nested is not None:
            found.extend(find_row_lists(nested, f"{path}<json>", depth + 1))
    return found


def match_article_fields(keys: list[str]) -> dict[str, str]:
    """Vai trò Article → tên key đầu tiên khớp."""
    matched: dict[str, str] = {}
    for role, pattern in _ROLE_PATTERNS.items():
        for key in keys:
            if pattern.search(_key_token(key)):
                matched[role] = key
                break
    return matched


def _row_keys(rows: list[dict]) -> list[str]:
    keys: list[str] = []
    for row in rows[:5]:
        for key in row:
            if key not in keys:
                keys.append(str(key))
    return keys


def mask_row(row: dict) -> dict:
    masked: dict[str, Any] = {}
    for key in list(row)[:MAX_SAMPLE_FIELDS]:
        value = row[key]
        name = safe_text(key, 80)
        if is_sensitive_name(key):
            masked[name] = HIDDEN
        elif isinstance(value, (dict, list)):
            masked[name] = f"<{type(value).__name__}>"
        elif isinstance(value, bool) or value is None:
            masked[name] = value
        elif isinstance(value, (int, float)):
            masked[name] = "<number>"
        else:
            masked[name] = mask_value(value)
    return masked


def row_list_candidates(value: Any) -> list[dict]:
    candidates: list[dict] = []
    for path, rows in find_row_lists(value):
        keys = _row_keys(rows)
        fields = match_article_fields(keys)
        looks_like_articles = "article_code" in fields and bool(
            {"article_name", "buyer_reference"} & set(fields)
        )
        candidates.append(
            {
                "json_path": safe_text(path, 200),
                "row_count": len(rows),
                "keys": [safe_text(key, 80) for key in keys[:MAX_SHAPE_KEYS]],
                "article_fields": {
                    role: safe_text(key, 80) for role, key in fields.items()
                },
                "looks_like_article_rows": looks_like_articles,
                "sample_rows": [mask_row(row) for row in rows[:MAX_SAMPLE_ROWS]],
            }
        )
    return candidates


def summarize_response_body(body: bytes | None, content_type: str) -> dict:
    """Hình dạng response: JSON → shape + danh sách row; HTML → gợi ý nhúng."""
    if body is None:
        return {"kind": "unavailable"}
    summary: dict[str, Any] = {"kind": "binary"}
    content_type = (content_type or "").casefold()
    if len(body) > MAX_BODY_BYTES:
        return {"kind": "too_large"}
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return summary
    stripped = text.strip()
    if "json" in content_type or stripped[:1] in {"{", "["}:
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if parsed is not None:
            return {
                "kind": "json",
                "shape": json_shape(parsed),
                "row_lists": row_list_candidates(parsed),
            }
    if "html" in content_type or stripped[:1] == "<":
        hints = sorted({match.group(1) for match in _HTML_FIELD_HINT.finditer(text)})
        return {
            "kind": "html",
            "embedded_field_hints": [safe_text(hint, 40) for hint in hints],
        }
    return {"kind": "text"}


def candidate_score(entry: dict) -> float:
    """Điểm ứng viên: số vai trò Article khớp là chính, số row là phụ."""
    best = 0.0
    for candidate in (entry.get("response") or {}).get("row_lists") or ():
        roles = len(candidate.get("article_fields") or {})
        if not roles:
            continue
        score = roles * 10 + math.log10(1 + int(candidate.get("row_count") or 0))
        if candidate.get("looks_like_article_rows"):
            score += 20
        if entry.get("from_catalog_grid"):
            score += 5
        best = max(best, score)
    return round(best, 2)


def best_candidate(entries: list[dict]) -> dict | None:
    scored = [
        (candidate_score(entry), index, entry)
        for index, entry in enumerate(entries)
    ]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    score, _index, entry = max(scored, key=lambda item: (item[0], -item[1]))
    rows = max(
        (entry.get("response") or {}).get("row_lists") or [{}],
        key=lambda candidate: (
            len(candidate.get("article_fields") or {}),
            candidate.get("row_count") or 0,
        ),
    )
    return {
        "index": entry.get("index"),
        "score": score,
        "method": entry.get("method"),
        "host": entry.get("host"),
        "path": entry.get("path"),
        "json_path": rows.get("json_path"),
        "row_count": rows.get("row_count"),
        "article_fields": rows.get("article_fields") or {},
        "looks_like_article_rows": bool(rows.get("looks_like_article_rows")),
    }


def build_report(entries: list[dict], *, category: str, app_version: str, run_note: str) -> dict:
    for entry in entries:
        entry["candidate_score"] = candidate_score(entry)
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "kind": "catalog-endpoint-probe",
        "created_at": _time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "app_version": app_version,
        "category": category,
        "note": run_note,
        "request_count": len(entries),
        "best_candidate": best_candidate(entries),
        "requests": entries,
    }


def candidate_message(candidate: dict | None, request_count: int) -> str:
    if candidate is None:
        return (
            f"Đã ghi {request_count} request; chưa thấy response nào có danh "
            "sách Article (có thể grid nhận dữ liệu nhúng trong trang)."
        )
    fields = ", ".join(sorted(candidate.get("article_fields") or {}))
    return (
        f"Đã ghi {request_count} request. Ứng viên tốt nhất: "
        f"{candidate.get('method')} {candidate.get('path')} · "
        f"{candidate.get('row_count')} dòng · trường: {fields or 'không rõ'}."
    )


# --- Playwright --------------------------------------------------------------


def _frame_info(request: Any) -> dict:
    try:
        frame = request.frame
        url = str(frame.url or "")
        name = str(frame.name or "")
    except Exception:
        return {"name": "", "path": "", "is_catalog_grid": False}
    return {
        "name": safe_text(name, 60),
        "path": safe_path(urlsplit(url).path),
        "is_catalog_grid": "wfxcataloglist" in url.casefold(),
    }


def _should_capture(request: Any, allowed_host: str) -> bool:
    try:
        resource_type = str(request.resource_type or "")
        url = str(request.url or "").casefold()
    except Exception:
        return False
    # Listener nằm trên context nên thấy cả tab người dùng tự mở (mail, web
    # khác). Chỉ ghi host WFX (kể cả subdomain cùng domain, phòng khi dữ liệu
    # đi qua máy chủ API riêng) để file chẩn đoán không chứa web khác.
    host = urlsplit(url).hostname or ""
    domain = ".".join(allowed_host.split(".")[-2:])
    if not allowed_host or (host != allowed_host and not host.endswith(f".{domain}")):
        return False
    if resource_type in _CAPTURED_RESOURCE_TYPES:
        return True
    # Grid có thể nhận dữ liệu nhúng thẳng trong document của chính nó.
    return resource_type == "document" and "wfxcataloglist" in url


class _Capture:
    def __init__(self) -> None:
        self.allowed_host = ""
        self.started = _time.monotonic()
        self.requests: list[tuple[Any, float]] = []
        self.responses: dict[int, Any] = {}

    def on_request(self, request: Any) -> None:
        if len(self.requests) < MAX_ENTRIES and _should_capture(
            request, self.allowed_host
        ):
            self.requests.append((request, _time.monotonic() - self.started))

    def on_response(self, response: Any) -> None:
        try:
            if not any(response.request is item for item, _ in self.requests):
                return
            self.responses[id(response.request)] = response
        except Exception:
            pass


def _describe_request(index: int, request: Any, elapsed: float, response: Any) -> dict:
    url_info = describe_url(str(request.url or ""))
    try:
        # `headers` chỉ là bản tạm; header JS tự gắn nằm trong all_headers().
        headers = dict(request.all_headers())
    except Exception:
        try:
            headers = dict(request.headers)
        except Exception:
            headers = {}
    request_type = str(headers.get("content-type") or "")
    try:
        post_data = request.post_data
    except Exception:
        post_data = None
    frame = _frame_info(request)
    entry: dict[str, Any] = {
        "index": index,
        "elapsed_ms": int(elapsed * 1000),
        "resource_type": safe_text(request.resource_type, 20),
        "method": safe_text(request.method, 10),
        "host": url_info["host"],
        "path": url_info["path"],
        "query_params": url_info["query_params"],
        "request_content_type": safe_text(request_type.split(";")[0], 80),
        "request_headers": describe_headers(headers),
        "body": describe_body(post_data, request_type),
        "frame": frame,
        "from_catalog_grid": frame["is_catalog_grid"],
    }
    if response is None:
        entry["status"] = None
        entry["response"] = {"kind": "no_response"}
        return entry
    try:
        content_type = str(response.headers.get("content-type") or "")
    except Exception:
        content_type = ""
    entry["status"] = int(response.status)
    entry["content_type"] = safe_text(content_type.split(";")[0], 80)
    try:
        body = response.body()
    except Exception:
        body = None
    entry["response_bytes"] = len(body) if body is not None else None
    entry["response"] = summarize_response_body(body, content_type)
    return entry


def _detach(context: Any, capture: _Capture) -> None:
    for event, handler in (
        ("request", capture.on_request),
        ("response", capture.on_response),
    ):
        try:
            context.remove_listener(event, handler)
        except Exception:
            pass


_PRIVACY_NOTE = (
    "Chỉ đọc: không ghi header/cookie, query thô hay giá trị nhạy cảm; dòng "
    "mẫu đã che."
)


def _write_probe_report(
    capture: _Capture,
    output_dir: Path | str,
    *,
    category_name: str,
    app_version: str,
    run_note: str,
) -> tuple[Path, dict]:
    entries = [
        _describe_request(
            index,
            request,
            elapsed,
            capture.responses.get(id(request)),
        )
        for index, (request, elapsed) in enumerate(capture.requests)
    ]
    report = build_report(
        entries,
        category=category_name,
        app_version=app_version,
        run_note=run_note,
    )
    target = Path(output_dir) / (
        f"catalog-endpoint-{_time.strftime('%Y%m%d-%H%M%S')}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(target, report, indent=2)
    return target, report


def probe_catalog_data_source(
    category_name: str,
    category_value: str,
    output_dir: Path | str,
    log: Callable[[str], None] = print,
    *,
    app_version: str = "",
) -> dict[str, Any]:
    """Chạy lại Mở Catalog và ghi hình dạng mọi request dữ liệu của grid."""
    playwright: Playwright | None = None
    context: Any = None
    capture = _Capture()
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        # Probe này CHỦ ĐỘNG mở lại Catalog như nút Mở Catalog, không phải probe
        # nền: grid Catalog chỉ được nhận khi tab đang hiển thị
        # (`visibilityState`), nên phải đưa tab WFX lên trước như
        # prepare_catalog_master.
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )
        context = browser.contexts[0]
        capture.allowed_host = (urlsplit(str(page.url or "")).hostname or "").casefold()
        # Gắn TRƯỚC khi mở Catalog: request nạp datasource đầu tiên phát ra
        # ngay khi Master tạo grid, đi sau là quá muộn.
        context.on("request", capture.on_request)
        context.on("response", capture.on_response)

        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        # Không tái dùng Master đang mở: grid cũ đã nạp xong nên sẽ không phát
        # request nào để quan sát.
        _open_catalog_tree_on_page(page, category_name, category_value, log)
        _write_log(log, "[CATALOG PROBE] Đang mở Master và ghi request của grid...")
        _click_catalog_master(page, log)
        try:
            _show_catalog_floating_filter(
                page,
                log,
                previous_frame=previous_grid,
                require_data_ready=True,
            )
        except PlaywrightTimeoutError as exc:
            # Request đã bắt được vẫn là dữ liệu chẩn đoán quý nhất; ghi bản
            # một phần thay vì bỏ hết chỉ vì grid chưa ổn định.
            message = f"Catalog Master chưa sẵn sàng để dò: {_first_line(exc)}"
            _write_log(log, message)
            _detach(context, capture)
            if not capture.requests:
                return _result(False, "CATALOG_PROBE_NOT_READY", message)
            try:
                target, _report = _write_probe_report(
                    capture,
                    output_dir,
                    category_name=category_name,
                    app_version=app_version,
                    run_note=f"Một phần (grid chưa ổn định). {_PRIVACY_NOTE}",
                )
            except OSError:
                return _result(False, "CATALOG_PROBE_NOT_READY", message)
            _write_log(log, f"[CATALOG PROBE] Đã lưu kết quả một phần: {target}")
            return _result(
                False,
                "CATALOG_PROBE_NOT_READY",
                f"{message} Đã lưu {len(capture.requests)} request vào file.",
                file_path=str(target),
                request_count=len(capture.requests),
            )
        _wait(page, TRAILING_CAPTURE_MS)
        _detach(context, capture)

        try:
            target, report = _write_probe_report(
                capture,
                output_dir,
                category_name=category_name,
                app_version=app_version,
                run_note=_PRIVACY_NOTE,
            )
        except OSError as exc:
            message = f"Không ghi được file chẩn đoán: {_first_line(exc)}"
            _write_log(log, message)
            return _result(False, "CATALOG_PROBE_WRITE_FAILED", message)

        best = report["best_candidate"]
        message = candidate_message(best, report["request_count"])
        _write_log(log, f"[CATALOG PROBE] {message}")
        _write_log(log, f"[CATALOG PROBE] Đã lưu kết quả: {target}")
        return _result(
            True,
            "CATALOG_DATA_SOURCE_PROBED",
            message,
            category=category_name,
            file_path=str(target),
            request_count=report["request_count"],
            best_candidate=best,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Catalog Master chưa sẵn sàng để dò: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_PROBE_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_PROBE_FAILED", message)
    finally:
        if context is not None:
            _detach(context, capture)
        if playwright is not None:
            playwright.stop()
