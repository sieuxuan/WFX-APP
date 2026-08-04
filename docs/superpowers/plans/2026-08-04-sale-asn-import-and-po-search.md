# Sale ASN Import and PO Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phát hành form Sale ASN 20 cột, điền Shipping Info theo Shipping Mode và tự thêm PO bằng chuỗi tiêu chí PO → Style → Destination có thể cấu hình.

**Architecture:** `sale_asn_workbook.py` là nguồn duy nhất cho schema/validation và tạo dropdown Excel. `sale_asn_create.py` nhận payload đã chuẩn hóa, ánh xạ shipping và điều khiển bộ lọc PO. Preferences đi từ `prefs.py` → `PanelAPI` → bootstrap UI, đồng thời được snapshot trong review token trước khi truyền vào automation.

**Tech Stack:** Python 3.11+, openpyxl, Playwright sync/CDP, pywebview bridge, vanilla JavaScript/HTML/CSS, pytest, Ruff.

## Global Constraints

- Chỉ sửa product source trong `wfx_panel/`, không sửa `dist/`.
- Giữ nguyên luồng `ORDER DETAILS` 8 cột.
- Không tự bấm Save trên Sale ASN.
- Không dùng heuristic Dispatched Qty sau khi hết ba tiêu chí tìm.
- Không đụng hoặc ghi đè thay đổi sẵn có trong `tests/test_ui_assets.py` và `wfx_panel/ui/style.css` nếu không cần cho tính năng này.
- Nội dung tiếng Việt phải là Unicode NFC.

---

### Task 1: Workbook schema và validation

**Files:**
- Modify: `wfx_panel/sale_asn_workbook.py`
- Test: `tests/test_sale_asn_create.py`

**Interfaces:**
- Produces: `SALE_ASN_COLUMNS` gồm 20 cột; `SaleASNRow.automation_payload()` có `consignee_address`, `ship_to`, `shipping_mode`; `read_sale_asn_workbook(...)` trả payload đã chuẩn hóa.
- Consumes: không có interface mới từ task khác.

- [ ] **Step 1: Viết test fail cho schema 20 cột và dropdown Shipping Mode**

```python
assert "SEASON" not in SALE_ASN_COLUMNS
assert "DESCRIPTION" not in SALE_ASN_COLUMNS
assert SALE_ASN_COLUMNS[-3:] == (
    "Consignee Address", "Ship To", "Shipping Mode",
)
assert sheet.data_validations.count == 1
assert '"AIR,SEA,COURIER"' in sheet.data_validations.dataValidation[0].formula1
```

- [ ] **Step 2: Chạy test mục tiêu và xác nhận fail vì schema vẫn là 19 cột**

Run: `python -m pytest tests/test_sale_asn_create.py::test_template_keeps_reference_schema_and_readable_format -v`

- [ ] **Step 3: Viết test fail cho Shipping Mode bắt buộc và Cargo Ready Date không fallback**

```python
document = read_sale_asn_workbook(source)
assert document["rows"][1]["cargo_ready_date"] == ""
assert document["rows"][0]["shipping_mode"] == "AIR"

with pytest.raises(SaleASNWorkbookError) as error:
    read_sale_asn_workbook(missing_mode_source)
assert any("Shipping Mode" in item for item in error.value.errors)
```

- [ ] **Step 4: Chạy test và xác nhận fail đúng do ngày đang kế thừa và chưa validate mode**

Run: `python -m pytest tests/test_sale_asn_create.py -k "reader or template" -v`

- [ ] **Step 5: Cập nhật schema, dataclass, reader và writer tối thiểu để test xanh**

```python
SHIPPING_MODES = ("AIR", "SEA", "COURIER")

shipping_mode = _text(raw["Shipping Mode"]).upper() or first_values["Shipping Mode"]
if require_shipping and shipping_mode not in SHIPPING_MODES:
    errors.append(f"T{source_row}: Shipping Mode bắt buộc chọn AIR, SEA hoặc COURIER.")

cargo_ready_date = _date_text(
    raw["Cargo Ready Date"], cell=f"Cargo Ready Date dòng {source_row}"
)
```

- [ ] **Step 6: Chạy toàn bộ test workbook Sale ASN**

Run: `python -m pytest tests/test_sale_asn_create.py -k "template or reader or workbook" -v`

---

### Task 2: Shipping mapping và fuzzy dropdown

**Files:**
- Modify: `wfx_panel/automation/sale_asn_create.py`
- Test: `tests/test_sale_asn_create.py`

**Interfaces:**
- Consumes: row keys `consignee_address`, `ship_to`, `shipping_mode` từ Task 1.
- Produces: `SHIPPING_MODE_VALUES`; `_best_dropdown_label(options, query) -> str | None`; `_fill_shipping(...) -> list[str]` điền các field mới.

- [ ] **Step 1: Viết test fail cho bảng mapping đủ ba mode**

