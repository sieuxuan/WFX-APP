# WFX Panel Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm 4 tính năng vào WFX Panel — khởi động cùng Windows (2 công tắc), đổi hotkey được, trạng thái Chrome/WFX ở footer, toast khi job dài xong lúc panel ẩn (có công tắc) — và chuyển Chrome extension sang `legacy/`.

**Architecture:** Ba module thuần mới (`hotkey.py`, `autostart.py`, `status.py`) dễ test độc lập; `prefs.py`/`panel_api.py` mở rộng để lưu và điều phối; `panel_app.py` nối vào vòng đời GUI. Cơ chế trung tâm là **result sink**: `PanelAPI` gọi callback sau MỌI thao tác automation, phục vụ đồng thời việc cập nhật trạng thái phiên và quyết định bắn toast.

**Tech Stack:** Python 3, pywebview, pystray, keyboard, winreg (stdlib), urllib (stdlib), pytest.

## Global Constraints

- KHÔNG sửa `login.py`, `app.py`, `wfx-tampermonkey.user.js`.
- Mọi chuỗi UI/log bằng tiếng Việt, file UTF-8, giữ đúng dấu.
- Nền tảng đích Windows; `python` là trình thông dịch; Bash tool là Git Bash.
- Chỉ ghi `HKEY_CURRENT_USER`, không cần quyền Administrator.
- Không ghi password/cookie/SessionID/LoginID/IP ra log.
- Hằng số cố định: `STATUS_POLL_SECONDS = 5`, `TOAST_MIN_SECONDS = 3.0`, `RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"`, `VALUE_NAME = "WFXPanel"`, `hotkey.DEFAULT = "ctrl+shift+x"`.
- Mặc định pref mới: `autostart=False`, `start_hidden=False`, `toast_enabled=True`, `hotkey="ctrl+shift+x"`.
- Test hiện có phải giữ xanh (43 test). Chạy full suite trước mỗi commit.
- Không commit `dist/`, `build/`.

---

## File Structure

- Create `wfx_panel/hotkey.py` — parse/validate/chuẩn hoá tổ hợp phím (hàm thuần).
- Create `wfx_panel/autostart.py` — bật/tắt Run key trong registry.
- Create `wfx_panel/status.py` — kiểm tra Chrome CDP còn sống.
- Modify `wfx_panel/prefs.py` — 4 khoá pref mới; `hotkey_label` chuyển thành giá trị dẫn xuất.
- Modify `wfx_panel/panel_api.py` — result sink, status, các setter thiết lập.
- Modify `wfx_panel/ui/index.html`, `style.css`, `panel.js` — footer health, bắt phím, 3 công tắc.
- Modify `wfx_panel/panel_app.py` — luồng poll status, toast, mở ẩn, đăng ký lại hotkey.
- Move `chrome-extension/` → `legacy/chrome-extension/`; create `legacy/README.md`.
- Tests: `tests/test_hotkey.py`, `tests/test_autostart.py`, `tests/test_status.py`, mở rộng `tests/test_prefs.py`, `tests/test_panel_api.py`, `tests/test_ui_assets.py`, `tests/test_panel_js.py`.

---

## Task 1: `wfx_panel/hotkey.py`

**Files:**
- Create: `wfx_panel/hotkey.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hotkey.DEFAULT: str = "ctrl+shift+x"`
  - `hotkey.MODIFIERS: tuple = ("ctrl", "alt", "shift", "windows")`
  - `hotkey.UNSAFE_KEYS: frozenset`
  - `hotkey.normalize(spec: str) -> str` (ném `ValueError` nếu không hợp lệ)
  - `hotkey.is_valid(spec: str) -> bool`
  - `hotkey.format_label(spec: str) -> str`
  - `hotkey.from_event(event: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hotkey.py`:

```python
import pytest

from wfx_panel import hotkey


def test_default_is_valid_and_normalized():
    assert hotkey.is_valid(hotkey.DEFAULT)
    assert hotkey.normalize(hotkey.DEFAULT) == "ctrl+shift+x"


def test_normalize_orders_modifiers_and_lowercases():
    assert hotkey.normalize("Shift + CTRL + X") == "ctrl+shift+x"
    assert hotkey.normalize("alt+ctrl+F5") == "ctrl+alt+f5"


def test_normalize_accepts_modifier_aliases():
    assert hotkey.normalize("control+shift+k") == "ctrl+shift+k"
    assert hotkey.normalize("win+shift+k") == "shift+windows+k"


@pytest.mark.parametrize("unsafe", ["ctrl+backspace", "alt+delete", "ctrl+shift+enter",
                                    "ctrl+tab", "ctrl+space", "alt+escape"])
def test_rejects_unsafe_base_keys(unsafe):
    # Hotkey toàn cục nuốt Backspace/Enter sẽ chặn thao tác gõ trên TOÀN MÁY.
    assert hotkey.is_valid(unsafe) is False
    with pytest.raises(ValueError):
        hotkey.normalize(unsafe)


def test_rejects_bare_key_without_modifier():
    assert hotkey.is_valid("x") is False


def test_allows_function_keys_without_modifier():
    assert hotkey.normalize("F5") == "f5"
    assert hotkey.is_valid("f12") is True


def test_rejects_f1_and_modifier_only():
    assert hotkey.is_valid("f1") is False       # F1 là phím Trợ giúp của Windows
    assert hotkey.is_valid("ctrl+shift") is False


def test_rejects_two_base_keys():
    assert hotkey.is_valid("ctrl+x+y") is False


def test_format_label():
    assert hotkey.format_label("ctrl+shift+x") == "Ctrl + Shift + X"
    assert hotkey.format_label("shift+windows+k") == "Shift + Win + K"
    assert hotkey.format_label("f9") == "F9"


def test_from_event_builds_spec():
    assert hotkey.from_event(
        {"ctrl": True, "alt": False, "shift": True, "meta": False, "key": "X", "code": "KeyX"}
    ) == "ctrl+shift+x"
    assert hotkey.from_event(
        {"ctrl": True, "alt": True, "shift": False, "meta": False, "key": "5", "code": "Digit5"}
    ) == "ctrl+alt+5"
    assert hotkey.from_event(
        {"ctrl": False, "alt": False, "shift": False, "meta": False, "key": "F7", "code": "F7"}
    ) == "f7"


def test_from_event_rejects_unsafe():
    with pytest.raises(ValueError):
        hotkey.from_event(
            {"ctrl": True, "alt": False, "shift": False, "meta": False,
             "key": "Backspace", "code": "Backspace"}
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wfx_panel.hotkey'`.

- [ ] **Step 3: Implement `wfx_panel/hotkey.py`**

