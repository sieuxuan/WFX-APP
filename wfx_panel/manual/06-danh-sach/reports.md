## Dùng để làm gì

Màn hình `Reports` giúp bạn chạy báo cáo WFX và tải file Excel. Hiện có báo cáo `Shipment Summary`.

## Các bước

1. Mở module `Reports`.
2. Bấm `Shipment Summary` để ứng dụng tải các tham số của báo cáo.
3. Chọn hoặc nhập các giá trị cần thiết trong phần `Tham số`.
4. Bấm `Last month` nếu muốn chọn nhanh từ ngày đầu tới ngày cuối của tháng trước.
5. Bấm `Lưu tham số` nếu muốn dùng lại các giá trị này ở lần sau.
6. Bấm `View report & Export Excel`.
7. Ứng dụng chờ WFX tải báo cáo tối đa 5 phút, sau đó Chrome tải file Excel để bạn mở hoặc lưu.

> [!meo]
> Bấm `Lưu tham số` để giữ các giá trị sau khi đóng ứng dụng. Lần chạy sau chỉ cần chỉnh phần thay đổi.
> Dropdown nhiều lựa chọn có nút `Chọn tất cả`. Tham số ngày mở lịch để bạn chọn thay vì phải gõ định dạng ngày của WFX.

> [!loi]
> Nếu báo `WFX chưa tải xong tham số báo cáo`, hãy chờ trang WFX ổn định rồi bấm lại `Shipment Summary`.

## Color Combination - Production

Báo cáo này chỉ xuất được một style mỗi lần chạy trên WFX. Ứng dụng tự lặp
qua danh sách style để bạn không phải chọn lại từng cái.

1. Mở module `Reports` rồi bấm `Color Combination - Production`.
2. Chọn `OC Division`, `Buyer`, `Season`. Mỗi lần chọn, ứng dụng chờ WFX nạp
   danh sách kế tiếp nên các ô bên dưới tạm khóa vài giây.
3. Danh sách `Style` hiện toàn bộ `BuyerStyleReference` của mùa và mặc định
   chọn hết. Bỏ tích những style không cần, hoặc gõ vào ô lọc rồi bấm
   `Chọn tất cả` để chọn nhanh nhóm đang hiện.
4. Bấm `Chọn…` để chỉ định thư mục lưu. Ứng dụng nhớ thư mục này cho lần sau.
5. Bấm `Tải báo cáo`. Mỗi style được lưu thành một file
   `BuyerStyleReference - StyleCode.xlsx`.
6. Chạy xong, thẻ kết quả cho biết bao nhiêu style thành công và bao nhiêu lỗi.

> [!meo]
> Tắt `Tải hàng loạt` nếu chỉ cần đúng một style.
> Ứng dụng tự chọn `StyleCode` có số lớn nhất, tức bản style mới nhất.
> `SizeVisibility` luôn được đặt `Yes`, còn `OCNum` giữ nguyên mặc định của WFX.
> Bấm `Stop` ở thanh dưới cùng để dừng; các file đã tải vẫn được giữ.

> [!loi]
> `Tham số báo cáo Color Combination chưa nạp xong`: WFX đang chậm. Chờ trang
> ổn định rồi chọn lại `OC Division`.
> `Không lưu được file báo cáo vào thư mục đã chọn`: kiểm tra quyền ghi và
> dung lượng của thư mục lưu.
> Style lỗi lẻ tẻ không làm dừng cả lượt; bấm `Chạy lại n style lỗi` ở thẻ
> kết quả.
