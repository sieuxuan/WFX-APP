# WFX Panel Phase 2 — Design

**Ngày:** 2026-07-26
**Tiền đề:** [WFX Floating Panel](2026-07-26-wfx-floating-panel-design.md) đã chạy được
(nhánh `feat/wfx-floating-panel`). Phase 2 bổ sung 4 tính năng người dùng yêu cầu và
chuyển Chrome extension sang thư mục lưu trữ.

## Quyết định đã chốt

- **Poll trạng thái:** CDP kiểm tra mỗi 5s (rẻ); phiên WFX + giờ login cập nhật **theo sự
  kiện** từ kết quả automation, cộng nút refresh tay. Không poll Playwright định kỳ.
- **Toast:** dùng `pystray.Icon.notify()` có sẵn — không thêm dependency. Đánh đổi: bấm vào
  toast không mở lại panel được.
- **Autostart:** hai công tắc riêng — "Khởi động cùng Windows" và "Mở ẩn trong tray".
- **Toast có công tắc bật/tắt riêng, mặc định BẬT.**
- Chrome extension chuyển sang `legacy/chrome-extension/`, chỉ để backup.

## Kiến trúc

```
wfx_panel/
├── autostart.py     # MỚI: registry HKCU\...\Run
├── hotkey.py        # MỚI: parse/validate/chuẩn hoá tổ hợp phím (hàm thuần)
├── status.py        # MỚI: kiểm tra Chrome CDP còn sống
├── prefs.py         # + autostart, start_hidden, toast_enabled, hotkey
├── panel_api.py     # + result sink, status, set_hotkey/set_* settings
├── panel_app.py     # + luồng poll status, toast, mở ẩn, đăng ký lại hotkey
└── ui/              # + footer health, ô bắt phím, 3 công tắc
legacy/chrome-extension/   # chuyển từ chrome-extension/
```

**Cơ chế trung tâm — result sink.** `PanelAPI.set_result_sink(fn)` nhận callback
`fn(method_name: str, result: dict, elapsed: float)`, được gọi sau MỌI method automation.
Một cơ chế phục vụ hai tính năng: cập nhật trạng thái phiên/giờ login (miễn phí — kết quả
đã có sẵn) và quyết định bắn toast. Không viết hai đường riêng.

## Chi tiết từng phần

### 1. `wfx_panel/hotkey.py` (hàm thuần, dễ test)

```python
DEFAULT = "ctrl+shift+x"
MODIFIERS = ("ctrl", "alt", "shift", "windows")   # thứ tự chuẩn hoá
UNSAFE_KEYS = frozenset({"backspace", "delete", "enter", "tab", "space", "escape", "esc"})
```

- `normalize(spec: str) -> str` — hạ chữ thường, bỏ khoảng trắng, sắp modifier theo
  `MODIFIERS`, đặt phím nền cuối. Ném `ValueError` (thông điệp tiếng Việt) nếu không hợp lệ.
- `is_valid(spec: str) -> bool` — không ném, trả bool.
- `format_label(spec: str) -> str` — `"ctrl+shift+x"` → `"Ctrl + Shift + X"`.
- `from_event(event: dict) -> str` — dựng từ payload keydown của JS
  `{ctrl, alt, shift, meta, key, code}`.

**Luật hợp lệ** (kế thừa `UNSAFE_HOTKEY_CODES` của extension, xem CLAUDE.md):

1. Đúng **một** phím nền (không phải modifier).
2. Phím nền **không** nằm trong `UNSAFE_KEYS`. Hotkey toàn cục nuốt Backspace sẽ hỏng thao
   tác gõ trên **toàn máy**, không riêng app — nghiêm trọng hơn hẳn bản extension.
3. Phải có **ít nhất một modifier**, HOẶC phím nền là `F2`–`F12`.

### 2. `wfx_panel/autostart.py`

```python
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WFXPanel"
```

- `launch_command() -> str` — khi đóng gói (`sys.frozen`): `f'"{sys.executable}"'`; khi chạy
  dev: `f'"{pythonw_path}" -m wfx_panel.panel_app'` (dùng `pythonw.exe` cạnh `sys.executable`
  để không hiện cửa sổ console).
- `is_enabled(*, key_path=RUN_KEY, value_name=VALUE_NAME) -> bool`
- `enable(command=None, *, key_path, value_name) -> None`
- `disable(*, key_path, value_name) -> None`
- `sync(enabled: bool, *, key_path, value_name) -> bool` — trả trạng thái thực tế sau khi ghi.

Chỉ ghi `HKEY_CURRENT_USER`, **không cần quyền Administrator**. Ngoài Windows (`os.name !=
"nt"`) mọi hàm trả `False`/no-op để test và import không vỡ. `key_path`/`value_name` bơm được
nên test dùng khoá nháp `Software\WFX-Panel-Test`, không đụng khoá thật.

### 3. `wfx_panel/status.py`