```python
"""Phân tích và kiểm tra tổ hợp phím cho hotkey toàn cục.

Toàn bộ là hàm thuần để test được mà không cần bàn phím thật hay GUI.

Luật an toàn khắt khe hơn bản extension: extension chỉ bắt phím trong trang
WFX, còn app này đăng ký hotkey ở cấp hệ điều hành — một tổ hợp nuốt Backspace
sẽ chặn thao tác xoá chữ trên TOÀN MÁY, không riêng app.
"""

from __future__ import annotations

DEFAULT = "ctrl+shift+x"
MODIFIERS = ("ctrl", "alt", "shift", "windows")
UNSAFE_KEYS = frozenset(
    {"backspace", "delete", "enter", "return", "tab", "space", "escape", "esc"}
)

_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "win": "windows", "windows": "windows", "meta": "windows",
    "cmd": "windows", "super": "windows",
}
_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Win"}


def _is_function_key(key: str) -> bool:
    # F1 bị loại: Windows dành riêng cho Trợ giúp.
    return (
        len(key) >= 2
        and key[0] == "f"
        and key[1:].isdigit()
        and 2 <= int(key[1:]) <= 12
    )


def normalize(spec: str) -> str:
    parts = [part.strip().lower() for part in str(spec).split("+") if part.strip()]
    if not parts:
        raise ValueError("Chưa nhận được tổ hợp phím.")

    modifiers: list[str] = []
    keys: list[str] = []
    for part in parts:
        alias = _MODIFIER_ALIASES.get(part)
        if alias is not None:
            if alias not in modifiers:
                modifiers.append(alias)
        else:
            keys.append(part)

    if len(keys) != 1:
        raise ValueError(
            "Tổ hợp phải có đúng một phím chính ngoài Ctrl/Alt/Shift/Win."
        )
    key = keys[0]
    if key in UNSAFE_KEYS:
        raise ValueError(
            f"Không dùng {key.upper()} làm hotkey được: phím này sẽ bị chặn "
            "trên toàn máy, khiến bạn không gõ hoặc xoá chữ được ở mọi ứng dụng."
        )
    if not modifiers and not _is_function_key(key):
        raise ValueError(
            "Tổ hợp phải có ít nhất một phím bổ trợ (Ctrl/Alt/Shift/Win), "
            "hoặc dùng một phím F2–F12."
        )

    ordered = [modifier for modifier in MODIFIERS if modifier in modifiers]
    return "+".join(ordered + [key])


def is_valid(spec: str) -> bool:
    try:
        normalize(spec)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def format_label(spec: str) -> str:
    parts = normalize(spec).split("+")
    labels = [
        _LABELS.get(part, part.upper() if len(part) <= 3 else part.capitalize())
        for part in parts
    ]
    return " + ".join(labels)


def from_event(event: dict) -> str:
    """Dựng spec từ payload keydown của trình duyệt.

    Ưu tiên `code` (vị trí phím vật lý) hơn `key` vì `key` đổi theo layout bàn
    phím và theo Shift — `KeyX` luôn là phím X, còn `key` có thể là "X" hoặc ký
    tự khác tuỳ layout.
    """
    parts = []
    if event.get("ctrl"):
        parts.append("ctrl")
    if event.get("alt"):
        parts.append("alt")
    if event.get("shift"):
        parts.append("shift")
    if event.get("meta"):
        parts.append("windows")

    code = str(event.get("code") or "")
    key = str(event.get("key") or "")
    if code.startswith("Key") and len(code) == 4:
        base = code[3].lower()
    elif code.startswith("Digit") and len(code) == 6:
        base = code[5]
    elif code.startswith("Numpad") and len(code) > 6:
        base = code[6:].lower()
    elif len(code) >= 2 and code[0] == "F" and code[1:].isdigit():
        base = code.lower()
    else:
        base = key.lower()

    parts.append(base)
    return normalize("+".join(parts))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hotkey.py -v`
Expected: PASS (14 passed — 6 trong số đó từ parametrize).

- [ ] **Step 5: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/hotkey.py tests/test_hotkey.py
git commit -m "feat(panel): hotkey spec parsing and safety validation"
```

---

## Task 2: `wfx_panel/autostart.py`

**Files:**
- Create: `wfx_panel/autostart.py`
- Test: `tests/test_autostart.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `autostart.RUN_KEY: str`, `autostart.VALUE_NAME: str = "WFXPanel"`
  - `autostart.launch_command() -> str`
  - `autostart.is_enabled(*, key_path=RUN_KEY, value_name=VALUE_NAME) -> bool`
  - `autostart.enable(command=None, *, key_path=RUN_KEY, value_name=VALUE_NAME) -> None`
  - `autostart.disable(*, key_path=RUN_KEY, value_name=VALUE_NAME) -> None`
  - `autostart.sync(enabled: bool, *, key_path=RUN_KEY, value_name=VALUE_NAME) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_autostart.py`:

```python
import os
import sys

import pytest

from wfx_panel import autostart

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Registry chỉ có trên Windows")

TEST_KEY = r"Software\WFX-Panel-Test\Run"


@pytest.fixture
def scratch_key():
    """Khoá nháp riêng — tuyệt đối không đụng Run key thật của người dùng."""
    yield TEST_KEY
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\WFX-Panel-Test")
    except OSError:
        pass


def test_disabled_when_value_absent(scratch_key):
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_enable_then_disable_round_trip(scratch_key):
    autostart.enable("\"C:\\fake\\WFX-Panel.exe\"", key_path=scratch_key, value_name="Probe")
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is True
    autostart.disable(key_path=scratch_key, value_name="Probe")
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_sync_returns_actual_state(scratch_key):
    assert autostart.sync(True, key_path=scratch_key, value_name="Probe") is True
    assert autostart.sync(False, key_path=scratch_key, value_name="Probe") is False


def test_disable_is_idempotent(scratch_key):
    autostart.disable(key_path=scratch_key, value_name="Probe")
    autostart.disable(key_path=scratch_key, value_name="Probe")
    assert autostart.is_enabled(key_path=scratch_key, value_name="Probe") is False


def test_launch_command_quotes_and_targets_module_in_dev():
    command = autostart.launch_command()
    assert command.startswith('"')
    assert "-m wfx_panel.panel_app" in command


def test_launch_command_uses_executable_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\app\WFX-Panel.exe")
    assert autostart.launch_command() == r'"C:\app\WFX-Panel.exe"'


def test_real_run_key_constant_is_hkcu_scoped():
    # Không được trỏ vào HKLM: sẽ cần quyền Administrator.
    assert autostart.RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert autostart.VALUE_NAME == "WFXPanel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wfx_panel.autostart'`.

- [ ] **Step 3: Implement `wfx_panel/autostart.py`**

```python
"""Bật/tắt khởi động cùng Windows qua Run key của HKEY_CURRENT_USER.

Dùng registry thay vì shortcut trong thư mục Startup: ghi/xoá được hoàn toàn
bằng thư viện chuẩn (`winreg`), không cần tạo file .lnk qua COM.

Chỉ đụng HKEY_CURRENT_USER — không cần quyền Administrator và không ảnh hưởng
tài khoản Windows khác trên cùng máy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WFXPanel"

_IS_WINDOWS = os.name == "nt"
if _IS_WINDOWS:
    import winreg


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # pythonw.exe chạy không kèm cửa sổ console đen.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m wfx_panel.panel_app'


def is_enabled(*, key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
        return bool(str(value).strip())
    except OSError:
        return False


def enable(
    command: str | None = None,
    *,
    key_path: str = RUN_KEY,
    value_name: str = VALUE_NAME,
) -> None:
    if not _IS_WINDOWS:
        return
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(
            key, value_name, 0, winreg.REG_SZ, command or launch_command()
        )


def disable(*, key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> None:
    if not _IS_WINDOWS:
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except OSError:
        # Không tồn tại sẵn, hoặc bị chính sách nhóm chặn. Không ném lỗi ở đây;
        # sync() đọc lại trạng thái thật nên caller vẫn biết được là chưa tắt.
        pass


def sync(
    enabled: bool,
    *,
    key_path: str = RUN_KEY,
    value_name: str = VALUE_NAME,
) -> bool:
    """Đặt trạng thái rồi ĐỌC LẠI. Trả về trạng thái thật, không phải mong muốn."""
    try:
        if enabled:
            enable(key_path=key_path, value_name=value_name)
        else:
            disable(key_path=key_path, value_name=value_name)
    except OSError:
        pass
    return is_enabled(key_path=key_path, value_name=value_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Verify the real Run key was not touched**

Run:
```bash
python -c "from wfx_panel import autostart; print('real key enabled:', autostart.is_enabled())"
```
Expected: `real key enabled: False` (test chỉ dùng khoá nháp).

- [ ] **Step 6: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/autostart.py tests/test_autostart.py
git commit -m "feat(panel): Windows autostart via HKCU Run key"
```

