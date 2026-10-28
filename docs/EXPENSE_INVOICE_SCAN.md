# Khảo sát New Expense Invoice — 28/10/2026

## Phạm vi và kết quả thực tế

Đã khảo sát trực tiếp phiên WFX đang mở qua giao diện Chrome. Trang đích là
`/WFXBase4.0/WFXExpenseInvoice.aspx?InvoiceType=Expense`, tiêu đề
`Expense Invoice - New`. Không lưu URL chứa thông tin phiên vào tài liệu này.

Đã tìm thấy đủ 13 trường người dùng yêu cầu. Đã mở editor Ledger, Qty, Rate
và danh sách Supplier, Payment Term, Brand, Team. Chưa chạy import có dữ liệu,
chưa bấm Save, Confirm hoặc Confirm & New. Đây là kết quả khảo sát giao diện,
chưa phải kết quả kiểm thử tính năng import của WFX Smart.

## Ánh xạ 13 cột Excel

| Cột Excel | Vị trí / ID đã thấy trên WFX | Cách thao tác cần triển khai |
| --- | --- | --- |
| Supplier | `#ddlSupplier` | Dropdown Select2 có tìm kiếm; phải xác nhận đúng tên/giá trị đã chọn. |
| Invoice No. | `#txtInvoiceNo` | Ô nhập văn bản; giữ số 0 đầu và nội dung nguyên bản từ Excel. |
| Invoice Date | `#dtInvoiceDate` | Ô ngày, WFX đang hiển thị dạng `28 Oct 2026`. |
| GL Date | `#dtGLDate` | Ô ngày cùng dạng Invoice Date. |
| Invoice Currency | `#ddlInvoiceCurrency` | Dropdown; giá trị đang hiển thị USD. Chưa liệt kê toàn bộ option. |
| Payment Term | `#ddlPaymentTerms` | Dropdown Select2; tên trong file cần ánh xạ tới option thực tế. |
| Due Date | `#dtDueDate` | Ô ngày; cần điền sau Supplier/Payment Term rồi đọc lại. |
| Ledger | Ô `ColLedgerAcName`, editor `#ddlLedgerAcName` | Mở editor trong đúng dòng Expense Details rồi chọn dropdown Select2. |
| Qty | Ô `ColExpenseQty`, editor `#txtExpenseQty` | Editor hiện khi mở ô của dòng; WFX định dạng lại khi rời ô. |
| Rate | Ô `ColExpenseRate`, editor `#txtExpenseRate` | Editor hiện khi mở ô của dòng; WFX định dạng lại khi rời ô. |
| Comments | `#txtComments` | Ô ghi chú chung của hóa đơn, không phải Description của từng dòng. |
| Brand | `#ddlBrand` | Dropdown Select2 ở Flex Field. |
| Team | `#ddlTeam` | Dropdown Select2 ở Flex Field; thấy Hongkong, Vietnam, Singapore. |

Các ID trên được thấy trong cây accessibility của WFX. Chưa kiểm thử locator
Playwright hoặc các handler thay đổi giá trị bằng script trong lượt khảo sát này.

## Hai trường cố định

- Invoice Type: `#ddlInvoiceType`, label `General Expense`. Code nguồn hiện tại
  đã dùng value `GeneralExpense` trong `automation/modules/creation.py`.
- Sub-Type: `#ddlSubType`, label chính xác trên WFX là **`ALL OTHER EXPENSES`**,
  có chữ **S** ở cuối. Không dùng chuỗi `ALL OTHER EXPENSE` làm exact label.
  Value nội bộ của option chưa được đọc; khi triển khai phải lấy từ option
  thực tế, không đoán value bằng label.

## Expense Details

- Header table: `#gridExpenseInvoiceExpenseDetail_tblGridHeader`.
- Content table: `#gridExpenseInvoiceExpenseDetail_tblGridContent`.
- Editor dùng chung: `#gridExpenseInvoiceExpenseDetail_divFocus`.
- Form đang có một dòng chi phí trống; mở ô Ledger bằng double-click thấy
  `#ddlLedgerAcName`, mở Qty/Rate thấy editor tương ứng.
- Ledger là dropdown, không phải ô text tự do. Nhãn có cả mã và tên, ví dụ
  `2111(2111 - MACHINERY)` và `6421901(6421901-WFX SUBSCRIPTION)`.
- Có nút `Add` và `Delete` trong khu vực Expense Details. Lượt này chưa bấm
  Add/Delete nên chưa xác minh cách tạo nhiều dòng hoặc định danh dòng mới.
- Các cột còn lại có Article, Ledger Amount (Doc. Currency), Ledger Amount
  (Comp. Currency), Cost Center, Buyer Order Profitability và Description.
  Chúng không nằm trong 13 cột được yêu cầu.
