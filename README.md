# WFX Smart 1.0.15

WFX Smart là ứng dụng desktop Windows giúp mở và tự động hóa các màn thường
dùng của WorldFashionExchange (WFX). App chạy bằng pywebview, điều khiển một
Chromium browser hệ thống qua Playwright/CDP và không phải Chrome Extension.

Xem danh sách đầy đủ dành cho người dùng tại
[`docs/USER_FEATURES.md`](./docs/USER_FEATURES.md).
Benchmark RAM/tốc độ của bản này nằm tại
[`docs/PERFORMANCE_1.0.15.md`](./docs/PERFORMANCE_1.0.15.md).

## Chức năng nổi bật

- Mở panel bằng launcher nổi, taskbar, system tray hoặc hotkey `Ctrl+Shift+X`;
  chuột phải launcher để chọn nơi thu gọn.
- Launcher và menu tự scale theo DPI của từng màn hình, gồm màn 2K ở 125%.
- Alert nghiệp vụ của WFX vẫn hiện trên Chrome và chờ người dùng xác nhận.
- Bản EXE mặc định khởi động cùng Windows; người dùng có thể tắt trong Settings
  và lựa chọn này được giữ nguyên.
- Chuyển màn và phản hồi tiến trình có animation ngắn, mượt, đồng thời tự giảm
  chuyển động theo thiết lập accessibility của Windows.
- Ghim module yêu thích lên đầu, trước ô tìm kiếm; module đã ghim không bị lặp
  lại ở danh sách bên dưới.
- Nhớ màn hình đang làm; có setting `Trở về List sau khi thao tác`.
- Đổi Division WOVEN/KNIT/PSSG và chỉ xác nhận khi WFX đổi thành công.
- Workflow riêng cho Catalog, OC List, Sample List, Sale ASN, RMPO,
  Indent/User Indent, QA/Advance PR/Expense Invoice, Supplier List, Buyer List
  và Company Setup.
- Search ưu tiên đúng List đã mở; nếu chưa mở, app tự vào đúng List, chờ
  grid/Floating Filter rồi mới tìm.
- Flow module bắt đầu automation ngay trong lúc app đưa Chrome lên foreground;
  nhận diện Floating Filter phản hồi nhanh hơn nhưng vẫn xác nhận đúng grid.
- Playwright/CDP được giữ trên một worker dùng chung giữa các flow, giảm thời
  gian kết nối lại và tránh tạo nhiều driver đồng thời; tự nhả sau 1 phút không
  có thao tác để trả RAM cho hệ thống.
- Nút `Stop` nằm ngay dòng trạng thái dưới cùng, dừng ở checkpoint an toàn và
  không cắt ngang bước Save của WFX.
- Chrome/WebView2 được giới hạn số renderer và tắt dịch vụ nền không cần thiết,
  tối ưu cho máy Windows RAM 8 GB.
- Lịch sử tác vụ, Run ID, ảnh lỗi cục bộ, retry có kiểm soát và Log kỹ thuật có
  thể bôi đen/copy.
- Webhook lỗi có mô tả tiếng Việt, hướng xử lý và context tài khoản; không gửi
  password, cookie, URL WFX hoặc nội dung tìm kiếm. Nếu nhánh automation cũ
  không trả message, app vẫn suy ra module/trường tìm/Division từ metadata an
  toàn thay vì gửi mô tả trống.
- Endpoint webhook được chốt trước khi tạo background thread; môi trường test
  đã tắt reporting không thể gửi trễ payload giả sang production.
- Tự kiểm tra và cài GitHub Release có xác minh checksum/chữ ký và rollback.

## Cách sử dụng nhanh

1. Mở WFX Smart và lưu User ID/password trong Settings. Khi đã kết nối, tab Tài
   khoản chỉ hiện trạng thái và nút `Đổi tài khoản`.
2. Bấm `Mở trình duyệt` để app mở browser automation và đăng nhập WFX.
3. Chọn Division nếu cần.
4. Chọn module. Có thể Search ngay; app tự mở List khi cần. Với New/Đổi FOC,
   bấm `List` trước để kiểm tra đúng màn hình.
5. Dùng ngôi sao để ghim module thường dùng.

Mật khẩu được DPAPI mã hóa thành `WFX_PASSWORD_ENC`. Bản Windows từ chối lưu
mật khẩu nếu DPAPI không hoạt động. Settings của bản đóng gói nằm tại
`%LOCALAPPDATA%\WFX-Panel`, tách khỏi thư mục cài đặt.

## Chạy bản development

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m wfx_panel.panel_app
```

Browser không được bundle trong ứng dụng. WFX Smart hỗ trợ Chrome Stable/Beta/
Dev/Canary, Edge, Brave hoặc Chromium. Có thể đặt `WFX_CHROME_PATH` nếu browser
nằm ở đường dẫn riêng.

## Kiến trúc chính

- `wfx_panel/automation/`: Playwright/CDP và các workflow WFX.
- `wfx_panel/panel_api.py`: bridge giữa UI và automation.
- `wfx_panel/catalog_controller.py`: state/context của Catalog.
- `wfx_panel/panel_app.py`: pywebview, launcher, tray và hotkey.
- `wfx_panel/ui/`: HTML/CSS/JavaScript của panel.
- `wfx_panel/telemetry.py`: webhook, outbox và redaction dữ liệu nhạy cảm.
- `n8n/`: Code node và workflow webhook có thể import.
- `CLAUDE.md`: đặc tả kỹ thuật chuẩn bắt buộc.

## Đóng gói EXE

```powershell
powershell -ExecutionPolicy Bypass -File build-panel.ps1
```

Kết quả:

```text
dist/WFX-Panel/WFX-Panel.exe
```

Đây là bản `onedir`; cần giữ cả `WFX-Panel.exe` và thư mục `_internal`.

## Kiểm thử

```powershell
python -m pytest
ruff check .
node --check wfx_panel/ui/panel.js
```

Test tích hợp WFX thật sử dụng tài khoản trong `.env`:

```powershell
$env:WFX_LIVE_TEST = "1"
python -m pytest tests/test_wfx_live.py tests/test_wfx_live_module_contexts.py -v
```

Test không được in credential hoặc nội dung tìm kiếm ra output.

## Release và cập nhật

Gói phát hành có dạng `WFX-Smart-v1.0.15-win64.zip`, kèm checksum `.sha256` và
chữ ký detached `.sha256.p7s`.

GitHub Actions cần hai secrets:

- `WFX_SIGNING_CERTIFICATE_BASE64`
- `WFX_SIGNING_CERTIFICATE_PASSWORD`

Updater xác minh chữ ký certificate đã ghim, SHA-256 và chỉ thay
`WFX-Panel.exe` cùng `_internal`. Nếu cài lỗi, app rollback hai thành phần này
và giữ nguyên tài khoản/settings.

Windows 11 thường có sẵn WebView2. Windows 10 cần Microsoft Edge WebView2
Runtime nếu UI không mở.
