## Dùng để làm gì

Mở Supplier Inv List, lọc nhiều điều kiện hoặc Cancel Supplier Invoice an toàn.
Bạn cũng có thể mở Org Structure và System Coding trên WFX.

## Các bước

1. Mở Supplier Inv List trong nhóm Finance và bấm `List`.
2. Nhập một hoặc nhiều điều kiện: Supplier, Invoice No., PO No. và ASN/GRN No.
3. Bấm `Tìm`.
4. Để Cancel, nhập đúng Invoice No. vào phần `Cancel Supplier Invoice` rồi bấm
   nút Cancel.
5. Nếu có đúng một invoice trùng khớp hoàn toàn Invoice No. bạn gõ, ứng dụng
   chọn dòng đó rồi bấm `Delete` khi Status là `Save`, hoặc `Cancel` khi Status
   là `Confirm`.
6. Nếu không có dòng nào trùng khớp hoàn toàn, ứng dụng dừng lại và hiện danh
   sách gần đúng với tiêu đề `Không có Invoice No. trùng khớp — chọn thủ công`.
   Tìm kiếm của WFX là tìm chứa chuỗi, nên gõ `SI-102` vẫn ra `SI-1024`.
7. Nếu có nhiều dòng, chọn đúng invoice trong danh sách của ứng dụng để tiếp
   tục; ứng dụng kiểm tra lại Status trước khi bấm nút trên WFX.
8. Kiểm tra hộp xác nhận native của WFX trong Chrome trước khi xác nhận thao tác.

Để mở Org Structure hoặc System Coding, bật Chế độ quản trị rồi bấm thẳng thẻ
module trong danh sách; ứng dụng mở ngay trên WFX, không có màn trung gian.

## Mẹo

> [!meo]
> Supplier Inv List nằm trong nhóm Finance. Org Structure và System Coding nằm
> trong nhóm Admin.

> [!luuy]
> Module chỉ hiện khi tài khoản được cấp quyền phù hợp trên WFX.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy module Admin | Mở Cài đặt, thẻ Giao diện và bật Chế độ quản trị. |
| WFX báo không có quyền | Nhờ quản trị WFX kiểm tra quyền của tài khoản hiện tại. |
| Màn hình không đổi | Chờ WFX tải xong rồi bấm lại thẻ module. |
| Status không phải Save/Confirm | Ứng dụng dừng, không bấm nút thay đổi hóa đơn. Kiểm tra lại invoice và Status trên WFX. |
| Có nhiều invoice | Chọn một dòng trong danh sách ứng dụng rồi Cancel; không thao tác trực tiếp từ kết quả mơ hồ. |
| Ứng dụng báo không có Invoice No. trùng khớp | Bạn gõ thiếu hoặc thừa ký tự. Đối chiếu lại Invoice No. trên WFX, hoặc chọn đúng dòng trong danh sách gần đúng. |