```python
assert sale_asn_create.SHIPPING_MODE_VALUES == {
    "AIR": {"port_of_loading": "HAN- Hanoi", "delivery_terms": "FCA HANOI, VIETNAM"},
    "SEA": {"port_of_loading": "HPH- Haiphong", "delivery_terms": "FOB HAIPHONG, VIETNAM"},
    "COURIER": {"port_of_loading": "HAN- Hanoi", "delivery_terms": "EXW"},
}
```

- [ ] **Step 2: Viết test fail cho fuzzy unique/không thấy/đồng hạng**

```python
assert _best_dropdown_label(["ACME HANOI OFFICE", "OTHER"], "acme hanoi") == "ACME HANOI OFFICE"
assert _best_dropdown_label(["ALPHA ONE", "ALPHA TWO"], "alpha") is None
assert _best_dropdown_label(["OTHER"], "missing") is None
```

- [ ] **Step 3: Chạy test và xác nhận fail vì helper/mapping chưa tồn tại**

Run: `python -m pytest tests/test_sale_asn_create.py -k "shipping_mode or fuzzy_dropdown" -v`

- [ ] **Step 4: Implement mapping và mode `closest` trong `_set_control`**

```python
SHIPPING_MODE_VALUES = {
    "AIR": {"port_of_loading": "HAN- Hanoi", "delivery_terms": "FCA HANOI, VIETNAM"},
    "SEA": {"port_of_loading": "HPH- Haiphong", "delivery_terms": "FOB HAIPHONG, VIETNAM"},
    "COURIER": {"port_of_loading": "HAN- Hanoi", "delivery_terms": "EXW"},
}
```

JavaScript control setter phải trả `option-not-found` khi không có một best match
duy nhất; Python chuyển kết quả đó thành warning và tiếp tục.

- [ ] **Step 5: Viết test fail cho `_fill_shipping` truyền đúng Address/Ship To/Port/Terms**

```python
assert ("#ddlDeliveryTerms", "FCA HANOI, VIETNAM", "exact", 6) in calls
assert any(call[1] == "HAN- Hanoi" for call in calls)
assert any(call[1] == "Closest consignee" and call[2] == "closest" for call in calls)
```

- [ ] **Step 6: Cập nhật `SHIPPING_FIELDS` và chạy test Shipping**

Run: `python -m pytest tests/test_sale_asn_create.py -k "shipping" -v`

---

### Task 3: Chuỗi tìm PO và chọn tất cả kết quả cuối

**Files:**
- Modify: `wfx_panel/automation/sale_asn_create.py`
- Test: `tests/test_sale_asn_create.py`

**Interfaces:**
- Produces: `SALE_ASN_PO_SEARCH_FIELDS = ("po", "style", "destination")`; `_auto_add_po(..., search_fields=SALE_ASN_PO_SEARCH_FIELDS)`.
- Consumes: `search_fields` snapshot do Task 4 truyền vào.

- [ ] **Step 1: Viết test fail cho thứ tự thu hẹp và dừng khi còn một dòng**

```python
assert searches == [
    {"po"},
    {"po", "style"},
    {"po", "style", "destination"},
]
```

- [ ] **Step 2: Viết test fail cho preference tắt tiêu chí**

```python
_auto_add_po(frame, row, log, search_fields=("style", "destination"))
assert searches == [{"style"}, {"style", "destination"}]
```

- [ ] **Step 3: Viết test fail cho chọn tất cả khi lượt cuối còn nhiều dòng**

```python
assert captured["selected_count"] == 3
assert action_clicked is True
```

- [ ] **Step 4: Chạy test và xác nhận fail do logic cũ dùng heuristic Style/Qty**

Run: `python -m pytest tests/test_sale_asn_create.py -k "auto_add_po or po_search" -v`

- [ ] **Step 5: Refactor `_search_po` nhận tập criteria tích lũy và `_auto_add_po` chọn theo count**

```python
for field in search_fields:
    active_fields.append(field)
    candidates = _search_po(frame, row, fields=tuple(active_fields))
    if len(candidates) == 1:
        return _select_and_continue(...)
    if not candidates:
        return False, [], "not_found"
return _select_and_continue(..., candidates=candidates, select_all=True)
```

- [ ] **Step 6: Chạy test PO và toàn file automation**

Run: `python -m pytest tests/test_sale_asn_create.py -k "po" -v`

---

### Task 4: Preference, API snapshot và Settings UI

**Files:**
- Modify: `wfx_panel/prefs.py`
- Modify: `wfx_panel/panel_api.py`
- Modify: `wfx_panel/ui/index.html`
- Modify: `wfx_panel/ui/panel.js`
- Modify: `wfx_panel/ui/style.css` chỉ trong block settings liên quan
- Test: `tests/test_prefs.py`
- Test: `tests/test_panel_api.py`
- Test: `tests/test_panel_js.py`
- Test: `tests/test_ui_assets.py`
- Test: `tests/test_sale_asn_create.py`

