"""Trích danh sách tính năng đang có từ chính file nguồn giao diện.

Đây là helper CHỈ dùng cho test: nó đọc panel.js và index.html bằng biểu thức
chính quy, cùng kiểu với tests/test_panel_js.py và tests/test_ui_assets.py.
Nhờ vậy thêm module hoặc thêm nút mới mà quên viết manual là test đỏ ngay.
"""

from __future__ import annotations

import re
from pathlib import Path

from wfx_panel import manual_book

_UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
_JS = (_UI / "panel.js").read_text(encoding="utf-8")
_HTML = (_UI / "index.html").read_text(encoding="utf-8")

_MODULE_ID = re.compile(r'\{ name: "[^"]+", id: "([^"]+)"')
_SETTINGS_PANEL = re.compile(
    r'<section class="settings-panel settings-(?:automation|appearance)-panel.*?</section>',
    re.S,
)
_INPUT_CLASS = re.compile(r'class="([a-z-]+-input)"')


def _action(prefix: str) -> set[str]:
    return set(re.findall(rf'data-{prefix}-action="([a-z0-9-]+)"', _HTML))


def module_ids() -> set[str]:
    return set(_MODULE_ID.findall(_JS))


def module_actions() -> set[str]:
    return _action("module")


def catalog_actions() -> set[str]:
    return _action("catalog")


def costing_actions() -> set[str]:
    return _action("costing")


def style_actions() -> set[str]:
    return _action("style")


def settings_controls() -> set[str]:
    controls: set[str] = set()
    for block in _SETTINGS_PANEL.findall(_HTML):
        controls.update(_INPUT_CLASS.findall(block))
    # Hai điều khiển không phải checkbox, phủ bằng id quy ước.
    controls.update({"hotkey", "theme"})
    return controls


def covered(kind: str) -> set[str]:
    manifest = manual_book.load_manifest()
    values: set[str] = set()
    for chapter in manifest["chapters"]:
        for entry in chapter["entries"]:
            values.update(entry.get("covers", {}).get(kind, []))
    return values
