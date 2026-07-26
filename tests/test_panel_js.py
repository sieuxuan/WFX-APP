from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "wfx_panel" / "ui" / "panel.js").read_text(encoding="utf-8")


def test_exposes_python_callable_globals():
    for name in ["wfxPushLog", "wfxSetStatus", "wfxSetBusy", "wfxApplyTheme", "wfxBootstrap"]:
        assert f"window.{name}" in JS


def test_wires_all_catalog_actions():
    for action in ["prepare", "code-find", "code-costsheet", "code-bom",
                   "buyer-find", "buyer-costsheet", "buyer-bom"]:
        assert f'"{action}"' in JS


def test_module_groups_present():
    assert JS.count("accent:") == 3
    assert "0003_6200" in JS and "0090_0250" in JS


def test_close_after_module_pref_is_consulted_after_open_module():
    # Finding C: the toggle was persisted/restored but never read anywhere.
    # openModule() must check closeAfterModule and call hide_panel() only
    # after a successful open_module result.
    assert "closeAfterModule" in JS
    assert "result.ok && closeAfterModule" in JS
    assert "api()?.hide_panel?.()" in JS


def test_header_mousedown_does_not_leak_into_drag_region():
    # Finding D: pywebview's frameless drag (easy_drag=False) attaches a
    # mousedown listener to every '.pywebview-drag-region' element. Header
    # buttons must stop that mousedown from bubbling up to the header so
    # clicking log/settings/close doesn't get treated as a window drag.
    assert '$(".header-actions")?.addEventListener("mousedown"' in JS
    assert "stopPropagation" in JS
