## Dùng để làm gì

Tạo nhiều Style Apparel từ một file Excel trong đúng Group bạn đã chọn. Ứng
dụng chuẩn bị từng Style trên WFX nhưng không tự bấm Save.

## Các bước

1. Mở module Catalog.
2. Chọn tab `Tạo Style`.
3. Bấm `Quét lại Group` nếu danh sách Group chưa hiện.
4. Chọn đúng một Group Apparel trong ô `Group bắt buộc`.
5. Bấm `Tải form Excel`.
6. Điền dữ liệu trong sheet `Tạo Style` rồi lưu file.
7. Bấm `Chọn file & kiểm tra` và chọn file vừa lưu.
8. Đọc dòng đang chờ rồi bấm `Chuẩn bị dòng đầu tiên`.
9. Kiểm tra toàn bộ trường trên WFX.
10. Tự bấm `Save` trên WFX nếu dữ liệu đúng.
11. Quay lại bảng điều khiển và bấm `Tôi đã Save · Chuẩn bị dòng tiếp theo`.

## Cách điền file

| Cột | Cách dùng |
|---|---|
| Type | Chọn `New` hoặc `Copy`. |
| Style copy | Bắt buộc với `Copy`. Mã bắt đầu bằng SWN/SKN được tìm theo Article Code; giá trị khác được tìm theo Buyer Reference. |
| Material Type | Chọn `KNIT` hoặc `WOVEN`. |
| Các cột còn lại | `New` cần điền đủ. Với `Copy`, ô trống giữ nguyên dữ liệu Style nguồn. |

> [!luuy]
> App luôn đặt Purchase UOM là `Pcs`, Price Per là `Article` và Color Definition
> là `Single Colors`.

> [!luuy]
> App không tự Save. Chỉ xác nhận dòng tiếp theo sau khi bạn đã kiểm tra và tự
> Save dòng hiện tại trên WFX.

> [!meo]
> Nếu tìm Copy ra nhiều Style, chọn đúng Style nguồn ngay trong bảng điều khiển.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Chưa chọn được Group | Bấm `Quét lại Group`, chờ danh sách hiện rồi chọn lại. |
| File báo sai header | Tải form mới và sao chép dữ liệu vào đúng cột. |
| New báo thiếu trường | Điền đủ các cột từ Material Type đến Internal Style Ref. |
| Không tìm thấy Style nguồn | Kiểm tra `Style copy`; SWN/SKN phải là Article Code, giá trị khác phải là Buyer Reference. |
| Một danh sách Style nguồn xuất hiện | Chọn đúng dòng theo Article Code và Buyer Reference. |
| Không điền được một trường | Giữ nguyên màn hình WFX, chụp ảnh lỗi trong Lịch sử và gửi cho nhóm hỗ trợ. |
