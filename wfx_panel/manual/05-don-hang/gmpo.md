## Dùng để làm gì

Xuất bảng Order Details của Blanket GMPO sang Excel để chỉnh số lượng theo PO, màu và size.

## Các bước

1. Mở bảng Order Details của Blanket GMPO trong trình duyệt làm việc.
2. Vào module `GMPO` và bấm `Xuất Excel GMPO`.
3. Chọn nơi lưu file Excel.
4. Sửa các ô màu xanh trong cột `Order Qty` của từng size. Excel tự tính lại `Total Qty`. Ô trống giữ số lượng gốc. Nhập `0` nếu muốn điền số lượng bằng 0. Sau đó lưu file.
5. Mở lại đúng tab Blanket GMPO và bấm `Nhập Order Qty`.
6. Chọn file Excel đã chỉnh.
7. Kiểm tra số lượng và `Total Qty` trên WFX, sau đó bấm `Save` trên WFX.

> [!luuy]
> Lưu ý
> Giữ nguyên tên cột và thông tin nhận diện dòng trong file. `Price` và `Total Value` dùng để đối chiếu. GMPO dạng Packing Kit hỗ trợ xuất Excel.

> [!loi]
> Gặp lỗi thì sao
> Nếu số lượng đã thay đổi trên WFX, hãy xuất lại Excel từ đúng đơn. Nếu WFX báo chỉ điền được một phần, kiểm tra các ô đã điền trên WFX trước khi lưu hoặc nhập lại.
