from __future__ import annotations

import json
import re
import time

_TIMESTAMP_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]")
_URL_QUERY_RE = re.compile(
    r"(https?://[^\s?#]+)(\?[^\s#]*)?",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(
        password|passwd|cookie|sessionid|loginid|userid|remoteip|
        access_token|token|authorization|auth|
        query|article_code|style_code|buyer_reference
    )\b
    \s*([:=])\s*
    (?:
        "(?:[^"\\]|\\.)*" |
        '(?:[^'\\]|\\.)*' |
        [^\s,;]+
    )
    """
)
_BUSINESS_DETAIL_RE = re.compile(
    r"""(?ix)
    (
        lọc\s+(?:gần\s+đúng|chính\s+xác) |
        kết\s+quả\s+grid |
        đã\s+nhập\s+query |
        (?:đang|đã)\s+mở\s+style |
        một\s+kết\s+quả,\s+đang\s+mở |
        đang\s+mở\s+buyer\s+đầu\s+tiên
    )
    \s*[:=]?\s*.*
    """
)


def sanitize_log_text(value: object) -> str:
    """Che credential, URL query và dữ liệu nghiệp vụ trước mọi nơi hiển thị/lưu."""
    text = str(value)
    text = _URL_QUERY_RE.sub(
        lambda match: (
            f"{match.group(1)}?[REDACTED]"
            if match.group(2)
            else match.group(1)
        ),
        text,
    )
    text = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    text = _BUSINESS_DETAIL_RE.sub(
        lambda match: f"{match.group(1)}: [REDACTED]",
        text,
    )
    return text


def js_string(value: str) -> str:
    """JSON-encode a string so it can be embedded directly in evaluate_js."""
    return json.dumps(str(value), ensure_ascii=False)


def format_log_line(message: str) -> str:
    text = sanitize_log_text(message)
    if _TIMESTAMP_RE.match(text):
        return text
    return f"[{time.strftime('%H:%M:%S')}] {text}"