**Interfaces:**
- Produces: `prefs.SALE_ASN_PO_SEARCH_FIELDS`; `_clean_sale_asn_po_search_fields`; `PanelAPI.set_sale_asn_po_search_fields(fields)`; bootstrap key `sale_asn_po_search_fields`.
- Consumes: `run_sale_asn_create(..., search_fields=...)` từ Task 3.

- [ ] **Step 1: Viết test fail cho prefs mặc định, normalize và persistence**

```python
assert load_prefs(tmp_path)["sale_asn_po_search_fields"] == ["po", "style", "destination"]
saved = save_prefs(tmp_path, sale_asn_po_search_fields=["destination", "po", "bad"])
assert saved["sale_asn_po_search_fields"] == ["po", "destination"]
assert save_prefs(tmp_path, sale_asn_po_search_fields=[])["sale_asn_po_search_fields"] == ["po", "style", "destination"]
```

- [ ] **Step 2: Chạy test prefs và xác nhận fail vì key chưa tồn tại**

Run: `python -m pytest tests/test_prefs.py -k "sale_asn" -v`

- [ ] **Step 3: Implement preference xuyên suốt `load_prefs`/`save_prefs`**

```python
SALE_ASN_PO_SEARCH_FIELDS = ("po", "style", "destination")

def _clean_sale_asn_po_search_fields(value: object) -> list[str]:
    if not isinstance(value, list):
        return list(SALE_ASN_PO_SEARCH_FIELDS)
    selected = {str(item or "").strip() for item in value}
    return [item for item in SALE_ASN_PO_SEARCH_FIELDS if item in selected] or list(SALE_ASN_PO_SEARCH_FIELDS)
```

- [ ] **Step 4: Viết test fail cho API bootstrap/save và review snapshot**

```python
assert api.get_initial_state()["sale_asn_po_search_fields"] == ["po", "style", "destination"]
api.set_sale_asn_po_search_fields(["po", "destination"])
reviewed = api.prepare_sale_asn_create(str(source), "BUYER A")
api.set_sale_asn_po_search_fields(["style"])
api.start_sale_asn_create(reviewed["review_token"])
assert login.calls[-1]["search_fields"] == ("po", "destination")
```

- [ ] **Step 5: Cập nhật `PanelAPI` để lưu, bootstrap, snapshot và truyền runner**

Review dict thêm `po_search_fields`; runner nhận keyword `search_fields` để giữ
tương thích rõ ràng với các tham số stage/skip/progress hiện có.

- [ ] **Step 6: Viết test fail cho ba toggle trong Settings và bootstrap JS**

HTML phải có đúng ba input `data-sale-asn-po-search-field`; JS phải gọi
`set_sale_asn_po_search_fields` khi change và áp dụng state bootstrap.

- [ ] **Step 7: Implement UI Settings và chạy test UI/API**

Run: `python -m pytest tests/test_prefs.py tests/test_panel_api.py tests/test_panel_js.py tests/test_ui_assets.py -k "sale_asn or prefs" -v`

---

### Task 5: Manual, đặc tả chuẩn và verification

**Files:**
- Modify: `CLAUDE.md`
- Modify: `wfx_panel/manual/05-don-hang/sale-asn.md`
- Modify: `wfx_panel/manual/whats_new.json`
- Regenerate: `docs/USER_FEATURES.md`
- Test: `tests/test_manual.py`

**Interfaces:**
- Consumes: hành vi hoàn chỉnh từ Tasks 1–4.
- Produces: tài liệu người dùng và single source of truth khớp production.

- [ ] **Step 1: Cập nhật phần Sale ASN trong `CLAUDE.md`**

Nội dung phải ghi schema 20 cột, Cargo Ready Date không fallback, ba shipping
mode/mapping, fuzzy Address/Ship To, và chuỗi search có settings.

- [ ] **Step 2: Viết lại phần form và xử lý PO trong manual**

Manual phải hướng dẫn chọn Shipping Mode, vị trí ba toggle và hành vi chọn tất cả
khi hết tiêu chí mà vẫn có nhiều dòng.

- [ ] **Step 3: Thêm whats-new và sinh lại tài liệu tổng hợp**

Run: `python scripts/generate_user_features.py`

- [ ] **Step 4: Chạy test mục tiêu**

Run: `python -m pytest tests/test_sale_asn_create.py tests/test_prefs.py tests/test_panel_api.py tests/test_panel_js.py tests/test_ui_assets.py tests/test_manual.py -v`

- [ ] **Step 5: Chạy full verification**

Run: `python -m pytest`

Run: `ruff check .`

Run: `git diff --check`

- [ ] **Step 6: Rà diff chỉ còn thay đổi trong phạm vi và báo cáo**

Không stage/commit hai file dirty ban đầu nếu phần thay đổi của user không thuộc
tính năng; nếu buộc sửa cùng file thì chỉ stage hunk do task tạo và báo rõ.
