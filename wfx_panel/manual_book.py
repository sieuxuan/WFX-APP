"""Đọc và dựng nội dung hướng dẫn sử dụng WFX Smart.

Module này cố ý không biết gì về pywebview hay UI: nó chỉ biến file
Markdown + manifest trong wfx_panel/manual/ thành cấu trúc dữ liệu đã dựng
sẵn HTML. Nhờ vậy test chạy được mà không cần cửa sổ, và cả bộ sinh tài liệu
docs/USER_FEATURES.md lẫn cửa sổ Manual đều dùng chung một nguồn.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import unicodedata

from wfx_panel import prefs, telemetry
from wfx_panel.version import APP_VERSION

CALLOUT_LABELS = {
    "meo": "Mẹo",
    "luuy": "Lưu ý",
    "loi": "Gặp lỗi thì sao",
}

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CALLOUT_OPEN = re.compile(r"^>\s*\[!(\w+)\]\s*$")
_ORDERED_ITEM = re.compile(r"^\d+\.\s+(.*)$")
_TABLE_DIVIDER = re.compile(r"^[\s|:-]+$")
_TAG = re.compile(r"<[^>]+>")

MANUAL_DIR = prefs.RESOURCE_DIR / "wfx_panel" / "manual"

FORBIDDEN_WORDS = (
    "frame",
    "selector",
    "CDP",
    "postback",
    "iframe",
    "XPath",
    "DOM",
    "endpoint",
    "payload",
    "token",
    "grid",
)

_COVER_KEYS = ("modules", "actions", "settings", "errors")


class ManualContentError(Exception):
    """Nội dung manual không hợp lệ — thiếu file, sai khoá, hoặc trùng id."""


def slugify(text: str) -> str:
    """Bỏ dấu tiếng Việt và đổi thành chuỗi an toàn cho thuộc tính id."""
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    ascii_text = ascii_text.replace("đ", "d").replace("Đ", "D")
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-").lower()


def render_inline(text: str) -> str:
    """Escape trước, rồi mới áp định dạng — không bao giờ cho HTML thô lọt."""
    escaped = html_lib.escape(text, quote=False)
    escaped = _INLINE_CODE.sub(r'<b class="ui-label">\1</b>', escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    return escaped


def strip_html(html_text: str) -> str:
    """Trả về văn bản thuần để dựng chỉ mục tìm kiếm và đoạn trích."""
    text = _TAG.sub(" ", html_text)
    return " ".join(html_lib.unescape(text).split())


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(source: str) -> str:
    """Dựng tập con Markdown đã thống nhất trong docs/MANUAL_AUTHORING.md."""
    lines = source.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    list_tag: str | None = None
    table: list[list[str]] = []
    callout: str | None = None
    paragraph: list[str] = []

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    def close_paragraph() -> None:
        if paragraph:
            out.append("<p>" + " ".join(paragraph) + "</p>")
            paragraph.clear()

    def close_table() -> None:
        nonlocal table
        if not table:
            return
        head, *body = table
        cells = "".join(f"<th>{render_inline(c)}</th>" for c in head)
        out.append(f"<table><thead><tr>{cells}</tr></thead><tbody>")
        for row in body:
            cells = "".join(f"<td>{render_inline(c)}</td>" for c in row)
            out.append(f"<tr>{cells}</tr>")
        out.append("</tbody></table>")
        table = []

    def close_callout() -> None:
        nonlocal callout
        if callout is not None:
            out.append("</div>")
            callout = None

    def close_all() -> None:
        close_paragraph()
        close_list()
        close_table()
        close_callout()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_all()
            continue

        opened = _CALLOUT_OPEN.match(stripped)
        if opened:
            close_all()
            kind = opened.group(1).lower()
            label = CALLOUT_LABELS.get(kind, kind)
            callout = kind
            out.append(f'<div class="callout callout-{kind}"><b>{label}</b>')
            continue

        if callout is not None:
            if stripped.startswith(">"):
                out.append("<p>" + render_inline(stripped[1:].strip()) + "</p>")
                continue
            close_callout()

        if stripped.startswith("## "):
            close_all()
            title = stripped[3:].strip()
            out.append(f'<h2 id="{slugify(title)}">{render_inline(title)}</h2>')
            continue

        if stripped.startswith("|"):
            close_paragraph()
            close_list()
            if not _TABLE_DIVIDER.match(stripped):
                table.append(_split_row(stripped))
            continue
        close_table()

        ordered = _ORDERED_ITEM.match(stripped)
        if ordered:
            close_paragraph()
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{render_inline(ordered.group(1))}</li>")
            continue

        if stripped.startswith("- "):
            close_paragraph()
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{render_inline(stripped[2:])}</li>")
            continue

        close_list()
        paragraph.append(render_inline(stripped))

    close_all()
    return "".join(out)


def load_manifest() -> dict:
    path = MANUAL_DIR / "manifest.json"
    if not path.is_file():
        raise ManualContentError(f"Thiếu {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_whats_new() -> list[dict]:
    path = MANUAL_DIR / "whats_new.json"
    if not path.is_file():
        raise ManualContentError(f"Thiếu {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_error_table(entries: dict) -> list[dict]:
    """Sinh bảng tra mã lỗi thẳng từ telemetry.ERROR_CODE_INFO.

    Nhờ đọc trực tiếp từ điển này, mã lỗi mới thêm vào code tự xuất hiện trong
    manual mà không phải sửa file .md.
    """
    owner: dict[str, str] = {}
    for entry in entries.values():
        for code in entry["covers"]["errors"]:
            owner.setdefault(code, entry["id"])
    rows = []
    for code, (title, suggestion) in telemetry.ERROR_CODE_INFO.items():
        rows.append(
            {
                "code": code,
                "title": title,
                "suggestion": suggestion,
                "entry": owner.get(code),
            }
        )
    rows.sort(key=lambda row: row["code"])
    return rows


def build_search_index(entries: dict) -> list[dict]:
    index = []
    for entry_id in entries:
        entry = entries[entry_id]
        haystack = " ".join(
            [
                entry["title"],
                entry["chapter_title"],
                entry["summary"],
                " ".join(entry["keywords"]),
                " ".join(entry["covers"]["errors"]),
                entry["text"],
            ]
        ).lower()
        index.append(
            {
                "id": entry_id,
                "title": entry["title"],
                "chapter_title": entry["chapter_title"],
                "haystack": haystack,
            }
        )
    return index


def load_book() -> dict:
    manifest = load_manifest()
    chapters: list[dict] = []
    entries: dict[str, dict] = {}
    order: list[str] = []

    for chapter in manifest["chapters"]:
        entry_ids: list[str] = []
        for entry in chapter["entries"]:
            entry_id = entry["id"]
            if entry_id in entries:
                raise ManualContentError(f"Trùng id mục: {entry_id}")
            path = MANUAL_DIR / entry["file"]
            if not path.is_file():
                raise ManualContentError(f"Thiếu file nội dung: {entry['file']}")
            body = render_markdown(path.read_text(encoding="utf-8"))
            covers = entry.get("covers", {})
            entries[entry_id] = {
                "id": entry_id,
                "chapter": chapter["id"],
                "chapter_title": chapter["title"],
                "title": entry["title"],
                "summary": entry.get("summary", ""),
                "keywords": list(entry.get("keywords", [])),
                "html": body,
                "text": strip_html(body),
                "covers": {key: list(covers.get(key, [])) for key in _COVER_KEYS},
            }
            entry_ids.append(entry_id)
            order.append(entry_id)
        chapters.append(
            {
                "id": chapter["id"],
                "title": chapter["title"],
                "summary": chapter.get("summary", ""),
                "entries": entry_ids,
            }
        )

    return {
        "version": APP_VERSION,
        "chapters": chapters,
        "entries": entries,
        "order": order,
        "error_table": build_error_table(entries),
        "search_index": build_search_index(entries),
        "whats_new": load_whats_new(),
    }
