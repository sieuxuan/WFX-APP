from __future__ import annotations

import json
import re
import time

_TIMESTAMP_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]")


def js_string(value: str) -> str:
    """JSON-encode a string so it can be embedded directly in evaluate_js."""
    return json.dumps(str(value), ensure_ascii=False)


def format_log_line(message: str) -> str:
    text = str(message)
    if _TIMESTAMP_RE.match(text):
        return text
    return f"[{time.strftime('%H:%M:%S')}] {text}"
