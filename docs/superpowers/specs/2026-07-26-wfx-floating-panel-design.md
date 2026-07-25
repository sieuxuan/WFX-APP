# WFX Floating Panel (Python) — Design

**Ngày:** 2026-07-26
**Mục tiêu:** Thay Chrome Extension bằng một app desktop Python đóng vai "floating panel" —
nổi luôn-trên-cùng đè lên Chrome, gọi/ẩn bằng hotkey toàn cục, giao diện giống hệt panel
extension, sau này đóng gói thành `.exe`. Engine automation ([login.py](../../../login.py))
giữ nguyên; đây chỉ là front-end mới thay [app.py](../../../app.py) (tkinter).

## Bối cảnh & quyết định đã chốt

- **Thay thế extension** (không chạy song song) → app dùng lại hotkey quen thuộc `Ctrl+Shift+X`.
- **Ẩn về system tray** khi bấm đóng hoặc nhấn hotkey; app vẫn chạy nền.
- **Công nghệ UI:** `pywebview` + tái dùng **nguyên** HTML/CSS panel của extension để giống
  pixel-perfect. Backend Python/Playwright nối qua bridge `js_api`.
- **Logo:** dùng chính SVG chữ "W" của extension (khung lục giác + nét W) cho brand header,
  icon cửa sổ và icon tray.
- **Giữ `app.py` tkinter cũ** làm bản dự phòng, không xoá. Entrypoint chính mới là `panel_app.py`.
- **Bỏ nút "launcher W" nổi trong trang** của extension — thay bằng tray icon + hotkey.

## Kiến trúc

```
wfx_panel/
├── panel_app.py        # entrypoint: cửa sổ pywebview + hotkey + tray + PanelAPI
├── panel_api.py        # class PanelAPI (js_api) — cầu nối WebView -> login.py
├── prefs.py            # đọc/ghi tài khoản (.env) + preferences (prefs.json)
├── assets/
│   └── wfx.ico         # icon exe/cửa sổ/tray, render từ SVG W của extension
└── ui/
    ├── index.html      # trích từ template panel extension (main.js ~2484-2589)
    ├── style.css       # trích nguyên khối STYLES (main.js ~2780-3098)
    └── panel.js        # MỚI: nối nút -> pywebview.api.*, render status/log/theme
login.py                # GIỮ NGUYÊN — engine Playwright
```

### Lớp 1 — UI (WebView)

- `index.html` + `style.css` lấy từ panel extension, **bỏ** phần launcher button và các phần
  chỉ có nghĩa trong trang WFX (shadow DOM host, `:host` → `:root`/`body`).
- Thành phần giữ lại y hệt extension:
  - Header: brand W + "WFX Smart / Automation workspace"; nút log, settings, close.
  - Catalog Control: dropdown Category + nút "Mở Catalog"; hàng Code (Tìm/Costsheet/BOM);
    hàng Buyer Reference (Tìm/Costsheet/BOM).
  - Ô search lọc module + nhãn hotkey `Ctrl + Shift + X`.
  - 3 nhóm module Operation/Finance/Admin, mỗi module có icon badge + accent
    (cyan/violet/amber). Danh sách module = `MODULE_GROUPS` (đồng bộ với `MODULE_GROUPS`
    trong app.py hiện tại).
  - Footer: trạng thái phiên + version.
  - Settings sheet: User ID/Password (nút hiện/ẩn), hotkey, "đóng panel sau khi mở module",
    theme sáng/tối (segmented), nút "Lưu thiết lập & kết nối".
  - Overlay log: dòng log tiếng Việt thân thiện + nút sao chép.
- `panel.js` (viết mới, mỏng):
  - Bind mọi nút `data-catalog-action`, nút module, save settings, theme, hotkey display,
    search filter module → gọi `window.pywebview.api.<method>(...)`.
  - Nhận cập nhật từ Python (Python gọi `window.evaluate_js`) qua các hàm global:
    `window.wfxPushLog(line)`, `window.wfxSetStatus(tone,label,detail)`,
    `window.wfxSetBusy(bool)`, `window.wfxSetAccount(userId)`, `window.wfxApplyTheme(theme)`.
  - KHÔNG chứa logic automation DOM của extension.

### Lớp 2 — Backend Python

**`panel_app.py`**
- Tạo cửa sổ pywebview: `frameless=True`, `on_top=True`, `width≈440`, `height≈600`,
  neo góc trên-phải màn hình, `easy_drag` qua vùng header (class `pywebview-drag-region`).
- Khởi động: nạp `ui/index.html`, khởi tạo `PanelAPI`, đăng ký hotkey + tray, và chạy
  auto-login nền nếu đã lưu tài khoản.
- **Hotkey toàn cục** `keyboard.add_hotkey("ctrl+shift+x", toggle)` → hiện/ẩn cửa sổ. Bắt ở
  cấp OS nên hoạt động cả khi focus đang trong Chrome/iframe WFX.
- **System tray** `pystray`: icon = `assets/wfx.ico`; menu **Hiện panel** / **Thoát**. Nút
  close của panel và hotkey (khi đang hiện) → `window.hide()` về tray, không thoát app.
- Thoát thật chỉ khi chọn "Thoát" ở tray; khi đó gỡ hotkey, dừng tray, đóng cửa sổ.

