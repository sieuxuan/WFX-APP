## Dùng để làm gì

Dành cho Admin. Ghi lại cách WFX nạp danh sách Article khi mở Catalog, để
nhóm phát triển biết sau này app có thể lấy danh sách Article thẳng từ WFX
thay vì đọc từng dòng trên màn hình. Thao tác này chỉ đọc: không sửa, không
lưu và không gửi gì lên mạng.

## Các bước

1. Đăng nhập tài khoản WFX có quyền quản trị.
2. Mở `Cài đặt > Tài khoản`.
3. Bật `Chế độ quản trị`.
4. Ở dòng `Dò nguồn dữ liệu Catalog`, bấm `Dò ngay`.
5. Đọc hộp xác nhận rồi bấm `OK`.
6. Chờ trình duyệt làm việc mở lại Catalog Apparel > Master.
7. Đọc đường dẫn file kết quả hiện ngay dưới tên dòng.

## Mẹo

> [!meo]
> File kết quả nằm trong thư mục `diagnostics` của dữ liệu ứng dụng. Tên file
> bắt đầu bằng `catalog-` và kết thúc bằng ngày giờ chạy. Gửi file này cho nhóm
> phát triển khi được yêu cầu.

> [!luuy]
> File không chứa mật khẩu, cookie, Session ID hay địa chỉ WFX đầy đủ. Giá trị
> mẫu của từng cột chỉ giữ vài ký tự đầu để nhận ra định dạng.

> [!luuy]
> Kết quả tìm Catalog đang mở sẽ được làm mới. Hãy tìm lại Style sau khi dò.

## Gặp lỗi thì sao

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy dòng `Dò nguồn dữ liệu Catalog` | Bật `Chế độ quản trị`; tài khoản không có quyền quản trị sẽ không thấy dòng này. |
| Báo Catalog chưa sẵn sàng để dò | Chờ WFX tải xong rồi bấm `Dò ngay` lại. |
| Báo không ghi được file chẩn đoán | Kiểm tra ổ đĩa còn trống và quyền ghi thư mục dữ liệu ứng dụng. |
