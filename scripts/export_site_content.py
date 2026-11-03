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
_MODULE = re.compile(r'\{\s*name:\s*"([^"]+)",\s*id:\s*"([^"]+)",.*?description:\s*"([^"]*)"')

APP_MODULE = "app"
# Đề xuất không thuộc module nào có sẵn vẫn cần một chỗ để chọn.
EXTRA_GROUP = {
    "name": "Chung",
    "modules": [
        {"id": APP_MODULE, "name": "Giao diện & cài đặt app", "description": "Bảng điều khiển, phím tắt, thông báo, cập nhật."},
        {"id": "new", "name": "Module mới", "description": "Màn WFX chưa có trong app."},
    ],
}
# Chương không khai báo module riêng nhưng là một workspace của module khác.
CHAPTER_MODULE = {"costing": "0003_6200"}
MANUAL_DIR = ROOT / "wfx_panel" / "manual"
_HEADING = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
# Tiêu đề khung chung của mọi mục Hướng dẫn, không phải tên một tính năng.
_NOT_FEATURE = re.compile(r"^(Dùng để làm gì|Các bước|Cách điền|Mẹo|Lưu ý|Gặp lỗi|Quy tắc)", re.IGNORECASE)


def load_entry_features() -> dict[str, list[str]]:
    """Tên các tính năng con trong từng mục Hướng dẫn, lấy từ tiêu đề ##/###."""
    manifest = json.loads((MANUAL_DIR / "manifest.json").read_text(encoding="utf-8"))
    features: dict[str, list[str]] = {}
    for chapter in manifest["chapters"]:
        for entry in chapter["entries"]:
            text = (MANUAL_DIR / entry["file"]).read_text(encoding="utf-8")
            features[entry["id"]] = [
                title.replace("`", "") for title in _HEADING.findall(text) if not _NOT_FEATURE.match(title)
            ]
    return features


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
                {"id": module.group(2), "name": module.group(1), "description": module.group(3)}
            )
    if not groups or not any(group["modules"] for group in groups):
        raise SystemExit(f"Không đọc được MODULE_GROUPS trong {CORE_JS}")
    return [*groups, EXTRA_GROUP]


def build_features(book: dict, module_groups: list[dict]) -> dict:
    """Gom mục Hướng dẫn theo module để trang Đề xuất liệt kê tính năng đang có.

    Mục khai báo `covers.modules` thuộc các module đó; mục sau nó trong cùng
    chương (Upload OC, Mở Costing...) thuộc module đầu tiên vừa gặp. Chương
    không có module nào là tính năng chung của app. Module mới chỉ cần có mục
    Hướng dẫn (test_manual đã bắt buộc) là tự hiện trên trang.
    """
    known = {module["id"] for group in module_groups for module in group["modules"]}
    by_module: dict[str, list[str]] = {}
    for chapter in book["chapters"]:
        current = CHAPTER_MODULE.get(chapter["id"])
        for entry_id in chapter["entries"]:
            modules = [m for m in book["entries"][entry_id]["covers"].get("modules", []) if m in known]
            if modules:
                current = modules[0]
            for module_id in modules or [current or APP_MODULE]:
                by_module.setdefault(module_id, []).append(entry_id)
    latest = book["whats_new"][0] if book["whats_new"] else {"version": "", "highlights": []}
    return {
        "modules": by_module,
        "sub": {entry_id: titles for entry_id, titles in load_entry_features().items() if titles},
        "new_version": latest["version"],
        "new_entries": sorted({h["entry"] for h in latest["highlights"] if h.get("entry")}),
    }


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
        "features": build_features(book, module_groups),
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
    # Console Windows cp1252 không in được tiếng Việt và làm `npm run deploy` dừng.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(
        f"Đã ghi {OUTPUT.relative_to(ROOT)}: {len(content['entries'])} mục, "
        f"{len(content['whats_new'])} phiên bản"
    )


if __name__ == "__main__":
    main()
