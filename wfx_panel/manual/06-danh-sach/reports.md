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

## ColorCombination Style Wise

Báo cáo theo style, mỗi file gộp tất cả OC của style đó.

1. Mở `Reports` rồi bấm `ColorCombination Style Wise`.
2. Chọn `OC Division`, `Buyer`, `Season`.
3. Chọn các mục trong danh sách `Style`. Dùng ô lọc và `Chọn tất cả` để chọn nhanh.
4. Bấm `Chọn…` để chỉ định thư mục lưu.
5. Bấm `Tải báo cáo`. Mỗi style có một file `BuyerStyleReference - StyleCode.xlsx`.

> [!meo]
> Tắt `Tải hàng loạt` nếu chỉ cần một style. Ứng dụng chọn StyleCode mới nhất,
> đặt SizeVisibility là Yes và chọn toàn bộ OC của style.
> Style không có OC được ghi `Không tìm thấy OC` và bỏ qua, không báo lỗi.

## ColorCombination PO Wise

Báo cáo theo PO, dùng danh sách PO_No riêng. Ứng dụng đi từng PO, từng
BuyerStyleReference và từng StyleCode; mỗi file gồm toàn bộ OC của đúng mã đó.

1. Mở `Reports` rồi bấm `ColorCombination PO Wise`.
2. Chọn `OC Division`, `Buyer`, `Season`. Chờ danh sách PO nạp xong.
3. Chọn các mục trong danh sách `PO No.`; mặc định chọn tất cả. Gõ vào ô `Lọc PO…`
   nếu muốn chọn một nhóm. Tắt `Tải hàng loạt` để chỉ chọn một PO.
4. Bấm `Chọn…` để chọn thư mục gốc lưu báo cáo.
5. Bấm `Tải báo cáo`. Ứng dụng tự duyệt hết BuyerStyleReference và StyleCode
   của từng PO. OC Num được tự nạp và chọn hết, không tách riêng từng OC.
6. Mỗi PO có một thư mục con. File được đặt tên `PO - StyleRef - StyleCode.xlsx`.
7. Xem thẻ kết quả: số file tải được, các mục bị bỏ qua và các mục lỗi.

> [!meo]
> Ví dụ PO `C0127-PS-2`, StyleRef `CF-LEGBB`, StyleCode `SKN0002374` sẽ được
> lưu tại `C0127-PS-2/C0127-PS-2 - CF-LEGBB - SKN0002374.xlsx` trong thư mục gốc.
> Khác với Style Wise, PO Wise tải từng StyleCode của mỗi style, không chỉ mã mới nhất.
> SearchPO giữ NULL để nạp đầy đủ danh sách PO theo buyer và mùa.

> [!luuy]
> Mục thiếu StyleCode hoặc OC Num sẽ được bỏ qua và ghi rõ lý do, không báo lỗi.
> Nếu toàn bộ mục đều thiếu dữ liệu, ứng dụng chỉ thông báo không có mục đủ dữ liệu để tải.
> Tên PO có ký tự không dùng được trong tên thư mục sẽ được đổi thành dấu gạch dưới.

## Mẹo khi tải hàng loạt

> [!meo]
> Bấm `Stop` để dừng; các file đã tải vẫn được giữ.
> File trùng tên được thêm `(2)`, `(3)` để tránh ghi đè.
> Thư mục gốc được nhớ cho lần sau. Hai báo cáo nhớ bộ tham số riêng theo tài khoản.

> [!loi]
> Tham số chưa nạp xong: chờ WFX ổn định rồi chọn lại OC Division.
> Không lưu được file: kiểm tra quyền ghi và dung lượng của thư mục đã chọn.
> Lỗi ở một mục không làm dừng cả lượt. Bấm `Chạy lại n mục lỗi` để chỉ tải lại
> những mục hỏng, dùng đúng buyer, mùa và thư mục của lần chạy trước.