- `cdp_url() -> str` — đọc `WFX_CDP_HOST` (mặc định `127.0.0.1`) và `WFX_CDP_PORT` (mặc định
  `9222`), khớp đúng `login.py`.
- `chrome_alive(timeout: float = 1.0) -> bool` — GET `{cdp_url()}/json/version`, trả `True`
  khi JSON có `webSocketDebuggerUrl`. Mọi `OSError`/JSON lỗi → `False`.

Tự đọc env thay vì gọi `login._chrome_is_ready` (hàm private) — biên rõ ràng, test được bằng
một HTTP server cục bộ.

### 4. `wfx_panel/prefs.py` — khoá mới

| Khoá | Mặc định | Ghi chú |
|---|---|---|
| `autostart` | `False` | |
| `start_hidden` | `False` | áp dụng cho mọi cách mở, không riêng autostart |
| `toast_enabled` | `True` | |
| `hotkey` | `"ctrl+shift+x"` | nguồn sự thật duy nhất |

`hotkey_label` **không còn là dữ liệu lưu trữ** — `load_prefs()` luôn tính lại bằng
`hotkey.format_label(hotkey)` để nhãn không bao giờ lệch với phím thật. Giá trị
`hotkey_label` trong file cũ bị bỏ qua khi đọc.

Tương thích ngược, phải làm đúng để không vỡ test hiện có:
- `load_prefs()` **vẫn trả khoá `hotkey_label`** (nay là giá trị dẫn xuất), nên
  `test_prefs_defaults` và `get_initial_state()` không đổi hành vi.
- `save_prefs(..., hotkey_label=...)` **giữ nguyên chữ ký** nhưng tham số này bị **bỏ qua**
  (nhận cho tương thích, không ghi xuống file). Thêm test khẳng định việc bỏ qua này là cố ý.
- Nếu `hotkey` đã lưu không hợp lệ (file sửa tay/dữ liệu hỏng), quay về `DEFAULT` thay vì tin
  nó — cùng tinh thần với `getHotkey()` của extension.

### 5. `wfx_panel/panel_api.py`

Thêm:
- `set_result_sink(fn)` — như `set_log_sink`.
- `get_status() -> dict` → `{chrome_alive, session_active, last_login_at}`.
- `refresh_status() -> dict` — chạy `status.chrome_alive()` ngay khi người dùng bấm.
- `set_hotkey(spec) -> dict` — validate **lại ở Python** (không tin client), lưu, gọi
  `hotkey_applier` do `panel_app` đăng ký; thất bại → rollback phím cũ.
- `set_autostart(enabled) -> dict`, `set_start_hidden(enabled) -> dict`,
  `set_toast_enabled(enabled) -> dict`.
- `get_initial_state()` trả thêm: `autostart`, `start_hidden`, `toast_enabled`, `hotkey`,
  `hotkey_label`, `chrome_alive`, `session_active`, `last_login_at`.

**Suy ra trạng thái phiên từ mã kết quả** (mã nào không nằm trong hai tập thì giữ nguyên
trạng thái cũ, không đoán bừa):

```python
SESSION_OK = {"LOGGED_IN", "SESSION_REUSED", "SESSION_ACTIVE", "MODULE_OPENED",
              "CATEGORY_SELECTED", "MASTER_OPENED", "CATALOG_PREPARED",
              "RESULT_OPENED", "MULTIPLE_RESULTS", "NO_RESULTS", "CODE_OPENED"}
SESSION_LOST = {"NOT_LOGGED_IN", "CHROME_CLOSED", "MISSING_CREDENTIALS",
                "LOGIN_FAILED", "LOGIN_TIMEOUT", "SESSION_CHECK_FAILED"}
```

`last_login_at` chỉ đặt khi mã ∈ `{LOGGED_IN, SESSION_REUSED, SESSION_ACTIVE}`, lưu dạng
`HH:MM:SS`.

### 6. `wfx_panel/panel_app.py`

- `STATUS_POLL_SECONDS = 5`, `TOAST_MIN_SECONDS = 3.0`
- `_status_loop()` — thread daemon, mỗi 5s gọi `status.chrome_alive()` rồi đẩy
  `window.wfxSetChromeStatus(<bool>)`. Chỉ đẩy khi giá trị **đổi** so với lần trước, tránh
  gọi `evaluate_js` 12 lần/phút vô ích.
- `_on_result(method, result, elapsed)` — đẩy `window.wfxSetSessionStatus(active, lastLoginAt)`;
  nếu `not self._visible` **và** `toast_enabled` **và** `elapsed >= TOAST_MIN_SECONDS` thì
  `self.tray.notify(message, "WFX Smart")`.
- `_register_hotkey(spec) -> str | None` — gỡ phím cũ, đăng ký phím mới; lỗi thì đăng ký lại
  phím cũ và trả thông điệp lỗi.
- `create_window(..., hidden=start_hidden)`; `self._visible = not start_hidden`.
- `quit()` dọn thêm luồng status.

### 7. UI

