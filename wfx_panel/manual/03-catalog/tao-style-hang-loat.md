## Dùng để làm gì

Tạo nhiều Style Apparel từ một file Excel trong đúng Group bạn đã chọn. Ứng
dụng chuẩn bị từng Style trên WFX. `Tự động Save` luôn mặc định tắt; bạn chỉ bật
khi muốn app Save ngay sau khi điền xong từng dòng.

## Các bước

1. Mở module Catalog.
2. Chọn tab `Tạo Style`.
3. Bấm nút làm mới nhỏ cạnh `Group bắt buộc` nếu cây Group chưa hiện.
4. Mở ô chọn Group, gõ tên hoặc đường dẫn để tìm rồi chọn đúng một Group Apparel.
5. Bấm `Tải form Excel`.
6. Điền dữ liệu trong sheet `Tạo Style` rồi lưu file.
7. Bấm `Chọn file & kiểm tra` và chọn file vừa lưu.
8. Đọc dòng đang chờ rồi bấm `Chuẩn bị dòng đầu tiên`.
9. Nếu `Tự động Save` đang tắt, kiểm tra toàn bộ trường trên WFX, tự bấm `Save`,
   rồi chọn `Tôi đã Save · Chuẩn bị dòng tiếp theo`.
10. Nếu `Tự động Save` đang bật, app Save đúng một lần sau khi điền xong và nút
    chuẩn bị chuyển thẳng sang dòng kế tiếp.

## Cách điền file

| Cột | Cách dùng |
|---|---|
| Type | Chọn `New` hoặc `Copy`. |
| Style copy | Bắt buộc với `Copy`. Mã bắt đầu bằng SWN/SKN được tìm theo Article Code; giá trị khác được tìm theo Buyer Reference. |
| Material Type | Chọn `KNIT` hoặc `WOVEN`. |
| Các cột còn lại | `New` cần điền đủ. Với `Copy`, ô trống giữ nguyên dữ liệu Style nguồn. |

Các cột Material Type, Buyer, Division, Product Group, Sub-Category, Color
Card, Size Range và Season có dropdown lấy từ cache dùng chung. Sub-Category tự
đổi danh sách theo Product Group của đúng dòng.

> [!luuy]
> App luôn đặt Purchase UOM là `Pcs`, Price Per là `Article` và Color Definition
> là `Single Colors`.

> [!luuy]
> `Tự động Save` mặc định tắt mỗi lần mở app. Khi bật, hãy kiểm tra file trước vì
> Style sẽ được ghi lên WFX ngay sau khi điền xong.

> [!meo]
> Dropdown ưu tiên snapshot PostgreSQL dùng chung và chỉ tự tải tối đa một lần
> mỗi 30 ngày. Nút `Đồng bộ ngay` nằm trong `Cài đặt > Tài khoản`. Nếu server
> tạm lỗi, app giữ nguyên cache gần nhất; Group đã chọn vẫn dùng để quét WFX khi
> cần làm mới trực tiếp.

> [!meo]
> Nếu tìm Copy ra nhiều Style, chọn đúng Style nguồn ngay trong bảng điều khiển.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Chưa chọn được Group | Bấm nút làm mới nhỏ, tìm bằng tên/đường dẫn rồi chọn lại. |
| Chưa quét được dropdown | Giữ Chrome đăng nhập, chọn Group có quyền tạo Style rồi tải lại form. App vẫn ưu tiên cache gần nhất khi server hoặc WFX tạm lỗi. |
| File báo sai header | Tải form mới và sao chép dữ liệu vào đúng cột. |
| New báo thiếu trường | Điền đủ các cột từ Material Type đến Internal Style Ref. |
| Không tìm thấy Style nguồn | Kiểm tra `Style copy`; SWN/SKN phải là Article Code, giá trị khác phải là Buyer Reference. |
| Một danh sách Style nguồn xuất hiện | Chọn đúng dòng theo Article Code và Buyer Reference. |
| Không điền được một trường | Giữ nguyên màn hình WFX, chụp ảnh lỗi trong Lịch sử và gửi cho nhóm hỗ trợ. |
