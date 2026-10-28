# Expense Invoice từ Excel

## Luồng đã triển khai

Trong Expense Inv: **Tải mẫu Excel → Chọn file Excel → Điền trên WFX**.
Mẫu có đúng 13 cột, một file cho một hóa đơn, mỗi dòng là một Ledger. Dòng
sau được kế thừa thông tin chung từ dòng đầu; dữ liệu mâu thuẫn bị từ chối.

Khi tải mẫu, người dùng chỉ chọn nơi lưu; app ghi file ngay, không mở Chrome
và không cần chọn Supplier. Mẫu có dropdown đầy đủ cho Supplier, Invoice
Currency, Payment Term, Ledger, Brand, Team, gắn bằng named range và sheet nguồn
veryHidden. Nguồn danh sách, theo thứ tự ưu tiên:

1. Cache danh sách thật của đúng tài khoản + Division (`expense-options.json`
   ở data dir), làm mới sau mỗi lượt `Điền trên WFX` thành công.
2. Bộ dữ liệu ban đầu đóng gói `assets/templates/Expense-Invoice-options.json`,
   quét từ WFX lúc phát hành bằng `python scripts/seed_expense_options.py`
   (mở một form Expense Invoice - New trên Chrome automation trước khi chạy).
3. Không có cả hai thì vẫn lưu mẫu, cột lựa chọn để nhập tự do.

`read_expense_options` chỉ đọc handler dropdown mà WFX tự gọi
(`GetBindDDLData`, GET tới `HdlrWFXDropDown.ashx`): Supplier, Payment Terms,
Ledger theo Sub-Type `ALL OTHER EXPENSES`; Currency là hợp các mã tiền tệ mặc
định của Supplier (WFX hiển thị Currency bằng mã). Brand/Team đọc từ Flex Field
đã bind sẵn. Không mousedown Invoice Currency khi chưa có Supplier vì WFX bật hộp
"Please select Supplier first". Form New không có dòng Expense Details nên không
có editor Ledger — đây là lý do bản quét cũ luôn báo "Chưa đọc đủ dropdown".

Dropdown trong Excel dùng errorStyle warning: danh sách có thể cũ hơn WFX, nên
người dùng vẫn gõ được Supplier/Ledger mới; WFX đối chiếu exact khi điền.

UI có phần nhập Excel và phần Tra cứu (Search + `Mở Expense Inv List`) luôn hiện.

Review chỉ đọc file local. Snapshot đã parse được giữ trong bộ nhớ 30 phút,
ràng buộc tài khoản/Division và chỉ dùng cho một lượt chạy. File gốc thay đổi
sau review không làm thay đổi snapshot. Phải chọn lại file để nhận thay đổi.

Automation nhận diện đúng WFXExpenseInvoice.aspx và bảng Expense Details,
chỉ điền New trống. Draft có Supplier/Invoice No./Comments/Flex Field/dòng
chi phí hoặc file đính kèm được bảo vệ. New chỉ chọn Supplier được phép tiếp
tục khi khớp Supplier trong file. Khi chưa có form, app mở New qua menu
đã có. Invoice Type cố định General Expense; Sub-Type cố định ALL OTHER
EXPENSES. Các lựa chọn phải khớp duy nhất; Ledger nhận full label hoặc mã exact.
Mọi trường được đọc lại sau khi điền. Automation không Save/Confirm và không
sử dụng Import Expense Invoice native. Hoàn tất có footer/toast để user kiểm tra.

## Mẫu và nơi tiếp tục phát triển

- Mẫu gốc để đóng gói: `wfx_panel/assets/templates/Expense-Invoice.xlsx`.
  Mẫu này giữ layout, định dạng văn bản/ngày/số, kiểm tra ngày/số và hướng dẫn.
  Sáu dropdown được app gắn từ dữ liệu WFX vào bản tải xuống.
- Đọc file và gắn dropdown: `wfx_panel/workbooks/expense_invoice.py`.
- Quét/điền WFX: `wfx_panel/automation/expense_invoice.py`.
- Review, cache, mã dùng một lần: `wfx_panel/controllers/finance.py`.
- Hộp thoại tải/chọn mẫu: `wfx_panel/app/dialogs.py`.
- Bridge: `wfx_panel/panel_api.py`, `wfx_panel/panel_app.py`.
- Giao diện: `wfx_panel/ui/index.html`, `ui/panel/lists.js`,
  `ui/panel/module_actions.js` và `ui/style.css`.
- Hướng dẫn: `wfx_panel/manual/06-danh-sach/qa-va-tai-chinh.md`.
- Khảo sát UI ban đầu: `docs/EXPENSE_INVOICE_SCAN.md`.
- Các kiểm thử riêng: `tests/test_expense_invoice.py`.

Mẫu được đóng gói qua `wfx_panel/wfx-panel.spec`; cập nhật source rồi chạy
`./build-panel.ps1 -SkipDependencies`. Không sửa tay file trong dist.

## Kiểm chứng

Các kiểm thử riêng bao phủ schema 13 cột, ngày/số, dòng kế thừa, dữ liệu
mâu thuẫn, giữ Invoice No. dạng text, dropdown/named range, snapshot file,
mã dùng một lần, đổi Division, khôi phục session trước khi sửa dữ liệu,
khớp Ledger duy nhất và editor đóng ngay trong onchange.

Kiểm thử trình duyệt dùng trang mô phỏng WFX độc lập: điền hai dòng, thêm
dòng, kiểm tra giá trị đã commit, bảo vệ draft và chứng minh không bấm
Save/Confirm. Kiểm tra giao diện 440px không tràn ngang hoặc lỗi JavaScript.
Không coi kiểm thử mô phỏng là xác nhận trên hệ thống WFX thật.

Bộ kiểm thử toàn dự án và Ruff đã chạy thành công. Bản desktop Python 3.12
đã build tại `dist/WFX-Panel/WFX-Panel.exe`. Chưa chạy import file thật trên
WFX; phiên ứng dụng đã cài đang mở vẫn là bản trước khi sửa. Cần mở bản build
mới để thử tải mẫu dropdown và nhập file bằng dữ liệu nghiệp vụ thực tế.

Nếu bản trong `dist` đang chạy, bản sửa Supplier/UI được đóng gói riêng tại
`dist-expense-fix/WFX-Panel/WFX-Panel.exe` để giữ nguyên phiên đang chạy.

Lệnh kiểm tra: `python -m pytest -q` và `python -m ruff check .`.

## Phạm vi hiện tại

Chỉ nhận XLSX, tối đa 5 MB/500 dòng. Qty > 0, tối đa 2 số thập phân;
Rate >= 0, tối đa 4 số thập phân. Không nhận công thức trong sheet nhập.
Comments/Brand/Team tùy chọn, các trường chung còn lại bắt buộc ở dòng đầu.

Khi lỗi hoặc Stop sau khi đã bắt đầu, giữ form điền dở để người dùng kiểm tra;
không rollback/xóa dữ liệu hoặc tự chạy lại các bước ghi. Tổng tiền review
là tổng Qty × Rate trong file; người dùng kiểm tra lại số tiền/tỷ giá và
nghiệp vụ WFX trước khi Confirm. Chưa có luồng nhiều hóa đơn trong một file.
