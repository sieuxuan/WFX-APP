## WFX Smart 1.0.7

Chạy dev:
    python -m pip install -r requirements-dev.txt
    python -m playwright install chromium
    python -m wfx_panel.panel_app

- Hotkey toàn cục mặc định Ctrl+Shift+X, có thể đổi trong Settings: ẩn/hiện
  panel kể cả khi focus ở Chrome.
- Launcher vuông 48×48 luôn nổi; click để mở panel ngay cạnh launcher, giữ để
  kéo và chuột phải để ẩn xuống system tray.
- Panel tự thu khi click ra ngoài. Launcher, panel và thông báo luôn được giữ
  trọn trong cùng màn hình, kể cả khi đặt sát góc, dùng nhiều màn hình hoặc đổi
  DPI/bố cục màn hình.
- Tài khoản lưu ở `.env`; theme/tuỳ chọn ở `prefs.json`.
- Mọi automation có `runId`, lịch sử cục bộ, thời gian chạy, ảnh lỗi và nút
  chạy lại. Không lưu User ID/password vào lịch sử.
- Khi tìm đúng một style Apparel, panel hiển thị thêm Season và Internal
  CostSheet Status đọc trực tiếp từ Catalog Grid.
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
  người dùng nhập lại; Settings được chia thành Tài khoản và Ứng dụng.
- App tự kiểm tra GitHub Release Stable mỗi 4 giờ. Khi có bản mới, người dùng
  chỉ cần bấm `Cập nhật ngay`; app tải gói đã xác minh SHA-256, đóng, cài và
  tự mở lại. Nếu cài lỗi, app tự trở về bản trước. Settings vẫn được giữ nguyên.
- `app.py`, `start_app.bat` và executable đều mở cùng UI pywebview; UI Tkinter
  cũ đã được loại bỏ.

## Đóng gói exe

    powershell -ExecutionPolicy Bypass -File build-panel.ps1

Kết quả: `dist/WFX-Panel/WFX-Panel.exe` (onedir).

Gói phát hành: `WFX-Panel-v1.0.7-win64.zip` kèm file checksum `.sha256`.

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
