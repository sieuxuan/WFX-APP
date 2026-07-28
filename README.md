# WFX Smart 1.0.14

WFX Smart là ứng dụng desktop Windows giúp mở và tự động hóa các màn thường
dùng của WorldFashionExchange (WFX). App chạy bằng pywebview, điều khiển một
Chromium browser hệ thống qua Playwright/CDP và không phải Chrome Extension.

Xem danh sách đầy đủ dành cho người dùng tại
[`docs/USER_FEATURES.md`](./docs/USER_FEATURES.md).

## Chức năng nổi bật

- Mở panel bằng launcher nổi, system tray hoặc hotkey `Ctrl+Shift+X`.
- Ghim module yêu thích lên đầu, trước ô tìm kiếm.
- Nhớ màn hình đang làm; có setting `Trở về List sau khi thao tác`.
- Đổi Division WOVEN/KNIT/PSSG và chỉ xác nhận khi WFX đổi thành công.
- Workflow riêng cho Catalog, OC List, Sample List, Sale ASN, Supplier List,
  Buyer List và Company Setup.
- Search chạy trên đúng List đã mở, không tải lại module. Nếu chưa mở List, app
  hướng dẫn người dùng thay vì gửi lỗi webhook.
- Lịch sử tác vụ, Run ID, ảnh lỗi cục bộ, retry có kiểm soát và Log kỹ thuật có
  thể bôi đen/copy.
- Webhook lỗi có mô tả tiếng Việt, hướng xử lý và context tài khoản; không gửi
  password, cookie, URL WFX hoặc nội dung tìm kiếm.
- Tự kiểm tra và cài GitHub Release có xác minh checksum/chữ ký và rollback.

## Cách sử dụng nhanh

1. Mở WFX Smart và lưu User ID/password trong Settings.
2. Bấm `Mở trình duyệt` để app mở browser automation và đăng nhập WFX.
3. Chọn Division nếu cần.
4. Chọn module. Với module có nhiều flow, bấm `List` trước rồi mới Search/New/
   thao tác tiếp theo.
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

Gói phát hành có dạng `WFX-Smart-v1.0.14-win64.zip`, kèm checksum `.sha256` và
chữ ký detached `.sha256.p7s`.

GitHub Actions cần hai secrets:

- `WFX_SIGNING_CERTIFICATE_BASE64`
- `WFX_SIGNING_CERTIFICATE_PASSWORD`

Updater xác minh chữ ký certificate đã ghim, SHA-256 và chỉ thay
`WFX-Panel.exe` cùng `_internal`. Nếu cài lỗi, app rollback hai thành phần này
và giữ nguyên tài khoản/settings.

Windows 11 thường có sẵn WebView2. Windows 10 cần Microsoft Edge WebView2
Runtime nếu UI không mở.
