# Thiết kế sửa download native Chrome cho WFX Smart 1.0.31

## Mục tiêu

Mọi file người dùng tải trực tiếp trên WFX hoặc qua nút download thông thường
phải được Chrome lưu vào Windows Known Folder `Downloads`. Chrome Download
history phải giữ đường dẫn thật để `Mở file` và `Hiện trong thư mục` tiếp tục
hoạt động sau khi WFX Smart nhả kết nối Playwright/CDP.

Các module chủ động cho người dùng chọn nơi lưu bằng hộp thoại Save As vẫn phải
lưu đúng đường dẫn người dùng đã chọn. Quy tắc Downloads mặc định không được ghi
đè lựa chọn đó.

## Nguyên nhân gốc đã xác nhận

Chrome history của profile automation hiện có nhiều mục hoàn tất nhưng
`target_path` và `current_path` trỏ vào
`%TEMP%\playwright-artifacts-*\<GUID>`. Đây là chế độ download artifact của
Playwright, không phải download native của Chrome. Khi artifact bị dọn, mục
history vẫn giữ đường dẫn chết, làm cả mở file và hiện trong thư mục thất bại.

`no_defaults=True` ngăn Playwright áp chế độ này cho kết nối mới, nhưng chưa
khôi phục triệt để một browser đã từng bị connection cũ đổi download behavior.
Do đó chỉ dựa vào tham số kết nối là chưa đủ.

## Thiết kế

### 1. Nguồn đường dẫn duy nhất

Runtime resolve Windows Known Folder Downloads, bao gồm trường hợp thư mục đã
redirect sang ổ khác hoặc OneDrive. Profile Chrome automation luôn được đồng bộ
`download.default_directory` về đường dẫn này trước khi Chrome khởi động.

Không lấy một `default_directory` cũ trong profile làm nguồn ưu tiên, vì chính
giá trị stale đó có thể làm app tiếp tục nhận sai folder. Windows Known Folder
là nguồn chuẩn; `%USERPROFILE%\Downloads` chỉ là fallback khi không đọc được
Known Folder.

### 2. Khôi phục download behavior tại mọi CDP attach

Mọi nhánh kết nối và tái kết nối Playwright đều truyền `no_defaults=True`.
Ngay sau khi attach, runtime gửi CDP `Browser.setDownloadBehavior` với behavior
`default` để xóa override `allowAndName`/artifact còn sót từ connection trước.
Không truyền `downloadPath` và không đặt `allow`, `allowAndName` hay `deny`.

Như vậy Chrome quay lại Download Manager native và tự dùng
`download.default_directory` trong profile. Đây là điểm sửa tại nguồn nên Chrome
history tự ghi đúng tên file và đúng đường dẫn thật.

### 3. Phân biệt download mặc định và Save As

- Download thủ công hoặc download WFX thông thường: Chrome tự lưu native vào
  Windows Downloads; runtime không gọi `download.path()` hoặc `download.save_as()`.
- Flow cần xử lý file vừa tải: chụp `snapshot_downloads()` trước click, đợi file
  native hoàn tất, rồi sao chép tới workspace nghiệp vụ nếu cần.
- Module có Save As: tiếp tục tạo/lưu file vào chính target người dùng chọn và
  mở/hiện target đó; không bị ép quay về Downloads.

### 4. Quan sát và lỗi

Khi runtime nhận event download không được flow claim, log đường dẫn Downloads
đã resolve. Nếu không reset được download behavior, connection phải thất bại rõ
ràng thay vì tiếp tục trong trạng thái có thể làm mất file.

Không sửa ngược các mục history cũ. Bản sửa bảo đảm mọi download phát sinh sau
khi chạy 1.0.31 có đường dẫn đúng; các file cũ trong artifact chỉ còn dùng được
nếu thư mục tạm vẫn tồn tại.

## Kiểm thử nghiệm thu

1. Known Folder được ưu tiên hơn `default_directory` stale trong profile.
2. Known Folder redirect/OneDrive được giữ nguyên và profile được đồng bộ về đó.
3. Mọi `connect_over_cdp` dùng `no_defaults=True` và ngay sau attach reset CDP
   download behavior về `default` mà không có `downloadPath`.
4. Reset cũng chạy sau recycle/reconnect, không chỉ lần attach đầu.
5. Download thủ công không gọi `path()`/`save_as()` và được ghi nhận ở Downloads.
6. Flow có Save As vẫn trả và mở đúng đường dẫn người dùng chọn.
7. Không có code sản phẩm nào gọi `Browser.setDownloadBehavior` với
   `allowAndName`, `allow`, `deny` hoặc thư mục Playwright artifact.
8. `python -m pytest` và `ruff check .` xanh; build panel, portable ZIP và Setup
   1.0.31 thành công.

## Phát hành

Bump toàn bộ metadata phiên bản lên `1.0.31`, cập nhật nội dung Có gì mới và tài
liệu người dùng, build bằng script chuẩn của repo. Sau khi kiểm tra artifact,
commit, push và tạo GitHub Release `v1.0.31` với cả Setup và portable ZIP nếu
credential/quyền GitHub hiện tại khả dụng.
