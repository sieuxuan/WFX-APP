# Color Combination - Production Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép user chọn OC Division/Buyer/Season một lần rồi tải hàng loạt báo cáo `Color combination cost sheet_Production`, mỗi BuyerStyleReference một file Excel.

**Architecture:** `reports.py` giữ primitive ReportViewer dùng chung; file mới `wfx_panel/automation/color_combination.py` chứa cascade tham số + vòng lặp batch. Logic thuần (chọn StyleCode, đặt tên file, điều khiển vòng lặp) tách khỏi Playwright để test được không cần Chrome. `PanelAPI` thêm ba method, UI thêm một workspace trong module `reports` sẵn có.

**Tech Stack:** Python 3.11+, Playwright sync API qua CDP, pywebview + JS thuần (không framework), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-07-color-combination-report-design.md`

## Global Constraints

- Mọi code sản phẩm nằm trong `wfx_panel/`. Không sửa file trong `dist/`.
- `python -m pytest` và `ruff check .` phải xanh trước mỗi commit.
- Chuỗi hiển thị cho user là tiếng Việt Unicode **NFC**, dùng `xóa`, `hủy`, `hóa`. `tests/test_ui_assets.py` sẽ đỏ nếu có ký tự NFD.
- Không ghi password, cookie, SessionID, LoginID hay URL WFX đầy đủ vào log. Mô tả lỗi gửi telemetry đi qua `redact_telemetry_text`.
- Mọi wait dài dùng `_wait()` theo lát ≤ 100 ms và gọi `checkpoint()` để nút Stop hoạt động.
- `AutomationCancelled` kế thừa `BaseException`, không phải `Exception` — `except Exception` không bắt được nó. Luôn bắt nó **trước** khi bắt `Exception`.
- Download đi qua Chrome native: chụp `snapshot_downloads()` trước click, không dùng `download.save_as()`.
- Mã lỗi reportable phải có mục trong `telemetry.ERROR_CODE_INFO`; mã không reportable phải nằm trong `panel_api.NON_REPORTABLE_FAILURES`.
- Thay đổi hành vi sản phẩm phải cập nhật `wfx_panel/manual/` trong cùng lần sửa, nếu không `tests/test_manual.py` đỏ. Không sửa tay `docs/USER_FEATURES.md`.
- Panel rộng 440px. Không thêm tầng tab mới, không lặp status bên trong màn module (footer là nơi hiển thị trạng thái tác vụ).

**Hằng số dùng chung, khai báo ở Task 1 và dùng nguyên văn ở các task sau:**

```python
REPORT_ID = "color_combination_production"
REPORT_NAME = "Color Combination - Production"
POSTBACK_TIMEOUT_SECONDS = 45.0
LEVEL_LABELS = {
    "division": "OC Division",
    "buyer": "Buyer",
    "season": "Season",
    "style_ref": "BuyerStyleReference",
}
CASCADE_KEYS = ("division", "buyer", "season")
STYLE_CODE_LABEL = "StyleCode"
SIZE_VISIBILITY_LABEL = "SizeVisibility"
```

## File Structure

| File | Trách nhiệm |
| --- | --- |
| `wfx_panel/automation/color_combination.py` (mới) | Cascade tham số, chọn StyleCode, vòng lặp batch, lưu file theo style |
| `wfx_panel/automation/reports.py` (sửa) | Thêm `_wait_postback_settled`, `_resolve_controls`, entry `REPORTS` mới, `kind` trong catalog |
| `wfx_panel/automation/__init__.py` (sửa) | Re-export hai hàm mới cho `PanelAPI` |
| `wfx_panel/panel_api.py` (sửa) | `load_color_report_options`, `run_color_report_batch`, mã lỗi non-reportable |
| `wfx_panel/panel_app.py` (sửa) | `choose_report_export_dir` dùng `webview.FOLDER_DIALOG` |
| `wfx_panel/prefs.py` (sửa) | `report_export_dir` |
| `wfx_panel/telemetry.py` (sửa) | `ERROR_CODE_INFO` cho hai mã reportable |
| `wfx_panel/ui/index.html`, `panel.js`, `style.css` (sửa) | Workspace `.color-report-workspace` |
| `wfx_panel/manual/06-danh-sach/reports.md`, `manifest.json` (sửa) | Hướng dẫn người dùng |
| `tests/test_color_combination.py` (mới) | Test logic thuần |

---

### Task 1: Chọn StyleCode theo số lớn nhất

**Files:**
- Create: `wfx_panel/automation/color_combination.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: không có (task đầu tiên)
- Produces: `REPORT_ID: str`, `REPORT_NAME: str`, `POSTBACK_TIMEOUT_SECONDS: float`, `LEVEL_LABELS: dict[str, str]`, `CASCADE_KEYS: tuple[str, ...]`, `STYLE_CODE_LABEL: str`, `SIZE_VISIBILITY_LABEL: str`, `pick_style_code(options: list[dict[str, str]]) -> dict[str, str] | None`

`options` là list `{"value": str, "label": str}` đọc từ `<select>` — `value` là giá trị gửi lên WFX, `label` là mã style hiển thị.

- [ ] **Step 1: Write the failing test**

Tạo `tests/test_color_combination.py`:

```python
from wfx_panel.automation import color_combination


def _options(*labels):
    return [
        {"value": str(index), "label": label}
        for index, label in enumerate(labels, start=1)
    ]


def test_picks_the_style_code_with_the_largest_trailing_number():
    """Số đuôi lớn hơn là style mới hơn, không phụ thuộc thứ tự WFX trả về."""
    picked = color_combination.pick_style_code(
        _options("SWV0004012", "SWV0003935")
    )

    assert picked["label"] == "SWV0004012"


def test_single_option_is_used_even_without_digits():
    picked = color_combination.pick_style_code(_options("SAMPLE"))

    assert picked["label"] == "SAMPLE"


def test_falls_back_to_the_last_option_when_no_code_has_digits():
    """WFX sắp xếp tăng dần, nên option cuối là phỏng đoán an toàn nhất."""
    picked = color_combination.pick_style_code(_options("ALPHA", "BETA"))

    assert picked["label"] == "BETA"


def test_ties_prefer_the_later_option():
    picked = color_combination.pick_style_code(
        _options("AAA0003935", "BBB0003935")
    )

    assert picked["label"] == "BBB0003935"


def test_empty_option_list_returns_none():
    assert color_combination.pick_style_code([]) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -v
```

Expected: FAIL với `ModuleNotFoundError: No module named 'wfx_panel.automation.color_combination'`

- [ ] **Step 3: Write minimal implementation**

Tạo `wfx_panel/automation/color_combination.py`:

```python
"""Báo cáo Color Combination - Production: cascade tham số và tải hàng loạt."""

from __future__ import annotations

import re
from collections.abc import Mapping

REPORT_ID = "color_combination_production"
REPORT_NAME = "Color Combination - Production"
POSTBACK_TIMEOUT_SECONDS = 45.0
LEVEL_LABELS = {
    "division": "OC Division",
    "buyer": "Buyer",
    "season": "Season",
    "style_ref": "BuyerStyleReference",
}
CASCADE_KEYS = ("division", "buyer", "season")
STYLE_CODE_LABEL = "StyleCode"
SIZE_VISIBILITY_LABEL = "SizeVisibility"

_TRAILING_DIGITS = re.compile(r"(\d+)\s*$")


def _style_code_rank(label: str) -> int | None:
    match = _TRAILING_DIGITS.search(str(label or ""))
    return int(match.group(1)) if match else None


def pick_style_code(
    options: list[Mapping[str, str]],
) -> dict[str, str] | None:
    """Chọn style mới nhất: mã có số đuôi lớn nhất, hòa thì lấy option sau."""
    cleaned = [dict(option) for option in options or () if option]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    ranked = [
        (rank, index, option)
        for index, option in enumerate(cleaned)
        if (rank := _style_code_rank(option.get("label", ""))) is not None
    ]
    if not ranked:
        return cleaned[-1]
    return max(ranked, key=lambda item: (item[0], item[1]))[2]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/color_combination.py tests/test_color_combination.py
```

Expected: 5 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py tests/test_color_combination.py
git commit -m "feat: chọn StyleCode mới nhất cho báo cáo Color Combination"
```

---

### Task 2: Đặt tên file Excel theo style

**Files:**
- Modify: `wfx_panel/automation/color_combination.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: module `color_combination` từ Task 1
- Produces: `safe_file_stem(style_ref: str, style_code: str) -> str`, `unique_target(directory: Path, stem: str, suffix: str = ".xlsx") -> Path`

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
def test_file_stem_joins_style_reference_and_code():
    stem = color_combination.safe_file_stem("GWSD15176", "SWV0003935")

    assert stem == "GWSD15176 - SWV0003935"


def test_file_stem_replaces_characters_windows_forbids():
    stem = color_combination.safe_file_stem("GW/SD:15176", "SWV*3935")

    assert stem == "GW_SD_15176 - SWV_3935"


def test_file_stem_drops_the_code_part_when_there_is_no_code():
    assert color_combination.safe_file_stem("GWSD15176", "") == "GWSD15176"


def test_file_stem_never_ends_with_a_dot_or_space():
    """Windows từ chối tên file kết thúc bằng dấu chấm hoặc khoảng trắng."""
    assert color_combination.safe_file_stem("GWSD15176.", "") == "GWSD15176"


