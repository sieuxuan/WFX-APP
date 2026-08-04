## Dùng để làm gì

Mở Supplier Inv List, lọc nhiều điều kiện hoặc Cancel Supplier Invoice an toàn.
Bạn cũng có thể mở Org Structure và System Coding trên WFX.

## Các bước

1. Mở Supplier Inv List trong nhóm Finance và bấm `List`.
2. Nhập một hoặc nhiều điều kiện: Supplier, Invoice No., PO No. và ASN/GRN No.
3. Bấm `Tìm`.
4. Để Cancel, nhập đúng Invoice No. vào phần `Cancel Supplier Invoice` rồi bấm
   nút Cancel.
5. Nếu chỉ có một dòng, ứng dụng chọn dòng đó rồi bấm `Delete` khi Status là
   `Save`, hoặc `Cancel` khi Status là `Confirm`.
6. Nếu có nhiều dòng, chọn đúng invoice trong danh sách của ứng dụng để tiếp
   tục; ứng dụng kiểm tra lại Status trước khi bấm nút trên WFX.
7. Kiểm tra hộp xác nhận native của WFX trong Chrome trước khi xác nhận thao tác.

Để mở Org Structure hoặc System Coding, bật Chế độ quản trị, mở thẻ module cần
dùng rồi bấm `Mở module trên WFX`.

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
| Màn hình không đổi | Chờ WFX tải xong rồi bấm `Mở module trên WFX` lại. |
| Status không phải Save/Confirm | Ứng dụng dừng, không bấm nút thay đổi hóa đơn. Kiểm tra lại invoice và Status trên WFX. |
| Có nhiều invoice | Chọn một dòng trong danh sách ứng dụng rồi Cancel; không thao tác trực tiếp từ kết quả mơ hồ. |