---

## Task 3: `wfx_panel/status.py`

**Files:**
- Create: `wfx_panel/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `status.cdp_url() -> str`
  - `status.chrome_alive(timeout: float = 1.0) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_status.py`:

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wfx_panel import status


def _serve(payload: bytes, status_code: int = 200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass  # giữ output test sạch

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture
def cdp_env(monkeypatch):
    def _apply(server):
        host, port = server.server_address
        monkeypatch.setenv("WFX_CDP_HOST", host)
        monkeypatch.setenv("WFX_CDP_PORT", str(port))
    return _apply


def test_cdp_url_defaults(monkeypatch):
    monkeypatch.delenv("WFX_CDP_HOST", raising=False)
    monkeypatch.delenv("WFX_CDP_PORT", raising=False)
    assert status.cdp_url() == "http://127.0.0.1:9222"


def test_cdp_url_honours_env(monkeypatch):
    monkeypatch.setenv("WFX_CDP_HOST", "10.0.0.5")
    monkeypatch.setenv("WFX_CDP_PORT", "9333")
    assert status.cdp_url() == "http://10.0.0.5:9333"


def test_alive_when_cdp_reports_websocket(cdp_env):
    server = _serve(json.dumps({"webSocketDebuggerUrl": "ws://x"}).encode())
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is True
    finally:
        server.shutdown()


def test_not_alive_when_payload_lacks_websocket(cdp_env):
    server = _serve(json.dumps({"Browser": "Chrome/1"}).encode())
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is False
    finally:
        server.shutdown()


def test_not_alive_when_payload_is_garbage(cdp_env):
    server = _serve(b"<html>not json</html>")
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is False
    finally:
        server.shutdown()


def test_not_alive_when_port_is_closed(monkeypatch):
    monkeypatch.setenv("WFX_CDP_HOST", "127.0.0.1")
    monkeypatch.setenv("WFX_CDP_PORT", "9")  # cổng discard, không ai nghe
    assert status.chrome_alive(timeout=1) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wfx_panel.status'`.

- [ ] **Step 3: Implement `wfx_panel/status.py`**

```python
"""Kiểm tra nhanh Chrome automation (CDP) còn sống hay không.

Cố tình KHÔNG gọi Playwright: `login.check_session()` phải bật rồi tắt cả
Playwright nên mất 1–2 giây mỗi lần, không thể poll mỗi 5 giây. Ở đây chỉ là
một HTTP GET tới endpoint CDP, tính bằng mili giây.

Đọc cùng biến môi trường với `login.py` (WFX_CDP_HOST/WFX_CDP_PORT) để hai bên
không bao giờ trỏ về hai nơi khác nhau.
"""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import urlopen


def cdp_url() -> str:
    host = os.getenv("WFX_CDP_HOST", "127.0.0.1")
    port = os.getenv("WFX_CDP_PORT", "9222")
    return f"http://{host}:{port}"


def chrome_alive(timeout: float = 1.0) -> bool:
    try:
        with urlopen(f"{cdp_url()}/json/version", timeout=timeout) as response:
            info = json.load(response)
        return bool(info.get("webSocketDebuggerUrl"))
    except (OSError, URLError, ValueError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_status.py -v`
Expected: PASS (6 passed, output sạch không có log HTTP).

- [ ] **Step 5: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/status.py tests/test_status.py
git commit -m "feat(panel): cheap Chrome CDP liveness probe"
```

---

## Task 4: Mở rộng `wfx_panel/prefs.py`

**Files:**
- Modify: `wfx_panel/prefs.py` (hàm `load_prefs` dòng 87-100, `save_prefs` dòng 103-122)
- Test: `tests/test_prefs.py` (bổ sung)

**Interfaces:**
- Consumes: `wfx_panel.hotkey` (`DEFAULT`, `is_valid`, `format_label`) từ Task 1.
- Produces:
  - `load_prefs(base_dir=None) -> dict` nay trả thêm `hotkey`, `autostart`, `start_hidden`, `toast_enabled` (vẫn giữ `theme`, `close_after_module`, `hotkey_label`).
  - `save_prefs(base_dir=None, *, theme=None, close_after_module=None, hotkey_label=None, hotkey=None, autostart=None, start_hidden=None, toast_enabled=None) -> dict`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_prefs.py`:

```python
def test_new_pref_defaults(tmp_path):
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["hotkey"] == "ctrl+shift+x"
    assert loaded["hotkey_label"] == "Ctrl + Shift + X"
    assert loaded["autostart"] is False
    assert loaded["start_hidden"] is False
    assert loaded["toast_enabled"] is True


def test_hotkey_round_trip_and_label_is_derived(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, hotkey="alt+shift+k")
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["hotkey"] == "alt+shift+k"
    assert loaded["hotkey_label"] == "Alt + Shift + K"


def test_hotkey_label_is_never_persisted(tmp_path):
    """Nhãn là giá trị dẫn xuất; lưu nó xuống file sẽ tạo nguy cơ lệch với phím thật."""
    import json
    prefs.save_prefs(base_dir=tmp_path, hotkey="ctrl+alt+j", hotkey_label="Nhãn Bịa Đặt")
    raw = json.loads((tmp_path / "prefs.json").read_text(encoding="utf-8"))
    assert "hotkey_label" not in raw
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey_label"] == "Ctrl + Alt + J"


def test_corrupt_hotkey_falls_back_to_default(tmp_path):
    (tmp_path / "prefs.json").write_text(
        '{"hotkey": "ctrl+backspace"}', encoding="utf-8"
    )
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_new_prefs_partial_update_preserves_others(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, autostart=True)
    prefs.save_prefs(base_dir=tmp_path, toast_enabled=False)
    prefs.save_prefs(base_dir=tmp_path, start_hidden=True)
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["autostart"] is True
    assert loaded["toast_enabled"] is False
    assert loaded["start_hidden"] is True
    assert loaded["theme"] == "light"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_prefs.py -v`
Expected: FAIL — `KeyError: 'hotkey'`.

- [ ] **Step 3: Update `wfx_panel/prefs.py`**

Add near the top imports:

```python
from wfx_panel import hotkey as hotkey_spec
```

Replace `load_prefs`'s return block (currently lines 96-100) with:

```python
    stored_hotkey = str(data.get("hotkey") or hotkey_spec.DEFAULT)
    # Dữ liệu hỏng hoặc sửa tay có thể chứa tổ hợp nguy hiểm (vd ctrl+backspace)
    # — không tin, quay về mặc định thay vì đăng ký nó ở cấp hệ điều hành.
    if not hotkey_spec.is_valid(stored_hotkey):
        stored_hotkey = hotkey_spec.DEFAULT
    return {
        "theme": "dark" if data.get("theme") == "dark" else "light",
        "close_after_module": data.get("close_after_module", True) is not False,
        "hotkey": stored_hotkey,
        # Dẫn xuất, KHÔNG lưu xuống file (xem save_prefs) để nhãn không lệch phím.
        "hotkey_label": hotkey_spec.format_label(stored_hotkey),
        "autostart": data.get("autostart", False) is True,
        "start_hidden": data.get("start_hidden", False) is True,
        "toast_enabled": data.get("toast_enabled", True) is not False,
    }
```

