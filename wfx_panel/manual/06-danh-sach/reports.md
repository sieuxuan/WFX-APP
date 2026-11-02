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

Báo cáo này có hai cách xuất: gộp theo Style hoặc tách riêng từng OCNum.
Chọn cách buyer yêu cầu; ứng dụng tự lặp qua các style đã chọn.

1. Mở module `Reports` rồi bấm `Color Combination - Production`.
2. Chọn `OC Division`, `Buyer`, `Season`. Mỗi lần chọn, ứng dụng chờ WFX nạp
   danh sách kế tiếp nên các ô bên dưới tạm khóa vài giây.
3. Danh sách `Style` hiện toàn bộ `BuyerStyleReference` của mùa và mặc định
   chọn hết. Bỏ tích những style không cần, hoặc gõ vào ô lọc rồi bấm
   `Chọn tất cả` để chọn nhanh nhóm đang hiện.
4. Trong `Xuất báo cáo theo`, chọn `Theo Style — gộp tất cả OCNum` (mặc định)
   hoặc `Theo OCNum — mỗi OC một file`.
5. Bấm `Chọn…` để chỉ định thư mục lưu. Ứng dụng nhớ thư mục này cho lần sau.
6. Bấm `Tải báo cáo`.
   - Theo Style: mỗi style có một file `BuyerStyleReference - StyleCode.xlsx`,
     gồm tất cả OCNum của style.
   - Theo OCNum: ứng dụng tải từng OC của mỗi style đã chọn, mỗi file chỉ có
     một OC và mang tên `BuyerStyleReference - StyleCode - OCNum.xlsx`.
7. Chạy xong, thẻ kết quả cho biết bao nhiêu báo cáo thành công và bao nhiêu lỗi.

> [!meo]
> Tắt `Tải hàng loạt` nếu chỉ cần đúng một style.
> Ứng dụng tự chọn `StyleCode` có số lớn nhất, tức bản style mới nhất.
> `SizeVisibility` luôn được đặt `Yes` ở cả hai cách xuất.
> Style chỉ có một OCNum vẫn được tải thành một file riêng khi xuất theo OCNum.
> Nếu style chưa có OCNum, ứng dụng hiện `Không tìm thấy OC` và bỏ qua style đó.
> Đây là thông báo bình thường, không phải lỗi ứng dụng; các style có OC vẫn được tải.
> Tắt `Tải hàng loạt` và chọn một style nếu chỉ cần tách OC của style đó.
> File trùng tên được thêm số `(2)`, `(3)` để giữ file đã tải.
> Bấm `Stop` ở thanh dưới cùng để dừng; các file đã tải vẫn được giữ.

> [!loi]
> `Tham số báo cáo Color Combination chưa nạp xong`: WFX đang chậm. Chờ trang
> ổn định rồi chọn lại `OC Division`.
> `Không lưu được file báo cáo vào thư mục đã chọn`: kiểm tra quyền ghi và
> dung lượng của thư mục lưu.
> Style hoặc OC lỗi lẻ tẻ không làm dừng cả lượt; bấm `Chạy lại n mục lỗi`
> ở thẻ kết quả. Khi xuất theo OCNum, ứng dụng chỉ tải lại những OC lỗi;
> nếu chưa đọc được danh sách OC của một style thì tải lại toàn bộ OC của style đó.
> Nếu các mục có lỗi đều không tải được file, ứng dụng báo lỗi và giữ danh sách cần chạy lại.
> Nếu toàn bộ style chưa có OCNum, ứng dụng chỉ thông báo `Không tìm thấy OC`.
