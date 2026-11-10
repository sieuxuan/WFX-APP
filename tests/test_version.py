from pathlib import Path

from wfx_panel.version import APP_VERSION, DISPLAY_VERSION, RELEASE_TAG

ROOT = Path(__file__).resolve().parents[1]


def test_public_version_is_1_1_8():
    assert APP_VERSION == "1.1.8"
    assert DISPLAY_VERSION == "1.1.8"
    assert RELEASE_TAG == "v1.1.8"


def test_windows_build_embeds_release_version():
    spec = (ROOT / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")
    info = (ROOT / "wfx_panel" / "version_info.txt").read_text(encoding="utf-8")
    assert 'version="version_info.txt"' in spec
    assert f"ProductVersion', '{APP_VERSION}" in info
    assert f"FileVersion', '{APP_VERSION}" in info
    components = ", ".join([*APP_VERSION.split("."), "0"])
    assert f"prodvers=({components})" in info
    assert f"filevers=({components})" in info


def test_project_metadata_matches_the_app_version():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == APP_VERSION