Replace `save_prefs` entirely with:

```python
def save_prefs(
    base_dir: Path | None = None,
    *,
    theme: str | None = None,
    close_after_module: bool | None = None,
    hotkey_label: str | None = None,
    hotkey: str | None = None,
    autostart: bool | None = None,
    start_hidden: bool | None = None,
    toast_enabled: bool | None = None,
) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = "dark" if theme == "dark" else "light"
    if close_after_module is not None:
        current["close_after_module"] = bool(close_after_module)
    if hotkey is not None:
        current["hotkey"] = hotkey_spec.normalize(hotkey)
        current["hotkey_label"] = hotkey_spec.format_label(current["hotkey"])
    if autostart is not None:
        current["autostart"] = bool(autostart)
    if start_hidden is not None:
        current["start_hidden"] = bool(start_hidden)
    if toast_enabled is not None:
        current["toast_enabled"] = bool(toast_enabled)
    # hotkey_label nhận vào cho tương thích ngược nhưng CỐ Ý bỏ qua: nó là giá
    # trị dẫn xuất từ `hotkey`, lưu riêng sẽ có ngày lệch nhau.
    _ = hotkey_label

    payload = {key: value for key, value in current.items() if key != "hotkey_label"}
    path = _prefs_path(base_dir)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current
```

Also delete the now-unused constant `DEFAULT_HOTKEY_LABEL` (line 17).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_prefs.py -v`
Expected: PASS — tất cả test cũ lẫn mới. Nếu `test_prefs_defaults` cũ còn assert dict bằng `==` với đúng 3 khoá, hãy sửa nó thành so sánh từng khoá (dict nay có nhiều khoá hơn); ghi rõ việc sửa này trong report.

- [ ] **Step 5: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/prefs.py tests/test_prefs.py
git commit -m "feat(panel): persist hotkey, autostart, start-hidden and toast prefs"
```

---

## Task 5: Mở rộng `wfx_panel/panel_api.py`

**Files:**
- Modify: `wfx_panel/panel_api.py`
- Test: `tests/test_panel_api.py` (bổ sung)

**Interfaces:**
- Consumes: `wfx_panel.hotkey`, `wfx_panel.autostart`, `wfx_panel.status`, `wfx_panel.prefs` (Tasks 1-4).
- Produces (thêm vào `PanelAPI`):
  - `set_result_sink(sink: Callable[[str, dict, float], None]) -> None`
  - `set_hotkey_applier(applier: Callable[[str], str | None]) -> None` — applier trả `None` khi thành công, hoặc chuỗi lỗi.
  - `get_status() -> dict` → `{"chrome_alive": bool, "session_active": bool | None, "last_login_at": str | None}`
  - `refresh_status() -> dict` (giống `get_status`)
  - `set_hotkey(spec: str) -> dict`
  - `set_autostart(enabled: bool) -> dict`
  - `set_start_hidden(enabled: bool) -> dict`
  - `set_toast_enabled(enabled: bool) -> dict`
  - `get_initial_state()` trả thêm `hotkey`, `autostart`, `start_hidden`, `toast_enabled`, `chrome_alive`, `session_active`, `last_login_at`
  - Module constants `SESSION_OK: frozenset`, `SESSION_LOST: frozenset`, `LOGIN_CODES: frozenset`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panel_api.py`:

```python
def test_result_sink_receives_method_result_and_elapsed(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, _ = make_api(tmp_path)
    seen = []
    api.set_result_sink(lambda method, result, elapsed: seen.append((method, result, elapsed)))
    api.find_code("Apparel", "ABC123")
    assert len(seen) == 1
    method, result, elapsed = seen[0]
    assert method == "find_code"
    assert result["code"] == "RESULT_OPENED"
    assert isinstance(elapsed, float) and elapsed >= 0


def test_session_state_tracks_result_codes(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, _ = make_api(tmp_path)
    assert api.get_status()["session_active"] is None

    api.login()  # FakeLogin.run -> LOGGED_IN
    status_after_login = api.get_status()
    assert status_after_login["session_active"] is True
    assert status_after_login["last_login_at"] is not None

    api.check_session()  # FakeLogin -> NOT_LOGGED_IN
    assert api.get_status()["session_active"] is False


def test_unknown_result_code_leaves_session_state_untouched(tmp_path):
    api, _ = make_api(tmp_path)
    api._session_active = True
    api._observe("whatever", {"ok": False, "code": "SOMETHING_NEW"}, 0.1)
    assert api.get_status()["session_active"] is True


def test_set_hotkey_rejects_unsafe_combo(tmp_path):
    api, _ = make_api(tmp_path)
    result = api.set_hotkey("ctrl+backspace")
    assert result["ok"] is False
    assert result["code"] == "HOTKEY_INVALID"
    # Không được ghi đè pref khi tổ hợp không hợp lệ.
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_set_hotkey_applies_and_persists(tmp_path):
    api, _ = make_api(tmp_path)
    applied = []
    api.set_hotkey_applier(lambda spec: applied.append(spec) or None)
    result = api.set_hotkey("Alt+Shift+K")
    assert result["ok"] is True
    assert result["hotkey"] == "alt+shift+k"
    assert applied == ["alt+shift+k"]
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "alt+shift+k"


def test_set_hotkey_rolls_back_when_registration_fails(tmp_path):
    api, _ = make_api(tmp_path)
    attempts = []

    def applier(spec):
        attempts.append(spec)
        return "Phím đang bị ứng dụng khác chiếm." if spec == "alt+shift+k" else None

    api.set_hotkey_applier(applier)
    result = api.set_hotkey("alt+shift+k")
    assert result["ok"] is False
    assert result["code"] == "HOTKEY_REGISTER_FAILED"
    # Đã đăng ký lại phím cũ, và pref không đổi.
    assert attempts == ["alt+shift+k", "ctrl+shift+x"]
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_toggle_prefs_persist(tmp_path):
    api, _ = make_api(tmp_path)
    assert api.set_start_hidden(True)["start_hidden"] is True
    assert api.set_toast_enabled(False)["toast_enabled"] is False
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["start_hidden"] is True
    assert loaded["toast_enabled"] is False


def test_initial_state_exposes_new_fields(tmp_path):
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    for field in ("hotkey", "hotkey_label", "autostart", "start_hidden",
                  "toast_enabled", "chrome_alive", "session_active", "last_login_at"):
        assert field in state, field
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_panel_api.py -v`
Expected: FAIL — `AttributeError: 'PanelAPI' object has no attribute 'set_result_sink'`.

- [ ] **Step 3: Update `wfx_panel/panel_api.py`**

Add imports and module constants at the top:

```python
import time

from wfx_panel import autostart, constants, hotkey as hotkey_spec, log_bridge, status
from wfx_panel import prefs as prefs_default

# Mã kết quả của login.py cho biết phiên WFX còn sống hay đã mất. Mã KHÔNG nằm
# trong hai tập này (lỗi lạ, lỗi mạng...) cố ý không đổi trạng thái — thà hiển
# thị thông tin cũ còn hơn đoán sai rồi báo "mất phiên" khi phiên vẫn tốt.
SESSION_OK = frozenset({
    "LOGGED_IN", "SESSION_REUSED", "SESSION_ACTIVE", "MODULE_OPENED",
    "CATEGORY_SELECTED", "MASTER_OPENED", "CATALOG_PREPARED",
    "RESULT_OPENED", "MULTIPLE_RESULTS", "NO_RESULTS", "CODE_OPENED",
})
SESSION_LOST = frozenset({
    "NOT_LOGGED_IN", "CHROME_CLOSED", "MISSING_CREDENTIALS",
    "LOGIN_FAILED", "LOGIN_TIMEOUT", "SESSION_CHECK_FAILED",
})
LOGIN_CODES = frozenset({"LOGGED_IN", "SESSION_REUSED", "SESSION_ACTIVE"})
```

In `__init__`, add:

```python
        self._result_sink: Callable[[str, dict, float], None] | None = None
        self._hotkey_applier: Callable[[str], str | None] | None = None
        self._session_active: bool | None = None
        self._last_login_at: str | None = None
```

Add these methods:

```python
    def set_result_sink(self, sink: Callable[[str, dict, float], None]) -> None:
        self._result_sink = sink

    def set_hotkey_applier(self, applier: Callable[[str], str | None]) -> None:
        self._hotkey_applier = applier

    def _observe(self, method_name: str, result: dict, elapsed: float) -> None:
        code = str(result.get("code") or "")
        if code in SESSION_OK:
            self._session_active = True
            if code in LOGIN_CODES:
                self._last_login_at = time.strftime("%H:%M:%S")
        elif code in SESSION_LOST:
            self._session_active = False
        if self._result_sink is not None:
            try:
                self._result_sink(method_name, result, elapsed)
            except Exception:
                # Sink chỉ để hiển thị/thông báo; lỗi ở đó không được làm hỏng
                # kết quả automation mà người dùng đang chờ.
                pass

    def _run(self, method_name: str, action: Callable[[], dict]) -> dict:
        started = time.monotonic()
        try:
            result = action()
        except Exception as error:
            result = {
                "ok": False,
                "code": "PANEL_ERROR",
                "message": f"{type(error).__name__}: {error}",
            }
        if not isinstance(result, dict):
            result = {"ok": False, "code": "PANEL_ERROR", "message": "Kết quả không hợp lệ."}
        self._observe(method_name, result, time.monotonic() - started)
        return result

    def get_status(self) -> dict:
        return {
            "chrome_alive": status.chrome_alive(),
            "session_active": self._session_active,
            "last_login_at": self._last_login_at,
        }

    def refresh_status(self) -> dict:
        return self.get_status()

    def set_hotkey(self, spec: str) -> dict:
        try:
            normalized = hotkey_spec.normalize(spec)
        except (ValueError, TypeError, AttributeError) as error:
            return {"ok": False, "code": "HOTKEY_INVALID", "message": str(error)}

        previous = self._prefs.load_prefs(base_dir=self._base_dir)["hotkey"]
        if self._hotkey_applier is not None:
            failure = self._hotkey_applier(normalized)
            if failure:
                # Đăng ký phím mới hỏng -> khôi phục phím cũ để app không mất
                # hotkey hoàn toàn, và KHÔNG ghi pref.
                self._hotkey_applier(previous)
                return {
                    "ok": False,
                    "code": "HOTKEY_REGISTER_FAILED",
                    "message": failure,
                    "hotkey": previous,
                    "hotkey_label": hotkey_spec.format_label(previous),
                }

        saved = self._prefs.save_prefs(base_dir=self._base_dir, hotkey=normalized)
        self._log(f"[SETTINGS] Đã đổi hotkey sang {saved['hotkey_label']}")
        return {
            "ok": True,
            "code": "HOTKEY_SAVED",
            "message": f"Đã đổi hotkey sang {saved['hotkey_label']}.",
            "hotkey": saved["hotkey"],
            "hotkey_label": saved["hotkey_label"],
        }

    def set_autostart(self, enabled: bool) -> dict:
        wanted = bool(enabled)
        actual = autostart.sync(wanted)
        self._prefs.save_prefs(base_dir=self._base_dir, autostart=actual)
        if actual != wanted:
            return {
                "ok": False,
                "code": "AUTOSTART_FAILED",
                "message": "Không ghi được thiết lập khởi động cùng Windows.",
                "autostart": actual,
            }
        return {
            "ok": True,
            "code": "AUTOSTART_SAVED",
            "message": "Đã bật khởi động cùng Windows." if actual
                       else "Đã tắt khởi động cùng Windows.",
            "autostart": actual,
        }

    def set_start_hidden(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, start_hidden=bool(enabled))
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": "Lần mở tới sẽ ẩn trong tray." if saved["start_hidden"]
                       else "Lần mở tới sẽ hiện panel.",
            "start_hidden": saved["start_hidden"],
        }

    def set_toast_enabled(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, toast_enabled=bool(enabled))
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": "Đã bật thông báo." if saved["toast_enabled"]
                       else "Đã tắt thông báo.",
            "toast_enabled": saved["toast_enabled"],
        }
