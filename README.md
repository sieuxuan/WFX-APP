## WFX Smart 1.0.11

Chạy dev:
    python -m pip install -r requirements-dev.txt
    python -m playwright install chromium
    python -m wfx_panel.panel_app

- Hotkey toàn cục mặc định Ctrl+Shift+X, có thể đổi trong Settings: ẩn/hiện
  panel kể cả khi focus ở Chrome. Hotkey dùng global hook của thư viện
  `keyboard`; nếu cửa sổ đang focus chạy quyền Administrator cao hơn app, hook có
  thể không nhận phím — khi đó bấm icon launcher hoặc tray để mở panel.
- Launcher vuông 48×48 luôn nổi; click để mở panel ngay cạnh launcher, giữ để
  kéo và chuột phải để ẩn xuống system tray.
- Panel tự thu khi click ra ngoài. Launcher, panel và thông báo luôn được giữ
  trọn trong cùng màn hình, kể cả khi đặt sát góc, dùng nhiều màn hình hoặc đổi
  DPI/bố cục màn hình.
- Tài khoản lưu ở `.env`; mật khẩu được DPAPI mã hoá thành
  `WFX_PASSWORD_ENC`. Bản Windows từ chối lưu nếu DPAPI không hoạt động;
  theme/tuỳ chọn ở `prefs.json`.
- Mọi automation có `runId`, lịch sử cục bộ, thời gian chạy, ảnh lỗi và nút
  chạy lại cho tác vụ không chứa truy vấn nhạy cảm. Không lưu User ID/password,
  Style Code hay nội dung tìm kiếm; lịch sử và ảnh lỗi tự xóa sau 7 ngày.
- Khi tìm đúng một style Apparel, panel hiển thị thêm Season và Internal
  CostSheet Status đọc trực tiếp từ Catalog Grid.
- Cây Group/Folder của Catalog Apparel chỉ scan một lần cho mỗi tài khoản và
  được dùng lại sau khi mở lại app; nút Refresh là thao tác duy nhất ép scan lại.
- Khi automation đang chạy, panel hiển thị tiến trình rõ ràng, chặn workflow
  chạy trùng nhưng vẫn cho phép đóng/thu giao diện; toast hiện chữ đồng bộ.
- Click module chỉ mở modal trong app trước; Catalog có workflow riêng trong
  modal. Các module chưa có workflow riêng sẽ mở thẳng WFX; controller riêng
  vẫn được giữ để mở rộng sau.
- Nếu chưa có browser automation, app có thể mở Chrome Stable/Beta/Dev/Canary,
  Edge, Brave hoặc Chromium. Có thể đặt `WFX_CHROME_PATH` khi browser nằm ở
  đường dẫn riêng. Nếu không có browser tương thích, UI hướng dẫn cài/cấu hình
  thay vì crash.
- Nút mở browser sẽ mở đúng Chromium browser automation rồi đăng nhập WFX ngay
  bằng tài khoản đã lưu.
- Settings có `Luôn trên cùng`; vị trí launcher được nhớ lại giữa các lần chạy
  và tự sửa nếu màn hình đã lưu không còn tồn tại.
- Ba nút Division `WOVEN`, `KNIT`, `PSSG` nằm trước Operation. App đọc
  `#CompanyName` của WFX để highlight Division thật và chỉ báo thành công sau
  khi WFX xác nhận đã chuyển.
- Khi chưa có tài khoản hoặc WFX từ chối đăng nhập, tab Tài khoản tự mở để
  người dùng nhập lại; Settings được chia thành Tài khoản, Tự động hóa và
  Giao diện.
- App tự kiểm tra GitHub Release Stable mỗi 4 giờ. Khi có bản mới, người dùng
  chỉ cần bấm `Cập nhật ngay`; app xác minh chữ ký certificate của checksum,
  kiểm tra SHA-256, chỉ thay `WFX-Panel.exe` và `_internal`, rồi tự mở lại.
  Nếu cài lỗi, app rollback đúng hai thành phần này. Settings vẫn được giữ nguyên.
- `app.py`, `start_app.bat` và executable đều mở cùng UI pywebview; UI Tkinter
  cũ đã được loại bỏ.

## Đóng gói exe

    powershell -ExecutionPolicy Bypass -File build-panel.ps1

Kết quả: `dist/WFX-Panel/WFX-Panel.exe` (onedir).

Gói phát hành: `WFX-Smart-v1.0.11-win64.zip` kèm checksum `.sha256` và chữ ký
detached `.sha256.p7s`.

Nâng cấp từ 1.0.10 trở xuống cần giải nén 1.0.11 vào một thư mục riêng đúng một
lần. Prefix gói mới cố ý không kích hoạt updater cũ vốn có thể xóa cả thư mục
chứa EXE. Bản 1.0.9–1.0.10 cũng cần nâng cấp thủ công một lần trên máy chỉ có
Windows PowerShell 5.1. Từ 1.0.11 trở đi, cập nhật tự động dùng chuỗi xác minh,
rollback và loader CMS tương thích cả PowerShell 5.1 lẫn PowerShell 7.

Workflow release yêu cầu hai GitHub Actions secrets:

- `WFX_SIGNING_CERTIFICATE_BASE64`: nội dung PFX đã base64.
- `WFX_SIGNING_CERTIFICATE_PASSWORD`: mật khẩu PFX.

Workflow đóng thumbprint certificate vào executable và ký CMS cho checksum.
Thiếu certificate sẽ fail release; bản chạy từ source không được phép tự cài
update. EXE được giữ unsigned như 1.0.8 để không thay đổi trải nghiệm publisher
của Windows; tính xác thực updater nằm ở chữ ký CMS ghim khóa của toàn bộ ZIP.

Certificate phát hành hiện là publisher certificate riêng được ghim thumbprint:
updater xác minh chữ ký toán học và đúng public key trước khi thay file. Windows
SmartScreen vẫn có thể đánh giá file tải từ Internet như bản 1.0.8; chỉ
certificate Code Signing từ CA công cộng hoặc Microsoft Store mới thay đổi tín
hiệu publisher của Windows.

- Windows 11 có sẵn WebView2 trong phần lớn bản cài.
- Windows 10 cần Microsoft Edge WebView2 Runtime. Edge hiện đại thường đã cài
  runtime này; nếu UI không mở, cài/cập nhật WebView2 Runtime.
- Automation không bundle Chromium; nó dùng một Chromium browser hệ thống qua
  CDP như `login.py`.
- Settings của bản đóng gói nằm tại `%LOCALAPPDATA%\WFX-Panel`, tách khỏi
  `dist`, nên build/update/rollback không xóa tài khoản hoặc tùy chọn cũ.

Test tích hợp WFX thật bằng tài khoản trong `.env`:

    $env:WFX_LIVE_TEST = "1"
    python -m pytest tests/test_wfx_live.py -v

Test không in credential hoặc Code ra output.
