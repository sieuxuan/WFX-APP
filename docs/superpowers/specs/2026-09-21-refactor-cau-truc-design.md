# Refactor cấu trúc WFX Smart Panel

Ngày: 2026-09-21

## Vấn đề

`python -m pytest` xanh (1598 passed) và `ruff check .` sạch, nhưng cấu trúc đã
quá tải:

| File | LOC | Triệu chứng |
| --- | ---: | --- |
| `wfx_panel/automation/costing.py` | 4684 | 110+ hàm module-level, 8 mối quan tâm trộn lẫn |
| `wfx_panel/panel_api.py` | 4085 | một class `PanelAPI` với 155 method — god object |
| `wfx_panel/automation/modules.py` | 3448 | menu + grid + search + 6 module nghiệp vụ |
| `wfx_panel/panel_app.py` | 2786 | shell + tray + bubble + 14 hộp thoại file |
| `wfx_panel/automation/catalog.py` | 2745 | state machine + filter + file + destination |
| `wfx_panel/automation/sale_asn_create.py` | 2739 | 5 bước flow trong một file |
| `wfx_panel/ui/panel.js` | 5729 | một IIFE chứa toàn bộ UI |

Hệ quả: mỗi lần sửa một flow phải đọc vài nghìn dòng không liên quan; review
diff khó; thêm module mới phải chèn vào giữa file lớn.

## Nguyên tắc refactor

1. **Không đổi hành vi.** Mọi stage giữ `python -m pytest` + `ruff check .` xanh.
   Test hiện có là lưới an toàn — không sửa test để hợp với code mới, trừ khi
   test đang khẳng định *vị trí file* thay vì *hành vi*.
2. **Package + façade.** File lớn tách thành package; `__init__.py` re-export
   đúng bề mặt cũ (kể cả tên `_private` mà test đang dùng). Caller và
   `wfx-panel.spec` không phải đổi.
3. **Một stage = một commit.** Revert được từng phần.
4. **Không đổi tên file mà `CLAUDE.md` đặc tả trỏ tới** (`panel_api.py`,
   `panel_app.py`, `catalog_controller.py`, `automation/runtime.py`, …) — chúng
   trở thành package cùng tên hoặc giữ nguyên vai trò điều phối.

## Ranh giới mục tiêu

### `automation/costing/` (từ costing.py)

| Module | Trách nhiệm |
| --- | --- |
| `constants.py` | XPath, snippet JS, `CostingFieldApplyError` |
| `context.py` | tìm page/frame Costing đang hoạt động, đọc Style Code/Name/status |
| `inventory.py` | quét grid → document, option của item |
| `articles.py` | Material Search, Add/Delete Article, split row |
| `variants.py` | thêm Material Color/Size còn thiếu |
| `dependencies.py` | quét và áp mapping Color/Size |
| `fields.py` | resolve/set/verify field live, Save Cost Sheet |
| `apply.py` | session apply, dry-run → apply → verify |
| `scan.py` | `scan_open_costing` |

### `automation/modules/` (từ modules.py)

`menu.py` (mở menu + cache route) · `grid.py` (floating filter, grid settled) ·
`search.py` (input, multi-field, list search) · `sample.py` · `rmpo.py` ·
`supplier_invoice.py` · `creation.py` (`open_module_new`) · `company.py`.

### `wfx_panel/controllers/` (từ PanelAPI)

Mở rộng đúng pattern `CatalogController` đã có: `sale_asn.py`, `oc.py`,
`inventory.py` (RMPO + GRN), `directory.py`, `reports.py`, `settings.py`,
`jobs.py`. `PanelAPI` giữ hạ tầng dùng chung (`_run`, session, telemetry,
observe) và ủy quyền phần còn lại.

### `wfx_panel/app/` (từ panel_app.py)

`dialogs.py` (hộp thoại chọn/tải file) · `tray.py` · `bubble.py` ·
`bridges.py`. `panel_app.py` còn lại là orchestrator + vòng lặp nền.

### `wfx_panel/ui/panel/` (từ panel.js)

Tách theo màn: `core.js` (bridge, busy, status, log) · `modules.js` ·
`catalog.js` · `costing.js` · `sale_asn.js` · `oc.js` · `inventory.js` ·
`reports.js` · `settings.js` · `jobs.js`. `index.html` nạp theo thứ tự;
`tests/test_panel_js.py` đọc bản nối của cả thư mục.

## Cross-cutting

Áp dụng trong lúc di chuyển code, không thành stage riêng:

- **Guard clause**: hàm lồng >3 tầng đổi sang early return.
- **Đặt tên tự giải thích**: `_visible_unique` → `require_single_visible`,
  `_clean_key` → `normalized_key_or`, … chỉ đổi tên nội bộ, không đổi tên mà
  test/CLAUDE.md phụ thuộc.
- **Hiệu năng**: bỏ quét O(n²) trong vòng lặp (tra cứu dựng `dict` một lần),
  gộp lời gọi CDP/`evaluate` lặp lại, không đọc file/prefs nhiều lần trong một
  flow.

## Thứ tự thực thi

Rủi ro tăng dần, mỗi stage tự đứng được:

1. `automation/costing/`
2. `automation/modules/`
3. `automation/catalog/` + `automation/sale_asn/`
4. `wfx_panel/controllers/` (tách `PanelAPI`)
5. `wfx_panel/app/` (tách `panel_app.py`)
6. `wfx_panel/ui/panel/` (tách `panel.js`)
7. Rà cross-cutting lần cuối + cập nhật `CLAUDE.md` bản đồ nhanh

## Ngoài phạm vi

- Xóa `build-*/`, `dist-*/`, `outputs/`, `job-screenshots/` trên đĩa: đã
  `.gitignore`, là dữ liệu local của anh — em không tự xóa.
- Đổi hành vi nghiệp vụ, đổi selector WFX, nâng cấp dependency.