```

Rewrite the five automation methods to route through `_run` (this is what feeds the sink):

```python
    def login(self) -> dict:
        account = self._account()
        return self._run("login", lambda: self._login.run(
            account["user_id"], account["password"], self._login.COMPANY_ID, self._log))

    def check_session(self) -> dict:
        return self._run("check_session", lambda: self._login.check_session(self._log))

    def open_module(self, module_id: str) -> dict:
        module = constants.MODULE_BY_ID.get(module_id)
        if module is None:
            return {"ok": False, "code": "MODULE_UNKNOWN", "message": f"Module lạ: {module_id}"}
        return self._run("open_module", lambda: self._login.open_module(
            module["name"], module["xpath"], self._log))

    def prepare_catalog(self, category_name: str) -> dict:
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}"}

        def action() -> dict:
            opened = self._login.open_module("Catalog", self._login.CATALOG_XPATH, self._log)
            if not opened.get("ok"):
                return opened
            return self._login.set_catalog_category(category_name, value, self._log)

        return self._run("prepare_catalog", action)
```

And `_quick` (keep `find_code`/`find_buyer_reference` delegating to it, but pass the caller name):

```python
    def find_code(self, category_name: str, code: str, destination: str | None = None) -> dict:
        return self._quick("find_code", category_name, "code", code, destination)

    def find_buyer_reference(self, category_name: str, query: str,
                             destination: str | None = None) -> dict:
        return self._quick("find_buyer_reference", category_name, "buyer_reference",
                           query, destination)

    def _quick(self, method_name, category_name, filter_kind, query, destination):
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}"}
        account = self._account()
        return self._run(method_name, lambda: self._login.quick_find_catalog(
            category_name, value, filter_kind, query,
            account["user_id"], account["password"], self._login.COMPANY_ID,
            self._log, destination=destination))
```

Finally extend `get_initial_state` to merge in the new prefs plus `self.get_status()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_panel_api.py -v`
Expected: PASS. Existing credential-order tests must still pass — `_quick` keeps the same positional order into `quick_find_catalog`.

- [ ] **Step 5: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/panel_api.py tests/test_panel_api.py
git commit -m "feat(panel): result sink, session status and settings setters"
```

---

## Task 6: UI — footer health, bắt phím, 3 công tắc

