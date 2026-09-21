"""Hợp đồng giữa JavaScript và bridge Python.

``PanelAPI`` và ``PanelApp`` là hai object duy nhất JavaScript gọi tới. Khi tách
chúng thành controller, một delegator bị bỏ sót sẽ KHÔNG làm test nào đỏ — nó
chỉ hiện ra lúc người dùng bấm đúng nút đó trên bản đã cài. Các canh dưới đây
đọc chính source JS để chặn chuyện đó.
"""

from __future__ import annotations

import re

from tests.fakes.ui_source import panel_js
from wfx_panel.panel_api import PanelAPI
from wfx_panel.panel_app import PanelApp

# Sink và applier do panel_app gắn vào lúc khởi động, JavaScript không gọi.
_WIRED_BY_PANEL_APP = frozenset(
    {
        "set_log_sink",
        "set_result_sink",
        "set_progress_sink",
        "set_hotkey_applier",
        "set_update_applier",
        "set_window_pref_appliers",
        "shutdown",
        "run_composite",
        "is_action_running",
        "refresh_status",
    }
)


def _methods_called_from_javascript() -> set[str]:
    source = panel_js()
    names: set[str] = set()
    names |= set(re.findall(r'\bcall\(\s*"([a-z_]+)"', source))
    names |= set(re.findall(r'\bcallQuiet\(\s*"([a-z_]+)"', source))
    names |= set(re.findall(r'runSelectedModuleAction\(\s*"([a-z_]+)"', source))
    names |= set(re.findall(r"api\(\)\.([a-z_]+)\(", source))
    run_methods = re.search(r"MODULE_RUN_METHODS = new Set\(\[(.*?)\]\)", source, re.S)
    assert run_methods, "Không còn bảng MODULE_RUN_METHODS trong panel UI"
    names |= set(re.findall(r'"([a-z_]+)"', run_methods.group(1)))
    return names


def test_every_method_javascript_calls_exists_on_the_bridge():
    called = _methods_called_from_javascript()
    assert len(called) > 100, "Bộ quét không còn bắt được lời gọi nào — canh đã mục"

    missing = sorted(
        name
        for name in called
        if not hasattr(PanelAPI, name) and not hasattr(PanelApp, name)
    )
    assert not missing, (
        "JavaScript gọi method không có trên bridge — người dùng sẽ bấm nút và "
        f"không có gì xảy ra: {', '.join(missing)}"
    )


def test_every_bridge_method_javascript_calls_is_callable():
    called = _methods_called_from_javascript()
    not_callable = sorted(
        name
        for name in called
        for owner in (PanelAPI, PanelApp)
        if hasattr(owner, name) and not callable(getattr(owner, name))
    )
    assert not not_callable, f"Không gọi được như hàm: {', '.join(not_callable)}"


def test_module_run_methods_are_all_real_bridge_methods():
    """Bảng MODULE_RUN_METHODS quyết định nút nào giữ highlight lúc chạy."""
    source = panel_js()
    block = re.search(r"MODULE_RUN_METHODS = new Set\(\[(.*?)\]\)", source, re.S)
    assert block is not None
    declared = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    assert declared, "MODULE_RUN_METHODS rỗng"
    # Bảng này gồm cả method của PanelApp: hộp thoại chọn/tải file cũng là một
    # lượt chạy mà nút phải giữ highlight.
    missing = sorted(
        name
        for name in declared
        if not hasattr(PanelAPI, name) and not hasattr(PanelApp, name)
    )
    assert not missing, (
        f"MODULE_RUN_METHODS nêu method không có trên bridge: {', '.join(missing)}"
    )
