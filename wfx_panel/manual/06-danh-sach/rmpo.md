## Dùng để làm gì

Mở RMPO List, lọc danh sách và thao tác trên đúng RMPO ngay trong bảng điều
khiển.

## Các bước

1. Mở module RMPO List.
2. Bấm `List` nếu bạn chỉ muốn mở danh sách hiện tại.
3. Nhập tên vào ô Supplier nếu bạn muốn lọc theo nhà cung cấp.
4. Nhập số vào ô RMPO No. nếu bạn muốn lọc theo đơn.
5. Bấm `Tìm`.
6. Chờ các dòng phù hợp hiện trong bảng kết quả của ứng dụng.
7. Bấm một dòng để chọn RMPO.
8. Chọn thao tác cần dùng:
   - `Kiểm tra PO` mở OC No. của dòng đó trên WFX.
   - `Sửa PO` mở RMPO và tự bấm `Revise`. Ứng dụng có thể chờ WFX tải tối đa 3 phút.
   - `Nhập kho` hiện khi RMPO chưa ở trạng thái Received. Nút này chuyển RMPO và
     Supplier sang module `(GRN) Nhập kho` để chọn luồng nước ngoài/trong nước.
   - `Check Received` mở thông tin nhận kho khi trạng thái là Received hoặc
     Part Received.

## Mẹo

> [!meo]
> Bạn có thể điền một hoặc cả hai điều kiện. Ô để trống không được dùng để lọc.

> [!luuy]
> RMPO ở trạng thái Part Received hiện cả `Nhập kho` và `Check Received`: bạn
> có thể nhập phần còn lại hoặc kiểm tra phần đã nhận.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy RMPO | Xóa bớt một điều kiện rồi tìm lại để kiểm tra dữ liệu. |
| Dòng hoặc Status đã thay đổi | Bấm `Tìm` lại rồi chọn đúng RMPO mới nhất. |
| Chưa mở được `Revise` | Chờ WFX tải xong cửa sổ RMPO rồi thử lại. |
