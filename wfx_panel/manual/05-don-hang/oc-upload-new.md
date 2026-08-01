## Dùng để làm gì

Kiểm tra file OC mới trên máy, xem lại số liệu rồi tạo OC trên WFX sau khi bạn
xác nhận.

## Các bước

1. Mở module OC List.
2. Bấm `Tải file mẫu` trong thẻ Upload OC New.
3. Mở file và chỉ nhập dữ liệu trong sheet OC INPUT.
4. Lưu file Excel.
5. Bấm `Chọn file` trong thẻ Upload OC New.
6. Đọc bảng Review trước khi Upload.
7. Kiểm tra Buyer, Season, số PO, số Style, Sum of Units và số dòng.
8. Bấm `Xác nhận Upload` để bắt đầu tạo OC trên WFX.

## Mẹo

> [!meo]
> Mỗi file chỉ được chứa một Buyer. Buyer và Factory có thể được nhập thêm nếu
> danh sách gợi ý chưa có giá trị mới.

> [!luuy]
> Ngày Buyer Order phải trước ngày Raw Material ETA. Ngày Raw Material ETA phải
> trước ngày Buyer Delivery và OC Delivery.

> [!luuy]
> Chọn file chỉ kiểm tra trên máy và hiện Review. Chỉ nút `Xác nhận Upload` mới
> bắt đầu thao tác trên WFX. Bấm `Hủy` thì không có dữ liệu nào được gửi đi.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Báo file có nhiều Buyer | Tách dữ liệu thành từng file, mỗi file chỉ giữ một Buyer. |
| Báo sai ngày hoặc số lượng | Mở đúng ô được báo, sửa giá trị rồi chọn lại file. |
| WFX chưa sẵn sàng nhận file | Giữ file đã sửa, kiểm tra phiên WFX rồi thực hiện Upload lại. |
