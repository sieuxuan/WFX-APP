from pathlib import Path

from PIL import Image

from wfx_panel.assets.generate_icon import build_icon


def test_build_icon_creates_valid_ico(tmp_path: Path):
    out = build_icon(tmp_path / "wfx.ico")
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "ICO"
