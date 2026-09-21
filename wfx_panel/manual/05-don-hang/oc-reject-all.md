## Dùng để làm gì

Reject lần lượt toàn bộ PO trong thẻ New hoặc Revision đang mở trên WFX.

## Các bước

1. Mở EDI Buyer PO trên WFX.
2. Chọn đúng thẻ New hoặc Revision cần xử lý.
3. Mở module OC List trong WFX Smart.
4. Bấm `Reject All · tab đang mở`.
5. Đọc cảnh báo rồi xác nhận Reject toàn bộ.
6. Chờ ứng dụng xử lý hết từng PO.

> [!luuy]
> Reject không thể hoàn tác. Ứng dụng chỉ xử lý thẻ đang mở và không tự chuyển
> sang thẻ còn lại.

> [!luuy]
> Ứng dụng chỉ chuyển sang PO tiếp theo sau khi PO hiện tại đã rời khỏi bảng.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không xác định được thẻ đang mở | Chọn lại thẻ New hoặc Revision trên WFX rồi bấm `Reject All · tab đang mở` lại. |
| PO chưa rời khỏi bảng | Kiểm tra kết quả Reject trên WFX trước khi chạy lại. |
| Không đọc được kết quả Reject | Không chạy lại ngay. Kiểm tra PO còn xuất hiện trong thẻ đang mở hay không. |
| Màn Reject chưa sẵn sàng | Chờ EDI Buyer PO tải xong rồi thử lại. |