**Footer** — thêm cụm sức khoẻ bên cạnh trạng thái hiện có:
`.footer-health` chứa `.health-chrome` (chấm + "Chrome"), `.health-session` (chấm + "WFX"),
`.health-login` (giờ login), và nút `.health-refresh`. Chấm đổi màu qua
`data-state="ok|bad|unknown"`.

**Settings** — bật lại nút `.hotkey-button` (đang `disabled`) và thêm 3 hàng công tắc:
`.autostart-input`, `.start-hidden-input`, `.toast-input`.

**Bắt phím** — listener `keydown` gắn **trực tiếp vào `.hotkey-button`**, không gắn vào
`document`. Đây là bài học từ chính extension: bản 1.3.x gắn vào `document` khiến cờ capture
kẹt và **mọi ô nhập trên trang không xoá được chữ** (CLAUDE.md ghi lại sự cố này). Nút mất
focus (`blur`) → thoát chế độ bắt phím ngay.

**Global JS mới** (Python gọi qua `evaluate_js`): `window.wfxSetChromeStatus(alive)`,
`window.wfxSetSessionStatus(active, lastLoginAt)`.

### 8. Chuyển Chrome extension

`git mv chrome-extension legacy/chrome-extension`.

Thư mục này **đang có 12 file sửa chưa commit** từ trước. `git mv` mang theo nội dung đã sửa
sang đường dẫn mới, không mất dữ liệu. `legacy/chrome-extension/build-extension.ps1` sẽ trỏ
sai đường dẫn sau khi chuyển — **chấp nhận**, vì mục đích chỉ còn là lưu trữ. Thêm
`legacy/README.md` một đoạn nói rõ thư mục này đóng băng, nguồn thay thế là `wfx_panel/`.

## Xử lý lỗi

- Hotkey mới đăng ký thất bại → rollback phím cũ, footer báo lỗi, prefs **không** đổi.
- Ghi registry thất bại (chính sách nhóm chặn) → trả `ok: False` kèm thông điệp, công tắc UI
  bật lại đúng trạng thái thật (`is_enabled()`), không để UI nói dối.
- `tray.notify` lỗi hoặc tray chưa sẵn sàng → nuốt lỗi, chỉ ghi log; toast không bao giờ được
  làm hỏng luồng automation.
- Luồng status chết → không làm sập app; chấm chuyển `unknown`.

## Kiểm thử

| Module | Cách test |
|---|---|
| `hotkey.py` | Hàm thuần: chuẩn hoá, thứ tự modifier, từ chối Backspace/Enter/…, từ chối phím trần, chấp nhận F2–F12, `from_event`, `format_label` |
| `autostart.py` | Khoá registry nháp `Software\WFX-Panel-Test`: enable → `is_enabled()` True → disable → False; `launch_command()` khác nhau giữa frozen/dev |
| `status.py` | `http.server` cục bộ trả JSON CDP giả; env trỏ vào nó. Có case server trả rác và case cổng chết |
| `panel_api.py` | Fake login: result sink nhận đúng `(method, result, elapsed)`; `SESSION_OK`/`SESSION_LOST` đổi trạng thái đúng; mã lạ giữ nguyên; `set_hotkey` từ chối phím không hợp lệ và rollback |
| `ui/` | Assert hook DOM mới + global JS mới tồn tại |

Toast, autostart thật, và hotkey toàn cục vẫn phải **người dùng nghiệm thu tay** — không tự
động hoá được.

## Ngoài phạm vi (YAGNI)

- Toast bấm được để mở panel (giới hạn của `pystray`; muốn thì phải thêm `winotify`).
- Đồng bộ prefs nhiều máy; auto-update; đa ngôn ngữ.
- Poll phiên WFX định kỳ bằng Playwright (đã bác bỏ vì tốn 1–2s mỗi nhịp).
- Sửa `legacy/chrome-extension/build-extension.ps1` cho khớp đường dẫn mới.

## Tiêu chí nghiệm thu

1. Settings có 3 công tắc mới; tắt/bật rồi mở lại app vẫn giữ đúng trạng thái.
2. Bật "Khởi động cùng Windows" → có value `WFXPanel` trong `HKCU\...\Run`; tắt → mất.
3. Bật "Mở ẩn trong tray" → mở app không thấy cửa sổ, chỉ có tray icon; hotkey gọi ra được.
4. Đổi hotkey trong Settings → phím mới có tác dụng ngay, không cần khởi động lại; phím cũ
   hết tác dụng; đặt Backspace bị từ chối kèm thông báo.
5. Footer hiện chấm Chrome đổi theo việc Chrome automation còn mở hay không (trong 5s), chấm
   WFX và giờ login cập nhật sau mỗi thao tác.
6. Panel đang ẩn + job Catalog chạy > 3s → hiện bong bóng tray; tắt công tắc toast thì không.
7. `chrome-extension/` không còn ở gốc; `legacy/chrome-extension/` có đủ file.
8. Toàn bộ test tự động xanh; `login.py` và `app.py` vẫn không bị sửa.
