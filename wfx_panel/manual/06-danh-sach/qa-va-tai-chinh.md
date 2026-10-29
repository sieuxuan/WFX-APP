## Dùng để làm gì

Mở danh sách hoặc tạo mới QA Request, Advance Payment Request và Expense
Invoice.

## Các bước

1. Mở QA List, Advance PR List hoặc Expense Inv List.
2. Bấm `List` để mở danh sách tương ứng trên WFX.
3. Bấm `New` nếu bạn muốn tạo yêu cầu hoặc hóa đơn mới.
4. Khi tạo Advance Payment Request, ứng dụng chọn sẵn `Advance Type = Against RMPO`.
5. Khi tạo Expense Invoice, ứng dụng chọn sẵn `Invoice Type = General Expense`.
6. Trong Advance PR List, nhập một hoặc nhiều điều kiện Buyer Name, Supplier,
   Invoice Number và Order No. rồi bấm `Tìm`.
7. Trong Expense Inv List, nhập một hoặc nhiều điều kiện Supplier, Invoice No.,
   Created By và Status rồi bấm `Tìm`. Không cần mở List trước: ứng dụng tự mở
   Expense Inv List khi WFX đang ở màn khác, rồi báo số hóa đơn tìm thấy hoặc
   báo không có dòng nào khớp.
8. Chờ WFX mở đúng màn hình rồi nhập dữ liệu nghiệp vụ.

## Nhập nhanh Expense Invoice từ Excel

1. Mở Expense Inv, bấm `Tải mẫu Excel`, chọn nơi lưu. Mẫu lưu ngay, không
   cần mở WFX hay chọn Supplier trước. Mẫu có sẵn dropdown đầy đủ cho
   Supplier, Invoice Currency, Payment Term, Ledger, Brand và Team.
2. Điền sheet `Expense Invoice`. Giữ nguyên 13 cột. Dòng đầu nhập Supplier,
   Invoice No., Invoice Date, GL Date, Invoice Currency, Payment Term, Due Date.
   Comments, Brand và Team có thể để trống.
3. Mỗi dòng nhập một Ledger, Qty lớn hơn 0 và Rate không âm. Qty có tối đa
   2 chữ số thập phân; Rate có tối đa 4 chữ số thập phân. Các dòng sau có thể
   để trống thông tin chung để dùng lại dòng đầu. Mỗi file chỉ có một hóa đơn.
4. Chọn dropdown cho Supplier, Invoice Currency, Payment Term, Ledger, Brand,
   Team. Ngày nhập dưới dạng ngày Excel hoặc `dd/mm/yyyy`. Không dùng công thức.
5. Lưu file rồi bấm `Chọn file Excel`. Kiểm tra Supplier, Invoice No., số dòng
   và tổng tiền hiện trong app. Bấm `Bỏ file` nếu muốn chọn lại.
6. Bấm `Điền trên WFX`. App đặt Invoice Type là `General Expense`, Sub-Type
   là `ALL OTHER EXPENSES`, điền và kiểm tra lại dữ liệu.
7. Khi app báo hoàn tất, tự kiểm tra hóa đơn trên WFX rồi bấm Save/Confirm.
   App không tự bấm các nút này.

> [!luuy]
> Nếu form đang có dữ liệu, app dừng để tránh ghi đè. Hãy kiểm tra/lưu hóa đơn
> đang làm rồi tự mở `New` trống trước khi chọn file và chạy lại. Nếu dừng hoặc
> gặp lỗi giữa chừng, hãy kiểm tra phần đã điền trên WFX trước khi chạy lại.

> [!meo]
> Lần đầu, dropdown dùng danh sách có sẵn trong app. Sau mỗi lần `Điền trên WFX`
> thành công, app tự lưu danh sách thật của tài khoản và Division đang dùng;
> tải lại mẫu để nhận danh sách mới nhất. Lựa chọn vẫn được đối chiếu lại khi
> điền WFX.

Phần `Tra cứu` luôn hiện ngay dưới phần nhập Excel, gồm các ô tìm kiếm và nút
`Mở Expense Inv List`.

## Mẹo

> [!meo]
> Nút `New` đi thẳng tới màn hình tạo mới. Bạn không cần bấm `List` trước.

> [!meo]
> Ứng dụng chỉ báo hoàn tất sau khi WFX xác nhận giá trị mặc định đã được chọn.

> [!meo]
> Với Advance PR và Expense Invoice, bạn có thể kết hợp nhiều điều kiện; để
> trống các ô không cần dùng.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy module | Bật Chế độ quản trị nếu module thuộc quyền quản trị, hoặc nhờ quản trị WFX kiểm tra quyền tài khoản. |
| New chưa mở | Chờ WFX tải xong rồi bấm `New` lại một lần. |
| Search chưa chạy | Nhập ít nhất một điều kiện, chờ danh sách WFX tải xong rồi thử lại. |
| File Expense Invoice chưa hợp lệ | Sửa dòng/cột được nêu trong thông báo; nếu đổi header thì tải lại mẫu. |
| File đã hết hiệu lực | Chọn lại file khi quá 30 phút hoặc sau khi đổi tài khoản/Division. |
| Dropdown thiếu Supplier/Ledger mới | Điền một hóa đơn trên WFX bằng app để cập nhật danh sách, rồi tải lại mẫu. Trong lúc chờ có thể gõ đúng tên như trên WFX. |
| Chưa điền xong hoặc đã bấm Stop | Kiểm tra phần đã điền trên WFX; lưu/xử lý bản đang làm trước khi mở New trống và chọn lại file. |
