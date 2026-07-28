from pathlib import Path

from wfx_panel.version import APP_VERSION, DISPLAY_VERSION, RELEASE_TAG

ROOT = Path(__file__).resolve().parents[1]


def test_public_version_is_1_0_12():
    assert APP_VERSION == "1.0.12"
    assert DISPLAY_VERSION == "1.0.12"
    assert RELEASE_TAG == "v1.0.12"


def test_windows_build_embeds_release_version():
    spec = (ROOT / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")
    info = (ROOT / "wfx_panel" / "version_info.txt").read_text(encoding="utf-8")
    assert 'version="version_info.txt"' in spec
    assert "ProductVersion', '1.0.12" in info