**Files:**
- Modify: `wfx_panel/ui/index.html` (footer dòng 83-86; settings sheet dòng 96-97)
- Modify: `wfx_panel/ui/style.css` (thêm cuối file)
- Modify: `wfx_panel/ui/panel.js`
- Test: `tests/test_ui_assets.py`, `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `PanelAPI` methods from Task 5.
- Produces (Python gọi qua `evaluate_js` ở Task 7): `window.wfxSetChromeStatus(alive: boolean)`, `window.wfxSetSessionStatus(active: boolean|null, lastLoginAt: string|null)`.
- DOM hooks mới: `.footer-health`, `.health-chrome`, `.health-session`, `.health-login`, `.health-refresh`, `.autostart-input`, `.start-hidden-input`, `.toast-input`, và `.hotkey-button` KHÔNG còn `disabled`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ui_assets.py`:

```python
def test_footer_has_health_indicators():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in ['class="footer-health"', 'class="health-chrome"',
                 'class="health-session"', 'class="health-login"',
                 'class="health-refresh"']:
        assert hook in html, hook


def test_settings_has_new_toggles_and_enabled_hotkey_button():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in ['class="autostart-input"', 'class="start-hidden-input"',
                 'class="toast-input"']:
        assert hook in html, hook
    # Nút hotkey phải bỏ disabled thì mới bắt phím được.
    hotkey_tag = html[html.index('class="hotkey-button"'):]
    hotkey_tag = hotkey_tag[:hotkey_tag.index(">")]
    assert "disabled" not in hotkey_tag
```

Add to `tests/test_panel_js.py`:

```python
def test_exposes_status_globals():
    for name in ["wfxSetChromeStatus", "wfxSetSessionStatus"]:
        assert f"window.{name}" in JS


def test_wires_new_settings_controls():
    for call in ["set_autostart", "set_start_hidden", "set_toast_enabled",
                 "set_hotkey", "refresh_status"]:
        assert call in JS, call


def test_hotkey_capture_is_bound_to_the_button_not_document():
    """Bản 1.3.x của extension gắn listener bắt phím vào `document`, làm kẹt cờ
    capture khiến MỌI ô nhập trên trang không xoá được chữ. Phải gắn vào nút."""
    assert 'hotkeyButton.addEventListener("keydown"' in JS
    assert 'document.addEventListener("keydown"' not in JS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_assets.py tests/test_panel_js.py -v`
Expected: FAIL — `assert 'class="footer-health"' in html`.

- [ ] **Step 3: Update `wfx_panel/ui/index.html`**

Replace the `<footer>` block (lines 83-86) with:

```html
    <footer class="panel-footer">
      <span class="footer-status" data-tone="neutral"><i></i><b class="footer-status-text">Đang kiểm tra...</b></span>
      <span class="footer-health">
        <span class="health-chrome" data-state="unknown" title="Chrome automation"><i></i>Chrome</span>
        <span class="health-session" data-state="unknown" title="Phiên WFX"><i></i>WFX</span>
        <span class="health-login" title="Lần đăng nhập gần nhất"></span>
        <button class="health-refresh" type="button" title="Kiểm tra lại">⟳</button>
      </span>
    </footer>
```

Replace the hotkey row (line 96) with:

```html
        <div class="setting-row hotkey-row"><div><strong>Hotkey mở panel</strong><span>Bấm nút rồi nhấn tổ hợp mới</span></div><button class="hotkey-button" type="button">Ctrl + Shift + X</button></div>
```

Insert these three rows immediately after the `close-module-input` row (line 97):

```html
        <label class="setting-row toggle-row"><div><strong>Khởi động cùng Windows</strong><span>Tự chạy khi bạn đăng nhập máy</span></div><input class="autostart-input" type="checkbox" /><i></i></label>
        <label class="setting-row toggle-row"><div><strong>Mở ẩn trong tray</strong><span>Không hiện panel khi khởi động</span></div><input class="start-hidden-input" type="checkbox" /><i></i></label>
        <label class="setting-row toggle-row"><div><strong>Thông báo khi xong việc</strong><span>Hiện bong bóng khi panel đang ẩn</span></div><input class="toast-input" type="checkbox" checked /><i></i></label>
```

- [ ] **Step 4: Append styles to `wfx_panel/ui/style.css`**

```css
/* Phase 2 — chỉ báo sức khoẻ ở footer */
.footer-health { display: flex; align-items: center; gap: 9px; font-size: 11px; color: var(--text-3); }
.footer-health > span { display: inline-flex; align-items: center; gap: 4px; }
.footer-health i { width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); }
.footer-health [data-state="ok"] i { background: #16a34a; }
.footer-health [data-state="bad"] i { background: #dc2626; }
.footer-health [data-state="unknown"] i { background: var(--text-3); opacity: .5; }
.health-refresh { border: 0; background: transparent; cursor: pointer; padding: 0 2px;
                  font-size: 13px; line-height: 1; color: var(--text-3); }
.health-refresh:hover { color: var(--accent); }
.hotkey-button[data-capturing="true"] { border-color: var(--accent); color: var(--accent); }
```

- [ ] **Step 5: Update `wfx_panel/ui/panel.js`**

Add the status globals (place beside the other `window.wfx*` definitions):

```javascript
  function setChromeStatus(alive) {
    const node = $(".health-chrome");
    if (node) node.dataset.state = alive ? "ok" : "bad";
  }
  window.wfxSetChromeStatus = setChromeStatus;

  function setSessionStatus(active, lastLoginAt) {
    const node = $(".health-session");
    if (node) node.dataset.state = active === null || active === undefined
      ? "unknown" : (active ? "ok" : "bad");
    const login = $(".health-login");
    if (login) login.textContent = lastLoginAt ? `· ${lastLoginAt}` : "";
  }
  window.wfxSetSessionStatus = setSessionStatus;
```

Add hotkey capture inside `bind()`:

```javascript
    // Bắt phím gắn TRỰC TIẾP vào nút, không gắn vào document: bản 1.3.x của
    // extension gắn vào document làm cờ capture kẹt lại, khiến mọi ô nhập trên
    // trang không xoá được chữ (xem CLAUDE.md).
    const hotkeyButton = $(".hotkey-button");
    hotkeyButton.addEventListener("click", () => {
      hotkeyButton.dataset.capturing = "true";
      hotkeyButton.textContent = "Đang chờ tổ hợp...";
      hotkeyButton.focus();
    });
    hotkeyButton.addEventListener("blur", () => {
      if (hotkeyButton.dataset.capturing === "true") resetHotkeyButton();
    });
    hotkeyButton.addEventListener("keydown", async (event) => {
      if (hotkeyButton.dataset.capturing !== "true") return;
      event.preventDefault();
      event.stopPropagation();
      if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return;
      if (event.key === "Escape") { resetHotkeyButton(); return; }
      const result = await callQuiet("set_hotkey", {
        ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey,
        meta: event.metaKey, key: event.key, code: event.code,
      });
      hotkeyButton.dataset.capturing = "false";
      if (result && result.ok) {
        hotkeyLabel = result.hotkey_label;
        setStatus("success", result.message || "");
      } else if (result) {
        setStatus("error", result.message || "");
      }
      resetHotkeyButton();
    });
```

Add these helpers near `call()`:

```javascript
  let hotkeyLabel = "Ctrl + Shift + X";

  function resetHotkeyButton() {
    const button = $(".hotkey-button");
    if (!button) return;
    button.dataset.capturing = "false";
    button.textContent = hotkeyLabel;
  }

  // Như call() nhưng KHÔNG khoá UI (setBusy) — dùng cho thao tác thiết lập
  // nhanh, tránh nhấp nháy toàn bộ panel mỗi lần bật một công tắc.
  async function callQuiet(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") return null;
    try {
      return await bridge[method](...args);
    } catch (error) {
      setStatus("error", String(error));
      return null;
    }
  }
```

