from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Tọa độ chuẩn hóa theo SVG logo gốc (viewBox 0 0 28 28).
_HEX = [(5.2, 6.7), (14, 2.4), (22.8, 6.7), (22.8, 17.3), (14, 25.6), (5.2, 17.3)]
_W = [(8.6, 9.2), (11.2, 18.4), (14.0, 12.2), (16.8, 18.4), (19.4, 9.2)]
_BG = (99, 102, 241)      # indigo-500
_MARK = (255, 255, 255)


def _scaled(points, size):
    factor = size / 28.0
    return [(x * factor, y * factor) for x, y in points]


def build_icon(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    master = 256
    image = Image.new("RGBA", (master, master), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(_scaled(_HEX, master), fill=_BG)
    draw.line(_scaled(_W, master), fill=_MARK, width=max(2, master // 14), joint="curve")
    image.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    out = build_icon(Path(__file__).with_name("wfx.ico"))
    print(f"Wrote {out}")
