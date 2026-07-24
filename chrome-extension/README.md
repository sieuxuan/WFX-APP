# WFX Smart Automation — Chrome Extension

Đây là bản Chrome Extension độc lập, không cần Tampermonkey.

## Cài bằng Load unpacked

1. Mở `chrome://extensions`.
2. Bật **Developer mode**.
3. Chọn **Load unpacked**.
4. Chọn thư mục `dist/WFX-Smart-Chrome-Extension`.
5. Reload tab WFX.

Extension chỉ chạy trên:

`https://prosports.worldfashionexchange.com/*`

Thiết lập tài khoản, hotkey và Catalog được lưu trong `chrome.storage.local`, tách biệt hoàn toàn với Tampermonkey.

## Build lại

Chạy từ thư mục project:

```powershell
powershell -ExecutionPolicy Bypass -File .\chrome-extension\build-extension.ps1
```

Build tạo:

- `chrome-extension/dist/WFX-Smart-Chrome-Extension/`
- `chrome-extension/dist/WFX-Smart-Chrome-Extension-v1.8.1.zip`