Wire the three toggles and the refresh button inside `bind()`:

```javascript
    $(".autostart-input").addEventListener("change", async (event) => {
      const result = await callQuiet("set_autostart", event.target.checked);
      if (result) {
        // Registry có thể bị chính sách nhóm chặn — đồng bộ ô tick về trạng
        // thái THẬT thay vì để UI nói dối.
        event.target.checked = Boolean(result.autostart);
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".start-hidden-input").addEventListener("change", (event) =>
      callQuiet("set_start_hidden", event.target.checked));
    $(".toast-input").addEventListener("change", (event) =>
      callQuiet("set_toast_enabled", event.target.checked));
    $(".health-refresh").addEventListener("click", async () => {
      const result = await callQuiet("refresh_status");
      if (result) {
        setChromeStatus(result.chrome_alive);
        setSessionStatus(result.session_active, result.last_login_at);
      }
    });
```

Extend `window.wfxBootstrap` to apply the new state:

```javascript
    if (state.hotkey_label) { hotkeyLabel = state.hotkey_label; resetHotkeyButton(); }
    $(".autostart-input").checked = state.autostart === true;
    $(".start-hidden-input").checked = state.start_hidden === true;
    $(".toast-input").checked = state.toast_enabled !== false;
    setChromeStatus(state.chrome_alive);
    setSessionStatus(state.session_active, state.last_login_at);
```

