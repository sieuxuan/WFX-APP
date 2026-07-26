"""Kiểm tra nhanh endpoint Chrome DevTools Protocol mà không bật Playwright."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import urlopen


def cdp_url() -> str:
    host = os.getenv("WFX_CDP_HOST", "127.0.0.1")
    port = os.getenv("WFX_CDP_PORT", "9222")
    return f"http://{host}:{port}"


def chrome_alive(timeout: float = 1.0) -> bool:
    try:
        with urlopen(f"{cdp_url()}/json/version", timeout=timeout) as response:
            info = json.load(response)
        return bool(info.get("webSocketDebuggerUrl"))
    except (OSError, URLError, ValueError):
        return False