**`panel_api.py` — class `PanelAPI`** (mỗi method chạy `login.py` trên thread nền, trả kết
quả + stream log về WebView; không block UI thread):
- `get_initial_state()` → { account.userId, theme, hotkeyLabel, closeAfterModule, logs }.
- `login()` → `login.run(...)`.
- `check_session()` → `login.check_session(...)`.
- `open_module(module_name, xpath)` → `login.open_module(...)`.
- `prepare_catalog(category_name)` → mở Catalog+Category+Master+Filter (dùng
  `login.open_module("Catalog", ...)` + `login.set_catalog_category(...)`).
- `find_code(category_name, code, destination)` → `login.quick_find_catalog(..., "code", ...)`.
- `find_buyer_reference(category_name, query, destination)` →
  `login.quick_find_catalog(..., "buyer_reference", ...)`.
- `save_account(user_id, password)` → ghi `.env` qua `prefs.py`.
- `set_theme(theme)` / `set_close_after_module(bool)` → ghi `prefs.json`.
- `copy_log()` không cần (clipboard làm ở JS); `clear_log()` xoá log.
- Mỗi callback log của login.py (`_write_log`) được bọc để đẩy `window.evaluate_js(
  "window.wfxPushLog(...)")` — an toàn escape chuỗi.

**`prefs.py`**
- Tài khoản: dùng lại định dạng `.env` hiện có (`WFX_USER_ID`, `WFX_PASSWORD`) để tương thích
  `login.py` (đọc qua `os.getenv`). Ghi bằng cơ chế temp-file replace như app.py.
- Preferences (theme, closeAfterModule, hotkeyLabel) trong `prefs.json` cạnh app.

### Lớp 3 — `login.py` giữ nguyên

Không sửa engine. Panel chỉ gọi các hàm public đã có. Nếu cần, chỉ thêm (không đổi chữ ký cũ)
— ví dụ một hàm gộp `prepare_catalog` — nhưng ưu tiên tái dùng hàm sẵn có.

## Luồng dữ liệu

```
WebView (panel.js)  --pywebview.api.X()-->  PanelAPI (thread nền)
       ^                                          |
       |  window.evaluate_js(wfxPushLog/...)      v
       +---------------------------------  login.py (Playwright/CDP -> Chrome automation)
```

- UI thread không bao giờ chạy Playwright; mọi lời gọi automation ở thread nền, kết quả và
  log được marshal về JS.
- Chrome automation vẫn là tiến trình Chrome riêng (`--remote-debugging-port`, profile
  `WFX-Automation`) do `login.py` tự mở — không đụng Chrome cá nhân.

## Xử lý lỗi

- Mọi method `PanelAPI` bọc try/except, trả `{ok, code, message}` như login.py; JS hiển thị
  message ở footer + log, đổi tone (success/warning/error).
- Hotkey: nếu `keyboard` đăng ký thất bại (thiếu quyền), log cảnh báo + vẫn dùng được nút
  tray để hiện/ẩn.
- WebView2 thiếu (máy không phải Win11): hiển thị hộp thoại hướng dẫn cài WebView2 Runtime.
- Auto-login lỗi/timeout: footer báo trạng thái, không treo (login.py đã có watchdog/timeout).

## Kiểm thử

- **Thủ công (chính):** mở panel → auto-login → mở vài module → prepare Catalog → find Code
  (0/1/nhiều kết quả) → Costsheet/BOM → đổi theme → đổi tài khoản → hotkey ẩn/hiện → tray
  Hiện/Thoát. Xác nhận khớp tiêu chí nghiệm thu trong CLAUDE.md (Master retry, không báo giả
  khi rawRows=0, đếm đúng unique Code, v.v. — do login.py đảm nhiệm, panel chỉ hiển thị).
- **Đơn vị:** `prefs.py` (đọc/ghi .env + prefs.json), và hàm escape chuỗi đẩy log sang JS.
- **Smoke:** `panel_app.py` khởi động, nạp UI, PanelAPI trả `get_initial_state()` hợp lệ
  (có thể kiểm bằng gọi trực tiếp class, không cần WebView).

## Đóng gói exe

- PyInstaller onedir; `--add-data "wfx_panel/ui;wfx_panel/ui"`, `--icon assets/wfx.ico`,
  `--noconsole`. Playwright cần trình duyệt: dùng CDP tới Chrome hệ thống (login.py) nên
  KHÔNG cần bundle Chromium của Playwright — chỉ cần gói `playwright` python.
- Ghi chú README cách chạy exe + yêu cầu WebView2 (mặc định có trên Win11).

## Ngoài phạm vi (YAGNI)

- Không port lại logic automation JS của extension sang panel.js.
- Không làm launcher button nổi trong trang.
- Không đa ngôn ngữ; giữ tiếng Việt như hiện tại.
- Không auto-update exe.

## Tiêu chí hoàn thành

1. Panel pywebview hiển thị giống panel extension (brand W, module có icon/accent, Catalog
   Control, Settings sheet, log overlay, theme sáng/tối).
2. `Ctrl+Shift+X` ẩn/hiện panel toàn cục kể cả khi focus ở Chrome.
3. Đóng panel → thu về tray; tray có Hiện/Thoát; app chạy nền.
4. Auto-login + mọi nút (module, prepare Catalog, find Code/Buyer Ref, Costsheet/BOM, save
   account, theme) hoạt động qua login.py.
5. Log tiếng Việt thân thiện + sao chép được.
6. Đóng gói `.exe` chạy trên Windows 11 (WebView2 sẵn có), không cần cài Python.
7. `app.py` cũ vẫn còn, `login.py` không bị đổi chữ ký hàm.
