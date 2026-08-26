## Dùng để làm gì

Confirm nhanh các Style đang chờ trong EDI Buyer PO sau khi Create Transaction.
Bạn vẫn dùng được chức năng này khi OC đã được upload ngoài ứng dụng.

## Các bước

1. Mở module OC List trong WFX Smart.
2. Bấm `Confirm New` nếu dữ liệu đang ở thẻ New trên WFX.
3. Bấm `Confirm Revision` nếu dữ liệu đang ở thẻ Revision trên WFX.
4. Chờ ứng dụng Confirm và process xong từng Style.
5. Kiểm tra thông báo hoàn tất trước khi đóng trình duyệt làm việc.

> [!luuy]
> Ứng dụng xử lý lần lượt từng Style. Chỉ khi Style hiện tại process xong thì
> ứng dụng mới chuyển sang Style tiếp theo.

> [!meo]
> Với Revision, dòng không có WFX Sales Order vẫn được bỏ qua. Dòng có đúng một
> lựa chọn sẽ được chọn tự động.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Style có nhiều WFX Sales Order | Chọn thủ công một WFX Sales Order cho Style được báo rồi bấm `Confirm Revision` lại. |
| Style chưa process xong | Kiểm tra Style đang dừng trên WFX. Chỉ chạy lại khi đã biết rõ kết quả trước đó. |
| Không đọc được kết quả Confirm | Kiểm tra thẻ New hoặc Revision trên WFX trước khi chạy lại để tránh Confirm nhầm Style. |
| Màn Confirm chưa sẵn sàng | Chờ EDI Buyer PO tải xong rồi thử lại. |
