# Manual hệ thống trong ứng dụng — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biến nút Manual trên top nav của WFX Smart thành một cửa sổ tra cứu hướng dẫn sử dụng đầy đủ, chạy offline, phủ mọi tính năng của sản phẩm, và có test chặn việc thêm tính năng mà quên viết manual.

**Architecture:** Nội dung là Markdown + `manifest.json` trong `wfx_panel/manual/`, dựng thành HTML ở phía Python bởi `wfx_panel/manual_book.py`. Một cửa sổ pywebview riêng (`wfx_panel/ui/manual.html`) hiển thị nội dung đó qua `_ManualBridge`. Bốn kiểm tra phủ trong `tests/test_manual.py` đối chiếu manifest với nguồn sự thật trong code (module, nút thao tác, công tắc cài đặt, mã lỗi). `docs/USER_FEATURES.md` được sinh lại từ chính nội dung manual.

**Tech Stack:** Python 3 (stdlib: `json`, `re`, `unicodedata`, `html`), pywebview, HTML/CSS/JS thuần không thư viện ngoài, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-01-manual-he-thong-design.md`

---

## Global Constraints

- Mọi code sản phẩm nằm trong `wfx_panel/`. Không sửa file trong `dist/`.
- `python -m pytest` và `ruff check .` phải xanh sau **mỗi** task.
- Không thư viện JavaScript ngoài. Manual chạy offline hoàn toàn: không gọi mạng, không cần Chrome, không cần phiên đăng nhập WFX.
- Toàn bộ nội dung người dùng viết bằng tiếng Việt.
- Từ cấm trong file `.md` của manual: `frame`, `selector`, `CDP`, `postback`, `iframe`, `XPath`, `DOM`, `endpoint`, `payload`, `token`, `grid`. Dùng thay thế: màn hình, nút, ô nhập, danh sách, file Excel, trình duyệt.
- Không có HTML thô trong file `.md`.
- Phiên bản lấy từ `wfx_panel/version.py` (`APP_VERSION = "1.0.17"`, `DISPLAY_VERSION`). Không hardcode số phiên bản ở nơi khác.
- Đường dẫn tài nguyên đọc qua `prefs.RESOURCE_DIR` (xem `wfx_panel/prefs.py:25`), không tự dựng đường dẫn từ `__file__`.
- Commit sau mỗi task. Message tiếng Việt, dạng `feat:` / `test:` / `docs:` / `fix:`.
- Kết thúc mỗi commit message:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- Nhánh làm việc: `feat/manual-he-thong` (đã tạo, đã có commit spec).

---

## Nguồn sự thật hiện có (đọc trước khi bắt đầu)

| Thứ cần phủ | Nằm ở đâu | Số lượng hiện tại |
|---|---|---|
| Module | `MODULE_GROUPS` đầu `wfx_panel/ui/panel.js` (dòng 3–26) | 16 |
| Nút thao tác module | `data-module-action="..."` trong `wfx_panel/ui/index.html` | 29 |
| Nút Catalog | `data-catalog-action="..."` | 6 |
| Nút Costing | `data-costing-action="..."` | 6 |
| Công tắc cài đặt | `class="*-input"` trong `.settings-automation-panel` và `.settings-appearance-panel` | 8 |
| Mã lỗi | `wfx_panel/telemetry.py` → `ERROR_CODE_INFO` | 84 |

Danh sách đầy đủ, dùng nguyên văn khi viết manifest:

**Module ids:** `0003_6200`, `0004_0050_0020`, `0004_0056_4070`, `0004_0070_0020`, `0005_0050_0020`, `0005_0080_0020`, `user_indent_list`, `0063_0030_0020`, `0065_0880_0010_0020`, `0065_0880_0020_0020`, `0065_0880_0030_0020`, `0090_0001`, `0090_0250`, `0090_0007`, `0004_0010_1720`, `0005_0010_1290`

**module actions:** `buyer-find`, `buyer-list`, `company-list`, `company-toggle-foc`, `indent-list`, `indent-search`, `list-new-list`, `list-new-new`, `oc-list`, `oc-review-cancel`, `oc-review-confirm`, `oc-revise-report`, `oc-search`, `oc-template`, `oc-upload-new`, `oc-upload-revise`, `rmpo-list`, `rmpo-search`, `sale-asn-documents`, `sale-asn-list`, `sale-asn-new`, `sale-asn-search`, `sample-check-file`, `sample-list`, `sample-new`, `sample-search`, `supplier-find`, `supplier-list`, `supplier-open`

**catalog actions:** `browse`, `find`, `costsheet`, `bom`, `files`, `refresh-folders`

**costing actions:** `export-xlsx`, `validate-file`, `import`, `apply`, `cancel-plan`, `clear-dependencies`

**settings inputs:** `return-list-input`, `focus-chrome-input`, `open-costing-file-input`, `autostart-input`, `start-hidden-input`, `admin-mode-input`, `always-on-top-input`, `toast-input`

Hai điều khiển cài đặt không phải checkbox, phủ bằng id quy ước: `hotkey` (nút `.hotkey-button`) và `theme` (nhóm `.seg-button[data-theme-choice]`).

---

## File Structure

**Tạo mới**

| File | Trách nhiệm |
|---|---|
| `wfx_panel/manual_book.py` | Đọc manifest + `.md` + `whats_new.json`, dựng HTML, dựng chỉ mục tìm kiếm, dựng bảng mã lỗi. Không biết gì về pywebview. |
| `wfx_panel/manual/manifest.json` | Danh mục chương/mục, từ khoá, khai báo phủ |
| `wfx_panel/manual/whats_new.json` | Thay đổi theo phiên bản |
| `wfx_panel/manual/NN-<chương>/*.md` | Nội dung |
| `wfx_panel/ui/manual.html` | Khung cửa sổ tra cứu |
| `wfx_panel/ui/manual.css` | Trình bày + sáng/tối + CSS bản in. Token màu độc lập với `style.css`. |
| `wfx_panel/ui/manual.js` | Điều hướng, tìm kiếm, tô từ khoá |
| `scripts/generate_user_features.py` | Sinh `docs/USER_FEATURES.md` |
| `tests/_manual_surface.py` | Helper test: trích module/nút/cài đặt từ file nguồn UI |
| `tests/test_manual.py` | Toàn vẹn manifest, dựng Markdown, bốn kiểm tra phủ |
| `docs/MANUAL_AUTHORING.md` | Prompt/hướng dẫn viết manual cho lần sau |
| `docs/README.md` | Mục lục tài liệu |

**Sửa**

| File | Sửa gì |
|---|---|
| `wfx_panel/panel_app.py` | `MANUAL_INDEX`, `_ManualBridge`, viết lại `open_wfx_manual()` |
| `wfx_panel/prefs.py` | Thêm khoá `manual_seen_version` |
| `wfx_panel/ui/index.html` | Nút `?` trong module page, nút trợ giúp ở footer, chấm báo trên nút Manual, badge phiên bản động |
| `wfx_panel/ui/panel.js` | Nối ba thứ trên |
| `wfx_panel/ui/style.css` | Style cho nút `?` và nút trợ giúp footer |
| `wfx_panel/wfx-panel.spec` | Thêm `("manual", "wfx_panel/manual")` vào `datas` |
| `tests/test_panel_app.py` | Viết lại `test_wfx_manual_opens_the_configured_url` |
| `tests/test_ui_assets.py`, `tests/test_panel_js.py`, `tests/test_prefs.py` | Bổ sung test |
| `README.md`, `CLAUDE.md` | Bổ sung phần thiếu |

---

# GIAI ĐOẠN 1 — Nền nội dung

### Task 1: Bộ dựng Markdown

**Files:**
- Create: `wfx_panel/manual_book.py`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: không có
- Produces:
  - `slugify(text: str) -> str`
  - `render_inline(text: str) -> str`
  - `render_markdown(source: str) -> str`
  - `strip_html(html_text: str) -> str`
  - Hằng `CALLOUT_LABELS: dict[str, str]`

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_manual.py`:

```python
from wfx_panel import manual_book


def test_slugify_bo_dau_tieng_viet():
    assert manual_book.slugify("Tìm Style trên WFX") == "tim-style-tren-wfx"
    assert manual_book.slugify("Gặp lỗi thì sao?") == "gap-loi-thi-sao"


def test_render_inline_escape_truoc_khi_dinh_dang():
    assert manual_book.render_inline("a < b & c") == "a &lt; b &amp; c"
    assert manual_book.render_inline("bấm `Mở Catalog`") == (
        'bấm <b class="ui-label">Mở Catalog</b>'
    )
    assert manual_book.render_inline("**quan trọng**") == (
        "<strong>quan trọng</strong>"
    )


def test_render_markdown_tieu_de_co_id():
    html = manual_book.render_markdown("## Các bước\n")
    assert html == '<h2 id="cac-buoc">Các bước</h2>'


def test_render_markdown_danh_sach_co_so_va_khong_so():
    html = manual_book.render_markdown("1. Mở panel\n2. Chọn Division\n")
    assert html == "<ol><li>Mở panel</li><li>Chọn Division</li></ol>"
    html = manual_book.render_markdown("- Một\n- Hai\n")
    assert html == "<ul><li>Một</li><li>Hai</li></ul>"


def test_render_markdown_bang_bo_dong_gach_ngang():
    source = "| Hiện tượng | Cách xử lý |\n|---|---|\n| Treo | Chờ 10 giây |\n"
    html = manual_book.render_markdown(source)
    assert "<thead><tr><th>Hiện tượng</th><th>Cách xử lý</th></tr></thead>" in html
    assert "<td>Treo</td><td>Chờ 10 giây</td>" in html
    assert "---" not in html


def test_render_markdown_ba_loai_khoi_nhan_manh():
    html = manual_book.render_markdown("> [!meo]\n> Gõ 2 ký tự là có gợi ý.\n")
    assert '<div class="callout callout-meo"><b>Mẹo</b>' in html
    assert "Gõ 2 ký tự là có gợi ý." in html
    assert manual_book.CALLOUT_LABELS["luuy"] == "Lưu ý"
    assert manual_book.CALLOUT_LABELS["loi"] == "Gặp lỗi thì sao"


def test_render_markdown_khong_cho_html_tho():
    html = manual_book.render_markdown("<script>alert(1)</script>\n")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_strip_html_tra_ve_van_ban_thuan():
    assert manual_book.strip_html("<p>Xin <strong>chào</strong></p>") == "Xin chào"
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -v
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'wfx_panel.manual_book'`.

- [ ] **Step 3: Viết `wfx_panel/manual_book.py`**

```python
"""Đọc và dựng nội dung hướng dẫn sử dụng WFX Smart.

Module này cố ý không biết gì về pywebview hay UI: nó chỉ biến file
Markdown + manifest trong wfx_panel/manual/ thành cấu trúc dữ liệu đã dựng
sẵn HTML. Nhờ vậy test chạy được mà không cần cửa sổ, và cả bộ sinh tài liệu
docs/USER_FEATURES.md lẫn cửa sổ Manual đều dùng chung một nguồn.
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata

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
```

- [ ] **Step 4: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

Kỳ vọng: 8 PASS.

- [ ] **Step 5: Chạy ruff**

```bash
ruff check wfx_panel/manual_book.py tests/test_manual.py
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual_book.py tests/test_manual.py
git commit -m "feat: bộ dựng Markdown cho hướng dẫn sử dụng

Dựng tập con Markdown (tiêu đề, danh sách, bảng, ba khối nhấn mạnh) ở phía
Python để cửa sổ Manual không cần thư viện JavaScript ngoài. Escape luôn chạy
trước khi áp định dạng nên file .md không thể chèn HTML thô.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Manifest và bộ nạp sách

**Files:**
- Modify: `wfx_panel/manual_book.py`
- Create: `wfx_panel/manual/manifest.json`
- Create: `wfx_panel/manual/01-bat-dau/mo-panel.md`
- Create: `wfx_panel/manual/01-bat-dau/dang-nhap.md`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `render_markdown`, `strip_html`, `slugify` (Task 1)
- Produces:
  - `MANUAL_DIR: Path`
  - `FORBIDDEN_WORDS: tuple[str, ...]`
  - `load_manifest() -> dict`
  - `load_book() -> dict` với khoá `version`, `chapters`, `entries`, `order`, `error_table`, `whats_new`
  - Ngoại lệ `ManualContentError(Exception)`

Cấu trúc `load_book()` trả về, các task sau phụ thuộc chính xác vào nó:

```python
{
  "version": "1.0.17",
  "chapters": [
      {"id": "bat-dau", "title": "Bắt đầu", "summary": "...",
       "entries": ["bat-dau-mo-panel", "bat-dau-dang-nhap"]},
  ],
  "entries": {
      "bat-dau-mo-panel": {
          "id": "bat-dau-mo-panel",
          "chapter": "bat-dau",
          "chapter_title": "Bắt đầu",
          "title": "Mở và đóng panel",
          "summary": "...",
          "keywords": ["hotkey", "phím tắt"],
          "html": "<h2 id=...>...",
          "text": "văn bản thuần để tìm kiếm",
          "covers": {"modules": [], "actions": [], "settings": ["hotkey"],
                     "errors": []},
      },
  },
  "order": ["bat-dau-mo-panel", "bat-dau-dang-nhap"],
  "error_table": [],
  "whats_new": [],
}
```

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_manual.py`:

```python
import json

import pytest


def test_manifest_ton_tai_va_dung_cau_truc():
    manifest = manual_book.load_manifest()
    assert isinstance(manifest["chapters"], list)
    for chapter in manifest["chapters"]:
        assert chapter["id"] and chapter["title"]
        for entry in chapter["entries"]:
            assert entry["id"] and entry["title"] and entry["file"]
            assert isinstance(entry.get("keywords", []), list)
            covers = entry.get("covers", {})
            for key in ("modules", "actions", "settings", "errors"):
                assert isinstance(covers.get(key, []), list), key


def test_moi_file_trong_manifest_deu_ton_tai():
    manifest = manual_book.load_manifest()
    for chapter in manifest["chapters"]:
        for entry in chapter["entries"]:
            path = manual_book.MANUAL_DIR / entry["file"]
            assert path.is_file(), entry["file"]


def test_khong_co_file_md_mo_coi():
    manifest = manual_book.load_manifest()
    declared = {
        entry["file"].replace("\\", "/")
        for chapter in manifest["chapters"]
        for entry in chapter["entries"]
    }
    on_disk = {
        path.relative_to(manual_book.MANUAL_DIR).as_posix()
        for path in manual_book.MANUAL_DIR.rglob("*.md")
    }
    assert on_disk == declared


def test_id_muc_la_duy_nhat():
    manifest = manual_book.load_manifest()
    ids = [
        entry["id"]
        for chapter in manifest["chapters"]
        for entry in chapter["entries"]
    ]
    assert len(ids) == len(set(ids))


def test_noi_dung_khong_chua_tu_cam_va_khong_bo_trong():
    for path in manual_book.MANUAL_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for word in manual_book.FORBIDDEN_WORDS:
            assert word.lower() not in lowered, f"{path.name} chứa '{word}'"
        for placeholder in ("todo", "tbd", "chưa viết"):
            assert placeholder not in lowered, f"{path.name} còn '{placeholder}'"
        assert "<" not in text, f"{path.name} có HTML thô"


def test_moi_muc_co_du_hai_phan_bat_buoc():
    for path in manual_book.MANUAL_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "## Dùng để làm gì" in text, path.name
        assert "## Các bước" in text, path.name


def test_load_book_dung_html_va_van_ban_tim_kiem():
    book = manual_book.load_book()
    assert book["version"]
    assert book["order"]
    first = book["entries"][book["order"][0]]
    assert first["html"].startswith("<")
    assert first["text"] and "<" not in first["text"]
    assert first["chapter_title"]


def test_load_book_bao_loi_khi_thieu_file(tmp_path, monkeypatch):
    monkeypatch.setattr(manual_book, "MANUAL_DIR", tmp_path)
    (tmp_path / "manifest.json").write_text(
        json.dumps({"chapters": [{"id": "x", "title": "X", "entries": [
            {"id": "x-1", "title": "Một", "file": "khong-co.md"}
        ]}]}),
        encoding="utf-8",
    )
    with pytest.raises(manual_book.ManualContentError):
        manual_book.load_book()
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -v
```

Kỳ vọng: 8 test mới FAIL với `AttributeError: module 'wfx_panel.manual_book' has no attribute 'load_manifest'`.

- [ ] **Step 3: Thêm bộ nạp vào `wfx_panel/manual_book.py`**

Thêm import ở đầu file:

```python
import json
from pathlib import Path

from wfx_panel import prefs
from wfx_panel.version import APP_VERSION
```

Thêm hằng và hàm vào cuối file:

```python
MANUAL_DIR = prefs.RESOURCE_DIR / "wfx_panel" / "manual"

FORBIDDEN_WORDS = (
    "frame", "selector", "CDP", "postback", "iframe",
    "XPath", "DOM", "endpoint", "payload", "token", "grid",
)

_COVER_KEYS = ("modules", "actions", "settings", "errors")


class ManualContentError(Exception):
    """Nội dung manual không hợp lệ — thiếu file, sai khoá, hoặc trùng id."""


def load_manifest() -> dict:
    path = MANUAL_DIR / "manifest.json"
    if not path.is_file():
        raise ManualContentError(f"Thiếu {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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
        "error_table": [],
        "whats_new": [],
    }
```

- [ ] **Step 4: Tạo `wfx_panel/manual/manifest.json`**

```json
{
  "chapters": [
    {
      "id": "bat-dau",
      "title": "Bắt đầu",
      "summary": "Cài đặt, mở ứng dụng và kết nối tài khoản WFX.",
      "entries": [
        {
          "id": "bat-dau-mo-panel",
          "title": "Mở và đóng bảng điều khiển",
          "summary": "Ba cách gọi WFX Smart ra màn hình.",
          "file": "01-bat-dau/mo-panel.md",
          "keywords": ["hotkey", "phím tắt", "khay hệ thống", "bong bóng"],
          "covers": { "settings": ["hotkey", "start-hidden-input"] }
        },
        {
          "id": "bat-dau-dang-nhap",
          "title": "Đăng nhập tài khoản WFX",
          "summary": "Lưu tài khoản một lần, ứng dụng tự giữ phiên.",
          "file": "01-bat-dau/dang-nhap.md",
          "keywords": ["tài khoản", "mật khẩu", "user id", "đăng nhập"],
          "covers": { "errors": ["LOGIN_FAILED", "LOGIN_TIMEOUT"] }
        }
      ]
    }
  ]
}
```

- [ ] **Step 5: Tạo `wfx_panel/manual/01-bat-dau/mo-panel.md`**

```markdown
## Dùng để làm gì

WFX Smart nằm sẵn bên cạnh trình duyệt để bạn gọi ra bất cứ lúc nào mà không
phải tìm trong Start Menu.

## Các bước

1. Nhấn tổ hợp phím `Ctrl + Shift + X` ở bất kỳ đâu, kể cả khi bạn đang làm
   việc trong màn hình WFX trên trình duyệt.
2. Bảng điều khiển hiện ra ở mép phải màn hình.
3. Nhấn lại tổ hợp đó, hoặc bấm nút dấu nhân ở góc trên, để thu bảng lại.

Hai cách gọi khác:

- Bấm vào biểu tượng tròn nhỏ luôn nổi trên màn hình.
- Bấm đúp vào biểu tượng WFX Smart ở khay hệ thống, cạnh đồng hồ Windows.

## Mẹo

> [!meo]
> Bảng điều khiển tự thu lại khi bạn bấm sang cửa sổ khác. Nếu một tác vụ đang
> chạy, bảng chờ tác vụ xong mới thu.

> [!meo]
> Đổi tổ hợp phím trong Cài đặt, thẻ Tự động hóa, dòng Hotkey mở panel.

> [!luuy]
> Bật Mở ẩn trong tray nếu bạn muốn ứng dụng khởi động yên lặng cùng Windows và
> chỉ hiện khi được gọi.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Nhấn phím tắt không thấy gì | Cửa sổ đang dùng chạy quyền quản trị cao hơn ứng dụng. Bấm biểu tượng tròn nổi hoặc biểu tượng ở khay hệ thống. |
| Không thấy biểu tượng ở khay | Bấm mũi tên mở rộng cạnh đồng hồ Windows để xem các biểu tượng bị ẩn. |
```

- [ ] **Step 6: Tạo `wfx_panel/manual/01-bat-dau/dang-nhap.md`**

```markdown
## Dùng để làm gì

Lưu tài khoản WFX một lần để ứng dụng tự đăng nhập và tự giữ phiên, bạn không
phải nhập lại mỗi ngày.

## Các bước

1. Bấm biểu tượng bánh răng ở góc trên bảng điều khiển.
2. Chọn thẻ Tài khoản.
3. Nhập Tên đăng nhập WFX và Mật khẩu.
4. Bấm `Lưu và đăng nhập WFX`.
5. Chờ dòng trạng thái dưới cùng báo đã kết nối.

## Mẹo

> [!meo]
> Sau lần đăng nhập đầu tiên, ứng dụng tự kiểm tra và duy trì phiên mỗi bốn
> phút khi trình duyệt đang rảnh. Bạn gần như không bao giờ phải nhập lại.

> [!luuy]
> Mật khẩu được mã hoá và lưu riêng trên máy này, không hiển thị lại và không
> được gửi đi đâu.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Ứng dụng mở lại màn hình nhập tài khoản | WFX đã từ chối phiên cũ. Nhập lại mật khẩu rồi bấm lưu. |
| Báo chưa có trình duyệt | Bấm `Mở trình duyệt` trên dải thông báo màu ở đầu bảng điều khiển. |
```

- [ ] **Step 7: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

Kỳ vọng: toàn bộ PASS.

- [ ] **Step 8: Commit**

```bash
git add wfx_panel/manual_book.py wfx_panel/manual tests/test_manual.py
git commit -m "feat: manifest và bộ nạp nội dung hướng dẫn

Thêm wfx_panel/manual/ với manifest khai báo chương, mục, từ khoá và phần
tính năng mà mục đó phủ. Bộ nạp kiểm tra thiếu file, trùng id, file mồ côi,
từ cấm và hai phần bắt buộc của mỗi mục.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Chỉ mục tìm kiếm, bảng mã lỗi và Có gì mới

**Files:**
- Modify: `wfx_panel/manual_book.py`
- Create: `wfx_panel/manual/whats_new.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `load_book`, `strip_html` (Task 2)
- Produces:
  - `build_error_table(entries: dict) -> list[dict]` — mỗi phần tử `{"code", "title", "suggestion", "entry"}`, `entry` là `str` hoặc `None`
  - `load_whats_new() -> list[dict]`
  - `build_search_index(entries: dict) -> list[dict]` — mỗi phần tử `{"id", "title", "chapter_title", "haystack"}`
  - `load_book()` từ Task 2 nay điền thật ba khoá `error_table`, `whats_new`, và thêm khoá `search_index`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_manual.py`:

```python
from wfx_panel import telemetry
from wfx_panel.version import APP_VERSION


def test_bang_ma_loi_phu_het_error_code_info():
    book = manual_book.load_book()
    codes = {row["code"] for row in book["error_table"]}
    assert codes == set(telemetry.ERROR_CODE_INFO)
    for row in book["error_table"]:
        title, suggestion = telemetry.ERROR_CODE_INFO[row["code"]]
        assert row["title"] == title
        assert row["suggestion"] == suggestion


def test_bang_ma_loi_tro_ve_muc_da_khai_bao_phu():
    book = manual_book.load_book()
    rows = {row["code"]: row["entry"] for row in book["error_table"]}
    assert rows["LOGIN_FAILED"] == "bat-dau-dang-nhap"


def test_whats_new_co_muc_cho_phien_ban_hien_tai():
    versions = {item["version"] for item in manual_book.load_whats_new()}
    assert APP_VERSION in versions, (
        f"whats_new.json thiếu mục cho phiên bản {APP_VERSION}"
    )


def test_whats_new_tham_chieu_muc_co_that():
    book = manual_book.load_book()
    for release in book["whats_new"]:
        for highlight in release["highlights"]:
            entry_id = highlight.get("entry")
            if entry_id:
                assert entry_id in book["entries"], entry_id


def test_chi_muc_tim_kiem_gom_tieu_de_tu_khoa_va_noi_dung():
    book = manual_book.load_book()
    row = next(
        item for item in book["search_index"] if item["id"] == "bat-dau-mo-panel"
    )
    assert "hotkey" in row["haystack"]
    assert "ctrl + shift + x" in row["haystack"]
    assert row["haystack"] == row["haystack"].lower()
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -v
```

Kỳ vọng: 5 test mới FAIL.

- [ ] **Step 3: Bổ sung `wfx_panel/manual_book.py`**

Thêm import:

```python
from wfx_panel import telemetry
```

Thêm hàm:

```python
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
```

Sửa phần `return` của `load_book()` thành:

```python
    return {
        "version": APP_VERSION,
        "chapters": chapters,
        "entries": entries,
        "order": order,
        "error_table": build_error_table(entries),
        "search_index": build_search_index(entries),
        "whats_new": load_whats_new(),
    }
```

- [ ] **Step 4: Tạo `wfx_panel/manual/whats_new.json`**

```json
[
  {
    "version": "1.0.17",
    "date": "2026-08-01",
    "highlights": [
      {
        "title": "Hướng dẫn sử dụng ngay trong ứng dụng",
        "body": "Bấm biểu tượng quyển sách ở góc trên để tra cứu mọi tính năng, không cần mạng.",
        "entry": "bat-dau-mo-panel"
      }
    ]
  }
]
```

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v && ruff check wfx_panel tests
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual_book.py wfx_panel/manual/whats_new.json tests/test_manual.py
git commit -m "feat: bảng tra mã lỗi, chỉ mục tìm kiếm và Có gì mới

Bảng mã lỗi đọc thẳng telemetry.ERROR_CODE_INFO nên mã mới tự xuất hiện.
whats_new.json bắt buộc có mục cho phiên bản hiện tại, phát hành mà quên ghi
thay đổi thì test đỏ.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Helper trích nguồn sự thật từ UI

**Files:**
- Create: `tests/_manual_surface.py`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: không có
- Produces (dùng ở Giai đoạn 3):
  - `module_ids() -> set[str]`
  - `module_actions() -> set[str]`
  - `catalog_actions() -> set[str]`
  - `costing_actions() -> set[str]`
  - `settings_controls() -> set[str]`
  - `covered(kind: str) -> set[str]` — hợp của mọi `covers[kind]` trong manifest

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_manual.py`:

```python
from tests import _manual_surface as surface


def test_helper_trich_dung_so_luong_hien_co():
    assert len(surface.module_ids()) == 16
    assert "0003_6200" in surface.module_ids()
    assert len(surface.module_actions()) == 29
    assert surface.catalog_actions() == {
        "browse", "find", "costsheet", "bom", "files", "refresh-folders",
    }
    assert surface.costing_actions() == {
        "export-xlsx", "validate-file", "import", "apply",
        "cancel-plan", "clear-dependencies",
    }
    assert surface.settings_controls() == {
        "return-list-input", "focus-chrome-input", "open-costing-file-input",
        "autostart-input", "start-hidden-input", "admin-mode-input",
        "always-on-top-input", "toast-input", "hotkey", "theme",
    }


def test_helper_doc_duoc_khai_bao_phu():
    assert "hotkey" in surface.covered("settings")
    assert "MISSING_CREDENTIALS" in surface.covered("errors")
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k helper -v
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'tests._manual_surface'`.

- [ ] **Step 3: Viết `tests/_manual_surface.py`**

```python
"""Trích danh sách tính năng đang có từ chính file nguồn giao diện.

Đây là helper CHỈ dùng cho test: nó đọc panel.js và index.html bằng biểu thức
chính quy, cùng kiểu với tests/test_panel_js.py và tests/test_ui_assets.py.
Nhờ vậy thêm module hoặc thêm nút mới mà quên viết manual là test đỏ ngay.
"""

from __future__ import annotations

import re
from pathlib import Path

from wfx_panel import manual_book

_UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
_JS = (_UI / "panel.js").read_text(encoding="utf-8")
_HTML = (_UI / "index.html").read_text(encoding="utf-8")

_MODULE_ID = re.compile(r'\{ name: "[^"]+", id: "([^"]+)"')
_SETTINGS_PANEL = re.compile(
    r'<section class="settings-panel settings-(?:automation|appearance)-panel.*?</section>',
    re.S,
)
_INPUT_CLASS = re.compile(r'class="([a-z-]+-input)"')


def _action(prefix: str) -> set[str]:
    return set(re.findall(rf'data-{prefix}-action="([a-z0-9-]+)"', _HTML))


def module_ids() -> set[str]:
    return set(_MODULE_ID.findall(_JS))


def module_actions() -> set[str]:
    return _action("module")


def catalog_actions() -> set[str]:
    return _action("catalog")


def costing_actions() -> set[str]:
    return _action("costing")


def settings_controls() -> set[str]:
    controls: set[str] = set()
    for block in _SETTINGS_PANEL.findall(_HTML):
        controls.update(_INPUT_CLASS.findall(block))
    # Hai điều khiển không phải checkbox, phủ bằng id quy ước.
    controls.update({"hotkey", "theme"})
    return controls


def covered(kind: str) -> set[str]:
    manifest = manual_book.load_manifest()
    values: set[str] = set()
    for chapter in manifest["chapters"]:
        for entry in chapter["entries"]:
            values.update(entry.get("covers", {}).get(kind, []))
    return values
```

- [ ] **Step 4: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v && ruff check tests
```

Nếu số đếm lệch với `16` / `29`, **không** sửa con số trong test một cách tuỳ tiện — mở `panel.js` và `index.html` xác minh số thật rồi mới cập nhật, kèm ghi chú lý do trong commit.

- [ ] **Step 5: Commit**

```bash
git add tests/_manual_surface.py tests/test_manual.py
git commit -m "test: helper trích danh sách tính năng từ nguồn giao diện

Đọc module, nút thao tác và công tắc cài đặt thẳng từ panel.js và index.html
để các kiểm tra phủ ở giai đoạn sau đối chiếu được với thực tế sản phẩm.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# GIAI ĐOẠN 2 — Cửa sổ tra cứu

### Task 5: Khung cửa sổ Manual

**Files:**
- Create: `wfx_panel/ui/manual.html`
- Create: `wfx_panel/ui/manual.css`
- Create: `wfx_panel/ui/manual.js`
- Test: `tests/test_ui_assets.py`

**Interfaces:**
- Consumes: hình dạng dữ liệu của `load_book()` (Task 2, 3)
- Produces:
  - `window.wfxManualGoTo(target: string)` — điều hướng tới mục hoặc mã lỗi, dùng ở Task 6 và Giai đoạn 4
  - Các class DOM: `.manual-search`, `.manual-toc`, `.manual-content`, `.manual-home`, `.manual-results`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_ui_assets.py`:

```python
def test_manual_window_co_du_ba_vung_chinh():
    html = (UI / "manual.html").read_text(encoding="utf-8")
    assert 'class="manual-search"' in html
    assert 'class="manual-toc"' in html
    assert 'class="manual-content"' in html
    assert "manual.css" in html
    assert "manual.js" in html
    # Manual chạy offline: không được nạp tài nguyên từ mạng.
    assert "http://" not in html
    assert "https://" not in html


def test_manual_css_co_token_rieng_va_ban_in():
    css = (UI / "manual.css").read_text(encoding="utf-8")
    assert ":root {" in css
    assert ':root[data-theme="dark"]' in css
    assert "@media print" in css
    assert ".callout-meo" in css
    assert ".callout-luuy" in css
    assert ".callout-loi" in css


def test_manual_js_phoi_bay_ham_dieu_huong():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "window.wfxManualGoTo" in js
    assert "get_manual_book" in js
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_ui_assets.py -k manual -v
```

Kỳ vọng: FAIL — `FileNotFoundError: ... manual.html`.

- [ ] **Step 3: Tạo `wfx_panel/ui/manual.html`**

```html
<!doctype html>
<html lang="vi" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFX Smart · Hướng dẫn sử dụng</title>
  <link rel="stylesheet" href="manual.css?v=20260801-1">
</head>
<body>
  <div class="manual-shell">
    <aside class="manual-side">
      <label class="manual-search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
        <input type="search" aria-label="Tìm trong hướng dẫn" placeholder="Tìm nội dung, tên nút, mã lỗi..." autocomplete="off">
      </label>
      <nav class="manual-toc" aria-label="Mục lục hướng dẫn"></nav>
      <div class="manual-results" hidden aria-label="Kết quả tìm kiếm"></div>
    </aside>
    <main class="manual-main">
      <div class="manual-home"></div>
      <article class="manual-content" hidden></article>
      <footer class="manual-foot">
        <button class="manual-prev" type="button">‹ Mục trước</button>
        <span class="manual-version"></span>
        <button class="manual-next" type="button">Mục sau ›</button>
      </footer>
    </main>
  </div>
  <script src="manual.js?v=20260801-1"></script>
</body>
</html>
```

- [ ] **Step 4: Tạo `wfx_panel/ui/manual.css`**

Token màu sao chép nguyên văn từ `wfx_panel/ui/style.css` dòng 82–118. Cố ý **không** dùng lại `style.css` vì file đó có `all: initial` và các override chỉ đúng cho panel.

```css
:root {
  color-scheme: light;
  --bg: #eef2f5; --panel-bg: #f7fafb;
  --surface: #ffffff; --surface-2: #eef3f6; --surface-3: rgba(15,45,60,.05);
  --border: rgba(15,45,60,.12); --border-strong: rgba(15,45,60,.2);
  --text: #10242f; --text-2: #46606b; --text-3: #6b828d;
  --accent: #0a94ae; --accent-strong: #0b7c93;
  --accent-soft: rgba(12,148,174,.1); --accent-border: rgba(12,148,174,.32);
  --good: #0f9d68; --good-soft: rgba(18,168,110,.12);
  --warn: #b9741a; --warn-soft: rgba(200,130,20,.14);
  --bad: #cf3f57; --bad-soft: rgba(208,66,90,.12);
  --mark: rgba(255,214,102,.55);
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #08141d; --panel-bg: #08141d;
  --surface: rgba(20,44,58,.72); --surface-2: #102a37; --surface-3: rgba(255,255,255,.035);
  --border: rgba(255,255,255,.08); --border-strong: rgba(255,255,255,.14);
  --text: #e9f4f8; --text-2: #a3b8c0; --text-3: #7d949e;
  --accent: #64deef; --accent-strong: #7ee5f2;
  --accent-soft: rgba(58,192,211,.1); --accent-border: rgba(102,222,239,.3);
  --good: #36e6a1; --good-soft: rgba(54,208,155,.1);
  --warn: #ffc36d; --warn-soft: rgba(255,188,91,.1);
  --bad: #ff6e7d; --bad-soft: rgba(255,86,105,.1);
  --mark: rgba(255,205,90,.34);
}

* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.65 "Segoe UI", system-ui, sans-serif; }

.manual-shell { display: grid; grid-template-columns: 264px 1fr; height: 100%; }

.manual-side { display: flex; flex-direction: column; min-height: 0;
  border-right: 1px solid var(--border); background: var(--panel-bg); }
.manual-search { display: flex; align-items: center; gap: 8px; margin: 12px;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface); }
.manual-search svg { width: 16px; flex: 0 0 auto; fill: none;
  stroke: var(--text-3); stroke-width: 1.8; }
.manual-search input { width: 100%; border: 0; outline: 0; background: none;
  color: var(--text); font: inherit; }
.manual-toc, .manual-results { flex: 1; min-height: 0; overflow-y: auto;
  padding: 0 8px 16px; }

.manual-chapter { margin-top: 10px; padding: 0 6px; color: var(--text-3);
  font-size: 11px; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase; }
.manual-link { display: block; width: 100%; padding: 7px 10px; margin-top: 2px;
  border: 0; border-radius: 8px; background: none; color: var(--text-2);
  font: inherit; text-align: left; cursor: pointer; }
.manual-link:hover { background: var(--surface-3); color: var(--text); }
.manual-link[aria-current="true"] { background: var(--accent-soft);
  color: var(--accent-strong); font-weight: 600; }
.manual-hit small { display: block; color: var(--text-3); font-size: 12px; }
.manual-hit mark { background: var(--mark); color: inherit; border-radius: 3px; }

.manual-main { display: flex; flex-direction: column; min-height: 0; }
.manual-home, .manual-content { flex: 1; min-height: 0; overflow-y: auto;
  padding: 26px 34px 40px; }
.manual-content { max-width: 760px; }

.manual-cards { display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.manual-card { padding: 14px 16px; border: 1px solid var(--border);
  border-radius: 12px; background: var(--surface); text-align: left;
  color: var(--text); font: inherit; cursor: pointer; }
.manual-card:hover { border-color: var(--accent-border);
  background: var(--accent-soft); }
.manual-card strong { display: block; margin-bottom: 4px; }
.manual-card span { color: var(--text-3); font-size: 13px; }
.manual-news { margin-bottom: 20px; padding: 16px 18px;
  border: 1px solid var(--accent-border); border-radius: 14px;
  background: var(--accent-soft); }

.manual-content h1 { margin: 0 0 4px; font-size: 25px; }
.manual-crumb { margin-bottom: 18px; color: var(--text-3); font-size: 13px; }
.manual-content h2 { margin: 26px 0 8px; color: var(--accent-strong);
  font-size: 12px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; }
.manual-content ol, .manual-content ul { padding-left: 22px; }
.manual-content li { margin: 4px 0; }
.manual-content table { width: 100%; margin: 10px 0; border-collapse: collapse; }
.manual-content th, .manual-content td { padding: 8px 10px; text-align: left;
  border: 1px solid var(--border); font-size: 14px; }
.manual-content th { background: var(--surface-2); }
.ui-label { padding: 1px 7px; border: 1px solid var(--border-strong);
  border-radius: 6px; background: var(--surface-2); font-weight: 600;
  font-size: 13px; }

.callout { margin: 12px 0; padding: 11px 14px; border-left: 3px solid;
  border-radius: 0 10px 10px 0; }
.callout b { display: block; margin-bottom: 3px; font-size: 12px;
  letter-spacing: .06em; text-transform: uppercase; }
.callout p { margin: 3px 0; }
.callout-meo { border-color: var(--good); background: var(--good-soft); }
.callout-meo b { color: var(--good); }
.callout-luuy { border-color: var(--warn); background: var(--warn-soft); }
.callout-luuy b { color: var(--warn); }
.callout-loi { border-color: var(--bad); background: var(--bad-soft); }
.callout-loi b { color: var(--bad); }

.manual-foot { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 34px; border-top: 1px solid var(--border);
  background: var(--panel-bg); color: var(--text-3); font-size: 13px; }
.manual-foot button { padding: 5px 12px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--surface); color: var(--text-2);
  font: inherit; cursor: pointer; }
.manual-foot button:disabled { opacity: .4; cursor: default; }

@media print {
  .manual-side, .manual-foot { display: none; }
  .manual-shell { display: block; }
  .manual-home, .manual-content { overflow: visible; padding: 0; max-width: none; }
  body { background: #fff; color: #000; }
}
```

- [ ] **Step 5: Tạo `wfx_panel/ui/manual.js`**

```javascript
"use strict";
(() => {
  const $ = (selector) => document.querySelector(selector);
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const escapeHtml = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  let book = null;
  let currentId = null;

  function renderToc() {
    $(".manual-toc").innerHTML = book.chapters.map((chapter) => {
      const links = chapter.entries.map((id) => {
        const entry = book.entries[id];
        return `<button class="manual-link" data-entry="${escapeHtml(id)}">`
          + `${escapeHtml(entry.title)}</button>`;
      }).join("");
      return `<div class="manual-chapter">${escapeHtml(chapter.title)}</div>${links}`;
    }).join("");
  }

  function renderHome() {
    const news = book.whats_new[0];
    const newsHtml = news
      ? `<section class="manual-news"><strong>Có gì mới trong bản ${
          escapeHtml(news.version)}</strong>${news.highlights.map((item) =>
          `<p><b>${escapeHtml(item.title)}</b> — ${escapeHtml(item.body)}</p>`
        ).join("")}</section>`
      : "";
    const cards = book.chapters.map((chapter) =>
      `<button class="manual-card" data-entry="${escapeHtml(chapter.entries[0])}">`
      + `<strong>${escapeHtml(chapter.title)}</strong>`
      + `<span>${escapeHtml(chapter.summary)}</span></button>`
    ).join("");
    $(".manual-home").innerHTML =
      `<h1>Hướng dẫn sử dụng WFX Smart</h1>`
      + `<p class="manual-crumb">Chọn một phần bên dưới, hoặc gõ vào ô tìm kiếm.</p>`
      + newsHtml
      + `<div class="manual-cards">${cards}</div>`;
  }

  function showEntry(entryId) {
    const entry = book.entries[entryId];
    if (!entry) return;
    currentId = entryId;
    $(".manual-home").hidden = true;
    $(".manual-content").hidden = false;
    $(".manual-content").innerHTML =
      `<p class="manual-crumb">${escapeHtml(entry.chapter_title)}</p>`
      + `<h1>${escapeHtml(entry.title)}</h1>${entry.html}`;
    $(".manual-content").scrollTop = 0;
    document.querySelectorAll(".manual-link").forEach((link) => {
      link.setAttribute("aria-current", String(link.dataset.entry === entryId));
    });
    syncNav();
  }

  function showHome() {
    currentId = null;
    $(".manual-content").hidden = true;
    $(".manual-home").hidden = false;
    syncNav();
  }

  function syncNav() {
    const position = book.order.indexOf(currentId);
    $(".manual-prev").disabled = position <= 0;
    $(".manual-next").disabled = position < 0 || position >= book.order.length - 1;
  }

  function snippet(entry, needle) {
    const text = entry.text;
    const at = text.toLowerCase().indexOf(needle);
    if (at < 0) return escapeHtml(entry.summary);
    const from = Math.max(0, at - 40);
    const raw = text.slice(from, from + 120);
    return escapeHtml(raw).replace(
      new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
      (hit) => `<mark>${hit}</mark>`
    );
  }

  function search(query) {
    const needle = query.trim().toLowerCase();
    const results = $(".manual-results");
    if (needle.length < 2) {
      results.hidden = true;
      $(".manual-toc").hidden = false;
      return;
    }
    const hits = book.search_index
      .filter((row) => row.haystack.includes(needle))
      .slice(0, 40);
    results.innerHTML = hits.length
      ? hits.map((hit) => {
          const entry = book.entries[hit.id];
          return `<button class="manual-link manual-hit" data-entry="${
            escapeHtml(hit.id)}"><b>${escapeHtml(entry.title)}</b>`
            + `<small>${snippet(entry, needle)}</small></button>`;
        }).join("")
      : `<p class="manual-chapter">Không tìm thấy nội dung phù hợp.</p>`;
    results.hidden = false;
    $(".manual-toc").hidden = true;
  }

  window.wfxManualGoTo = (target) => {
    if (!book || !target) { if (book) showHome(); return; }
    if (book.entries[target]) { showEntry(target); return; }
    const row = book.error_table.find((item) => item.code === target);
    if (row && row.entry) { showEntry(row.entry); return; }
    showHome();
  };

  async function bootstrap() {
    const bridge = api();
    if (!bridge) { setTimeout(bootstrap, 120); return; }
    book = await bridge.get_manual_book();
    document.documentElement.dataset.theme = book.theme === "dark" ? "dark" : "light";
    $(".manual-version").textContent = `WFX Smart ${book.version}`;
    renderToc();
    renderHome();
    window.wfxManualGoTo(book.target || "");
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-entry]");
    if (link) showEntry(link.dataset.entry);
  });
  $(".manual-search input").addEventListener("input",
    (event) => search(event.target.value));
  $(".manual-prev").addEventListener("click",
    () => showEntry(book.order[book.order.indexOf(currentId) - 1]));
  $(".manual-next").addEventListener("click",
    () => showEntry(book.order[book.order.indexOf(currentId) + 1]));
  window.addEventListener("keydown", (event) => {
    const input = $(".manual-search input");
    if (event.ctrlKey && event.key.toLowerCase() === "f") {
      event.preventDefault(); input.focus(); input.select(); return;
    }
    if (event.key === "Escape") {
      if (input.value) { input.value = ""; search(""); }
      else api()?.close_manual?.();
      return;
    }
    if (document.activeElement === input) return;
    if (event.key === "ArrowLeft" && !$(".manual-prev").disabled) $(".manual-prev").click();
    if (event.key === "ArrowRight" && !$(".manual-next").disabled) $(".manual-next").click();
  });

  window.addEventListener("pywebviewready", bootstrap);
  bootstrap();
})();
```

- [ ] **Step 6: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_ui_assets.py -v
```

- [ ] **Step 7: Commit**

```bash
git add wfx_panel/ui/manual.html wfx_panel/ui/manual.css wfx_panel/ui/manual.js tests/test_ui_assets.py
git commit -m "feat: giao diện cửa sổ hướng dẫn sử dụng

Bố cục hai cột với mục lục, tìm kiếm tô từ khoá, ba loại khối nhấn mạnh và
CSS bản in. Token màu độc lập với style.css vì file đó có all: initial chỉ
đúng cho panel.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Mở cửa sổ Manual từ nút top nav

**Files:**
- Modify: `wfx_panel/panel_app.py` (dòng 83–90 vùng hằng, dòng 340 vùng bridge, dòng 1217 `open_wfx_manual`)
- Test: `tests/test_panel_app.py` (thay `test_wfx_manual_opens_the_configured_url` ở dòng 1620)

**Interfaces:**
- Consumes: `manual_book.load_book()` (Task 3), `window.wfxManualGoTo` (Task 5)
- Produces:
  - `PanelApp.open_wfx_manual(target: str = "") -> dict` — mã trả về `MANUAL_OPENED`, `MANUAL_FOCUSED`, `MANUAL_OPEN_FAILED`
  - `PanelApp.manual_window` — `None` khi chưa mở hoặc đã đóng
  - `_ManualBridge.get_manual_book() -> dict`, `.open_manual_external() -> dict`, `.close_manual() -> dict`

- [ ] **Step 1: Viết test thất bại**

Thay hàm `test_wfx_manual_opens_the_configured_url` trong `tests/test_panel_app.py` bằng:

```python
class _FakeEvents:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _FakeWindow:
    def __init__(self, title, url, **kwargs):
        self.title = title
        self.url = url
        self.kwargs = kwargs
        self.events = type("E", (), {"closed": _FakeEvents()})()
        self.shown = 0
        self.scripts = []

    def show(self):
        self.shown += 1

    def evaluate_js(self, script):
        self.scripts.append(script)


def _patch_manual_window(monkeypatch, module):
    created = []

    def create_window(title, **kwargs):
        window = _FakeWindow(title, kwargs.get("url"), **kwargs)
        created.append(window)
        return window

    monkeypatch.setattr(module.webview, "create_window", create_window)
    return created


def test_wfx_manual_mo_cua_so_rieng(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    created = _patch_manual_window(monkeypatch, module)

    result = app.open_wfx_manual()

    assert result["code"] == "MANUAL_OPENED"
    assert len(created) == 1
    assert created[0].kwargs["width"] == 1000
    assert created[0].kwargs["height"] == 720
    assert str(module.MANUAL_INDEX) == created[0].url
    assert app.manual_window is created[0]


def test_wfx_manual_khong_tao_cua_so_trung(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    created = _patch_manual_window(monkeypatch, module)

    app.open_wfx_manual()
    result = app.open_wfx_manual()

    assert result["code"] == "MANUAL_FOCUSED"
    assert len(created) == 1
    assert created[0].shown == 1


def test_wfx_manual_dieu_huong_toi_muc_khi_da_mo(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    created = _patch_manual_window(monkeypatch, module)

    app.open_wfx_manual()
    app.open_wfx_manual("bat-dau-dang-nhap")

    assert any("wfxManualGoTo" in script for script in created[0].scripts)
    assert any("bat-dau-dang-nhap" in script for script in created[0].scripts)


def test_manual_bridge_tra_ve_sach_kem_theme_va_dich(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    _patch_manual_window(monkeypatch, module)
    app.open_wfx_manual("bat-dau-dang-nhap")

    payload = module._ManualBridge(app).get_manual_book()

    assert payload["entries"]["bat-dau-dang-nhap"]["title"]
    assert payload["theme"] in {"light", "dark", "system"}
    assert payload["target"] == "bat-dau-dang-nhap"
    assert payload["manual_url"] == module.WFX_MANUAL_URL


def test_manual_bridge_mo_trang_web_wfx(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    monkeypatch.setattr(
        module.webbrowser,
        "open",
        lambda url, *, new: calls.append((url, new)) or True,
    )

    result = module._ManualBridge(app).open_manual_external()

    assert result["ok"] is True
    assert calls == [(module.WFX_MANUAL_URL, 2)]
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_panel_app.py -k manual -v
```

Kỳ vọng: FAIL — `AttributeError: module 'wfx_panel.panel_app' has no attribute 'MANUAL_INDEX'`.

- [ ] **Step 3: Thêm hằng vào `wfx_panel/panel_app.py`**

Ngay dưới `BUBBLE_INDEX` (dòng 89):

```python
MANUAL_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "manual.html"
MANUAL_WINDOW_TITLE = "WFX Smart · Hướng dẫn sử dụng"
MANUAL_WINDOW_WIDTH = 1000
MANUAL_WINDOW_HEIGHT = 720
MANUAL_WINDOW_MIN = (720, 520)
```

Thêm import ở đầu file, cạnh các import `wfx_panel` khác:

```python
from wfx_panel import manual_book
```

- [ ] **Step 4: Thêm `_ManualBridge` ngay dưới `_BubbleBridge` (sau dòng 360)**

```python
class _ManualBridge:
    """Cầu nối JS cho cửa sổ Hướng dẫn sử dụng.

    Cửa sổ này hoàn toàn offline: nó chỉ đọc nội dung tĩnh đã đóng gói, không
    chạm tới Playwright, Chrome hay phiên WFX. Nhờ vậy người dùng tra cứu được
    ngay cả khi chưa đăng nhập hoặc đang mất mạng.
    """

    def __init__(self, app: PanelApp):
        self._app = app

    def get_manual_book(self) -> dict:
        return self._app.manual_payload()

    def open_manual_external(self) -> dict:
        try:
            opened = bool(webbrowser.open(WFX_MANUAL_URL, new=2))
        except Exception as error:
            return {
                "ok": False,
                "code": "MANUAL_OPEN_FAILED",
                "message": f"Không mở được trang WFX: {error}",
            }
        return {
            "ok": opened,
            "code": "MANUAL_OPENED" if opened else "MANUAL_OPEN_FAILED",
            "message": (
                "Đã mở System Manual của WFX."
                if opened
                else "Không tìm thấy trình duyệt."
            ),
        }

    def close_manual(self) -> dict:
        self._app.close_manual_window()
        return {"ok": True, "code": "MANUAL_CLOSED", "message": ""}
```

- [ ] **Step 5: Viết lại `open_wfx_manual` (thay toàn bộ hàm ở dòng 1217)**

```python
    def manual_payload(self) -> dict:
        """Nội dung sách hướng dẫn kèm theme và mục cần mở sẵn."""
        book = manual_book.load_book()
        book["theme"] = prefs.load_prefs().get("theme", "light")
        book["target"] = self._manual_target
        book["manual_url"] = WFX_MANUAL_URL
        return book

    def close_manual_window(self) -> None:
        window, self.manual_window = self.manual_window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def open_wfx_manual(self, target: str = "") -> dict:
        """Mở cửa sổ Hướng dẫn sử dụng; bấm lần hai thì đưa cửa sổ đó lên trước.

        `target` là id mục manual hoặc mã lỗi. Rỗng thì mở trang chủ hướng dẫn.
        """
        self._manual_target = str(target or "")
        if self.manual_window is not None:
            try:
                self.manual_window.show()
                if self._manual_target:
                    self.manual_window.evaluate_js(
                        f"window.wfxManualGoTo({json.dumps(self._manual_target)})"
                    )
                return {
                    "ok": True,
                    "code": "MANUAL_FOCUSED",
                    "message": "Cửa sổ hướng dẫn đang mở.",
                }
            except Exception:
                self.manual_window = None
        try:
            window = webview.create_window(
                MANUAL_WINDOW_TITLE,
                url=str(MANUAL_INDEX),
                js_api=_ManualBridge(self),
                width=MANUAL_WINDOW_WIDTH,
                height=MANUAL_WINDOW_HEIGHT,
                min_size=MANUAL_WINDOW_MIN,
                resizable=True,
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "MANUAL_OPEN_FAILED",
                "message": f"Không mở được hướng dẫn: {error}",
            }
        self.manual_window = window
        try:
            window.events.closed += self._on_manual_closed
        except Exception:
            pass
        return {
            "ok": True,
            "code": "MANUAL_OPENED",
            "message": "Đã mở hướng dẫn sử dụng.",
        }

    def _on_manual_closed(self) -> None:
        self.manual_window = None
```

- [ ] **Step 6: Khởi tạo hai thuộc tính trong `PanelApp.__init__`**

Đặt cạnh `self.bubble_window`:

```python
        self.manual_window = None
        self._manual_target = ""
```

Kiểm tra `import json` đã có ở đầu `panel_app.py`; nếu chưa thì thêm.

- [ ] **Step 7: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_panel_app.py -v && ruff check wfx_panel tests
```

- [ ] **Step 8: Kiểm tra thủ công**

```bash
python app.py
```

Bấm nút quyển sách ở góc trên. Xác nhận: cửa sổ hướng dẫn mở, mục lục hiện hai mục, gõ `hotkey` vào ô tìm ra kết quả có tô vàng, bấm nút Manual lần nữa không tạo cửa sổ thứ hai, đóng cửa sổ rồi bấm lại thì mở được.

- [ ] **Step 9: Commit**

```bash
git add wfx_panel/panel_app.py tests/test_panel_app.py
git commit -m "feat: nút Manual mở cửa sổ hướng dẫn trong ứng dụng

Thay việc mở URL ngoài bằng một cửa sổ pywebview riêng 1000x720 đọc nội dung
đã đóng gói. Bấm lần hai đưa cửa sổ đang mở lên trước thay vì tạo trùng, và
điều hướng thẳng tới mục được yêu cầu.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# GIAI ĐOẠN 3 — Viết đủ nội dung

Bảy task dưới đây có cùng khuôn. Mỗi task: viết test phủ cho phần của mình (đỏ) → viết nội dung `.md` + khai báo `covers` trong `manifest.json` → test xanh → commit.

**Quy tắc chung cho mọi file `.md` ở giai đoạn này** (đọc `docs/MANUAL_AUTHORING.md` sau khi Task 21 tạo nó; trước đó theo đúng đây):

- Bắt buộc có `## Dùng để làm gì` và `## Các bước`. `## Mẹo` và `## Gặp lỗi thì sao` tuỳ nội dung.
- Câu ngắn, ngôi thứ hai ("bạn"), mỗi bước một hành động.
- Tên nút đặt trong dấu backtick, viết y hệt chữ trên màn hình.
- Không dùng từ trong `manual_book.FORBIDDEN_WORDS`.
- Không có `<` trong file.

---

### Task 7: Chương 1 — Bắt đầu

**Files:**
- Create: `wfx_panel/manual/01-bat-dau/cai-dat.md`, `khoi-dong-cung-windows.md`, `chon-division.md`, `mo-trinh-duyet.md`
- Modify: `wfx_panel/manual/manifest.json`, `wfx_panel/manual/01-bat-dau/mo-panel.md`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.settings_controls()`, `surface.covered()` (Task 4)
- Produces: các mục phủ `settings`: `hotkey`, `start-hidden-input`, `autostart-input`, `always-on-top-input`

- [ ] **Step 1: Viết test thất bại**

```python
def test_chuong_bat_dau_phu_cai_dat_khoi_dong():
    covered = surface.covered("settings")
    for control in ("hotkey", "start-hidden-input", "autostart-input",
                    "always-on-top-input"):
        assert control in covered, control
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k bat_dau -v
```

Kỳ vọng: FAIL — `autostart-input` chưa được phủ.

- [ ] **Step 3: Viết bốn file nội dung**

`01-bat-dau/cai-dat.md` — cài đặt bằng bộ cài `WFX-Smart-Setup-v<phiên bản>.exe`, cài cho riêng người dùng, không cần quyền quản trị, tạo lối tắt Desktop và Start Menu, nâng cấp không mất dữ liệu.

`01-bat-dau/khoi-dong-cung-windows.md` — công tắc `Khởi động cùng Windows` và `Mở ẩn trong tray` trong Cài đặt thẻ Tự động hóa; giải thích bản cài đặt mới mặc định bật, nếu bạn tắt thì lựa chọn đó được giữ.

`01-bat-dau/chon-division.md` — ba nút WOVEN / KNIT / PSSG ở đầu bảng điều khiển, đổi Division trước khi làm việc, ứng dụng chờ WFX xác nhận đã đổi.

`01-bat-dau/mo-trinh-duyet.md` — dải thông báo `Chưa có trình duyệt automation`, nút `Mở trình duyệt`, ứng dụng dùng Chrome, Edge, Brave hoặc Chromium.

Mỗi file theo đúng khuôn bốn phần. Bổ sung công tắc `Luôn trên cùng` vào phần Mẹo của `mo-panel.md`.

- [ ] **Step 4: Cập nhật `manifest.json`**

Thêm bốn mục vào chương `bat-dau` với `covers` tương ứng:

```json
{ "id": "bat-dau-cai-dat", "title": "Cài đặt ứng dụng",
  "summary": "Tải bộ cài và cài cho riêng máy bạn.",
  "file": "01-bat-dau/cai-dat.md",
  "keywords": ["cài đặt", "setup", "gỡ cài đặt"], "covers": {} },
{ "id": "bat-dau-khoi-dong", "title": "Khởi động cùng Windows",
  "summary": "Để ứng dụng sẵn sàng ngay khi bật máy.",
  "file": "01-bat-dau/khoi-dong-cung-windows.md",
  "keywords": ["tự khởi động", "tray", "ẩn"],
  "covers": { "settings": ["autostart-input", "start-hidden-input"] } },
{ "id": "bat-dau-division", "title": "Chọn Division",
  "summary": "Chọn đúng Division trước khi thao tác.",
  "file": "01-bat-dau/chon-division.md",
  "keywords": ["woven", "knit", "pssg", "division"],
  "covers": { "errors": ["DIVISION_CHANGE_NOT_CONFIRMED"] } },
{ "id": "bat-dau-trinh-duyet", "title": "Mở trình duyệt làm việc",
  "summary": "Ứng dụng cần một cửa sổ trình duyệt để thao tác trên WFX.",
  "file": "01-bat-dau/mo-trinh-duyet.md",
  "keywords": ["chrome", "edge", "trình duyệt"], "covers": {} }
```

Thêm `"always-on-top-input"` vào `covers.settings` của `bat-dau-mo-panel`.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương Bắt đầu của hướng dẫn sử dụng

Cài đặt, mở bảng điều khiển, khởi động cùng Windows, chọn Division và mở
trình duyệt làm việc.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Chương 2 — Dùng bảng điều khiển hằng ngày

**Files:**
- Create: `wfx_panel/manual/02-hang-ngay/tim-module.md`, `ghim-yeu-thich.md`, `dung-tac-vu.md`, `thanh-trang-thai.md`, `giao-dien-thong-bao.md`
- Modify: `wfx_panel/manual/manifest.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.settings_controls()`, `surface.covered()`
- Produces: phủ trọn `settings` — sau task này kiểm tra toàn bộ công tắc cài đặt bật được

- [ ] **Step 1: Viết test thất bại**

```python
def test_moi_cong_tac_cai_dat_deu_co_huong_dan():
    missing = surface.settings_controls() - surface.covered("settings")
    assert not missing, f"Chưa có hướng dẫn cho: {sorted(missing)}"
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k cong_tac -v
```

Kỳ vọng: FAIL, liệt kê `admin-mode-input`, `focus-chrome-input`, `open-costing-file-input`, `return-list-input`, `theme`, `toast-input`.

- [ ] **Step 3: Viết năm file nội dung**

`tim-module.md` — ô `Tìm nhanh module...`, gõ để lọc, bấm để mở màn hình module.

`ghim-yeu-thich.md` — nút ngôi sao trên thẻ module, khu `Yêu thích` nằm trên ô tìm kiếm, module đã ghim không lặp lại bên dưới.

`dung-tac-vu.md` — nút `Stop` ở thanh dưới cùng khi đang chạy; giải thích tác vụ dừng ở điểm an toàn kế tiếp chứ không cắt ngang lúc WFX đang ghi dữ liệu, và không đóng trình duyệt.

`thanh-trang-thai.md` — dòng trạng thái, hai đèn Chrome và WFX, nút kiểm tra lại; công tắc `Trở về List sau khi thao tác` và `Đưa Chrome lên khi chạy module`.

`giao-dien-thong-bao.md` — Sáng / Tối / Tự động, `Thông báo khi xong việc`, `Chế độ quản trị`, `Mở file Costing sau khi tải`.

- [ ] **Step 4: Cập nhật `manifest.json`**

Thêm chương:

```json
{
  "id": "hang-ngay",
  "title": "Dùng hằng ngày",
  "summary": "Những thao tác bạn lặp lại mỗi ngày trên bảng điều khiển.",
  "entries": [
    { "id": "hang-ngay-tim-module", "title": "Tìm và mở module",
      "summary": "Gõ vài chữ là ra đúng màn hình cần dùng.",
      "file": "02-hang-ngay/tim-module.md",
      "keywords": ["tìm", "module", "danh sách"], "covers": {} },
    { "id": "hang-ngay-yeu-thich", "title": "Ghim module hay dùng",
      "summary": "Đưa module quen thuộc lên đầu.",
      "file": "02-hang-ngay/ghim-yeu-thich.md",
      "keywords": ["yêu thích", "ghim", "ngôi sao"], "covers": {} },
    { "id": "hang-ngay-dung-tac-vu", "title": "Dừng một tác vụ đang chạy",
      "summary": "Dừng an toàn mà không làm hỏng dữ liệu đang ghi.",
      "file": "02-hang-ngay/dung-tac-vu.md",
      "keywords": ["stop", "dừng", "huỷ"], "covers": {} },
    { "id": "hang-ngay-trang-thai", "title": "Đọc thanh trạng thái",
      "summary": "Biết ứng dụng đang làm gì và đã kết nối chưa.",
      "file": "02-hang-ngay/thanh-trang-thai.md",
      "keywords": ["trạng thái", "kết nối", "đèn"],
      "covers": { "settings": ["return-list-input", "focus-chrome-input"] } },
    { "id": "hang-ngay-giao-dien", "title": "Giao diện và thông báo",
      "summary": "Chọn nền sáng tối và bật tắt thông báo.",
      "file": "02-hang-ngay/giao-dien-thong-bao.md",
      "keywords": ["giao diện", "tối", "thông báo", "quản trị"],
      "covers": { "settings": ["theme", "toast-input", "admin-mode-input",
                               "open-costing-file-input"] } }
  ]
}
```

> Chỉ khai báo trong `covers.errors` những mã **có thật** trong `telemetry.ERROR_CODE_INFO`. Các trạng thái như huỷ tác vụ hay chưa nhập từ khoá nằm trong nhóm không báo lỗi nên không có mã — đừng bịa mã cho chúng. Test ở Task 13 sẽ bắt mọi mã không tồn tại.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương Dùng hằng ngày, phủ trọn công tắc cài đặt

Tìm module, ghim yêu thích, dừng tác vụ an toàn, đọc thanh trạng thái, giao
diện và thông báo. Test nay bắt buộc mọi công tắc cài đặt đều có hướng dẫn.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Chương 3 — Catalog

**Files:**
- Create: `wfx_panel/manual/03-catalog/tim-style.md`, `mo-costing.md`, `mo-bom.md`, `tai-file-dinh-kem.md`, `thu-vien-article.md`, `cay-thu-muc.md`
- Modify: `wfx_panel/manual/manifest.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.catalog_actions()`, `surface.module_ids()`
- Produces: phủ trọn 6 `catalog actions` và module `0003_6200`

- [ ] **Step 1: Viết test thất bại**

```python
def test_moi_nut_catalog_deu_co_huong_dan():
    missing = surface.catalog_actions() - surface.covered("actions")
    assert not missing, f"Chưa có hướng dẫn cho nút Catalog: {sorted(missing)}"


def test_module_catalog_co_huong_dan():
    assert "0003_6200" in surface.covered("modules")
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k catalog -v
```

- [ ] **Step 3: Viết sáu file nội dung**

`tim-style.md` (phủ `find`, `browse`) — chọn Division, mở `Catalog`, chọn Category, chọn kiểu tìm (Article Code với mọi Category; Buyer Reference cho Apparel; Article Name cho Category khác), gõ từ 2 ký tự để nhận gợi ý, bấm `Tìm`. Nêu rõ: một kết quả duy nhất thì ứng dụng tự mở; nhiều kết quả thì bạn chọn một dòng.

`mo-costing.md` (phủ `costsheet`) — sau khi tìm được Style, bấm `Costing`; nói rõ ứng dụng chuyển sang khu Costing.

`mo-bom.md` (phủ `bom`) — bấm `BOM`.

`tai-file-dinh-kem.md` (phủ `files`) — bấm `File`, ứng dụng quét bốn nhóm file, chọn file để tải, thư mục chứa file tự mở sau khi tải xong.

`thu-vien-article.md` — danh sách Article dùng cho gợi ý, tự cập nhật mỗi giờ, dùng bản gần nhất khi mất mạng, bạn không phải làm gì.

`cay-thu-muc.md` (phủ `refresh-folders`) — nút icon nhỏ cạnh `Mở Catalog` để đặt vị trí Apparel mặc định, nút làm mới danh sách thư mục.

- [ ] **Step 4: Cập nhật `manifest.json`** — thêm chương `catalog` với `covers.actions` phủ đủ sáu nút, `covers.modules: ["0003_6200"]` ở mục `catalog-tim-style`, và `covers.errors` gồm các mã bắt đầu bằng `CATALOG_`.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương Catalog của hướng dẫn sử dụng

Tìm Style theo ba kiểu, mở Costing và BOM, tải file đính kèm, thư viện Article
và cây thư mục. Test bắt buộc mọi nút trong màn Catalog đều có hướng dẫn.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Chương 4 — File Costing

**Files:**
- Create: `wfx_panel/manual/04-costing/xuat-file.md`, `kiem-tra-file.md`, `nhap-file.md`, `ap-dung.md`, `color-size-mapping.md`, `xoa-phu-thuoc.md`, `quet-lai-chi-phi.md`
- Modify: `wfx_panel/manual/manifest.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.costing_actions()`
- Produces: phủ trọn 6 `costing actions` và `catalog-special-rescan-input`

- [ ] **Step 1: Viết test thất bại**

```python
def test_moi_nut_costing_deu_co_huong_dan():
    missing = surface.costing_actions() - surface.covered("actions")
    assert not missing, f"Chưa có hướng dẫn cho nút Costing: {sorted(missing)}"


def test_cong_tac_quet_lai_chi_phi_co_huong_dan():
    assert "catalog-special-rescan-input" in surface.covered("settings")
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k costing -v
```

- [ ] **Step 3: Viết bảy file nội dung**

Điểm nghiệp vụ bắt buộc phải có, vì đây là phần dễ sai nhất:

- `xuat-file.md` (`export-xlsx`) — xuất được ở mọi trạng thái Costing. Trước khi hiện hộp thoại, ứng dụng đọc Style Code, Style Name và trạng thái rồi dùng Style Name đặt tên file. Hộp thoại nhớ thư mục lần trước. Thư mục chứa file luôn tự mở sau khi tải xong.
- `kiem-tra-file.md` (`validate-file`) — nút `Kiểm tra file` chỉ soát file Excel, báo sai ở sheet nào ô nào, không đụng tới WFX.
- `nhap-file.md` (`import`) — chỉ bật khi Costing đang ở trạng thái `Open`. Nếu khác `Open` hoặc chưa có Costing, ứng dụng dừng và bạn phải tự tạo hoặc mở Costing trên WFX trước.
- `ap-dung.md` (`apply`, `cancel-plan`) — hai bước: bước một chỉ kiểm tra và lập bản xem trước, chưa ghi gì lên WFX; bước hai mới ghi và lưu. Bản xem trước có hiệu lực 15 phút. Nút huỷ bỏ bản xem trước.
- `color-size-mapping.md` — hai bảng `Color Mapping` và `Size Mapping`, mỗi dòng viết `Vật tư => Style 1 | Style 2`. Giá trị chọn từ danh sách có sẵn; tên Style nằm trong ghi chú của ô.
- `xoa-phu-thuoc.md` (`clear-dependencies`) — nút `Clear All Dependency`, chỉ chạy khi Costing đang `Open`, có hỏi xác nhận, xoá toàn bộ liên kết phụ thuộc rồi lưu một lần.
- `quet-lai-chi-phi.md` — công tắc `Quét lại danh sách chi phí` cạnh Thư viện Article, mặc định tắt, chỉ ép một lần xuất hoặc nhập kế tiếp rồi tự tắt.

Trong `ap-dung.md`, phần Lưu ý phải nêu: ô để trống nghĩa là giữ nguyên giá trị đang có; muốn xoá giá trị phải ghi `__CLEAR__`; cột Action để trống nghĩa là thêm mới hoặc cập nhật.

- [ ] **Step 4: Cập nhật `manifest.json`** — chương `costing`, phủ đủ sáu nút, `settings: ["catalog-special-rescan-input"]`, `errors` gồm các mã bắt đầu bằng `COSTING_`.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương File Costing của hướng dẫn sử dụng

Xuất, kiểm tra, nhập, áp dụng hai bước, bảng Color/Size Mapping, xoá phụ thuộc
và quét lại danh sách chi phí.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Chương 5 — Đơn hàng và chứng từ

**Files:**
- Create: `wfx_panel/manual/05-don-hang/oc-tim.md`, `oc-upload-new.md`, `oc-revise.md`, `sample-list.md`, `sample-check-file.md`, `sale-asn.md`, `sale-asn-documents.md`
- Modify: `wfx_panel/manual/manifest.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.module_actions()`
- Produces: phủ các action `oc-*`, `sample-*`, `sale-asn-*` và ba module `0004_0050_0020`, `0004_0056_4070`, `0004_0070_0020`

- [ ] **Step 1: Viết test thất bại**

```python
def test_nhom_don_hang_co_du_huong_dan():
    covered = surface.covered("actions")
    missing = {
        action
        for action in surface.module_actions()
        if action.startswith(("oc-", "sample-", "sale-asn-"))
    } - covered
    assert not missing, f"Chưa có hướng dẫn cho: {sorted(missing)}"
    for module_id in ("0004_0050_0020", "0004_0056_4070", "0004_0070_0020"):
        assert module_id in surface.covered("modules"), module_id
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k don_hang -v
```

- [ ] **Step 3: Viết bảy file nội dung**

- `oc-tim.md` (`oc-list`, `oc-search`) — mở `OC List`, chọn tìm theo OC No. hoặc Style.
- `oc-upload-new.md` (`oc-template`, `oc-upload-new`, `oc-review-confirm`, `oc-review-cancel`) — tải mẫu, chỉ nhập vào sheet `OC INPUT`, chọn file, ứng dụng kiểm tra trước rồi hiện bảng tóm tắt gồm Buyer, mùa, số PO, số Style, tổng số lượng và số dòng. Chỉ khi bạn bấm `Xác nhận Upload` thì mới chạy trên WFX; bấm huỷ thì không có gì được gửi đi. Nêu rõ: mỗi file chỉ được chứa một Buyer, và thứ tự ngày bắt buộc là ngày đặt hàng trước ngày nguyên liệu về, trước ngày giao hàng.
- `oc-revise.md` (`oc-revise-report`, `oc-upload-revise`) — bấm mở báo cáo, tự chọn tham số và xuất Excel trên WFX, sửa file rồi chọn lại ở thẻ Revise. Giữ nguyên các cột định danh của OC gốc.
- `sample-list.md` (`sample-list`, `sample-search`, `sample-new`) — mở danh sách, tìm theo Sample Order No., Style hoặc người tạo, tạo Sample Order mới.
- `sample-check-file.md` (`sample-check-file`) — nút `Check File` tự tìm trước; một kết quả thì mở luôn và liệt kê file tải được, nhiều kết quả thì bạn chọn một dòng.
- `sale-asn.md` (`sale-asn-list`, `sale-asn-search`, `sale-asn-new`) — tìm theo Invoice No., Buyer Order Ref hoặc OC No.
- `sale-asn-documents.md` (`sale-asn-documents`) — tải Packing List và Buyer Invoice, ứng dụng ghép thành một file Excel hai sheet giữ nguyên định dạng gốc, tên file mặc định là Invoice No.

- [ ] **Step 4: Cập nhật `manifest.json`** — chương `don-hang`, phủ đủ action và ba module, `errors` gồm các mã bắt đầu bằng `OC_`, `SAMPLE_`, `SALE_ASN_`.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương Đơn hàng và chứng từ

OC tìm/Upload New/Revise, Sample List và kiểm tra file, Sale ASN và bộ
Documents Excel.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Chương 6 — Các danh sách khác

**Files:**
- Create: `wfx_panel/manual/06-danh-sach/rmpo.md`, `indent.md`, `qa-va-tai-chinh.md`, `buyer.md`, `supplier.md`, `company-setup.md`, `module-khac.md`
- Modify: `wfx_panel/manual/manifest.json`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `surface.module_ids()`, `surface.module_actions()`
- Produces: phủ trọn 16 module và 29 module action

- [ ] **Step 1: Viết test thất bại**

```python
def test_moi_module_deu_co_huong_dan():
    missing = surface.module_ids() - surface.covered("modules")
    assert not missing, f"Module chưa có hướng dẫn: {sorted(missing)}"


def test_moi_nut_thao_tac_module_deu_co_huong_dan():
    missing = surface.module_actions() - surface.covered("actions")
    assert not missing, f"Nút chưa có hướng dẫn: {sorted(missing)}"
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k "moi_module or moi_nut_thao_tac" -v
```

- [ ] **Step 3: Viết bảy file nội dung**

- `rmpo.md` (`rmpo-list`, `rmpo-search`; module `0005_0050_0020`) — tìm kết hợp theo nhà cung cấp và số RMPO.
- `indent.md` (`indent-list`, `indent-search`; module `0005_0080_0020`, `user_indent_list`) — tìm kết hợp bốn điều kiện: nhà cung cấp, Article, số Indent, Style.
- `qa-va-tai-chinh.md` (`list-new-list`, `list-new-new`; module `0063_0030_0020`, `0065_0880_0010_0020`, `0065_0880_0030_0020`) — mở danh sách và tạo mới; nêu rõ nút tạo mới bấm thẳng vào menu tương ứng nên không cần mở danh sách trước.
- `buyer.md` (`buyer-list`, `buyer-find`; module `0004_0010_1720`) — tìm và mở Buyer đầu tiên phù hợp.
- `supplier.md` (`supplier-list`, `supplier-open`, `supplier-find`; module `0005_0010_1290`) — đổi Category, mở Master, tìm trên mọi Category; nêu rõ nếu một Category lỗi thì ứng dụng vẫn tiếp tục và báo kết quả một phần.
- `company-setup.md` (`company-list`, `company-toggle-foc`; module `0090_0007`) — đổi nơi áp dụng FOC, ứng dụng tự mở Company Setup rồi vào Miscellaneous Settings.
- `module-khac.md` (module `0065_0880_0020_0020`, `0090_0001`, `0090_0250`) — các module chỉ có nút mở danh sách; hiển thị theo quyền của tài khoản.

- [ ] **Step 4: Cập nhật `manifest.json`** — chương `danh-sach`, phủ đủ module và action còn lại.

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v
```

- [ ] **Step 6: Commit**

```bash
git add wfx_panel/manual tests/test_manual.py
git commit -m "docs: chương Các danh sách khác, phủ trọn 16 module

RMPO, Indent, QA và tài chính, Buyer, Supplier, Company Setup và các module
chỉ có nút mở danh sách. Test nay bắt buộc mọi module và mọi nút thao tác đều
có hướng dẫn.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: Chương 7 — Cài đặt, cập nhật và xử lý sự cố

**Files:**
- Create: `wfx_panel/manual/07-su-co/lich-su-va-log.md`, `gop-y-bao-loi.md`, `cap-nhat.md`, `tra-ma-loi.md`, `quyen-rieng-tu.md`, `gioi-han.md`
- Modify: `wfx_panel/manual/manifest.json`, `wfx_panel/ui/manual.js`
- Test: `tests/test_manual.py`, `tests/test_ui_assets.py`

**Interfaces:**
- Consumes: `book.error_table` (Task 3), `showEntry` (Task 5)
- Produces: `renderErrorTable()` trong `manual.js`, mục `su-co-tra-ma-loi` hiển thị bảng 84 mã lỗi

- [ ] **Step 1: Viết test thất bại**

```python
def test_muc_tra_ma_loi_ton_tai():
    book = manual_book.load_book()
    assert "su-co-tra-ma-loi" in book["entries"]


def test_covers_khong_khai_bao_ma_loi_khong_ton_tai():
    unknown = surface.covered("errors") - set(telemetry.ERROR_CODE_INFO)
    assert not unknown, f"Mã lỗi không có thật: {sorted(unknown)}"


def test_moi_ma_loi_deu_nam_trong_bang_tra():
    book = manual_book.load_book()
    codes = {row["code"] for row in book["error_table"]}
    assert set(telemetry.ERROR_CODE_INFO) <= codes
```

Thêm vào `tests/test_ui_assets.py`:

```python
def test_manual_js_dung_bang_ma_loi():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "error_table" in js
    assert "su-co-tra-ma-loi" in js
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py tests/test_ui_assets.py -k "ma_loi" -v
```

- [ ] **Step 3: Viết sáu file nội dung**

- `lich-su-va-log.md` — nút danh sách ở góc trên, hai thẻ `Tác vụ` và `Log kỹ thuật`, lịch sử tự xoá sau 7 ngày, không lưu nội dung bạn đã tìm, nút sao chép.
- `gop-y-bao-loi.md` (`feedback-diagnostics-input`) — chọn loại, mô tả từ 5 ký tự, tuỳ chọn đính kèm chẩn đoán an toàn; nêu rõ không gửi mật khẩu, không gửi nội dung tìm kiếm, không tự chụp màn hình.
- `cap-nhat.md` — dải thông báo có bản mới, một lần bấm để tải và cài rồi ứng dụng tự mở lại; dữ liệu và cài đặt của bạn được giữ nguyên.
- `tra-ma-loi.md` — mục này chỉ cần phần `## Dùng để làm gì` và `## Các bước` hướng dẫn cách dùng bảng; bảng thật do `manual.js` dựng từ dữ liệu.
- `quyen-rieng-tu.md` — những gì ứng dụng gửi đi khi có lỗi và những gì tuyệt đối không gửi.
- `gioi-han.md` — phím tắt có thể không nhận khi cửa sổ đang dùng chạy quyền quản trị cao hơn; một số thao tác phụ thuộc tốc độ WFX.

- [ ] **Step 4: Cập nhật `manifest.json`** — chương `su-co`, mục `su-co-tra-ma-loi` với `covers.errors` để trống (bảng dựng từ dữ liệu), `gop-y-bao-loi` phủ `settings: ["feedback-diagnostics-input"]`.

- [ ] **Step 5: Dựng bảng mã lỗi trong `manual.js`**

Trong `showEntry`, sau khi gán `innerHTML`, thêm:

```javascript
    if (entryId === "su-co-tra-ma-loi") {
      const rows = book.error_table.map((row) =>
        `<tr><td><b class="ui-label">${escapeHtml(row.code)}</b></td>`
        + `<td>${escapeHtml(row.title)}</td>`
        + `<td>${escapeHtml(row.suggestion)}`
        + (row.entry
            ? ` <button class="manual-link" data-entry="${escapeHtml(row.entry)}">`
              + `Xem hướng dẫn</button>`
            : "")
        + `</td></tr>`
      ).join("");
      $(".manual-content").insertAdjacentHTML("beforeend",
        `<table id="bang-ma-loi"><thead><tr><th>Mã</th><th>Nghĩa là gì</th>`
        + `<th>Cách xử lý</th></tr></thead><tbody>${rows}</tbody></table>`);
    }
```

- [ ] **Step 6: Chạy test để xác nhận xanh**

```bash
python -m pytest -v && ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add wfx_panel/manual wfx_panel/ui/manual.js tests
git commit -m "docs: chương Cài đặt, cập nhật và xử lý sự cố

Lịch sử, góp ý, cập nhật, quyền riêng tư, giới hạn và bảng tra 84 mã lỗi dựng
tự động từ telemetry.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# GIAI ĐOẠN 4 — Kết nối và đồng bộ tài liệu

### Task 14: Nút trợ giúp trong từng màn module

**Files:**
- Modify: `wfx_panel/ui/index.html` (khối `.module-modal-heading`, dòng 116–119)
- Modify: `wfx_panel/ui/panel.js` (`openModulePage`, dòng 1143)
- Modify: `wfx_panel/ui/style.css`
- Modify: `wfx_panel/panel_app.py` (thêm `manual_entry_for_module`, đăng ký bridge cạnh dòng 1868)
- Test: `tests/test_panel_js.py`, `tests/test_ui_assets.py`, `tests/test_panel_app.py`

**Interfaces:**
- Consumes: `open_wfx_manual(target)` (Task 6), `covers.modules` trong manifest
- Produces:
  - `PanelApp.manual_entry_for_module(module_id: str) -> str` — trả id mục đầu tiên phủ module đó, hoặc chuỗi rỗng
  - Bridge JS mới: `get_manual_entry_for_module(module_id)` gắn vào `self.api` cạnh `open_wfx_manual`

- [ ] **Step 1: Viết test thất bại**

`tests/test_ui_assets.py`:

```python
def test_module_page_co_nut_tro_giup():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="icon-button module-help-button"' in html
```

`tests/test_panel_js.py`:

```python
def test_nut_tro_giup_module_goi_manual():
    assert '".module-help-button"' in JS
    assert '"get_manual_entry_for_module"' in JS
    assert '"open_wfx_manual"' in JS
```

`tests/test_panel_app.py`:

```python
def test_manual_entry_cho_module_catalog():
    import wfx_panel.panel_app as module

    app = module.PanelApp()

    assert app.manual_entry_for_module("0003_6200")
    assert app.manual_entry_for_module("khong-co-that") == ""
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_ui_assets.py tests/test_panel_js.py tests/test_panel_app.py -k "tro_giup or manual_entry" -v
```

- [ ] **Step 3: Thêm nút vào `index.html`**

Đổi khối `.module-modal-identity` (dòng 115–120) thành:

```html
          <div class="module-modal-identity">
            <div class="module-modal-heading">
              <strong id="module-page-title">Catalog</strong>
              <span class="module-modal-subtitle">Tìm Article · Season · Costing/BOM.</span>
            </div>
            <button class="icon-button module-help-button" type="button" aria-label="Xem hướng dẫn cho module này" title="Hướng dẫn module này">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .9-1 1.6v.4"/><path d="M12 17h.01"/></svg>
            </button>
          </div>
```

- [ ] **Step 4: Thêm phương thức vào `panel_app.py`**

```python
    def manual_entry_for_module(self, module_id: str) -> str:
        """Mục hướng dẫn đầu tiên khai báo phủ module này."""
        book = manual_book.load_book()
        for entry_id in book["order"]:
            if module_id in book["entries"][entry_id]["covers"]["modules"]:
                return entry_id
        return ""

    def get_manual_entry_for_module(self, module_id: str) -> dict:
        return {
            "ok": True,
            "code": "MANUAL_ENTRY",
            "message": "",
            "entry": self.manual_entry_for_module(str(module_id or "")),
        }
```

Đăng ký bridge cạnh dòng 1868:

```python
        self.api.get_manual_entry_for_module = (  # type: ignore[attr-defined]
            self.get_manual_entry_for_module
        )
```

- [ ] **Step 5: Nối trong `panel.js`**

Trong khối gắn sự kiện (cạnh `$(".manual-button")`, dòng 2742):

```javascript
    $(".module-help-button").addEventListener("click", async () => {
      const moduleId = selectedModule?.id || "";
      const found = await callQuiet("get_manual_entry_for_module", moduleId);
      await callQuiet("open_wfx_manual", found?.entry || "");
    });
```

- [ ] **Step 6: Thêm style vào `style.css`**

```css
    .module-modal-identity { display: flex; align-items: center; gap: 8px; }
    .module-modal-heading { flex: 1; min-width: 0; }
    .module-help-button { flex: 0 0 auto; }
```

- [ ] **Step 7: Chạy test và kiểm tra thủ công**

```bash
python -m pytest -v && ruff check .
```

```bash
python app.py
```

Mở module Catalog, bấm nút dấu hỏi, xác nhận cửa sổ hướng dẫn mở đúng mục Tìm Style.

- [ ] **Step 8: Commit**

```bash
git add wfx_panel/ui/index.html wfx_panel/ui/panel.js wfx_panel/ui/style.css wfx_panel/panel_app.py tests
git commit -m "feat: nút trợ giúp mở hướng dẫn đúng module đang mở

Tra ngược khai báo phủ trong manifest để biết mục nào nói về module này, nên
người dùng không phải tự tìm trong mục lục.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Liên kết hướng dẫn từ lỗi ở thanh trạng thái

**Files:**
- Modify: `wfx_panel/ui/index.html` (khối `.footer-status`, dòng 97)
- Modify: `wfx_panel/ui/panel.js` (`setStatus` dòng 440, `handleResult` dòng 977)
- Modify: `wfx_panel/ui/style.css`
- Modify: `wfx_panel/panel_app.py` (thêm `manual_error_codes` và khoá `manual_error_codes` trong state khởi động)
- Test: `tests/test_panel_js.py`, `tests/test_ui_assets.py`, `tests/test_panel_app.py`

**Interfaces:**
- Consumes: `open_wfx_manual(target)` (Task 6), `book["error_table"]` (Task 3)
- Produces:
  - `PanelApp.manual_error_codes() -> list[str]` — mã lỗi có mục hướng dẫn riêng
  - Nút DOM `.footer-help-button`

- [ ] **Step 1: Viết test thất bại**

`tests/test_ui_assets.py`:

```python
def test_footer_co_nut_xem_huong_dan():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="footer-help-button"' in html
```

`tests/test_panel_js.py`:

```python
def test_the_loi_moi_duoc_link_toi_huong_dan():
    assert '".footer-help-button"' in JS
    assert "lastErrorCode" in JS
```

`tests/test_panel_app.py`:

```python
def test_danh_sach_ma_loi_co_huong_dan():
    import wfx_panel.panel_app as module

    codes = module.PanelApp().manual_error_codes()

    assert "LOGIN_FAILED" in codes
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest -k "footer_co_nut or the_loi_moi or ma_loi_co_huong_dan" -v
```

- [ ] **Step 3: Thêm nút vào `index.html`**

Ngay sau `.footer-status` (dòng 97):

```html
      <button class="footer-help-button" type="button" title="Xem hướng dẫn xử lý" aria-label="Xem hướng dẫn xử lý lỗi này" hidden>?</button>
```

- [ ] **Step 4: Thêm phương thức vào `panel_app.py`**

```python
    def manual_error_codes(self) -> list[str]:
        """Mã lỗi đã có mục hướng dẫn riêng, dùng cho nút trợ giúp ở footer."""
        book = manual_book.load_book()
        return [row["code"] for row in book["error_table"] if row["entry"]]
```

Trong hàm trả `initial state` cho UI (cùng chỗ trả `hotkey_label`, `theme`), thêm khoá:

```python
            "manual_error_codes": self.manual_error_codes(),
```

- [ ] **Step 5: Nối trong `panel.js`**

Thêm biến ở vùng khai báo trạng thái đầu IIFE:

```javascript
  let manualErrorCodes = new Set();
  let lastErrorCode = "";
```

Trong hàm nhận state khởi động, thêm:

```javascript
    if (Array.isArray(state.manual_error_codes)) {
      manualErrorCodes = new Set(state.manual_error_codes);
    }
```

Trong `handleResult`, ngay sau lời gọi `setStatus(...)`:

```javascript
    lastErrorCode = (!result.ok && result.code) ? result.code : "";
    $(".footer-help-button").hidden = !manualErrorCodes.has(lastErrorCode);
```

Trong khối gắn sự kiện:

```javascript
    $(".footer-help-button").addEventListener("click", () => {
      callQuiet("open_wfx_manual", lastErrorCode);
    });
```

- [ ] **Step 6: Thêm style vào `style.css`**

```css
    .footer-help-button { width: 18px; height: 18px; flex: 0 0 auto; padding: 0;
      color: var(--bad); border: 1px solid var(--bad-soft); border-radius: 50%;
      background: var(--bad-soft); font-size: 11px; font-weight: 700;
      line-height: 1; cursor: pointer; }
    .footer-help-button:hover { border-color: var(--bad); }
```

- [ ] **Step 7: Chạy test**

```bash
python -m pytest -v && ruff check .
```

- [ ] **Step 8: Commit**

```bash
git add wfx_panel/ui wfx_panel/panel_app.py tests
git commit -m "feat: nút xem hướng dẫn xử lý cạnh trạng thái lỗi

Khi tác vụ thất bại với mã lỗi đã có mục hướng dẫn, thanh dưới cùng hiện một
nút nhỏ mở thẳng mục đó.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 16: Chấm báo Có gì mới trên nút Manual

**Files:**
- Modify: `wfx_panel/prefs.py` (`load_prefs`, `save_prefs`, `_save_prefs_locked`)
- Modify: `wfx_panel/panel_app.py` (`open_wfx_manual`, state khởi động)
- Modify: `wfx_panel/ui/index.html` (nút `.manual-button`, dòng 19)
- Modify: `wfx_panel/ui/panel.js`
- Test: `tests/test_prefs.py`, `tests/test_panel_app.py`, `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `load_whats_new()` (Task 3), `open_wfx_manual` (Task 6)
- Produces:
  - Khoá prefs `manual_seen_version: str`
  - `PanelApp.manual_has_news() -> bool`
  - Chấm DOM `.manual-alert`, class `has-alert` trên `.manual-button`

- [ ] **Step 1: Viết test thất bại**

`tests/test_prefs.py`:

```python
def test_manual_seen_version_mac_dinh_la_phien_ban_hien_tai(tmp_path):
    from wfx_panel import prefs
    from wfx_panel.version import APP_VERSION

    assert prefs.load_prefs(tmp_path)["manual_seen_version"] == APP_VERSION


def test_manual_seen_version_luu_duoc(tmp_path):
    from wfx_panel import prefs

    prefs.save_prefs(tmp_path, manual_seen_version="1.0.9")

    assert prefs.load_prefs(tmp_path)["manual_seen_version"] == "1.0.9"
```

`tests/test_panel_app.py`:

```python
def test_khong_bao_tin_moi_khi_cai_moi(monkeypatch, tmp_path):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(module.prefs, "DATA_DIR", tmp_path)

    assert module.PanelApp().manual_has_news() is False


def test_bao_tin_moi_sau_khi_cap_nhat(monkeypatch, tmp_path):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(module.prefs, "DATA_DIR", tmp_path)
    module.prefs.save_prefs(tmp_path, manual_seen_version="1.0.9")

    assert module.PanelApp().manual_has_news() is True


def test_mo_manual_xoa_cham_bao(monkeypatch, tmp_path):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(module.prefs, "DATA_DIR", tmp_path)
    module.prefs.save_prefs(tmp_path, manual_seen_version="1.0.9")
    app = module.PanelApp()
    _patch_manual_window(monkeypatch, module)

    app.open_wfx_manual()

    assert app.manual_has_news() is False
```

`tests/test_panel_js.py`:

```python
def test_cham_bao_tin_moi_tren_nut_manual():
    assert "manual-alert" in JS
    assert "manual_has_news" in JS
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest -k "manual_seen or tin_moi or cham_bao" -v
```

- [ ] **Step 3: Thêm khoá vào `prefs.py`**

Trong `load_prefs`, thêm import ở đầu file `from wfx_panel.version import APP_VERSION`, và thêm vào dict trả về:

```python
        # Cài mới ghi luôn phiên bản hiện tại nên người dùng mới không bị báo
        # tin của chính bản họ vừa cài. Chấm báo chỉ xuất hiện sau khi cập nhật.
        "manual_seen_version": str(
            data.get("manual_seen_version") or APP_VERSION
        ),
```

Thêm `manual_seen_version: str | None = None` vào chữ ký `save_prefs` và `_save_prefs_locked`, truyền tiếp trong lời gọi, và trong `_save_prefs_locked` thêm:

```python
    if manual_seen_version is not None:
        current["manual_seen_version"] = str(manual_seen_version)
```

- [ ] **Step 4: Thêm vào `panel_app.py`**

```python
    def manual_has_news(self) -> bool:
        """Có tin mới chưa đọc cho đúng phiên bản đang chạy hay không."""
        seen = prefs.load_prefs().get("manual_seen_version", "")
        if seen == APP_VERSION:
            return False
        try:
            versions = {item["version"] for item in manual_book.load_whats_new()}
        except manual_book.ManualContentError:
            return False
        return APP_VERSION in versions
```

Thêm import `from wfx_panel.version import APP_VERSION` nếu chưa có.

Trong `open_wfx_manual`, ngay sau `self._manual_target = str(target or "")`:

```python
        if self.manual_has_news() and not self._manual_target:
            self._manual_target = "co-gi-moi"
        prefs.save_prefs(manual_seen_version=APP_VERSION)
```

Thêm `"manual_has_news": self.manual_has_news(),` vào state khởi động.

- [ ] **Step 5: Thêm chấm vào `index.html`**

Trong nút `.manual-button` (dòng 19–21), thêm ngay trước `</button>`:

```html
          <span class="manual-alert" aria-hidden="true"></span>
```

- [ ] **Step 6: Nối trong `panel.js`**

Trong hàm nhận state khởi động:

```javascript
    $(".manual-button").classList.toggle("has-alert", state.manual_has_news === true);
```

Trong handler `.manual-button` (dòng 2742), sau lời gọi:

```javascript
      $(".manual-button").classList.remove("has-alert");
```

- [ ] **Step 7: Thêm style vào `style.css`**

Sao chép quy tắc của `.log-alert` cho `.manual-alert`, đổi bộ chọn cha thành `.manual-button.has-alert .manual-alert`.

- [ ] **Step 8: Xử lý mục `co-gi-moi` trong `manual.js`**

Trong `window.wfxManualGoTo`, thêm nhánh đầu tiên:

```javascript
    if (target === "co-gi-moi") { showHome(); return; }
```

- [ ] **Step 9: Chạy test**

```bash
python -m pytest -v && ruff check .
```

- [ ] **Step 10: Commit**

```bash
git add wfx_panel tests
git commit -m "feat: chấm báo Có gì mới trên nút hướng dẫn

Sau khi ứng dụng tự cập nhật, nút hướng dẫn hiện chấm đỏ và mở thẳng phần Có
gì mới. Cài đặt mới ghi luôn phiên bản hiện tại nên không làm phiền người dùng
mới.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 17: Sinh `docs/USER_FEATURES.md` từ manual

**Files:**
- Create: `scripts/generate_user_features.py`
- Modify: `docs/USER_FEATURES.md` (ghi đè bằng bản sinh)
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `load_book()` (Task 3)
- Produces:
  - `build_user_features(book: dict) -> str` trong `scripts/generate_user_features.py`
  - `main() -> None` ghi ra `docs/USER_FEATURES.md`

- [ ] **Step 1: Viết test thất bại**

```python
def test_user_features_dong_bo_voi_manual():
    import sys

    root = manual_book.MANUAL_DIR.parent.parent
    sys.path.insert(0, str(root / "scripts"))
    import generate_user_features

    expected = generate_user_features.build_user_features(manual_book.load_book())
    actual = (root / "docs" / "USER_FEATURES.md").read_text(encoding="utf-8")

    assert actual == expected, (
        "docs/USER_FEATURES.md đã lệch. Chạy: "
        "python scripts/generate_user_features.py"
    )
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k user_features -v
```

- [ ] **Step 3: Viết `scripts/generate_user_features.py`**

```python
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
        parts.append(f"| `{row['code']}` | {row['title']} | {row['suggestion']} |\n")
    return "".join(parts)


def main() -> None:
    text = build_user_features(manual_book.load_book())
    (ROOT / "docs" / "USER_FEATURES.md").write_text(text, encoding="utf-8")
    print("Đã cập nhật docs/USER_FEATURES.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Sinh file**

```bash
python scripts/generate_user_features.py
```

- [ ] **Step 5: Chạy test để xác nhận xanh**

```bash
python -m pytest tests/test_manual.py -v && ruff check scripts
```

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_user_features.py docs/USER_FEATURES.md tests/test_manual.py
git commit -m "docs: sinh USER_FEATURES.md từ nội dung hướng dẫn

Tài liệu người dùng nay chỉ còn một nguồn duy nhất. Test so sánh file trên đĩa
với kết quả sinh lại nên hai bên không thể lệch nhau.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 18: Đóng gói nội dung vào bản EXE

**Files:**
- Modify: `wfx_panel/wfx-panel.spec` (khối `datas`, dòng 16–20)
- Test: `tests/test_installer.py`

**Interfaces:**
- Consumes: `wfx_panel/manual/` (Task 2)
- Produces: không có

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_installer.py`:

```python
def test_spec_dong_goi_noi_dung_huong_dan():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = (root / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")

    assert '("manual", "wfx_panel/manual")' in spec
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_installer.py -k huong_dan -v
```

- [ ] **Step 3: Sửa `wfx_panel/wfx-panel.spec`**

```python
    datas=[
        ("ui", "wfx_panel/ui"),
        ("manual", "wfx_panel/manual"),
        ("assets/wfx.ico", "wfx_panel/assets"),
        ("../Article List.csv", "."),
    ],
```

Thêm `"wfx_panel.manual_book"` vào `hiddenimports`.

- [ ] **Step 4: Chạy test và build thử**

```bash
python -m pytest tests/test_installer.py -v
```

```powershell
powershell -ExecutionPolicy Bypass -File build-panel.ps1
```

Chạy `dist/WFX-Panel/WFX-Panel.exe`, bấm nút hướng dẫn, xác nhận nội dung hiện đầy đủ trong bản đóng gói.

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/wfx-panel.spec tests/test_installer.py
git commit -m "build: đóng gói nội dung hướng dẫn vào bản EXE

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 19: Bản prompt viết manual cho lần sau

**Files:**
- Create: `docs/MANUAL_AUTHORING.md`
- Create: `docs/README.md`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: `FORBIDDEN_WORDS`, `CALLOUT_LABELS` (Task 1, 2)
- Produces: không có (tài liệu)

- [ ] **Step 1: Viết test thất bại**

```python
def test_huong_dan_viet_manual_liet_ke_du_tu_cam():
    root = manual_book.MANUAL_DIR.parent.parent
    text = (root / "docs" / "MANUAL_AUTHORING.md").read_text(encoding="utf-8")
    for word in manual_book.FORBIDDEN_WORDS:
        assert word in text, word
    for label in manual_book.CALLOUT_LABELS.values():
        assert label in text, label
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest tests/test_manual.py -k viet_manual -v
```

- [ ] **Step 3: Viết `docs/MANUAL_AUTHORING.md`**

Nội dung bắt buộc có sáu phần:

1. **Mục tiêu và người đọc** — nhân viên nghiệp vụ dệt may, không rành máy tính. Viết như đang chỉ cho đồng nghiệp ngồi cạnh.
2. **Quy trình sáu bước khi có tính năng mới:**
   1. Xác định tính năng vừa thêm: module nào, nút nào, công tắc nào, mã lỗi nào.
   2. Chọn chương phù hợp trong `wfx_panel/manual/manifest.json`.
   3. Tạo file `.md` theo khuôn ở phần 3 dưới đây.
   4. Khai báo `covers` cho đúng những thứ ở bước 1.
   5. Chạy `python scripts/generate_user_features.py`.
   6. Chạy `python -m pytest tests/test_manual.py` cho tới khi xanh.
3. **Khuôn file `.md`** — chép nguyên khối mẫu có đủ bốn phần và ba loại khối nhấn mạnh (`> [!meo]`, `> [!luuy]`, `> [!loi]`) với nhãn `Mẹo`, `Lưu ý`, `Gặp lỗi thì sao`.
4. **Bảng từ cấm và từ thay thế** — liệt kê đủ mọi từ trong `FORBIDDEN_WORDS`, mỗi từ kèm cách viết thay thế.
5. **Quy tắc giọng văn** — câu ngắn; ngôi thứ hai; mỗi bước một hành động; luôn nói rõ bấm nút nào trên màn hình nào; tên nút đặt trong dấu backtick và viết y hệt chữ trên màn hình.
6. **Checklist tự kiểm** — đủ bốn phần, không từ cấm, không HTML thô, `covers` khớp thực tế, đã chạy generator, test xanh.

- [ ] **Step 4: Viết `docs/README.md`**

Mục lục tài liệu:

| File | Dùng cho ai | Nội dung |
|---|---|---|
| `USER_FEATURES.md` | người dùng | Danh sách chức năng, sinh tự động từ `wfx_panel/manual/` |
| `MANUAL_AUTHORING.md` | người viết tài liệu | Cách bổ sung manual khi có tính năng mới |
| `CATALOG_COSTING_FILES.md` | người phát triển | Chi tiết file Costing xuất/nhập |
| `PERFORMANCE_1.0.15.md` | người phát triển | Ghi chép tối ưu hiệu năng bản 1.0.15 |
| `superpowers/specs/` | người phát triển | Thiết kế đã chốt |
| `superpowers/plans/` | người phát triển | Kế hoạch triển khai |

- [ ] **Step 5: Chạy test**

```bash
python -m pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add docs/MANUAL_AUTHORING.md docs/README.md tests/test_manual.py
git commit -m "docs: hướng dẫn viết manual và mục lục tài liệu

Quy trình sáu bước, khuôn file, bảng từ cấm và checklist để lần sau thêm tính
năng là biết viết manual thế nào cho đúng giọng văn.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 20: Vá tài liệu kỹ thuật và badge phiên bản

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `wfx_panel/ui/index.html` (dòng 16, badge phiên bản)
- Modify: `wfx_panel/ui/panel.js`
- Test: `tests/test_ui_assets.py`, `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `DISPLAY_VERSION` từ `wfx_panel/version.py`
- Produces: không có

- [ ] **Step 1: Viết test thất bại**

`tests/test_ui_assets.py`:

```python
def test_badge_phien_ban_khong_hardcode():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert '<span class="app-version"></span>' in html
    assert "Phiên bản 1.0<" not in html
```

`tests/test_panel_js.py`:

```python
def test_badge_phien_ban_lay_tu_state():
    assert ".app-version" in JS
    assert "state.version" in JS
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

```bash
python -m pytest -k badge_phien_ban -v
```

- [ ] **Step 3: Sửa badge phiên bản**

`index.html` dòng 16 đổi thành:

```html
        <div><strong>WFX Smart</strong><span class="app-version"></span></div>
```

`panel.js`, trong hàm nhận state khởi động:

```javascript
    if (state.version) $(".app-version").textContent = `Phiên bản ${state.version}`;
```

Kiểm tra state khởi động đã có khoá `version` (dùng `DISPLAY_VERSION`); nếu chưa thì thêm trong `panel_app.py`.

- [ ] **Step 4: Bổ sung `README.md`**

Trong mục `## Chức năng nổi bật`, thêm bốn gạch đầu dòng còn thiếu: tải bộ Documents Excel của Sale ASN, kiểm tra file của Sample List, xoá toàn bộ phụ thuộc trong Costing, thư viện Article tự cập nhật. Thêm một mục mới `## Hướng dẫn sử dụng trong ứng dụng` mô tả nút Manual mở cửa sổ tra cứu offline, và trỏ tới `docs/MANUAL_AUTHORING.md`.

- [ ] **Step 5: Bổ sung `CLAUDE.md`**

Trong `## Trạng thái sản phẩm hiện tại`, ngay dưới đoạn nói về `docs/USER_FEATURES.md`, thay đoạn đó bằng:

```markdown
Danh sách chức năng dành cho người dùng nằm trong `wfx_panel/manual/` và được
sinh ra `docs/USER_FEATURES.md` bằng `python scripts/generate_user_features.py`.
Không sửa tay `docs/USER_FEATURES.md`. `README.md` là hướng dẫn cài/chạy/build
ngắn gọn.

Thay đổi hành vi sản phẩm phải cập nhật `wfx_panel/manual/` trong cùng lần sửa:
thêm module, thêm nút thao tác, thêm công tắc cài đặt hoặc thêm mã lỗi mà chưa
có mục hướng dẫn phủ thì `tests/test_manual.py` sẽ đỏ. Cách viết nằm ở
`docs/MANUAL_AUTHORING.md`.
```

Trong `### Hành vi giao diện`, thêm:

```markdown
- Nút Manual ở top nav mở một cửa sổ Hướng dẫn sử dụng riêng 1000×720, đọc nội
  dung đã đóng gói trong `wfx_panel/manual/`. Cửa sổ này chạy offline hoàn toàn:
  không gọi mạng, không cần Chrome, không cần phiên WFX. Bấm lần hai đưa cửa sổ
  đang mở lên trước, không tạo cửa sổ trùng. Cửa sổ Manual không tham gia logic
  tự thu của panel. Mỗi màn module có nút dấu hỏi mở đúng mục của module đó, và
  thanh trạng thái hiện nút trợ giúp khi lỗi có mục hướng dẫn. Sau khi ứng dụng
  tự cập nhật, nút Manual hiện chấm đỏ và mở thẳng phần Có gì mới.
```

- [ ] **Step 6: Chạy toàn bộ test**

```bash
python -m pytest -v && ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add README.md CLAUDE.md wfx_panel/ui tests
git commit -m "docs: đồng bộ tài liệu hệ thống và badge phiên bản động

Bổ sung bốn chức năng còn thiếu trong README, thêm luật bắt buộc cập nhật
manual vào CLAUDE.md, và badge phiên bản lấy từ version.py thay vì chuỗi cứng.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 21: Rà soát cuối và hoàn tất

**Files:**
- Test: toàn bộ

- [ ] **Step 1: Chạy đầy đủ**

```bash
python -m pytest -v
```

```bash
ruff check .
```

- [ ] **Step 2: Kiểm tra thủ công theo danh sách**

Chạy `python app.py` và xác nhận từng điểm:

1. Bấm nút quyển sách → cửa sổ hướng dẫn mở, 7 chương hiện trong mục lục.
2. Gõ `costing` vào ô tìm → có kết quả, từ khoá được tô vàng.
3. Gõ `COSTING_SAVE_ALERT` → ra bảng tra mã lỗi.
4. Bấm nút Manual lần hai → không có cửa sổ thứ hai.
5. Bấm sang cửa sổ hướng dẫn → bảng điều khiển thu lại, cửa sổ hướng dẫn vẫn mở nguyên.
6. Mở module Catalog → bấm nút dấu hỏi → đúng mục Tìm Style.
7. Đổi giao diện sang Tối trong Cài đặt → mở lại hướng dẫn → nền tối.
8. `Ctrl+F` trong cửa sổ hướng dẫn → con trỏ nhảy vào ô tìm.
9. `Ctrl+P` → bản in không có cột mục lục.
10. Ngắt mạng → mở hướng dẫn → vẫn đầy đủ nội dung.

- [ ] **Step 3: Xác nhận không sót**

```bash
python -c "from tests import _manual_surface as s; print('module thiếu:', sorted(s.module_ids() - s.covered('modules'))); print('nút thiếu:', sorted((s.module_actions() | s.catalog_actions() | s.costing_actions()) - s.covered('actions'))); print('cài đặt thiếu:', sorted(s.settings_controls() - s.covered('settings')))"
```

Cả ba dòng phải in ra danh sách rỗng.

- [ ] **Step 4: Commit cuối và mở pull request**

```bash
git add -A
git commit -m "chore: hoàn tất tính năng hướng dẫn sử dụng trong ứng dụng

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

```bash
gh pr create --title "Manual hệ thống trong ứng dụng" --body "Nút Manual nay mở cửa sổ hướng dẫn offline phủ toàn bộ tính năng, có tìm kiếm và bảng tra mã lỗi. docs/USER_FEATURES.md được sinh từ cùng nguồn. Test chặn việc thêm tính năng mà quên viết manual.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Ghi chú cho người triển khai

**Thứ tự bắt buộc.** Giai đoạn 1 → 2 → 3 → 4. Trong giai đoạn 3, thứ tự các task 7–13 có thể đổi, nhưng Task 12 phải chạy sau Task 9 và 11 vì nó bật kiểm tra phủ toàn bộ module.

**Khi một kiểm tra phủ đỏ.** Đừng nới lỏng test. Đỏ nghĩa là sản phẩm có thứ mà tài liệu chưa nói tới — hãy viết mục manual cho thứ đó.

**Khi số đếm trong Task 4 lệch.** Có nghĩa `panel.js` hoặc `index.html` đã đổi từ lúc viết kế hoạch. Mở file xác minh số thật, cập nhật test kèm ghi chú lý do, rồi viết bổ sung manual cho phần mới.

**Nội dung viết bằng tiếng Việt cho người không rành máy tính.** Nếu một câu bạn viết chỉ người lập trình hiểu, viết lại.

**Đừng bịa mã lỗi.** 84 mã có thật chỉ thuộc các tiền tố sau — kiểm tra bằng lệnh dưới trước khi ghi vào `covers.errors`:

```bash
python -c "from wfx_panel import telemetry; print('\n'.join(sorted(telemetry.ERROR_CODE_INFO)))"
```

Tiền tố hiện có: `BUYER_`, `CATALOG_`, `CATEGORY_`, `CHROME_`, `CODE_`, `COMPANY_`, `COSTING_`, `DIVISION_`, `FILTER_`, `FLOATING_`, `LOGIN_`, `MASTER_`, `MODULE_`, `OC_`, `PANEL_`, `QUICK_`, `RESULT_`, `SALE_ASN_`, `SAMPLE_`, `SESSION_`, `SUPPLIER_`.

Các trạng thái người dùng thường gặp như huỷ tác vụ, chưa nhập từ khoá, không có kết quả, Costing chưa mở đều **không có mã** vì chúng nằm trong nhóm không báo lỗi. Vẫn viết hướng dẫn cho chúng, chỉ là không khai báo vào `covers.errors`.
