## Dùng để làm gì

Tạo nhiều Style Apparel từ một file Excel trong đúng Group bạn đã chọn. Ứng
dụng chuẩn bị từng Style trên WFX. `Tự động Save` luôn mặc định tắt; bạn chỉ bật
khi muốn app Save ngay sau khi điền xong từng dòng.

## Các bước

1. Mở module Catalog.
2. Chọn tab `Tạo Style`.
3. Bấm nút làm mới nhỏ cạnh `Group đích` nếu cây Group chưa hiện.
4. Mở ô chọn Group, gõ tên hoặc đường dẫn để tìm rồi chọn đúng một Group Apparel.
5. Bấm `Tải mẫu Excel`.
6. Điền dữ liệu trong sheet `Tạo Style` rồi lưu file.
7. Bấm `Chọn file Excel` và chọn file vừa lưu.
8. Bấm `Chuẩn bị Style`. Nếu có lỗi, xem hướng dẫn ngay dưới dòng đang xử lý.
   Chọn `Thử lại` hoặc `Bỏ qua` khi nút xuất hiện. Khi bỏ qua, đừng Save bản nháp
   của dòng đó trên WFX.
9. Nếu `Tự động Save` đang tắt, kiểm tra các trường trên WFX, tự bấm `Save`,
   rồi chọn `Xác nhận đã Save`. Nếu gặp lỗi khi Save thủ công, có thể
   chọn `Bỏ qua, chưa Save` sau khi xác nhận Style chưa được lưu. Nếu bật
   `Tự động Save`, app bấm Save sau khi điền xong.
10. Bấm `Chuẩn bị Style` để xử lý dòng tiếp theo. Cuối lượt, xem tổng kết và
    mở mục `Bỏ qua` để đọc lý do của từng dòng.

`Style 1/1 · Dòng Excel 2` nghĩa là file có một Style, lấy dữ liệu ở hàng 2.
Tiến độ và tổng kết nằm trong màn Tạo Style. Windows báo khi gặp lỗi trong lúc
chuẩn bị Style.

## Cách điền file

| Cột | Cách dùng |
|---|---|
| Type | Chọn `New` hoặc `Copy`. |
| Style copy | Bắt buộc với `Copy`. Dropdown lấy `Article Name` trong Article List có `Article Category = Apparel`; app tìm trên WFX bằng `ArticleCode/Name`. |
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
> Dropdown ưu tiên snapshot PostgreSQL dùng chung. Nút `Đồng bộ ngay` nằm trong
> `Cài đặt > Tài khoản`. Nếu server tạm lỗi, app giữ nguyên cache gần nhất; Group
> đã chọn vẫn dùng để quét WFX khi cần làm mới trực tiếp.

> [!luuy]
> Bấm `Tải mẫu Excel` sẽ hỏi nơi lưu file ngay. Nếu dữ liệu dropdown đã quá 30
> ngày, app lấy danh sách mới sau khi bạn chọn xong nơi lưu, nên bước này có thể
> chờ thêm một lúc. Lúc quét, app tự mở rồi tự đóng một cửa sổ Style trên trình
> duyệt làm việc; cửa sổ đó chỉ để đọc danh sách và không ghi gì lên WFX.

> [!meo]
> Nếu tìm Copy ra nhiều Style, chọn đúng Style nguồn ngay trong bảng điều khiển.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Chưa chọn được Group | Bấm nút làm mới nhỏ, tìm bằng tên/đường dẫn rồi chọn lại. |
| Chưa quét được dropdown | Giữ Chrome đăng nhập, chọn Group có quyền tạo Style rồi tải lại form. App vẫn ưu tiên cache gần nhất khi server hoặc WFX tạm lỗi. |
| File báo sai header | Tải form mới và sao chép dữ liệu vào đúng cột. |
| New báo thiếu trường | Điền đủ các cột từ Material Type đến Internal Style Ref. |
| Không tìm thấy Style nguồn | Kiểm tra `Style copy` theo đúng Article Name trong danh sách Apparel. |
| Một danh sách Style nguồn xuất hiện | Chọn đúng dòng theo Article Code hoặc Article Name. |
| WFX chỉ hiện Material Type | Chờ app chuẩn bị dòng và đưa cửa sổ Style cần kiểm tra lên trước. |
| Không điền được một trường | Kiểm tra giá trị trong Excel với dropdown WFX. Có thể thử lại hoặc bỏ qua dòng và xử lý dòng kế tiếp. |
| Lỗi trong bước Save tự động | Kiểm tra Style đã xuất hiện trên WFX chưa trước khi chạy lại dòng đó. |
