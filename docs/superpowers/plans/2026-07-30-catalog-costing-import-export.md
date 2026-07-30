# Catalog Costing XLSX — kế hoạch triển khai hiện hành

## Mục tiêu

Cho phép người dùng tải Costing `Open` ra XLSX, điền form chuẩn, import để xem
dry-run, rồi áp dụng và Save trên đúng màn hình đang mở. Luồng không chuyển tab,
không reload Costing và không tự tạo New Costing.

## Ràng buộc

- Chỉ Category `Apparel`.
- Chỉ chạy khi Internal CostSheet Status là `Open`.
- Nếu chưa có Costing hoặc status khác `Open`, dừng với `COSTING_NOT_OPEN`.
- Chỉ `.xlsx`; không hỗ trợ CSV.
- Không click Body Type, Delete/Edit/Copy Section.
- Add Article qua `#imgAdd`; exact Article Code trước, Article Name sau.
- Không có kết quả: skip và báo. Nhiều kết quả: chờ người dùng resolve.
- Delete chỉ sau khi đã chọn đúng Article.
- Mọi Minutes editable được đặt thành `1`.
- Save bằng nút trong `#titlebarCostSheet`, rồi verify DOM.

## Workbook v2

File có đúng hai sheet:

1. `Hướng dẫn`: Style Code, status, format version và quy tắc nhập.
2. `Costing`: form cột cố định, có Article live và ba dòng trống cho mỗi
   section chuẩn.

Bộ cột visible:

- Section, Action, Article Code, Article Name;
- Material Size, Material Color, Color Dep., Size Dep.;
- Shrinkage %(LxW), Cons. Qty., Waste %;
- Supplier, Curr., Rate;
- Remarks, Placement, Purchase Officer.

Các cột kỹ thuật cuối form được ẩn: Section Key, Item Key, Row Order, Item Type.
Không có `Cost Sheet`, `Sections`, `Items`, `_Fields`, `_Meta`.

Chỉ field item `editable=true` và thuộc bộ form chuẩn được export/import. Loại
CM Costs, Production Costs, Indirect Costs; Delivery Terms; Process Required;
BOM; SNO; Roll/Lot Avg; Destination Country; Des. Specific; Material Cost;
Included In.

## Luồng export

1. Xác nhận context style hiện tại và Costing status `Open`.
2. Scan `#sectionCostSheetTree` và `#sectionCostSheetDetail`.
3. Chuẩn hóa section, Article và editable item field.
4. Mở Save dialog và ghi đúng đường dẫn người dùng chọn.
5. Không điều hướng lại Costing và không đưa Chrome lên foreground.

## Luồng import/apply

1. Validate extension, workbook version, đúng hai sheet và đủ toàn bộ cột chuẩn.
2. Reject formula; blank là giữ nguyên, `__CLEAR__` là xóa rõ ràng.
3. Scan lại Costing live; chặn nếu không còn `Open` hoặc style mismatch.
4. Lập plan add/update/delete/field change và trả dry-run bằng token.
5. Resolve Article trùng nếu cần.
6. Trước Apply, re-scan để chống stale.
7. Ghi field theo thứ tự dependency, xử lý Article, đặt Minutes = 1.
8. Save đúng một lần trong cancellation-deferred section.
9. Đọc lại DOM và chỉ báo thành công khi giá trị khớp.

## UX ứng dụng

- Category và Mở Master nằm trên một hàng compact.
- Tìm Style tách khỏi ba đích Costing/BOM/File.
- Badge cho biết `Open` hoặc `Cần Costing Open`; nút XLSX disabled khi chưa Open.
- Khi con trỏ ở trong panel, không auto-hide và không bật external toast.
- Kết quả nhiều style giữ panel mở để người dùng chọn.
- Ctrl+Shift+X và double-click tray đều restore bubble lẫn panel.

## Kiểm thử/QA

- Unit: workbook round-trip hai sheet, form chuẩn, filter field/section, reject
  formula/CSV, add/update/delete và `COSTING_NOT_OPEN`.
- UI: compact hooks, Open-only controls, pointer-aware auto-hide.
- Desktop: hotkey/taskbar/tray đều khôi phục bubble + panel; toast bị suppress
  khi panel visible.
- Spreadsheet QA: import bằng `artifact_tool`, inspect sheet/range và render cả
  hai sheet để kiểm tra trực quan.
- Regression: chạy toàn bộ pytest, Ruff và build PyInstaller.