- Qty đang bằng 0 được WFX hiển thị thành `0.00`, Rate bằng 0 thành `0.0000`
  khi rời editor. Chưa thử công thức Qty × Rate với dữ liệu khác 0.

Khi triển khai, phải giới hạn locator vào đúng content table và đúng dòng;
không lấy editor theo ID toàn trang mà không xác nhận dòng đang chỉnh sửa.
Phải đọc lại giá trị sau khi rời ô để xác nhận WFX đã nhận và tính lại tiền.

## Dropdown và thứ tự điền

Supplier, Payment Term, Ledger, Brand và Team đều đã hiện danh sách Select2.
Supplier có danh sách dài, cây accessibility bị cắt; không dùng kết quả đó
làm snapshot đầy đủ cho dropdown của file mẫu.

Payment Term có tên hiển thị và mã nội bộ khác nhau. Ví dụ đã thấy
`TT Before Shipment` gắn với option mang hậu tố `7740009`; Brand cũng có
nhãn và mã khác nhau như `UNITED LEGWEAR` / `ULC`. Các hậu tố này chỉ là
bằng chứng từ UI, không phải cam kết về value cho mọi phiên/Division.

Thứ tự đề xuất để kiểm thử khi triển khai:

1. Xác nhận đúng trang Expense Invoice - New.
2. Chọn Invoice Type rồi Supplier; chờ các dữ liệu phụ thuộc ổn định.
3. Chọn Sub-Type đúng label, Currency và Payment Term.
4. Điền Invoice No., Invoice Date, GL Date và Due Date; đọc lại sau các thay
   đổi dropdown để tránh ngày mặc định ghi đè ngày từ file.
5. Điền lần lượt Ledger, Qty, Rate cho từng dòng; rời editor và đọc lại.
6. Điền Comments, Brand, Team và đối chiếu dữ liệu cuối cùng.
7. Chỉ thông báo hoàn tất khi đã đối chiếu đủ; giữ form cho user tự kiểm tra
   và tự Save/Confirm trên WFX.

Đây là thứ tự đề xuất; các hiệu ứng đổi Supplier/Payment Term/Currency và
công thức tiền cần được kiểm thử thêm, chưa được xác nhận trong lượt này.

## Import có sẵn trong WFX

Tab danh sách đang mở riêng dùng
`/WFXBase4.0/WFXExpenseInvoiceList.aspx`, bảng
`gridExpenseInvoiceList`. Không nhầm trang này với New hoặc AP Invoice List.

Menu `More` có hai mục:

- `Expense Invoice Download Import Format`.
- `Import Expense Invoice`.

Đã mở giao diện import: tiêu đề `Import Excel`, có nút `Import`, `Close` và
khu vực chọn file `#FileUpload`. Chưa chọn file và chưa bấm Import. Chưa xác
minh import native tạo chứng từ ngay hay chỉ chuẩn bị bản nháp; chưa xác minh
schema của format native. Vì vậy không dùng đường native này làm luồng tự
điền trước Confirm nếu chưa khảo sát thêm ranh giới ghi dữ liệu.

## Luồng WFX Smart theo yêu cầu

`Tải form Excel → người dùng điền → chọn/import file → validate local → tự
điền New Expense Invoice → thông báo hoàn tất → người dùng kiểm tra và Confirm`.

Form có đúng 13 cột theo thứ tự người dùng đưa ra. Hai trường cố định không
cần trở thành cột người dùng nhập. Cần xác định quy tắc một/nhiều hóa đơn
trong một file khi triển khai; đề xuất ban đầu là mỗi file một hóa đơn, mỗi
dòng là một Ledger, các trường chung phải thống nhất giữa các dòng.

Những phần chưa được thực hiện: tạo workbook mẫu, parser/validation, bridge,
UI import/review, automation điền dữ liệu, thông báo hoàn tất và kiểm thử
toàn luồng. Lượt này chỉ xác minh khả năng truy cập form và các control.

## Điểm tích hợp nguồn hiện tại

- `wfx_panel/automation/modules/creation.py`: mở trực tiếp New qua menu
  `//*[@id="0065_0880_0030_0010"]/a`, hiện chỉ chọn General Expense.
- `wfx_panel/controllers/finance.py`: điều phối nghiệp vụ Finance.
- `wfx_panel/panel_api.py`: bridge từ giao diện sang controller.
- `wfx_panel/app/dialogs.py`: hộp thoại tải/chọn file.
- `wfx_panel/workbooks/`: vị trí parser và writer Excel thuần Python.
- `wfx_panel/ui/index.html`: workspace `expense_invoice` hiện có List/New/Search.
- `wfx_panel/ui/panel/module_actions.js`: dispatcher các nút Expense Invoice.
- `wfx_panel/manual/06-danh-sach/qa-va-tai-chinh.md`: hướng dẫn cần cập nhật
  cùng lúc triển khai tính năng.
