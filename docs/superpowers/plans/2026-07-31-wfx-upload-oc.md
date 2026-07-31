# Kế hoạch triển khai Upload OC trong OC List

## Goal

Hoàn thiện một workflow an toàn trong WFX Smart cho cả `Upload OC New` và
`Revise OC`: người dùng chỉ nhập hoặc sửa một file Excel đơn giản; app validate,
tự tạo `Sheet1` đúng chuẩn EDI, upload vào `EDI Buyer PO`, chỉ Create Transaction
khi ba tầng kiểm tra của WFX đều thành công và trả lỗi có thể sửa được khi fail.

## Nguyên tắc sản phẩm

- Một nguồn nhập liệu: form phát hành từ app chỉ có một sheet visible `OC INPUT`
  và một hàng header.
- Không để người dùng duy trì công thức hoặc tự ghép `Sheet1`.
- Workbook gửi WFX chỉ chứa giá trị tĩnh, đúng 51 cột và một Buyer mỗi file.
- Validate cục bộ trước khi chạm tới WFX; validate EDI lần hai trước Create
  Transaction.
- Không tự retry sau ranh giới Create Transaction vì có thể tạo OC trùng.
- File mẫu cũ tiếp tục đọc được trong giai đoạn chuyển đổi.

## Flow Upload OC New

1. User bấm `Tải form mới` trong workspace OC List.
2. App sinh `.xlsx` gồm:
   - `OC INPUT`: 24 cột nghiệp vụ, một header, màu phân biệt bắt buộc/tuỳ chọn,
     comment và dropdown có kiểm soát.
   - `REFERENCES`: danh mục Buyer/Factory/Order Type/Currency/Country/PO Type,
     trạng thái `veryHidden`.
3. User nhập mỗi phối hợp Color/Size trên một dòng rồi upload lại file đó.
4. App preflight file ZIP/XLSX, đọc `OC INPUT`, chuẩn hoá text/date/number và
   báo lỗi kèm dòng/cột.
5. App hiện review Buyer, Season, số PO distinct, số Article distinct, tổng
   Units và số dòng. Chỉ tiếp tục khi user bấm `Xác nhận Upload`.
6. App mapping 24 cột vào schema EDI 51 cột, suy ra Final Destination/Market,
   tự tính `Total Qty` theo Ship Under PO Ref + Delivery Buyer Order Ref + Buyer
   Style và ghi workbook tạm chỉ có `Sheet1`.
7. Automation mở `EDI Buyer PO`, kích hoạt `mousedown` để WFX bind đủ option,
   chọn exact Buyer, package
   `StandardSalesOrder`, Import file và `Process Package`.
8. Mở/đọc Error Resolution. Chỉ đi tiếp khi `Data Imported`, `Data Validated`,
   `Mapping Resolved` đều Success.
9. Mở Pending Transaction Detail, chọn dòng đầu và bấm `Create Transaction`.
   Thành công được ghi nhận tại tab `New`; trạng thái không xác nhận được yêu
   cầu user kiểm tra WFX và không chạy lại tự động.

## Flow Revise OC

1. User bấm `Mở report`; app mở `Reporting & Analytic` (`0004_0110`) và report
   `Upload OC from OC_Sale` (node `258`).
2. User tự chọn tham số và Export Excel trên report WFX. Đây là ranh giới sản
   phẩm đã chốt; app không tự động hoá bước download report.
3. User sửa các cột được phép và upload file xuất từ WFX vào app.
4. App yêu cầu đúng schema 51 cột, một Buyer, dữ liệu bắt buộc và định danh OC
   gốc (`DeliveryOCID`); app chuẩn hoá ngày/số và tính lại `Total Qty`.
5. App hiện cùng review nghiệp vụ và chờ user xác nhận.
6. App chạy chung pipeline EDI ở trên; transaction thành công được tạo tại tab
   `Revision`.

## Validation và thông báo lỗi

- Chỉ nhận `.xlsx`; giới hạn 100 MB, tối đa 10.000 dòng dữ liệu, chặn ZIP bất
  thường/path traversal hoặc tổng dữ liệu giải nén quá lớn.
- Header phải đúng và không trùng; không nhận ô có chuỗi lỗi công thức như
  `#VALUE!`, `#REF!`, `#N/A`.
- Ngày bắt buộc phải parse được; Units là số nguyên dương; Selling Price dương;
  Extra Production không âm.
- Buyer/Factory có dropdown gợi ý nhưng được phép nhập master data mới. Buyer
  phải khớp exact trên WFX, Factory được xác thực khi Process Package; Country
  phải thuộc bảng mapping Market. Một file không trộn Buyer; dòng trùng bị chặn.
- Lỗi trước EDI trả vị trí dòng/cột. Lỗi WFX giữ lại bảng status/detail để user
  đối chiếu. `OC_TRANSACTION_UNCONFIRMED` phải nói rõ không retry.

## Thành phần code

- `wfx_panel/oc_workbook.py`: template, parser legacy/new/revise, mapping, verify.
- `wfx_panel/automation/oc.py`: report launcher và EDI workflow.
- `wfx_panel/panel_api.py`: bridge, temp workspace, error/result contract.
- `wfx_panel/panel_app.py`: hộp thoại tải/chọn file.
- `wfx_panel/ui/`: hai card New/Revise và vùng kết quả.
- `tests/test_oc_workbook.py`, `tests/test_oc_automation.py` cùng test bridge/UI.

## Tiêu chí nghiệm thu

1. Form tải từ app chỉ để user nhìn và nhập trên `OC INPUT`, đúng một header.
2. Một file hợp lệ sinh `Sheet1` đúng 51 header, không công thức và giữ đúng số
   dòng; workbook đầu ra được verify trước khi upload.
3. Lỗi dữ liệu được phát hiện trước khi mở EDI và chỉ rõ nơi cần sửa.
4. Review hiển thị đúng Buyer/Season/PO/Article/Sum of Units; chưa confirm thì
   không gọi EDI.
5. Buyer và StandardSalesOrder được chọn exact sau `mousedown`; file được
   Process Package.
6. Một trạng thái Imported/Validated/Mapping fail thì không Create Transaction.
7. Ba trạng thái Success thì chỉ click Create Transaction một lần.
8. New trả tab `New`, Revise trả tab `Revision`; unconfirmed không tự retry.
9. Report Revise được mở đúng node 258; user tự lọc và Export Excel trên WFX.
10. Unit/integration UI tests, `node --check`, full `pytest`, `ruff check` và
   `git diff --check` đều xanh.

## Rủi ro và kiểm soát

- Markup WFX thay đổi: selector theo ID/menu/report node trước, fallback theo
  nhãn; lỗi có Run ID và ảnh chẩn đoán.
- WFX xử lý chậm: poll có timeout và cancellation checkpoint, không sleep dài.
- Dialog success không thống nhất: kiểm tra cả dialog lẫn label/bảng status.
- Giao dịch trùng: không retry tự động sau Create Transaction; user kiểm tra
  tab đích trước khi quyết định thao tác tiếp.
- Danh mục Buyer/Factory thay đổi: dropdown chỉ là gợi ý và cho nhập master data
  mới; app vẫn bắt Buyer khớp exact, còn WFX xác thực Factory khi Process
  Package. Danh sách gợi ý được cập nhật lại khi phát hành template mới.
