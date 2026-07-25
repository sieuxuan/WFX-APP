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
