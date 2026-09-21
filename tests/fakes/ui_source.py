"""Đọc source JavaScript của panel theo đúng thứ tự trình duyệt nạp.

``panel.js`` đã tách thành ``wfx_panel/ui/panel/*.js``. Các canh theo mẫu chuỗi
cần nhìn thấy đúng một văn bản liền mạch, và thứ tự phải là thứ tự thật trong
``index.html`` — không phải thứ tự alphabet — vì các script chia chung một
global scope và chạy tuần tự.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent.parent / "wfx_panel" / "ui"
_SCRIPT_SRC = re.compile(r'<script[^>]+src="([^"]+)"')


@cache
def panel_script_paths() -> tuple[Path, ...]:
    """Các file script mà index.html nạp, theo đúng thứ tự khai báo."""
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    paths = tuple(
        UI_DIR / src.split("?", 1)[0] for src in _SCRIPT_SRC.findall(html)
    )
    assert paths, "index.html không khai báo script nào"
    missing = [path for path in paths if not path.is_file()]
    assert not missing, f"index.html trỏ tới file không tồn tại: {missing}"
    return paths


@cache
def panel_js() -> str:
    """Toàn bộ JavaScript của panel, nối theo thứ tự nạp."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in panel_script_paths()
    )