def test_unique_target_adds_a_counter_when_the_name_is_taken(tmp_path):
    (tmp_path / "GWSD15176.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "GWSD15176 (2).xlsx").write_text("x", encoding="utf-8")

    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176 (3).xlsx"


def test_unique_target_uses_the_plain_name_when_it_is_free(tmp_path):
    target = color_combination.unique_target(tmp_path, "GWSD15176")

    assert target == tmp_path / "GWSD15176.xlsx"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -v
```

Expected: FAIL với `AttributeError: module 'wfx_panel.automation.color_combination' has no attribute 'safe_file_stem'`

- [ ] **Step 3: Write minimal implementation**

Thêm `from pathlib import Path` vào import của `color_combination.py`, rồi thêm:

```python
_FORBIDDEN_FILE_CHARS = re.compile(r'[\\/:*?"<>|]')


def safe_file_stem(style_ref: str, style_code: str) -> str:
    """Tên file theo style; ký tự Windows cấm được thay bằng gạch dưới."""
    reference = str(style_ref or "").strip()
    code = str(style_code or "").strip()
    stem = f"{reference} - {code}" if reference and code else (reference or code)
    stem = _FORBIDDEN_FILE_CHARS.sub("_", stem).strip().rstrip(" .")
    return stem or "report"


def unique_target(
    directory: Path, stem: str, suffix: str = ".xlsx"
) -> Path:
    """Không ghi đè file đã có: thêm hậu tố (2), (3)... như Chrome."""
    target = Path(directory) / f"{stem}{suffix}"
    index = 2
    while target.exists():
        target = Path(directory) / f"{stem} ({index}){suffix}"
        index += 1
    return target
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/color_combination.py tests/test_color_combination.py
```

Expected: 11 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py tests/test_color_combination.py
git commit -m "feat: đặt tên file Excel theo BuyerStyleReference và StyleCode"
```

---

### Task 3: Lọc giá trị cascade đã lưu

**Files:**
- Modify: `wfx_panel/automation/color_combination.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: `CASCADE_KEYS` từ Task 1
- Produces: `prune_selection(values: Mapping[str, str], options_by_key: Mapping[str, list[Mapping[str, str]]]) -> dict[str, str]`

Trả về các cấp còn hợp lệ theo đúng thứ tự `CASCADE_KEYS`. Gặp cấp không hợp lệ thì dừng, các cấp dưới bị bỏ — vì option của cấp dưới do cấp trên sinh ra, giữ lại là giữ dữ liệu của mùa khác.

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
def test_prune_keeps_every_level_that_still_exists():
    values = {"division": "d1", "buyer": "b1", "season": "s1"}
    options = {
        "division": _options("d1"),
        "buyer": _options("b1"),
        "season": _options("s1"),
    }
    options["division"][0]["value"] = "d1"
    options["buyer"][0]["value"] = "b1"
    options["season"][0]["value"] = "s1"

    assert color_combination.prune_selection(values, options) == values


def test_prune_drops_lower_levels_once_one_is_stale():
    """Buyer đổi thì Season của buyer cũ không còn ý nghĩa."""
    values = {"division": "d1", "buyer": "gone", "season": "s1"}
    options = {
        "division": [{"value": "d1", "label": "D1"}],
        "buyer": [{"value": "b1", "label": "B1"}],
        "season": [{"value": "s1", "label": "S1"}],
    }

    assert color_combination.prune_selection(values, options) == {
        "division": "d1"
    }


def test_prune_returns_nothing_when_the_first_level_is_missing():
    assert color_combination.prune_selection({}, {}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -v
```

Expected: FAIL với `AttributeError: ... has no attribute 'prune_selection'`

- [ ] **Step 3: Write minimal implementation**

Thêm vào `color_combination.py`:

```python
def prune_selection(
    values: Mapping[str, str],
    options_by_key: Mapping[str, list[Mapping[str, str]]],
) -> dict[str, str]:
    """Giữ các cấp cascade còn hợp lệ; gặp cấp hỏng thì bỏ luôn cấp dưới."""
    cleaned: dict[str, str] = {}
    for key in CASCADE_KEYS:
        available = {
            str(option.get("value") or "")
            for option in options_by_key.get(key) or ()
        }
        current = str((values or {}).get(key) or "")
        if not current or current not in available:
            break
        cleaned[key] = current
    return cleaned
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/color_combination.py tests/test_color_combination.py
```

Expected: 14 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py tests/test_color_combination.py
git commit -m "feat: bỏ giá trị cascade cũ không còn trên WFX"
```

---

### Task 4: Vòng lặp batch chịu lỗi và chịu Stop

**Files:**
- Modify: `wfx_panel/automation/color_combination.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: module `color_combination` từ Task 1
- Produces:
  - `class StyleFailure(Exception)` với `.code: str` và `.message: str`
  - `batch_styles(style_refs: list[str], run_one: Callable[[str], dict], progress: Callable[..., None] | None = None, log: Callable[[str], None] = print) -> dict`
  - trả `{"saved": list[dict], "failed": list[dict], "cancelled": bool}`
  - `run_one(style_ref)` trả `{"style_ref": str, "style_code": str, "file_path": str, "file_name": str}`
  - mỗi phần tử `failed` là `{"style_ref": str, "code": str, "message": str}`
  - `progress(stage, message, step, total)` — `message` **phải** kết thúc bằng `n/m`, UI đọc đúng hậu tố đó

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
import pytest

from wfx_panel.automation.runtime import AutomationCancelled


def _saved(style_ref):
    return {
        "style_ref": style_ref,
        "style_code": "SWV0000001",
        "file_path": f"D:/out/{style_ref}.xlsx",
        "file_name": f"{style_ref}.xlsx",
    }


def test_batch_continues_after_a_style_fails():
    """50 style một lượt: một style hỏng không được giết cả lượt chạy."""

    def run_one(style_ref):
        if style_ref == "B":
            raise color_combination.StyleFailure(
                "COLOR_REPORT_STYLECODE_MISSING", "Không có StyleCode."
            )
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "C"]
    assert result["failed"] == [
        {
            "style_ref": "B",
            "code": "COLOR_REPORT_STYLECODE_MISSING",
            "message": "Không có StyleCode.",
        }
    ]
    assert result["cancelled"] is False


def test_batch_labels_unexpected_errors_with_a_generic_code():
    def run_one(_style_ref):
        raise ValueError("frame detached")

    result = color_combination.batch_styles(
        ["A"], run_one, log=lambda _line: None
    )

    assert result["failed"][0]["code"] == "COLOR_REPORT_STYLE_FAILED"
    assert "frame detached" in result["failed"][0]["message"]


