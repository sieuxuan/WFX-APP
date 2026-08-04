## Dùng để làm gì

Tạo `(GDN) Dispatch` từ Invoice GRN sau khi hàng thành phẩm đã nhập kho trên WFX.

## Các bước

1. Hoàn tất `(GRN) nhập kho hàng thành phẩm` trên WFX.
2. Chờ ít nhất 15 phút để dữ liệu được đồng bộ.
3. Mở module `(GDN) Dispatch` trong WFX Smart.
4. Nhập đúng `Invoice GRN`.
5. Đánh dấu xác nhận GRN đã hoàn tất ít nhất 15 phút.
6. Bấm `Tạo Dispatch`.
7. Theo dõi sáu bước ngay trong thẻ `Tiến độ GDN`.

WFX Smart sẽ tự tải report, làm mới file Excel, Process Package và chọn giao dịch
`Pending` mới nhất theo `Processed ON`.

Các bước hiển thị lần lượt là: mở báo cáo, tải Excel, chuẩn hóa XLSX, mở EDI,
Process Package, rồi tạo và xác nhận transaction.

> [!luuy]
> Chờ đủ 15 phút
> Không Submit ngay sau khi nhập GRN. Dữ liệu chưa đồng bộ có thể làm package lỗi
> hoặc không tạo được Dispatch.

> [!loi]
> Gặp lỗi thì sao
> Nếu WFX báo invoice đã được import, hãy kiểm tra GDN hiện có trước khi chạy lại.
> Nếu thông báo nói chưa xác nhận được kết quả, không Submit lại. Bấm
> `Mở EDI kiểm tra` trong thẻ tiến độ, rồi kiểm tra giao dịch mới nhất để tránh
> tạo trùng.
