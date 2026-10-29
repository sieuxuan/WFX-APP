"""Xuất nội dung Manual, Có gì mới và danh sách module cho website site/.

Website WFX Smart (Cloudflare Worker trong site/) không tự viết lại hướng
dẫn: nó đọc đúng sách mà cửa sổ Manual trong app đang dùng, qua
manual_book.load_book(). Danh sách module cho form Đề xuất tính năng lấy từ
MODULE_GROUPS của panel UI để tên module trên web khớp chữ trên app.

Chạy: python scripts/export_site_content.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wfx_panel import manual_book  # noqa: E402

CORE_JS = ROOT / "wfx_panel" / "ui" / "panel" / "core.js"
OUTPUT = ROOT / "site" / "public" / "content" / "site.json"

_GROUP = re.compile(r'\{\s*name:\s*"([^"]+)",\s*accent:')
_MODULE = re.compile(r'\{\s*name:\s*"([^"]+)",\s*id:\s*"[^"]+",.*?description:\s*"([^"]*)"')

# Đề xuất không thuộc module nào có sẵn vẫn cần một chỗ để chọn.
EXTRA_GROUP = {
    "name": "Chung",
    "modules": [
        {"name": "Giao diện & cài đặt app", "description": "Bảng điều khiển, phím tắt, thông báo, cập nhật."},
        {"name": "Module mới", "description": "Màn WFX chưa có trong app."},
    ],
}


def load_module_groups(source: str) -> list[dict]:
    groups: list[dict] = []
    for line in source.splitlines():
        group = _GROUP.search(line)
        if group:
            groups.append({"name": group.group(1), "modules": []})
            continue
        module = _MODULE.search(line)
        if module and groups:
            groups[-1]["modules"].append(
                {"name": module.group(1), "description": module.group(2)}
            )
    if not groups or not any(group["modules"] for group in groups):
        raise SystemExit(f"Không đọc được MODULE_GROUPS trong {CORE_JS}")
    return [*groups, EXTRA_GROUP]


def build_site_content(book: dict, module_groups: list[dict]) -> dict:
    search = {row["id"]: row["haystack"] for row in book["search_index"]}
    entries = {
        entry_id: {
            "id": entry_id,
            "chapter": entry["chapter"],
            "title": entry["title"],
            "summary": entry["summary"],
            "html": entry["html"],
            "search": search.get(entry_id, ""),
        }
        for entry_id, entry in book["entries"].items()
    }
    errors = [
        {key: row[key] for key in ("code", "title", "suggestion", "entry", "haystack")}
        for row in book["error_table"]
    ]
    return {
        "version": book["version"],
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chapters": book["chapters"],
        "entries": entries,
        "order": book["order"],
        "errors": errors,
        "whats_new": book["whats_new"],
        "module_groups": module_groups,
    }


def main() -> None:
    content = build_site_content(
        manual_book.load_book(),
        load_module_groups(CORE_JS.read_text(encoding="utf-8")),
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Đã ghi {OUTPUT.relative_to(ROOT)}: {len(content['entries'])} mục, "
        f"{len(content['whats_new'])} phiên bản"
    )


if __name__ == "__main__":
    main()
