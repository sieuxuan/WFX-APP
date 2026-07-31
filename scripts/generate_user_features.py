"""Sinh docs/USER_FEATURES.md từ nội dung hướng dẫn trong ứng dụng.

Tài liệu người dùng chỉ có một nguồn duy nhất là wfx_panel/manual/. File này
biến nội dung đó thành Markdown phẳng cho người đọc trên GitHub.

Chạy: python scripts/generate_user_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wfx_panel import manual_book  # noqa: E402

HEADER = (
    "# Danh sách chức năng WFX Smart\n\n"
    "> File này được sinh tự động từ `wfx_panel/manual/`. Đừng sửa tay —\n"
    "> sửa nội dung trong `wfx_panel/manual/` rồi chạy\n"
    "> `python scripts/generate_user_features.py`.\n"
)


def build_user_features(book: dict) -> str:
    parts = [HEADER]
    parts.append(f"\nPhiên bản: {book['version']}\n")
    for index, chapter in enumerate(book["chapters"], start=1):
        parts.append(f"\n## {index}. {chapter['title']}\n")
        if chapter["summary"]:
            parts.append(f"\n{chapter['summary']}\n")
        for entry_id in chapter["entries"]:
            entry = book["entries"][entry_id]
            parts.append(f"\n### {entry['title']}\n")
            if entry["summary"]:
                parts.append(f"\n{entry['summary']}\n")
            parts.append(f"\n{entry['text']}\n")
    parts.append("\n## Bảng tra mã lỗi\n\n")
    parts.append("| Mã | Nghĩa là gì | Cách xử lý |\n|---|---|---|\n")
    for row in book["error_table"]:
        parts.append(
            f"| `{row['code']}` | {row['title']} | {row['suggestion']} |\n"
        )
    return "".join(parts)


def main() -> None:
    text = build_user_features(manual_book.load_book())
    (ROOT / "docs" / "USER_FEATURES.md").write_text(text, encoding="utf-8")
    print("Updated docs/USER_FEATURES.md")


if __name__ == "__main__":
    main()