(Keep the existing `$(".hotkey-label").textContent = state.hotkey_label` line so the search-box badge stays in sync.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui_assets.py tests/test_panel_js.py -v`
Expected: PASS.

- [ ] **Step 7: Visually verify the page still renders**

Run:
```bash
python -c "from pathlib import Path; html=Path('wfx_panel/ui/index.html').read_text(encoding='utf-8'); print('health block:', 'footer-health' in html); print('toggles:', all(k in html for k in ['autostart-input','start-hidden-input','toast-input']))"
```
Expected: both `True`. (Trình duyệt thật do người dùng kiểm ở Task 8.)

- [ ] **Step 8: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/ui/index.html wfx_panel/ui/style.css wfx_panel/ui/panel.js tests/test_ui_assets.py tests/test_panel_js.py
git commit -m "feat(panel): footer health, hotkey capture and settings toggles"
```

---

## Task 7: Nối vào `wfx_panel/panel_app.py`

**Files:**
- Modify: `wfx_panel/panel_app.py`
- Test: `tests/test_panel_app.py` (bổ sung)

**Interfaces:**
- Consumes: mọi thứ từ Tasks 1-6.
- Produces: `PanelApp._apply_hotkey(spec) -> str | None`, `PanelApp._on_result(method, result, elapsed)`, `PanelApp._status_loop()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panel_app.py`:

```python
def test_toast_only_when_hidden_enabled_and_slow(monkeypatch):
    from wfx_panel.panel_app import PanelApp, TOAST_MIN_SECONDS

    app = PanelApp()
    sent = []

    class FakeTray:
        def notify(self, message, title=None):
            sent.append((message, title))

    app.tray = FakeTray()
    app.window = None
    app._toast_enabled = True

    app._visible = True   # panel đang hiện -> không làm phiền
    app._on_result("find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1)
    assert sent == []

    app._visible = False  # ẩn nhưng job nhanh -> không spam
    app._on_result("find_code", {"ok": True, "message": "xong"}, 0.2)
    assert sent == []

    app._visible = False  # ẩn + job chậm -> có toast
    app._on_result("find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1)
    assert len(sent) == 1

    app._toast_enabled = False  # đã tắt công tắc -> im lặng
    app._on_result("find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1)
    assert len(sent) == 1


def test_toast_failure_never_breaks_the_result_flow():
    from wfx_panel.panel_app import PanelApp, TOAST_MIN_SECONDS

    app = PanelApp()

    class ExplodingTray:
        def notify(self, message, title=None):
            raise RuntimeError("tray hỏng")

    app.tray = ExplodingTray()
    app.window = None
    app._visible = False
    app._toast_enabled = True
    # Không được ném ra ngoài: người dùng đang chờ kết quả automation.
    app._on_result("find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1)


def test_apply_hotkey_returns_error_message_on_failure(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()

    def boom(spec, callback):
        raise ValueError("phím bị chiếm")

    monkeypatch.setattr(module.keyboard, "add_hotkey", boom)
    monkeypatch.setattr(module.keyboard, "remove_hotkey", lambda spec: None)
    assert "phím bị chiếm" in (app._apply_hotkey("ctrl+alt+j") or "")


def test_apply_hotkey_returns_none_on_success(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    registered = []
    monkeypatch.setattr(module.keyboard, "add_hotkey",
                        lambda spec, callback: registered.append(spec))
    monkeypatch.setattr(module.keyboard, "remove_hotkey", lambda spec: None)
    assert app._apply_hotkey("ctrl+alt+j") is None
    assert registered == ["ctrl+alt+j"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_panel_app.py -v`
Expected: FAIL — `ImportError: cannot import name 'TOAST_MIN_SECONDS'`.

- [ ] **Step 3: Update `wfx_panel/panel_app.py`**

Add constants beside `HOTKEY`:

```python
STATUS_POLL_SECONDS = 5
TOAST_MIN_SECONDS = 3.0
```

Add imports:

```python
from wfx_panel import prefs, status
```

In `__init__`, replace the fixed-hotkey fields and add state:

```python
        preferences = prefs.load_prefs()
        self._hotkey = preferences["hotkey"]
        self._toast_enabled = preferences["toast_enabled"]
        self._start_hidden = preferences["start_hidden"]
        self._chrome_alive: bool | None = None
        self._stop_status = threading.Event()
```

Add methods:

```python
    def _apply_hotkey(self, spec: str) -> str | None:
        """Đăng ký hotkey mới. Trả None nếu thành công, hoặc thông điệp lỗi."""
        try:
            keyboard.remove_hotkey(self._hotkey)
        except (KeyError, ValueError):
            pass
        try:
            keyboard.add_hotkey(spec, self.toggle)
        except Exception as error:
            return str(error)
        self._hotkey = spec
        return None

    def _on_result(self, method: str, result: dict, elapsed: float) -> None:
        state = self.api.get_status()
        if self.window is not None:
            import json
            try:
                self.window.evaluate_js(
                    "window.wfxSetSessionStatus("
                    f"{json.dumps(state['session_active'])},"
                    f"{json.dumps(state['last_login_at'])})"
                )
            except Exception:
                pass
        if self._visible or not self._toast_enabled or elapsed < TOAST_MIN_SECONDS:
            return
        if self.tray is None:
            return
        try:
            self.tray.notify(str(result.get("message") or "Đã xong."), "WFX Smart")
        except Exception:
            # Toast chỉ là tiện ích; hỏng nó không được ảnh hưởng automation.
            pass

    def _status_loop(self) -> None:
        while not self._stop_status.wait(STATUS_POLL_SECONDS):
            alive = status.chrome_alive()
            if alive == self._chrome_alive:
                continue  # chỉ đẩy khi ĐỔI, tránh 12 lần evaluate_js mỗi phút
            self._chrome_alive = alive
            if self.window is None:
                continue
            try:
                self.window.evaluate_js(
                    f"window.wfxSetChromeStatus({'true' if alive else 'false'})"
                )
            except Exception:
                pass
```

In `run()`, before `create_window`:

```python
        self.api.set_result_sink(self._on_result)
        self.api.set_hotkey_applier(self._apply_hotkey)
```

Change `create_window(...)` to add `hidden=self._start_hidden`, and right after assigning `self.window` set `self._visible = not self._start_hidden`.

In `background()`, replace the hard-coded `HOTKEY` with `self._hotkey`, and start the status thread:

```python
            try:
                keyboard.add_hotkey(self._hotkey, self.toggle)
            except Exception as error:
                self._hotkey_error = str(error)
            finally:
                self._hotkey_ready.set()
            threading.Thread(target=self._status_loop, daemon=True).start()
            self._build_tray()
```

In `_startup`, keep `set_toast_enabled` in sync after bootstrap by re-reading prefs:

```python
        self._toast_enabled = prefs.load_prefs()["toast_enabled"]
```
(place right after the `wfxBootstrap` call) — and in `PanelAPI.set_toast_enabled`'s result sink path nothing else is needed, because `_on_result` re-reads nothing; instead add to `run()` a small wrapper so the toggle takes effect immediately: after `self.api.set_result_sink(...)`, also assign

```python
        self._refresh_toggles = lambda: None  # placeholder removed below
```
**Do not add that placeholder.** Instead, make `_on_result` read the live value:
replace `self._toast_enabled` in `_on_result` with `prefs.load_prefs()["toast_enabled"]`
cached at most once per call — simplest correct form:

```python
        if self._visible or elapsed < TOAST_MIN_SECONDS:
            return
        if not prefs.load_prefs()["toast_enabled"]:
            return
```
Keep `self._toast_enabled` as the value the tests set directly; make `_on_result` prefer the instance attribute when it is not `None`:

```python
        enabled = self._toast_enabled
        if enabled is None:
            enabled = prefs.load_prefs()["toast_enabled"]
        if self._visible or not enabled or elapsed < TOAST_MIN_SECONDS:
            return
```
and initialise `self._toast_enabled = preferences["toast_enabled"]` as above, updating it in a new method the API can call:

```python
    def set_toast_enabled_state(self, enabled: bool) -> None:
        self._toast_enabled = bool(enabled)
```
Wire it by wrapping the API setter in `run()`:

```python
        original_set_toast = self.api.set_toast_enabled

        def set_toast(enabled):
            result = original_set_toast(enabled)
            self.set_toast_enabled_state(result.get("toast_enabled", enabled))
            return result

        self.api.set_toast_enabled = set_toast  # type: ignore[method-assign]
```

In `quit()`, add `self._stop_status.set()` before stopping the tray.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_panel_app.py -v`
Expected: PASS.

- [ ] **Step 5: Static verification**

Run:
```bash
python -c "import wfx_panel.panel_app as m; a=m.PanelApp(); print('hotkey:', a._hotkey); print('toast:', a._toast_enabled); print('hidden:', a._start_hidden); print('poll:', m.STATUS_POLL_SECONDS, 'toast_min:', m.TOAST_MIN_SECONDS)"
```
Expected: prints `ctrl+shift+x`, `True`, `False`, `5 3.0` — no exception.

Do NOT launch the GUI; the user verifies it manually.

- [ ] **Step 6: Run full suite and commit**

```bash
python -m pytest -q
git add wfx_panel/panel_app.py tests/test_panel_app.py
git commit -m "feat(panel): status polling, completion toast and live hotkey rebinding"
```

---

## Task 8: Chuyển Chrome extension sang `legacy/` và build lại exe

**Files:**
- Move: `chrome-extension/` → `legacy/chrome-extension/`
- Create: `legacy/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Confirm nothing in the app references the old path**

Run:
```bash
grep -rn "chrome-extension" --include=*.py --include=*.js --include=*.html --include=*.css --include=*.spec wfx_panel tests || echo "OK: no references"
```
Expected: `OK: no references`. If anything matches, STOP and report — moving would break it.

- [ ] **Step 2: Move the directory preserving history**

Run:
```bash
mkdir -p legacy
git mv chrome-extension legacy/chrome-extension
git status --short | head -20
```
Expected: renames staged. The 12 pre-existing uncommitted edits inside that folder travel with it — verify with `git status` that no file was lost.

- [ ] **Step 3: Create `legacy/README.md`**

```markdown
# Legacy — Chrome Extension (đóng băng)

Thư mục này chỉ để **lưu trữ**. Bản Chrome Extension đã được thay thế hoàn toàn
bởi app desktop Python trong `wfx_panel/`.

- Không phát triển tiếp, không sửa lỗi ở đây.
- `chrome-extension/build-extension.ps1` chứa đường dẫn tương đối theo vị trí
  cũ (gốc repo) nên **không còn chạy đúng** sau khi chuyển. Đây là chủ ý: giữ
  nguyên nội dung để tham chiếu, không duy trì khả năng build.
- Nguồn hành vi chuẩn cho automation vẫn là `login.py` và `CLAUDE.md` ở gốc repo.
```

- [ ] **Step 4: Note the move in the root `README.md`**

Append:

```markdown
## Chrome Extension (cũ)

Đã chuyển sang `legacy/chrome-extension/` và đóng băng — xem `legacy/README.md`.
App desktop `wfx_panel/` là bản thay thế.
```

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: all green — no test reads from `chrome-extension/`.

- [ ] **Step 6: Rebuild the exe with all Phase 2 changes**

Run:
```bash
python -m PyInstaller --noconfirm --clean wfx_panel/wfx-panel.spec
```
Then verify the new UI made it into the bundle:
```bash
grep -c "footer-health" dist/WFX-Panel/_internal/wfx_panel/ui/index.html
grep -c "wfxSetChromeStatus" dist/WFX-Panel/_internal/wfx_panel/ui/panel.js
```
Expected: `1` and `1`. Do NOT launch the exe.

- [ ] **Step 7: Commit (source only, no build output)**

```bash
git add legacy README.md
git add -u
git commit -m "chore: archive chrome extension under legacy/"
git status --short | grep -E "^(\?\?|.M) (dist|build)/" && echo "ERROR: build output staged" || echo "OK: no build output"
```

---

## Self-Review Notes

- **Spec coverage:** hotkey.py (T1) ↔ spec §1; autostart.py (T2) ↔ §2; status.py (T3) ↔ §3; prefs keys + derived label + backward-compat `hotkey_label` (T4) ↔ §4; result sink, session inference, setters, `get_initial_state` (T5) ↔ §5; footer health, capture-on-button, 3 toggles, JS globals (T6) ↔ §7; status loop, toast gating, hidden start, rebinding, quit cleanup (T7) ↔ §6; legacy move + README (T8) ↔ §8. Error-handling rows in the spec map to: hotkey rollback (T5), autostart truth-sync (T5 + T6 checkbox resync), toast swallow (T7), status thread isolation (T7).
- **Type consistency:** `_apply_hotkey(spec) -> str | None` in T7 matches the `set_hotkey_applier` contract in T5 (None = success). `get_status()` keys `chrome_alive`/`session_active`/`last_login_at` are identical in T5, T6 (`refresh_status` consumer) and T7. `save_prefs` keyword names in T4 match every call site in T5.
- **Known wrinkle flagged for the implementer:** T4 Step 4 warns that the pre-existing `test_prefs_defaults` may assert an exact 3-key dict and will need widening — this is expected, not a regression.
- **Manual-only acceptance:** autostart actually running at Windows login, global hotkey rebinding taking effect, tray balloon appearing, and hidden start — all require the user; T7/T8 deliberately stop at static verification.