def test_batch_keeps_saved_files_when_the_user_presses_stop():
    """Stop giữa lượt vẫn phải trả về file đã tải, không mất trắng."""

    def run_one(style_ref):
        if style_ref == "C":
            raise AutomationCancelled("ACTION_CANCELLED")
        return _saved(style_ref)

    result = color_combination.batch_styles(
        ["A", "B", "C", "D"], run_one, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A", "B"]
    assert result["cancelled"] is True


def test_batch_progress_messages_end_with_the_counter_suffix():
    """UI đọc hậu tố n/m để hiện bộ đếm; đổi định dạng là hỏng thẻ tiến độ."""
    seen = []

    color_combination.batch_styles(
        ["A", "B"],
        _saved,
        progress=lambda stage, message, step, total: seen.append(
            (stage, message, step, total)
        ),
        log=lambda _line: None,
    )

    assert [item[1].endswith(suffix) for item, suffix in zip(seen, ("1/2", "2/2"))] == [
        True,
        True,
    ]
    assert seen[0][0] == "style"
    assert seen[1][2:] == (2, 2)


def test_batch_ignores_blank_style_references():
    result = color_combination.batch_styles(
        ["A", "  ", ""], _saved, log=lambda _line: None
    )

    assert [item["style_ref"] for item in result["saved"]] == ["A"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -v
```

Expected: FAIL với `AttributeError: ... has no attribute 'StyleFailure'`

- [ ] **Step 3: Write minimal implementation**

Thêm `from collections.abc import Callable, Mapping` (thay dòng import `Mapping` cũ) và `from wfx_panel.automation.runtime import AutomationCancelled, checkpoint` vào `color_combination.py`, rồi thêm:

```python
class StyleFailure(Exception):
    """Lỗi ở mức một style; vòng lặp ghi lại rồi chạy tiếp style kế."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def batch_styles(
    style_refs: list[str],
    run_one: Callable[[str], dict],
    progress: Callable[..., None] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Chạy từng style, bỏ qua style lỗi, và giữ kết quả khi user bấm Stop."""
    references = [
        str(reference).strip()
        for reference in style_refs or ()
        if str(reference).strip()
    ]
    total = len(references)
    saved: list[dict] = []
    failed: list[dict] = []
    for index, reference in enumerate(references, start=1):
        try:
            checkpoint()
            if progress is not None:
                progress(
                    "style", f"Đang tải {reference}… {index}/{total}", index, total
                )
            saved.append(run_one(reference))
        except AutomationCancelled:
            log(f"[COLOR] Đã dừng theo yêu cầu sau {len(saved)}/{total} style.")
            return {"saved": saved, "failed": failed, "cancelled": True}
        except StyleFailure as failure:
            log(f"[COLOR] Bỏ qua {reference}: {failure.message}")
            failed.append(
                {
                    "style_ref": reference,
                    "code": failure.code,
                    "message": failure.message,
                }
            )
        except Exception as error:
            log(f"[COLOR] Bỏ qua {reference}: {type(error).__name__}: {error}")
            failed.append(
                {
                    "style_ref": reference,
                    "code": "COLOR_REPORT_STYLE_FAILED",
                    "message": f"{type(error).__name__}: {error}",
                }
            )
    return {"saved": saved, "failed": failed, "cancelled": False}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/color_combination.py tests/test_color_combination.py
```

Expected: 19 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py tests/test_color_combination.py
git commit -m "feat: vòng lặp tải hàng loạt bỏ qua style lỗi và giữ kết quả khi Stop"
```

---

### Task 5: Đăng ký báo cáo vào catalog

**Files:**
- Modify: `wfx_panel/automation/reports.py:28-60`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: `REPORT_ID`, `REPORT_NAME` từ Task 1
- Produces: `REPORTS["color_combination_production"]`, `report_catalog()` trả thêm khóa `kind` (`"simple"` hoặc `"cascade_batch"`)

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
from wfx_panel.automation import reports


def test_catalog_exposes_the_kind_so_the_ui_picks_the_right_form():
    """Shipment Summary dùng form tham số một lượt; báo cáo mới dùng cascade."""
    catalog = {item["id"]: item for item in reports.report_catalog()}

    assert catalog["shipment_summary"]["kind"] == "simple"
    assert catalog[color_combination.REPORT_ID]["kind"] == "cascade_batch"
    assert catalog[color_combination.REPORT_ID]["name"] == (
        color_combination.REPORT_NAME
    )


def test_color_combination_report_points_at_the_wfx_custom_report():
    entry = reports.REPORTS[color_combination.REPORT_ID]

    assert entry["custom_report_id"] == "0864e93b-ee5d-4dbc-840e-c83a1b44d728"
    assert entry["custom_report_id"] in entry["url"]
    assert entry["url"].startswith("https://")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -k catalog -v
```

Expected: FAIL với `KeyError: 'kind'`

- [ ] **Step 3: Write minimal implementation**

Trong `wfx_panel/automation/reports.py`, thêm `"kind": "simple"` vào entry `shipment_summary` và thêm entry mới vào dict `REPORTS`:

```python
    "color_combination_production": {
        "id": "color_combination_production",
        "name": "Color Combination - Production",
        "kind": "cascade_batch",
        "custom_report_id": "0864e93b-ee5d-4dbc-840e-c83a1b44d728",
        "url": (
            "https://prosports.worldfashionexchange.com/WFXBase4.0/"
            "WFXBICustomReportView.aspx?BICustomReportID="
            "0864e93b-ee5d-4dbc-840e-c83a1b44d728&Path="
            "/WFXPSHLIVE/Production%20Reports/"
            "Color%20combination%20cost%20sheet_Production&"
            "LoginID=psh45&GUID=cc0170bb-4722-47fa-928e-8d5d6e4c6c03&"
            "ReportParams="
        ),
    },
```

Sửa `report_catalog()`:

```python
def report_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "kind": item.get("kind", "simple"),
        }
        for item in REPORTS.values()
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/reports.py
```

Expected: 21 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/reports.py tests/test_color_combination.py
git commit -m "feat: đăng ký báo cáo Color Combination vào catalog"
```

---

### Task 6: Primitive postback và resolve control theo nhãn

**Files:**
- Modify: `wfx_panel/automation/reports.py` (thêm sau `_open_report`, khoảng dòng 102)
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: `PARAMETER_TABLE`, `_wait`, `checkpoint` đã có trong `reports.py`
- Produces:
  - `_wait_postback_settled(page: Page, timeout_s: float = 45.0) -> None` — raise `PlaywrightTimeoutError` khi quá hạn
  - `resolve_controls(page: Page) -> dict[str, str]` — map `{nhãn tham số: element id}`
  - `read_select_options(page: Page, control_id: str) -> list[dict[str, str]]`
  - `read_select_value(page: Page, control_id: str) -> str`

Không hardcode control id: ReportViewer render lại bảng tham số sau mỗi postback nên id có thể đổi. Nhãn lấy từ `valueCell.previousElementSibling` đúng như `_read_parameters` đang làm.

- [ ] **Step 1: Write the failing test**

Test dùng fake page vì đây là lớp mỏng bọc `evaluate`. Thêm vào cuối `tests/test_color_combination.py`:

```python
class _FakeLocator:
    def __init__(self, payload):
        self._payload = payload

    def evaluate(self, _script, *_args):
        return self._payload


class _FakePage:
    def __init__(self, payload):
        self._payload = payload
        self.selectors = []

    def locator(self, selector):
        self.selectors.append(selector)
        return _FakeLocator(self._payload)


def test_resolve_controls_maps_parameter_labels_to_element_ids():
    page = _FakePage(
        {
            "OC Division": "ctl04_ctl03_ddValue",
            "BuyerStyleReference": "ctl04_ctl09_ddValue",
        }
    )

    controls = reports.resolve_controls(page)

    assert controls["BuyerStyleReference"] == "ctl04_ctl09_ddValue"
    assert reports.PARAMETER_TABLE in page.selectors[0]


def test_read_select_options_returns_value_and_label_pairs():
    page = _FakePage([{"value": "1", "label": "GWSD15176"}])

    options = reports.read_select_options(page, "ctl04_ctl09_ddValue")

    assert options == [{"value": "1", "label": "GWSD15176"}]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -k "resolve_controls or read_select" -v
```

Expected: FAIL với `AttributeError: module 'wfx_panel.automation.reports' has no attribute 'resolve_controls'`

- [ ] **Step 3: Write minimal implementation**

Thêm vào `wfx_panel/automation/reports.py`:

```python
POSTBACK_SETTLE_SECONDS = 0.5


def _wait_postback_settled(page: Page, timeout_s: float = 45.0) -> None:
    """Chờ async postback của ReportViewer xong và ổn định trước khi đọc lại."""
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    while time.monotonic() < deadline:
        checkpoint()
        now = time.monotonic()
        try:
            busy = bool(
                page.evaluate(
                    """() => {
                      const manager = window.Sys?.WebForms?.PageRequestManager
                        ?.getInstance?.();
                      if (manager?.get_isInAsyncPostBack?.()) return true;
                      return [...document.querySelectorAll(
                        '[id*="AsyncWait"], [aria-busy="true"]'
                      )].some(element => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none' &&
                          style.visibility !== 'hidden' &&
                          rect.width > 0 && rect.height > 0;
                      });
                    }"""
                )
            )
            if busy:
                stable_since = 0.0
            elif not stable_since:
                stable_since = now
            elif now - stable_since >= POSTBACK_SETTLE_SECONDS:
                return
        except PlaywrightError:
            stable_since = 0.0
        _wait(page, 100)
    raise PlaywrightTimeoutError(
        f"Tham số báo cáo chưa nạp xong sau {int(timeout_s)} giây."
    )


def resolve_controls(page: Page) -> dict[str, str]:
    """Map nhãn tham số sang element id; id đổi sau mỗi postback nên đọc lại."""
    return page.locator(PARAMETER_TABLE).evaluate(
        """table => {
          const controls = {};
          for (const element of table.querySelectorAll('input, select')) {
            if (!element.id || element.type === 'hidden') continue;
            const valueCell = element.closest('td, th');
            const label = (valueCell?.previousElementSibling?.textContent || '')
              .replace(/\\s+/g, ' ').trim();
            if (label && !(label in controls)) controls[label] = element.id;
          }
          return controls;
        }"""
    )


def read_select_options(page: Page, control_id: str) -> list[dict[str, str]]:
    cleaned = str(control_id or "").replace(chr(34), "")
    if not cleaned:
        return []
    return page.locator(f'[id="{cleaned}"]').evaluate(
        """element => [...(element.options || [])].map(option => ({
          value: option.value,
          label: (option.textContent || option.value).trim(),
        })).filter(option => option.label)"""
    )


def read_select_value(page: Page, control_id: str) -> str:
    cleaned = str(control_id or "").replace(chr(34), "")
    if not cleaned:
        return ""
    return str(
        page.locator(f'[id="{cleaned}"]').evaluate("element => element.value || ''")
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/automation/reports.py
```

Expected: 23 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/reports.py tests/test_color_combination.py
git commit -m "feat: chờ postback và resolve control ReportViewer theo nhãn"
```

---

### Task 7: Nạp option cascade từ WFX

**Files:**
- Modify: `wfx_panel/automation/color_combination.py`
- Modify: `wfx_panel/automation/__init__.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: `resolve_controls`, `read_select_options`, `read_select_value`, `_wait_postback_settled`, `_open_report`, `REPORTS` từ Task 5–6; `prune_selection`, `LEVEL_LABELS`, `CASCADE_KEYS` từ Task 1–3
- Produces:
  - `select_and_settle(page, controls, label, value) -> dict[str, str]` — trả control map mới
  - `read_cascade(page, values) -> dict` — trả `{"levels": {key: {"options": [...], "value": str}}}`
  - `load_color_report_options(values: Mapping[str, str] | None, log=print) -> dict`

`load_color_report_options` trả `_result(...)` với code `COLOR_REPORT_OPTIONS_READY`, kèm `levels`, `report_id`, `report_name`.

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
class _CascadePage:
    """Giả lập ReportViewer: đổi một cấp thì cấp dưới đổi theo."""

    OPTIONS = {
        "OC Division": [{"value": "d1", "label": "PRO SPORTS - WOVEN HANOI"}],
        "Buyer": [{"value": "b1", "label": "J.LINDEBERG"}],
        "Season": [{"value": "s1", "label": "WH25"}],
        "BuyerStyleReference": [
            {"value": "r1", "label": "GWSD15176"},
            {"value": "r2", "label": "GWSD15177"},
        ],
    }

    def __init__(self):
        self.selected = {}
        self.settled = 0


def _install_cascade_fakes(monkeypatch, page):
    monkeypatch.setattr(
        color_combination, "resolve_controls", lambda _page: {
            label: f"id::{label}" for label in _CascadePage.OPTIONS
        }
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_options",
        lambda _page, control_id: _CascadePage.OPTIONS[control_id.split("::")[1]],
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_value",
        lambda _page, control_id: page.selected.get(control_id.split("::")[1], ""),
    )

    def fake_select(_page, controls, label, value):
        page.selected[label] = value
        page.settled += 1
        return controls

    monkeypatch.setattr(color_combination, "select_and_settle", fake_select)


def test_read_cascade_applies_saved_values_and_returns_every_level(monkeypatch):
    page = _CascadePage()
    _install_cascade_fakes(monkeypatch, page)

    levels = color_combination.read_cascade(
        page, {"division": "d1", "buyer": "b1", "season": "s1"}
    )["levels"]

    assert page.selected["Season"] == "s1"
    assert levels["style_ref"]["options"] == _CascadePage.OPTIONS[
        "BuyerStyleReference"
    ]
    assert levels["division"]["value"] == "d1"


def test_read_cascade_stops_applying_at_the_first_stale_value(monkeypatch):
    """Division cũ không còn thì không được áp Buyer/Season của lần trước."""
    page = _CascadePage()
    _install_cascade_fakes(monkeypatch, page)

    color_combination.read_cascade(
        page, {"division": "gone", "buyer": "b1", "season": "s1"}
    )

    assert page.selected == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -k cascade -v
```

Expected: FAIL với `AttributeError: ... has no attribute 'read_cascade'`

- [ ] **Step 3: Write minimal implementation**

Thêm vào `color_combination.py` (import thêm `from wfx_panel.automation._common import Page, Playwright, PlaywrightTimeoutError, _result, _write_log, sync_playwright`, `from wfx_panel.automation.browser import _attach_dialog_handler, _chrome_is_ready, _connect_to_chrome`, `from wfx_panel.automation.session import _session_is_active`, và `from wfx_panel.automation.reports import REPORTS, _open_report, _wait_postback_settled, read_select_options, read_select_value, resolve_controls`):

```python
def select_and_settle(
    page: Page,
    controls: Mapping[str, str],
    label: str,
    value: str,
) -> dict[str, str]:
    """Đặt một select rồi chờ WFX nạp xong các tham số phía dưới."""
    checkpoint()
    control_id = str(controls.get(label) or "").replace(chr(34), "")
    if not control_id:
        raise StyleFailure(
            "COLOR_REPORT_OPTIONS_NOT_READY",
            f"Không tìm thấy tham số {label} trên báo cáo.",
        )
    page.locator(f'[id="{control_id}"]').select_option(str(value))
    _wait_postback_settled(page, POSTBACK_TIMEOUT_SECONDS)
    return resolve_controls(page)


def read_cascade(page: Page, values: Mapping[str, str] | None) -> dict:
    """Áp giá trị đã lưu tới cấp còn hợp lệ rồi đọc option của mọi cấp."""
    controls = resolve_controls(page)
    wanted = dict(values or {})
    levels: dict[str, dict] = {}
    for key in CASCADE_KEYS:
        label = LEVEL_LABELS[key]
        options = read_select_options(page, controls.get(label, ""))
        levels[key] = {"options": options, "value": ""}
        allowed = prune_selection(wanted, {key: options})
        target = allowed.get(key, "")
        if target and target != read_select_value(page, controls.get(label, "")):
            controls = select_and_settle(page, controls, label, target)
            options = read_select_options(page, controls.get(label, ""))
            levels[key] = {"options": options, "value": target}
        elif target:
            levels[key]["value"] = target
        else:
            # Cấp này không áp được thì các cấp dưới là của lựa chọn khác.
            wanted = {}
        levels[key]["value"] = levels[key]["value"] or read_select_value(
            page, controls.get(label, "")
        )
    style_label = LEVEL_LABELS["style_ref"]
    levels["style_ref"] = {
        "options": read_select_options(page, controls.get(style_label, "")),
        "value": read_select_value(page, controls.get(style_label, "")),
    }
    return {"levels": levels}


def load_color_report_options(
    values: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    report = REPORTS[REPORT_ID]
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        _write_log(log, f"[COLOR] Đang tải tham số {report['name']}...")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        cascade = read_cascade(report_page, values)
        styles = cascade["levels"]["style_ref"]["options"]
        if cascade["levels"]["season"]["value"] and not styles:
            return _result(
                False,
                "COLOR_REPORT_STYLE_LIST_EMPTY",
                "Mùa đang chọn không có BuyerStyleReference nào.",
            )
        _write_log(log, f"[COLOR] Đã đọc {len(styles)} style.")
        return _result(
            True,
            "COLOR_REPORT_OPTIONS_READY",
            f"Đã tải tham số cho {report['name']}.",
            report_id=REPORT_ID,
            report_name=report["name"],
            **cascade,
        )
    except StyleFailure as failure:
        return _result(False, failure.code, failure.message)
    except PlaywrightTimeoutError as error:
        return _result(False, "COLOR_REPORT_OPTIONS_NOT_READY", str(error))
    except Exception as error:
        return _result(
            False, "REPORT_LOAD_FAILED", f"{type(error).__name__}: {error}"
        )
    finally:
        if playwright is not None:
            playwright.stop()
```

Trong `wfx_panel/automation/__init__.py`, thêm re-export cạnh các export report hiện có:

```python
from wfx_panel.automation.color_combination import (
    load_color_report_options,
    run_color_report_batch,
)
```

(Import này chỉ chạy được sau Task 8; nếu Task 8 chưa xong thì tạm chỉ export `load_color_report_options` và bổ sung ở Task 8.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/
```

Expected: 25 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py wfx_panel/automation/__init__.py tests/test_color_combination.py
git commit -m "feat: nạp option cascade Division/Buyer/Season/Style từ WFX"
```

---

### Task 8: Chạy vòng lặp thật và lưu file

**Files:**
- Modify: `wfx_panel/automation/color_combination.py`
- Modify: `wfx_panel/automation/__init__.py`
- Test: `tests/test_color_combination.py`

**Interfaces:**
- Consumes: `batch_styles`, `pick_style_code`, `safe_file_stem`, `unique_target`, `select_and_settle`, `resolve_controls`, `read_select_options`, `read_select_value`
- Consumes từ `reports.py`: `_click_view_report`, `_wait_report_ready`, `_export_excel`, `_open_report`
- Produces: `run_color_report_batch(selection: Mapping[str, str], style_refs: list[str], output_dir: str, log=print, progress=None) -> dict`

Trả code `COLOR_REPORT_BATCH_DONE` (`ok=True`) hoặc `COLOR_REPORT_CANCELLED` (`ok=False`), kèm `saved`, `failed`, `output_dir`.

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `tests/test_color_combination.py`:

```python
def test_run_one_style_saves_the_native_download_under_the_style_name(
    monkeypatch, tmp_path
):
    """File native của Chrome được sao chép sang thư mục user chọn."""
    source = tmp_path / "downloaded.xlsx"
    source.write_text("excel", encoding="utf-8")
    controls = {"BuyerStyleReference": "id::ref", "StyleCode": "id::code"}

    monkeypatch.setattr(
        color_combination, "select_and_settle", lambda *_a, **_k: controls
    )
    monkeypatch.setattr(
        color_combination,
        "read_select_options",
        lambda _page, _id: [{"value": "c1", "label": "SWV0003935"}],
    )
    monkeypatch.setattr(color_combination, "read_select_value", lambda *_a: "")
    monkeypatch.setattr(color_combination, "_view_and_download", lambda *_a: source)

    saved = color_combination._run_one_style(
        object(), controls, "GWSD15176", tmp_path, lambda _line: None
    )

    assert saved["style_code"] == "SWV0003935"
    assert saved["file_name"] == "GWSD15176 - SWV0003935.xlsx"
    assert (tmp_path / "GWSD15176 - SWV0003935.xlsx").read_text(
        encoding="utf-8"
    ) == "excel"


def test_run_one_style_reports_a_missing_style_code(monkeypatch, tmp_path):
    controls = {"BuyerStyleReference": "id::ref", "StyleCode": "id::code"}
    monkeypatch.setattr(
        color_combination, "select_and_settle", lambda *_a, **_k: controls
    )
    monkeypatch.setattr(color_combination, "read_select_options", lambda *_a: [])

    with pytest.raises(color_combination.StyleFailure) as error:
        color_combination._run_one_style(
            object(), controls, "GWSD15176", tmp_path, lambda _line: None
        )

    assert error.value.code == "COLOR_REPORT_STYLECODE_MISSING"


def test_batch_requires_a_style_selection(tmp_path):
    result = color_combination.run_color_report_batch(
        {"division": "d1"}, [], str(tmp_path), log=lambda _line: None
    )

    assert result["code"] == "COLOR_REPORT_NO_STYLE_SELECTED"
    assert result["ok"] is False


def test_batch_requires_an_existing_output_directory(tmp_path):
    result = color_combination.run_color_report_batch(
        {"division": "d1"},
        ["GWSD15176"],
        str(tmp_path / "khong-ton-tai"),
        log=lambda _line: None,
    )

    assert result["code"] == "COLOR_REPORT_OUTPUT_DIR_REQUIRED"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_color_combination.py -k "run_one_style or batch_requires" -v
```

Expected: FAIL với `AttributeError: ... has no attribute '_run_one_style'`

- [ ] **Step 3: Write minimal implementation**

Thêm `import shutil` và `from wfx_panel.automation.reports import _click_view_report, _export_excel, _wait_report_ready` vào `color_combination.py`, rồi thêm:

```python
def _view_and_download(page: Page, log: Callable[[str], None]) -> Path:
    """Chạy report rồi trả về file Chrome vừa tải trong Downloads."""
    from wfx_panel.automation.runtime import _user_downloads_dir

    _click_view_report(page)
    _wait_report_ready(page, log)
    file_name = _export_excel(page)
    return _user_downloads_dir() / file_name


def _run_one_style(
    page: Page,
    controls: Mapping[str, str],
    style_ref: str,
    output_dir: Path,
    log: Callable[[str], None],
) -> dict:
    """Một style: chọn ref, chọn StyleCode mới nhất, chạy report, lưu file."""
    current = select_and_settle(
        page, controls, LEVEL_LABELS["style_ref"], style_ref
    )
    style_options = read_select_options(
        page, current.get(STYLE_CODE_LABEL, "")
    )
    picked = pick_style_code(style_options)
    if picked is None:
        raise StyleFailure(
            "COLOR_REPORT_STYLECODE_MISSING",
            f"Không có StyleCode cho {style_ref}.",
        )
    if len(style_options) > 1:
        current = select_and_settle(
            page, current, STYLE_CODE_LABEL, picked["value"]
        )
    # SizeVisibility luôn phải là Yes; chỉ đặt khi đang khác để tránh
    # một postback thừa cho mỗi style.
    size_id = current.get(SIZE_VISIBILITY_LABEL, "")
    if size_id:
        for option in read_select_options(page, size_id):
            if option["label"].strip().casefold() == "yes":
                if read_select_value(page, size_id) != option["value"]:
                    current = select_and_settle(
                        page, current, SIZE_VISIBILITY_LABEL, option["value"]
                    )
                break
    # OCNum giữ nguyên mặc định WFX: nó được nạp lại theo style và
    # mặc định đã chọn hết PO.
    source = _view_and_download(page, log)
    target = unique_target(
        Path(output_dir), safe_file_stem(style_ref, picked["label"])
    )
    try:
        shutil.copy2(source, target)
    except OSError as error:
        raise StyleFailure(
            "COLOR_REPORT_SAVE_FAILED",
            f"Không lưu được file cho {style_ref}: {type(error).__name__}",
        ) from error
    return {
        "style_ref": style_ref,
        "style_code": picked["label"],
        "file_path": str(target),
        "file_name": target.name,
    }


def run_color_report_batch(
    selection: Mapping[str, str],
    style_refs: list[str],
    output_dir: str,
    log: Callable[[str], None] = print,
    progress: Callable[..., None] | None = None,
) -> dict:
    references = [
        str(item).strip() for item in style_refs or () if str(item).strip()
    ]
    if not references:
        return _result(
            False,
            "COLOR_REPORT_NO_STYLE_SELECTED",
            "Hãy chọn ít nhất một BuyerStyleReference trước khi tải.",
        )
    target_dir = Path(str(output_dir or ""))
    if not str(output_dir or "").strip() or not target_dir.is_dir():
        return _result(
            False,
            "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
            "Hãy chọn thư mục lưu báo cáo trước khi tải.",
        )
    report = REPORTS[REPORT_ID]
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        read_cascade(report_page, selection)
        controls = resolve_controls(report_page)
        outcome = batch_styles(
            references,
            lambda reference: _run_one_style(
                report_page, controls, reference, target_dir, log
            ),
            progress=progress,
            log=log,
        )
        saved = outcome["saved"]
        failed = outcome["failed"]
        if outcome["cancelled"]:
            return _result(
                False,
                "COLOR_REPORT_CANCELLED",
                f"Đã dừng theo yêu cầu. Đã tải {len(saved)}/{len(references)} style.",
                saved=saved,
                failed=failed,
                output_dir=str(target_dir),
            )
        message = f"Đã tải {len(saved)}/{len(references)} style."
        if failed:
            message += f" {len(failed)} style lỗi."
        return _result(
            True,
            "COLOR_REPORT_BATCH_DONE",
            message,
            saved=saved,
            failed=failed,
            output_dir=str(target_dir),
        )
    except Exception as error:
        return _result(
            False, "REPORT_EXPORT_FAILED", f"{type(error).__name__}: {error}"
        )
    finally:
        if playwright is not None:
            playwright.stop()
```

Nếu Task 7 chưa export `run_color_report_batch` trong `wfx_panel/automation/__init__.py`, bổ sung bây giờ.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_color_combination.py -v && ruff check wfx_panel/
```

Expected: 29 passed, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/automation/color_combination.py wfx_panel/automation/__init__.py tests/test_color_combination.py
git commit -m "feat: chạy report từng style và lưu Excel theo tên style"
```

---

### Task 9: Bridge PanelAPI, mã lỗi và telemetry

**Files:**
- Modify: `wfx_panel/panel_api.py` (`NON_REPORTABLE_FAILURES` ~dòng 159, danh sách method reportable ~dòng 862, thêm method sau `export_report_excel` ~dòng 1338)
- Modify: `wfx_panel/telemetry.py` (`ERROR_CODE_INFO`, cạnh `REPORT_EXPORT_FAILED` ~dòng 843)
- Test: `tests/test_panel_api.py`

**Interfaces:**
- Consumes: `load_color_report_options`, `run_color_report_batch` từ Task 7–8; `self._run`, `self._progress_for`, `self._saved_report_parameters`, `self.save_report_parameters` đã có
- Produces: `PanelAPI.load_color_report_options(values)`, `PanelAPI.run_color_report_batch(selection, style_refs, output_dir)`

`load_color_report_options` khi được gọi với `values` rỗng thì dùng lựa chọn đã lưu của tài khoản; `run_color_report_batch` lưu lại lựa chọn trước khi chạy. Cả hai dùng `report-parameters.json` sẵn có với `report_id = "color_combination_production"`, không thêm file lưu trữ mới.

- [ ] **Step 1: Write the failing test**

Thêm vào `tests/test_panel_api.py`. `FakeLogin` ở đầu file là login giả dùng chung; thêm hai method vào class đó:

```python
    def load_color_report_options(self, values, log=print):
        self.calls.append(("load_color_report_options", dict(values)))
        return {
            "ok": True,
            "code": "COLOR_REPORT_OPTIONS_READY",
            "message": "ok",
            "levels": {"division": {"options": [], "value": ""}},
        }

    def run_color_report_batch(
        self, selection, style_refs, output_dir, log=print, progress=None
    ):
        self.calls.append(("run_color_report_batch", dict(selection)))
        if progress is not None:
            progress("style", "Đang tải GWSD15176… 1/1", 1, 1)
        return {
            "ok": True,
            "code": "COLOR_REPORT_BATCH_DONE",
            "message": "ok",
            "saved": [],
            "failed": [],
            "output_dir": output_dir,
        }
```

Rồi thêm các test:

```python
def test_color_report_batch_passes_progress_with_its_own_method(tmp_path):
    """Thẻ tiến độ rẽ theo `method`; sai method là đè nhầm thẻ GDN/Sale ASN."""
    fake = FakeLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    seen = {}
    api.set_progress_sink(seen.update)

    api.run_color_report_batch({"division": "d1"}, ["GWSD15176"], str(tmp_path))

    assert seen["method"] == "run_color_report_batch"
    assert seen["message"].endswith("1/1")


def test_color_report_remembers_the_cascade_between_sessions(tmp_path):
    """Mở lại app không phải chọn lại Division/Buyer/Season."""
    fake = FakeLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    api.save_account("psh45", "secret")

    api.run_color_report_batch(
        {"division": "d1", "buyer": "b1", "season": "s1"},
        ["GWSD15176"],
        str(tmp_path),
    )
    reopened = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    reopened.load_color_report_options({})

    assert fake.calls[-1] == (
        "load_color_report_options",
        {"division": "d1", "buyer": "b1", "season": "s1"},
    )


def test_color_report_user_errors_are_not_reported_to_telemetry():
    for code in (
        "COLOR_REPORT_NO_STYLE_SELECTED",
        "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
        "COLOR_REPORT_STYLE_LIST_EMPTY",
        "COLOR_REPORT_CANCELLED",
    ):
        assert code in panel_api.NON_REPORTABLE_FAILURES


def test_reportable_color_report_codes_have_telemetry_guidance():
    for code in ("COLOR_REPORT_OPTIONS_NOT_READY", "COLOR_REPORT_SAVE_FAILED"):
        assert code not in panel_api.NON_REPORTABLE_FAILURES
        assert code in telemetry.ERROR_CODE_INFO
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_panel_api.py -k color_report -v
```

Expected: FAIL với `AssertionError` (mã chưa có trong `NON_REPORTABLE_FAILURES`)

- [ ] **Step 3: Write minimal implementation**

Trong `wfx_panel/panel_api.py`, thêm vào `NON_REPORTABLE_FAILURES`:

```python
        "COLOR_REPORT_NO_STYLE_SELECTED",
        "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
        "COLOR_REPORT_STYLE_LIST_EMPTY",
        "COLOR_REPORT_CANCELLED",
```

Thêm hai tên method vào set method được gửi telemetry (cạnh `"load_report_parameters"`, `"export_report_excel"` khoảng dòng 862):

```python
                "load_color_report_options",
                "run_color_report_batch",
```

Thêm method sau `export_report_excel`:

```python
    def load_color_report_options(
        self, values: Mapping[str, Any] | None = None
    ) -> dict:
        loader = getattr(self._login, "load_color_report_options", None)
        if not callable(loader):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ báo cáo này.",
            }
        safe_values = {
            str(key): str(value)[:500]
            for key, value in dict(values or {}).items()
            if isinstance(value, (str, int, float))
        }
        if not safe_values:
            # Mở module lần sau dùng lại lựa chọn đã lưu của chính tài khoản này.
            saved = self._saved_report_parameters("color_combination_production")
            safe_values = {
                key: str(saved.get(key) or "")
                for key in ("division", "buyer", "season")
                if str(saved.get(key) or "")
            }
        return self._run(
            "load_color_report_options",
            lambda: loader(safe_values, self._log),
            {"module_id": "reports", "report_id": "color_combination_production"},
        )

    def run_color_report_batch(
        self,
        selection: Mapping[str, Any] | None = None,
        style_refs: list[str] | None = None,
        output_dir: str = "",
    ) -> dict:
        runner = getattr(self._login, "run_color_report_batch", None)
        if not callable(runner):
            return {
                "ok": False,
                "code": "REPORT_UNAVAILABLE",
                "message": "Phiên bản tự động hóa chưa hỗ trợ báo cáo này.",
            }
        safe_selection = {
            str(key): str(value)[:500]
            for key, value in dict(selection or {}).items()
            if isinstance(value, (str, int, float))
        }
        safe_refs = [
            str(item)[:200] for item in (style_refs or [])[:500] if str(item).strip()
        ]
        method = "run_color_report_batch"
        # Lưu cascade trước khi chạy để lần mở sau không phải chọn lại.
        self.save_report_parameters("color_combination_production", safe_selection)
        return self._run(
            method,
            lambda: runner(
                safe_selection,
                safe_refs,
                str(output_dir or ""),
                self._log,
                progress=self._progress_for(method),
            ),
            {"module_id": "reports", "style_count": len(safe_refs)},
        )
```

Trong `wfx_panel/telemetry.py`, thêm vào `ERROR_CODE_INFO` cạnh `REPORT_EXPORT_FAILED`:

```python
        "COLOR_REPORT_OPTIONS_NOT_READY": (
            "Tham số báo cáo Color Combination chưa nạp xong",
            "Chờ trang WFX ổn định rồi chọn lại OC Division.",
        ),
        "COLOR_REPORT_SAVE_FAILED": (
            "Không lưu được file báo cáo vào thư mục đã chọn",
            "Kiểm tra quyền ghi và dung lượng của thư mục lưu báo cáo.",
        ),
```

Trong `wfx_panel/telemetry.py` còn hai bảng nữa phải khai báo, nếu không telemetry sẽ gửi tên method thô thay vì mô tả:

`METHOD_LABELS` (dòng ~31):

```python
    "load_color_report_options": "Tải tham số Color Combination",
    "run_color_report_batch": "Tải hàng loạt Color Combination",
```

`_METHOD_MODULES` (dòng ~870):

```python
    "load_color_report_options": "Reports",
    "run_color_report_batch": "Reports",
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_panel_api.py tests/test_color_combination.py -v && ruff check wfx_panel/
```

Expected: tất cả PASS, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/panel_api.py wfx_panel/telemetry.py wfx_panel/panel_app.py tests/test_panel_api.py
git commit -m "feat: bridge PanelAPI và mã lỗi cho báo cáo Color Combination"
```

---

### Task 10: Nhớ thư mục lưu báo cáo

**Files:**
- Modify: `wfx_panel/prefs.py` (`load_prefs` ~dòng 724, `save_prefs` ~dòng 835, `_write_prefs` ~dòng 897)
- Modify: `wfx_panel/panel_app.py` (thêm method cạnh `choose_costing_export_file` ~dòng 685; đăng ký lên `self.api` cạnh dòng 2617)
- Test: `tests/test_prefs.py`

**Interfaces:**
- Consumes: pattern `costing_export_dir` sẵn có
- Produces: `prefs` key `report_export_dir`, `PanelApp.choose_report_export_dir() -> dict` và `PanelApp.open_report_export_dir(path: str) -> dict`, cả hai gắn lên `self.api`

- [ ] **Step 1: Write the failing test**

Thêm vào `tests/test_prefs.py`:

```python
def test_report_export_dir_round_trips(tmp_path):
    """Thư mục lưu báo cáo phải sống qua lần mở app sau."""
    prefs.save_prefs(tmp_path, report_export_dir="D:\\Reports")

    assert prefs.load_prefs(tmp_path)["report_export_dir"] == "D:\\Reports"


def test_report_export_dir_defaults_to_empty(tmp_path):
    assert prefs.load_prefs(tmp_path)["report_export_dir"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_prefs.py -k report_export_dir -v
```

Expected: FAIL với `KeyError: 'report_export_dir'`

- [ ] **Step 3: Write minimal implementation**

Trong `wfx_panel/prefs.py`, ba chỗ, mô phỏng đúng `sale_asn_import_dir`:

1. `load_prefs` — thêm cạnh `"sale_asn_import_dir"`:
```python
        "report_export_dir": str(
            data.get("report_export_dir") or ""
        ),
```
2. `save_prefs` — thêm tham số `report_export_dir: str | None = None,` và truyền xuống `_write_prefs(..., report_export_dir=report_export_dir, ...)`.
3. `_write_prefs` — thêm tham số `report_export_dir: str | None,` và:
```python
    if report_export_dir is not None:
        current["report_export_dir"] = str(report_export_dir).strip()[:32_000]
```

Trong `wfx_panel/panel_app.py`, thêm method:

```python
    def choose_report_export_dir(self) -> dict:
        """Chọn thư mục lưu báo cáo hàng loạt; nhớ cho lần chạy sau."""
        if self.window is None:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_UNAVAILABLE",
                "message": "Cửa sổ chọn thư mục chưa sẵn sàng.",
            }
        saved_directory = str(
            prefs.load_prefs(self._base_dir).get("report_export_dir") or ""
        ).strip()
        if not saved_directory or not Path(saved_directory).is_dir():
            saved_directory = ""
        try:
            selected = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=saved_directory,
            )
        except Exception as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_FAILED",
                "message": f"Không mở được cửa sổ chọn thư mục: {error}",
            }
        if not selected:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_CANCELLED",
                "message": "Đã hủy chọn thư mục lưu báo cáo.",
            }
        try:
            target = _dialog_selected_path(selected)
        except ValueError as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_DIALOG_FAILED",
                "message": str(error),
            }
        try:
            prefs.save_prefs(self._base_dir, report_export_dir=str(target))
        except OSError:
            pass
        return {
            "ok": True,
            "code": "REPORT_DIR_SELECTED",
            "message": f"Sẽ lưu báo cáo vào {target.name}.",
            "output_dir": str(target),
        }
```

Thêm method mở thư mục — `_reveal_downloaded_file` chỉ nhận file, còn ở đây user cần mở chính thư mục chứa cả lượt tải:

```python
    def open_report_export_dir(self, path: str = "") -> dict:
        """Mở thư mục chứa các file báo cáo vừa tải."""
        directory = Path(str(path or "")).expanduser()
        if not directory.is_dir():
            return {
                "ok": False,
                "code": "REPORT_DIR_MISSING",
                "message": "Thư mục lưu báo cáo không còn tồn tại.",
            }
        if os.name != "nt":
            return {"ok": False, "code": "REPORT_DIR_MISSING", "message": "Không hỗ trợ."}
        try:
            os.startfile(directory)  # type: ignore[attr-defined]
        except (OSError, ValueError) as error:
            return {
                "ok": False,
                "code": "REPORT_DIR_MISSING",
                "message": f"Không mở được thư mục: {type(error).__name__}",
            }
        return {
            "ok": True,
            "code": "REPORT_DIR_OPENED",
            "message": f"Đã mở {directory.name}.",
        }
```

Đăng ký cạnh dòng 2617:

```python
        self.api.choose_report_export_dir = self.choose_report_export_dir  # type: ignore[attr-defined]
        self.api.open_report_export_dir = self.open_report_export_dir  # type: ignore[attr-defined]
```

Thêm bốn mã vào `NON_REPORTABLE_FAILURES` trong `panel_api.py`: `"REPORT_DIR_DIALOG_CANCELLED"`, `"REPORT_DIR_DIALOG_UNAVAILABLE"`, `"REPORT_DIR_DIALOG_FAILED"`, `"REPORT_DIR_MISSING"`.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_prefs.py tests/test_panel_app.py -v && ruff check wfx_panel/
```

Expected: tất cả PASS, ruff sạch

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/prefs.py wfx_panel/panel_app.py wfx_panel/panel_api.py tests/test_prefs.py
git commit -m "feat: nhớ thư mục lưu báo cáo hàng loạt"
```

---

### Task 11: Khung HTML và CSS cho workspace mới

**Files:**
- Modify: `wfx_panel/ui/index.html:821-842`
- Modify: `wfx_panel/ui/style.css`
- Test: `tests/test_ui_assets.py`

**Interfaces:**
- Consumes: không có
- Produces: DOM class dùng ở Task 12–13 — `.color-report-workspace`, `.color-report-level` (`data-level="division|buyer|season"`), `.color-report-batch-toggle`, `.color-report-style-list`, `.color-report-style-filter`, `.color-report-style-count`, `.color-report-single-style`, `.color-report-dir-path`, `.color-report-progress-card`, `.color-report-progress-count`, `.color-report-progress-style`, `.color-report-result-card`; `data-module-action` mới: `report-color-combination`, `color-report-level-change`, `color-report-select-all`, `color-report-clear-all`, `color-report-choose-dir`, `color-report-run`, `color-report-retry-failed`, `color-report-open-dir`

- [ ] **Step 1: Write the failing test**

Thêm vào `tests/test_ui_assets.py`:

```python
def test_color_report_workspace_exists_with_its_controls():
    html = (UI / "index.html").read_text(encoding="utf-8")

    assert 'class="color-report-workspace"' in html
    for action in (
        "report-color-combination",
        "color-report-select-all",
        "color-report-clear-all",
        "color-report-choose-dir",
        "color-report-run",
    ):
        assert f'data-module-action="{action}"' in html


def test_color_report_result_and_progress_cards_start_hidden():
    """Mở module lần sau không được thấy kết quả của lượt chạy trước."""
    html = (UI / "index.html").read_text(encoding="utf-8")

    for block in ("color-report-progress-card", "color-report-result-card"):
        marker = html.index(block)
        assert "hidden" in html[marker : marker + 200]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_ui_assets.py -k color_report -v
```

Expected: FAIL với `AssertionError` (chưa có markup)

- [ ] **Step 3: Write minimal implementation**

Trong `wfx_panel/ui/index.html`, thêm nút thứ hai vào `<section class="reports-list">` ngay sau nút Shipment Summary:

```html
            <button type="button" class="workflow-choice workflow-choice-wide" data-module-action="report-color-combination">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4V5Z"/><path d="M4 10h16M9 10v9"/></svg>
              <span><strong>Color Combination - Production</strong><small>Tải hàng loạt theo BuyerStyleReference</small></span>
            </button>
```

Thêm section mới ngay sau `<section class="report-parameters">…</section>`, trước khi đóng `</div>` của `reports-workspace`:

```html
          <section class="color-report-workspace" hidden aria-live="polite">
            <label class="color-report-level-field"><span>OC Division</span>
              <select class="color-report-level" data-level="division" data-module-action="color-report-level-change"></select>
            </label>
            <label class="color-report-level-field"><span>Buyer</span>
              <select class="color-report-level" data-level="buyer" data-module-action="color-report-level-change" disabled></select>
            </label>
            <label class="color-report-level-field"><span>Season</span>
              <select class="color-report-level" data-level="season" data-module-action="color-report-level-change" disabled></select>
            </label>
            <label class="color-report-batch-row">
              <input type="checkbox" class="color-report-batch-toggle" checked/>
              <span>Tải hàng loạt</span>
            </label>
            <div class="color-report-style-block">
              <div class="color-report-style-heading">
                <span>Style</span>
                <small class="color-report-style-count">0/0</small>
              </div>
              <div class="color-report-style-tools">
                <button type="button" class="module-secondary-button" data-module-action="color-report-select-all">Chọn tất cả</button>
                <button type="button" class="module-secondary-button" data-module-action="color-report-clear-all">Bỏ chọn</button>
                <input type="search" class="color-report-style-filter" placeholder="lọc style…" aria-label="Lọc danh sách style"/>
              </div>
              <div class="color-report-style-list" role="group" aria-label="Danh sách BuyerStyleReference"></div>
            </div>
            <label class="color-report-level-field color-report-single-style" hidden><span>BuyerStyleReference</span>
              <select class="color-report-single-select"></select>
            </label>
            <div class="color-report-dir-row">
              <span class="color-report-dir-path">Chưa chọn thư mục lưu</span>
              <button type="button" class="module-secondary-button" data-module-action="color-report-choose-dir">Chọn…</button>
            </div>
            <button type="button" class="special-primary-button" data-module-action="color-report-run">Tải báo cáo</button>
            <div class="color-report-progress-card" hidden>
              <div class="color-report-progress-heading">
                <strong>Đang tải báo cáo</strong>
                <span class="color-report-progress-count">0/0</span>
              </div>
              <small class="color-report-progress-style"></small>
              <div class="color-report-progress-track"><i></i></div>
            </div>
            <div class="color-report-result-card" hidden></div>
          </section>
```

Trong `wfx_panel/ui/style.css`, thêm ở cuối (bám biến màu/khoảng cách đang dùng cho `.sale-asn-*` — mở file, tìm khối `.sale-asn-progress-card` và tái dùng đúng các custom property ở đó):

```css
.color-report-workspace { display: flex; flex-direction: column; gap: 10px; }
.color-report-level-field { display: flex; flex-direction: column; gap: 4px; }
.color-report-level-field select:disabled { opacity: .55; }
.color-report-batch-row { display: flex; align-items: center; gap: 8px; }
.color-report-style-heading { display: flex; justify-content: space-between; align-items: baseline; }
.color-report-style-tools { display: flex; gap: 6px; align-items: center; margin: 6px 0; }
.color-report-style-tools .color-report-style-filter { flex: 1 1 auto; min-width: 0; }
.color-report-style-list { max-height: 190px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.color-report-style-list label { display: flex; gap: 8px; align-items: center; padding: 2px 4px; }
.color-report-style-list label[hidden] { display: none; }
.color-report-dir-row { display: flex; gap: 8px; align-items: center; }
.color-report-dir-path { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.color-report-progress-heading { display: flex; justify-content: space-between; align-items: baseline; }
.color-report-progress-track { height: 4px; border-radius: 2px; overflow: hidden; background: rgba(127,127,127,.25); }
.color-report-progress-track > i { display: block; height: 100%; width: 0; transition: width .2s ease; background: currentColor; }
.color-report-result-row { display: flex; gap: 8px; align-items: baseline; }
.color-report-result-actions { display: flex; gap: 8px; margin-top: 8px; }
@media (prefers-reduced-motion: reduce) {
  .color-report-progress-track > i { transition: none; }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_ui_assets.py -v
```

Expected: tất cả PASS (gồm cả canh NFC)

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/ui/index.html wfx_panel/ui/style.css tests/test_ui_assets.py
git commit -m "feat: khung giao diện workspace Color Combination"
```

---

### Task 12: Toàn bộ giao diện JS của báo cáo

Task này làm trọn phần `panel.js`: cascade, danh sách style, lượt chạy, thẻ tiến độ và thẻ kết quả. Chúng gọi lẫn nhau nên tách ra sẽ để lại hàm rỗng và test đỏ giữa chừng.

**Files:**
- Modify: `wfx_panel/ui/panel.js` (state ~dòng 168, `BUSY_MESSAGES` ~dòng 321, `METHOD_LABELS` ~dòng 391, `MODULE_ACTIONS` ~dòng 2689, `BACKEND_PROGRESS_HANDLERS` ~dòng 2505, hàm mới cạnh `renderReportParameters` ~dòng 3519, hiển thị workspace ~dòng 1528, reset khi mở module ~dòng 1513)
- Test: `tests/test_panel_js.py`

**Interfaces:**
- Consumes: DOM class từ Task 11; bridge `load_color_report_options`, `run_color_report_batch`, `choose_report_export_dir`, `open_report_export_dir` từ Task 9–10
- Produces: `colorReportState` (`{levels, styleRefs, selected: Set, outputDir}`), `colorReportRunActive`, `renderColorReportLevels(result)`, `renderColorReportStyles()`, `setColorReportSelection(selected)`, `updateColorReportProgress(progress)`, `resetColorReportProgress({show, total})`, `renderColorReportResult(result)`

- [ ] **Step 1: Write the failing test**

Thêm vào `tests/test_panel_js.py`:

```python
def test_color_report_locks_lower_levels_while_loading():
    """Postback mất vài giây; để select mở là user chọn trên dữ liệu cũ."""
    assert "function setColorReportLevelsBusy" in JS
    assert "colorReportState" in JS


def test_color_report_run_is_guarded_by_an_active_flag():
    """Không có cờ thì payload progress đến trễ xóa mất thẻ kết quả."""
    assert "colorReportRunActive" in JS
    assert "run_color_report_batch: updateColorReportProgress" in JS


def test_color_report_progress_reads_the_counter_suffix():
    start = JS.index("function updateColorReportProgress")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert "colorReportRunActive" in body
    assert "/(\\d+\\/\\d+)\\s*$/" in body


def test_color_report_select_all_only_touches_visible_rows():
    """Sau khi lọc, Chọn tất cả phải theo đúng cái user đang thấy."""
    start = JS.index("function setColorReportSelection")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert "hidden" in body
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_panel_js.py -k color_report -v
```

Expected: FAIL với `ValueError: substring not found` / `AssertionError`

- [ ] **Step 3: Write minimal implementation**

Trong `wfx_panel/ui/panel.js`:

1. Cạnh `let selectedReportId = "";` thêm state:

```js
  let colorReportRunActive = false;
  const colorReportState = {
    levels: { division: [], buyer: [], season: [] },
    styleRefs: [],
    selected: new Set(),
    outputDir: "",
  };
```

2. Thêm vào `BUSY_MESSAGES`:

```js
    load_color_report_options: "Đang tải tham số báo cáo…",
    run_color_report_batch: "Đang tải báo cáo theo từng style…",
```

3. Thêm vào `METHOD_LABELS`:

```js
    load_color_report_options: "Tải tham số Color Combination",
    run_color_report_batch: "Tải hàng loạt Color Combination",
```

4. Thêm vào mảng method được nhận diện là module action (cạnh `"load_report_parameters", "export_report_excel",` dòng ~250):

```js
    "load_color_report_options", "run_color_report_batch",
```

5. Thêm nhóm hàm mới cạnh `renderReportParameters`:

```js
  function setColorReportLevelsBusy(fromKey) {
    // Option của cấp dưới do cấp trên sinh ra; khóa lại để user không
    // thao tác trên danh sách của lựa chọn cũ trong lúc WFX postback.
    const order = ["division", "buyer", "season"];
    const from = order.indexOf(fromKey);
    order.slice(from + 1).forEach((key) => {
      const select = $(`.color-report-level[data-level="${key}"]`);
      if (!select) return;
      select.disabled = true;
      select.innerHTML = '<option value="">Đang tải…</option>';
    });
    $(".color-report-style-list").innerHTML = "";
    colorReportState.styleRefs = [];
    colorReportState.selected = new Set();
    renderColorReportStyles();
  }

  function renderColorReportLevels(result) {
    const levels = result?.levels || {};
    ["division", "buyer", "season"].forEach((key) => {
      const select = $(`.color-report-level[data-level="${key}"]`);
      if (!select) return;
      const options = levels[key]?.options || [];
      colorReportState.levels[key] = options;
      select.innerHTML = ['<option value="">— chọn —</option>']
        .concat(options.map((option) =>
          `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
        )).join("");
      select.value = String(levels[key]?.value || "");
      select.disabled = options.length === 0;
    });
    colorReportState.styleRefs = levels.style_ref?.options || [];
    colorReportState.selected = new Set(
      colorReportState.styleRefs.map((option) => String(option.value))
    );
    renderColorReportStyles();
  }

  function renderColorReportStyles() {
    const list = $(".color-report-style-list");
    const single = $(".color-report-single-select");
    if (!list || !single) return;
    const batch = $(".color-report-batch-toggle").checked;
    list.innerHTML = colorReportState.styleRefs.map((option) => {
      const value = escapeHtml(option.value);
      const checked = colorReportState.selected.has(String(option.value));
      return `<label><input type="checkbox" class="color-report-style" value="${value}"${checked ? " checked" : ""}/><span>${escapeHtml(option.label)}</span></label>`;
    }).join("");
    single.innerHTML = colorReportState.styleRefs.map((option) =>
      `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
    ).join("");
    $(".color-report-style-block").hidden = !batch;
    $(".color-report-single-style").hidden = batch;
    list.querySelectorAll(".color-report-style").forEach((box) =>
      box.addEventListener("change", () => {
        if (box.checked) colorReportState.selected.add(box.value);
        else colorReportState.selected.delete(box.value);
        updateColorReportCount();
      })
    );
    applyColorReportFilter();
    updateColorReportCount();
  }

  function applyColorReportFilter() {
    const needle = ($(".color-report-style-filter")?.value || "")
      .trim().toLocaleLowerCase("vi");
    $(".color-report-style-list").querySelectorAll("label").forEach((row) => {
      row.hidden = Boolean(needle) &&
        !row.textContent.toLocaleLowerCase("vi").includes(needle);
    });
  }

  function updateColorReportCount() {
    const count = $(".color-report-style-count");
    if (count) {
      count.textContent =
        `${colorReportState.selected.size}/${colorReportState.styleRefs.length}`;
    }
  }

  function setColorReportSelection(selected) {
    // Chỉ tác động lên dòng đang hiện sau khi lọc.
    $(".color-report-style-list").querySelectorAll("label").forEach((row) => {
      if (row.hidden) return;
      const box = row.querySelector(".color-report-style");
      box.checked = selected;
      if (selected) colorReportState.selected.add(box.value);
      else colorReportState.selected.delete(box.value);
    });
    updateColorReportCount();
  }

  function colorReportSelection() {
    return {
      division: $('.color-report-level[data-level="division"]').value,
      buyer: $('.color-report-level[data-level="buyer"]').value,
      season: $('.color-report-level[data-level="season"]').value,
    };
  }

  async function loadColorReportOptions(fromKey) {
    if (fromKey) setColorReportLevelsBusy(fromKey);
    $(".color-report-workspace").hidden = false;
    $(".report-parameters").hidden = true;
    selectedReportId = "color_combination_production";
    const result = await call("load_color_report_options", colorReportSelection());
    if (result?.ok) renderColorReportLevels(result);
    return result;
  }

  async function chooseColorReportDir() {
    const result = await callQuiet("choose_report_export_dir");
    if (result?.ok) {
      colorReportState.outputDir = String(result.output_dir || "");
      $(".color-report-dir-path").textContent = colorReportState.outputDir;
    }
    return result;
  }

  async function runColorReportBatch(onlyRefs) {
    const batch = $(".color-report-batch-toggle").checked;
    const refs = onlyRefs || (batch
      ? colorReportState.styleRefs
          .map((option) => String(option.value))
          .filter((value) => colorReportState.selected.has(value))
      : [$(".color-report-single-select").value].filter(Boolean));
    resetColorReportProgress({ show: true, total: refs.length });
    colorReportRunActive = true;
    const result = await call(
      "run_color_report_batch",
      colorReportSelection(),
      refs,
      colorReportState.outputDir,
    );
    colorReportRunActive = false;
    renderColorReportResult(result);
    return result;
  }
```

6. Thêm vào `MODULE_ACTIONS` cạnh các action `report-*`:

```js
    "report-color-combination": () => loadColorReportOptions(""),
    "color-report-level-change": (element) =>
      loadColorReportOptions(element.dataset.level),
    "color-report-select-all": () => setColorReportSelection(true),
    "color-report-clear-all": () => setColorReportSelection(false),
    "color-report-choose-dir": chooseColorReportDir,
    "color-report-run": () => runColorReportBatch(null),
```

Nếu dispatcher `MODULE_ACTIONS` hiện không truyền element vào handler, sửa chỗ gọi để truyền `element` — kiểm tra hàm bắt `click` trên `[data-module-action]` và thêm tham số. Riêng `<select class="color-report-level">` phải nghe sự kiện `change`, không phải `click`: thêm listener riêng trong phần khởi tạo:

```js
  $$(".color-report-level").forEach((select) =>
    select.addEventListener("change", () =>
      loadColorReportOptions(select.dataset.level)
    )
  );
  $(".color-report-style-filter")?.addEventListener("input", applyColorReportFilter);
  $(".color-report-batch-toggle")?.addEventListener("change", renderColorReportStyles);
```

7. Ở chỗ hiện workspace theo module (dòng ~1528), đổi thành:

```js
    } else if (module.kind === "reports") {
      $(".report-parameters").hidden = !selectedReportId ||
        selectedReportId === "color_combination_production";
      $(".color-report-workspace").hidden =
        selectedReportId !== "color_combination_production";
    }
```

- [ ] **Step 4: Viết tiếp thẻ tiến độ và thẻ kết quả**

`runColorReportBatch` ở trên gọi `resetColorReportProgress` và `renderColorReportResult`; viết luôn thân thật của chúng, không dùng stub rỗng. Nội dung ở phần "Thẻ tiến độ và thẻ kết quả" ngay bên dưới.

- [ ] **Step 5: Write the failing test cho thẻ tiến độ và kết quả**

Ba test `color_report` đã viết ở Step 1 (`..._guarded_by_an_active_flag`, `..._reads_the_counter_suffix`) là test cho phần này. Thêm hai test nữa:

```python
def test_color_report_result_card_is_cleared_when_the_module_reopens():
    """Lần mở sau không được còn nút Mở thư mục của lượt chạy cũ."""
    start = JS.index("function resetColorReportProgress")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert '$(".color-report-result-card").hidden = true' in body


def test_color_report_result_scrolls_itself_into_view():
    start = JS.index("function renderColorReportResult")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert "scrollIntoView" in body
    assert "color-report-retry-failed" in body
```

- [ ] **Step 6: Run test to verify it fails**

```bash
python -m pytest tests/test_panel_js.py -k color_report -v
```

Expected: FAIL với `ValueError: substring not found`

- [ ] **Step 7: Thẻ tiến độ và thẻ kết quả**

Thêm vào `wfx_panel/ui/panel.js`, cùng nhóm hàm ở Step 3:

```js
  function resetColorReportProgress({ show = false, total = 0 } = {}) {
    const card = $(".color-report-progress-card");
    if (card) {
      card.hidden = !show;
      $(".color-report-progress-count").textContent = `0/${total}`;
      $(".color-report-progress-style").textContent = "";
      $(".color-report-progress-track > i").style.width = "0%";
    }
    $(".color-report-result-card").hidden = true;
    $(".color-report-result-card").innerHTML = "";
  }

  // Progress chỉ để hiển thị; renderColorReportResult chạy sau và là nguồn
  // sự thật, nên payload đến trễ không được để lại trạng thái sai.
  function updateColorReportProgress(progress) {
    const card = $(".color-report-progress-card");
    if (!card || !progress || !colorReportRunActive) return;
    card.hidden = false;
    const counter = /(\d+\/\d+)\s*$/.exec(String(progress.message || ""));
    const step = Math.max(1, Number(progress.step || 1));
    const total = Math.max(1, Number(progress.total || 1));
    $(".color-report-progress-count").textContent = counter
      ? counter[1]
      : `${step}/${total}`;
    $(".color-report-progress-style").textContent =
      String(progress.message || "").replace(/\s*\d+\/\d+\s*$/, "");
    $(".color-report-progress-track > i").style.width =
      `${Math.round((step / total) * 100)}%`;
    if (busy && progress.message) {
      $(".operation-progress-text").textContent = progress.message;
    }
  }

  function renderColorReportResult(result) {
    const card = $(".color-report-result-card");
    if (!card || !result) return;
    $(".color-report-progress-card").hidden = true;
    const saved = result.saved || [];
    const failed = result.failed || [];
    if (!saved.length && !failed.length) {
      card.hidden = true;
      return;
    }
    const failedRows = failed.map((item) =>
      `<div class="color-report-result-row"><strong>${escapeHtml(item.style_ref)}</strong><span>${escapeHtml(item.message)}</span></div>`
    ).join("");
    const savedRows = saved.map((item) =>
      `<div class="color-report-result-row"><strong>${escapeHtml(item.style_ref)}</strong><span>${escapeHtml(item.file_name)}</span></div>`
    ).join("");
    card.innerHTML = `
      <div class="color-report-result-row">
        <span class="chip">${saved.length} thành công</span>
        <span class="chip">${failed.length} lỗi</span>
      </div>
      ${failedRows}
      ${saved.length ? `<details><summary>${saved.length} style đã tải</summary>${savedRows}</details>` : ""}
      <div class="color-report-result-actions">
        ${failed.length ? `<button type="button" class="module-secondary-button" data-module-action="color-report-retry-failed">Chạy lại ${failed.length} style lỗi</button>` : ""}
        <button type="button" class="module-secondary-button" data-module-action="color-report-open-dir">Mở thư mục</button>
      </div>`;
    card.dataset.failedRefs = JSON.stringify(
      failed.map((item) => String(item.style_ref))
    );
    card.hidden = false;
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
```

Trong `renderColorReportResult`, ngay trước `card.scrollIntoView(...)`, mở sẵn thư mục khi có file — đúng quy tắc "thư mục chứa file luôn tự mở sau mọi download/export thành công":

```js
    if (saved.length && colorReportState.outputDir) {
      callQuiet("open_report_export_dir", colorReportState.outputDir);
    }
```

Thêm hai action vào `MODULE_ACTIONS`:

```js
    "color-report-retry-failed": () => runColorReportBatch(
      JSON.parse($(".color-report-result-card").dataset.failedRefs || "[]")
    ),
    "color-report-open-dir": () => callQuiet(
      "open_report_export_dir", colorReportState.outputDir
    ),
```

Thêm vào `BACKEND_PROGRESS_HANDLERS`:

```js
    run_color_report_batch: updateColorReportProgress,
```

Gọi `resetColorReportProgress();` trong nhánh reset khi mở module (cạnh `resetSaleAsnProgress();` dòng ~1513).

- [ ] **Step 8: Run test to verify it passes**

```bash
python -m pytest tests/test_panel_js.py tests/test_ui_assets.py -v && python -m pytest -q
```

Expected: toàn bộ test PASS, không còn test `color_report` nào đỏ

- [ ] **Step 9: Commit**

```bash
git add wfx_panel/ui/panel.js tests/test_panel_js.py
git commit -m "feat: giao diện cascade, tiến độ và kết quả cho Color Combination"
```

---

### Task 13: Hướng dẫn người dùng và kiểm tra cuối

**Files:**
- Modify: `wfx_panel/manual/06-danh-sach/reports.md`
- Modify: `wfx_panel/manual/manifest.json`
- Generate: `docs/USER_FEATURES.md`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: mã lỗi từ Task 9–10
- Produces: mục hướng dẫn phủ hết nút và mã lỗi mới

- [ ] **Step 1: Run the test to see what the manual is missing**

```bash
python -m pytest tests/test_manual.py -v
```

Expected: FAIL — có nút/mã lỗi mới chưa được mục hướng dẫn nào phủ. Đọc kỹ thông báo để biết chính xác cần khai báo gì; `docs/MANUAL_AUTHORING.md` mô tả cú pháp.

- [ ] **Step 2: Write the manual section**

Thêm vào cuối `wfx_panel/manual/06-danh-sach/reports.md`:

```markdown
## Color Combination - Production

Báo cáo này chỉ xuất được một style mỗi lần chạy trên WFX. Ứng dụng tự lặp
qua danh sách style để bạn không phải chọn lại từng cái.

1. Mở module `Reports` rồi bấm `Color Combination - Production`.
2. Chọn `OC Division`, `Buyer`, `Season`. Mỗi lần chọn, ứng dụng chờ WFX nạp
   danh sách kế tiếp nên các ô bên dưới tạm khóa vài giây.
3. Danh sách `Style` hiện toàn bộ `BuyerStyleReference` của mùa và mặc định
   chọn hết. Bỏ tích những style không cần, hoặc gõ vào ô lọc rồi bấm
   `Chọn tất cả` để chọn nhanh nhóm đang hiện.
4. Bấm `Chọn…` để chỉ định thư mục lưu. Ứng dụng nhớ thư mục này cho lần sau.
5. Bấm `Tải báo cáo`. Mỗi style được lưu thành một file
   `BuyerStyleReference - StyleCode.xlsx`.
6. Chạy xong, thẻ kết quả cho biết bao nhiêu style thành công và bao nhiêu lỗi.

> [!meo]
> Tắt `Tải hàng loạt` nếu chỉ cần đúng một style.
> Ứng dụng tự chọn `StyleCode` có số lớn nhất, tức bản style mới nhất.
> `SizeVisibility` luôn được đặt `Yes`, còn `OCNum` giữ nguyên mặc định của WFX.
> Bấm `Stop` ở thanh dưới cùng để dừng; các file đã tải vẫn được giữ.

> [!loi]
> `Tham số báo cáo Color Combination chưa nạp xong`: WFX đang chậm. Chờ trang
> ổn định rồi chọn lại `OC Division`.
> `Không lưu được file báo cáo vào thư mục đã chọn`: kiểm tra quyền ghi và
> dung lượng của thư mục lưu.
> Style lỗi lẻ tẻ không làm dừng cả lượt; bấm `Chạy lại n style lỗi` ở thẻ
> kết quả.
```

Trong `wfx_panel/manual/manifest.json`, cập nhật entry của `reports.md`: thêm keyword `"color combination"`, `"hàng loạt"`, `"buyerstylereference"` và thêm vào `covers`:

```json
          "covers": {
            "errors": [
              "COLOR_REPORT_OPTIONS_NOT_READY",
              "COLOR_REPORT_SAVE_FAILED",
              "COLOR_REPORT_STYLE_LIST_EMPTY",
              "COLOR_REPORT_NO_STYLE_SELECTED",
              "COLOR_REPORT_OUTPUT_DIR_REQUIRED",
              "COLOR_REPORT_CANCELLED"
            ]
          }
```

Giữ nguyên các mã đã khai báo sẵn trong entry đó, chỉ thêm vào danh sách.

- [ ] **Step 3: Regenerate the user features document**

```bash
python scripts/generate_user_features.py
```

Expected: `docs/USER_FEATURES.md` được ghi lại. Không sửa tay file này.

- [ ] **Step 4: Run the whole suite and the linter**

```bash
python -m pytest -q && ruff check .
```

Expected: toàn bộ PASS, ruff sạch. Nếu `test_manual.py` còn báo thiếu nút hoặc mã lỗi, bổ sung đúng mục vào `reports.md` và `manifest.json` rồi chạy lại từ Step 3.

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/manual/06-danh-sach/reports.md wfx_panel/manual/manifest.json docs/USER_FEATURES.md
git commit -m "docs: hướng dẫn tải hàng loạt báo cáo Color Combination"
```

---

## Kiểm thử thủ công trước khi phát hành

Test tự động không chạm Chrome thật. Sau Task 13, chạy app từ source và kiểm tra tay:

1. Mở Chrome làm việc, đăng nhập WFX, mở module `Reports` → `Color Combination - Production`.
2. Xác nhận ba select nạp đúng và cấp dưới bị khóa trong lúc chờ.
3. Chọn 3 style, chọn thư mục, bấm `Tải báo cáo`. Xác nhận đủ 3 file với tên `BuyerStyleReference - StyleCode.xlsx` và nội dung khác nhau.
4. Bấm `Stop` giữa lượt 10 style: xác nhận thẻ kết quả vẫn liệt kê file đã tải.
5. Xác nhận tab Costing/tab đang làm của user không bị kéo lên foreground ngoài lúc report chạy.
6. Đóng và mở lại module: xác nhận thẻ kết quả cũ đã biến mất và Division/Buyer/Season được nhớ.
7. Build lại bằng `build-panel.ps1` và chạy thử bản đóng gói.
