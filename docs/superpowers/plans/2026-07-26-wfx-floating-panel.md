# WFX Floating Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay Chrome Extension bằng một app desktop Python (`pywebview`) đóng vai floating panel: nổi luôn-trên-cùng, gọi/ẩn bằng hotkey toàn cục Ctrl+Shift+X, thu về system tray, giao diện tái dùng nguyên HTML/CSS của extension, đóng gói được thành `.exe`.

**Architecture:** WebView hiển thị UI (HTML/CSS trích từ extension); `panel.js` nối nút → `window.pywebview.api.*`; `PanelAPI` (Python) gọi engine [login.py](../../../login.py) đã có, stream log ngược về WebView qua `window.evaluate_js`. `panel_app.py` dựng cửa sổ frameless always-on-top + hotkey (`keyboard`) + tray (`pystray`). `login.py` không đổi.

**Tech Stack:** Python 3, pywebview, keyboard, pystray, Pillow, Playwright (đã có), pytest (test), PyInstaller (đóng gói).

## Global Constraints

- Không sửa chữ ký các hàm public trong `login.py`; chỉ gọi lại. Giữ nguyên `app.py` cũ.
- Hotkey mặc định v1 cố định `Ctrl+Shift+X` (rebinding để lại sau — ngoài phạm vi).
- Tài khoản lưu ở `.env` gốc repo với đúng key `WFX_USER_ID`, `WFX_PASSWORD` để `login.py` (đọc qua `os.getenv`) thấy được; khi lưu phải cập nhật cả `os.environ` trong tiến trình.
- Không ghi password/cookie/SessionID/LoginID/IP ra log.
- Chrome automation vẫn do `login.py` tự mở qua CDP (`--remote-debugging-port`, profile `WFX-Automation`); KHÔNG bundle Chromium của Playwright vào exe.
- Tiếng Việt cho toàn bộ chuỗi UI/log. Windows là nền tảng đích.
- Danh sách Category và Module phải khớp bảng dưới (nguồn: `main.js` MODULE_GROUPS 298-332 / CATEGORIES 273-280):
  - CATEGORIES: `Apparel=01, Fixed Asset=04, Miscellaneous=12, Services=06, Textiles/Fabric=03, Trims=05`.
  - Operation (accent cyan): `Catalog/0003_6200/CA`, `OC List/0004_0050_0020/OC`, `Sample List/0004_0056_4070/SL`, `Sale ASN/0004_0070_0020/AS`, `RMPO List/0005_0050_0020/RM`, `Indent List/0005_0080_0020/IN`, `QA List/0063_0030_0020/QA`.
  - Finance (accent violet): `Advance PR List/0065_0880_0010_0020/PR`, `Supplier Inv List/0065_0880_0020_0020/SI`, `Expense Inv List/0065_0880_0030_0020/EI`.
  - Admin (accent amber): `Org Structure/0090_0001/OR`, `System Coding/0090_0250/SC`, `Company Setup/0090_0007/CO`, `Buyer List/0004_0010_1720/BU`, `Supplier List/0005_0010_1290/SU`.

---

## File Structure

- Create `wfx_panel/__init__.py` — package marker.
- Create `wfx_panel/prefs.py` — đọc/ghi `.env` (tài khoản) + `prefs.json` (theme, close_after_module, hotkey_label).
- Create `wfx_panel/log_bridge.py` — format dòng log + escape chuỗi an toàn cho `evaluate_js`.
- Create `wfx_panel/constants.py` — `CATEGORIES`, `MODULE_GROUPS` (Python bản sao của bảng trên).
- Create `wfx_panel/panel_api.py` — class `PanelAPI` (js_api) nối WebView → `login.py`.
- Create `wfx_panel/ui/style.css` — trích khối `STYLES` của extension.
- Create `wfx_panel/ui/index.html` — trích template panel (bỏ launcher).
- Create `wfx_panel/ui/panel.js` — render + wiring.
- Create `wfx_panel/assets/generate_icon.py` + `wfx_panel/assets/wfx.ico` — logo W.
- Create `wfx_panel/panel_app.py` — entrypoint: cửa sổ + hotkey + tray + auto-login.
- Create `tests/__init__.py`, `tests/test_prefs.py`, `tests/test_log_bridge.py`, `tests/test_panel_api.py`, `tests/test_ui_assets.py`, `tests/test_icon.py`.
- Modify `requirements.txt` (thêm runtime deps) và create `requirements-dev.txt` (pytest, pyinstaller).
- Modify `README.md` gốc (thêm mục chạy panel + build exe) — trong Task 8.

---

## Task 1: Dependencies, package scaffold, và prefs

**Files:**
- Create: `wfx_panel/__init__.py`, `wfx_panel/prefs.py`, `tests/__init__.py`, `tests/test_prefs.py`, `requirements-dev.txt`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `wfx_panel.prefs.load_account(base_dir: Path = APP_DIR) -> dict` → `{"user_id": str, "password": str}`
  - `wfx_panel.prefs.save_account(user_id: str, password: str, base_dir: Path = APP_DIR) -> None`
  - `wfx_panel.prefs.load_prefs(base_dir: Path = APP_DIR) -> dict` → `{"theme": str, "close_after_module": bool, "hotkey_label": str}`
  - `wfx_panel.prefs.save_prefs(base_dir: Path = APP_DIR, *, theme=None, close_after_module=None, hotkey_label=None) -> dict`
  - Constant `wfx_panel.prefs.APP_DIR: Path` (gốc repo).

- [ ] **Step 1: Update requirements**

Modify `requirements.txt` to:

```
playwright>=1.58,<2
pywebview>=5,<6
keyboard>=0.13,<1
pystray>=0.19,<1
Pillow>=10
```

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8
pyinstaller>=6
```

- [ ] **Step 2: Create package markers**

Create `wfx_panel/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 3: Write the failing test**

Create `tests/test_prefs.py`:

```python
from pathlib import Path

from wfx_panel import prefs


def test_account_round_trip(tmp_path: Path):
    prefs.save_account("user1", "secret", base_dir=tmp_path)
    loaded = prefs.load_account(base_dir=tmp_path)
    assert loaded == {"user_id": "user1", "password": "secret"}


def test_account_updates_environ(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WFX_USER_ID", raising=False)
    prefs.save_account("abc", "pw", base_dir=tmp_path)
    import os
    assert os.environ["WFX_USER_ID"] == "abc"
    assert os.environ["WFX_PASSWORD"] == "pw"


def test_load_account_missing_returns_empty(tmp_path: Path):
    assert prefs.load_account(base_dir=tmp_path) == {"user_id": "", "password": ""}


def test_prefs_defaults(tmp_path: Path):
    assert prefs.load_prefs(base_dir=tmp_path) == {
        "theme": "light",
        "close_after_module": True,
        "hotkey_label": "Ctrl + Shift + X",
    }


def test_prefs_partial_update_preserves_others(tmp_path: Path):
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    prefs.save_prefs(base_dir=tmp_path, close_after_module=False)
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["theme"] == "dark"
    assert loaded["close_after_module"] is False
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_prefs.py -v`
Expected: FAIL (ModuleNotFoundError: wfx_panel.prefs).

- [ ] **Step 5: Implement `wfx_panel/prefs.py`**

```python
from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HOTKEY_LABEL = "Ctrl + Shift + X"


def _env_path(base_dir: Path) -> Path:
    return Path(base_dir) / ".env"


def _prefs_path(base_dir: Path) -> Path:
    return Path(base_dir) / "prefs.json"


def load_account(base_dir: Path = APP_DIR) -> dict:
    path = _env_path(base_dir)
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            try:
                values[key.strip()] = json.loads(value) if value.startswith('"') else value
            except json.JSONDecodeError:
                values[key.strip()] = value.strip('"')
    return {
        "user_id": values.get("WFX_USER_ID", ""),
        "password": values.get("WFX_PASSWORD", ""),
    }


def save_account(user_id: str, password: str, base_dir: Path = APP_DIR) -> None:
    content = (
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}\n"
        f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}\n"
    )
    path = _env_path(base_dir)
    temp = path.with_suffix(".env.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    os.environ["WFX_USER_ID"] = user_id
    os.environ["WFX_PASSWORD"] = password


def load_prefs(base_dir: Path = APP_DIR) -> dict:
    path = _prefs_path(base_dir)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    return {
        "theme": "dark" if data.get("theme") == "dark" else "light",
        "close_after_module": data.get("close_after_module", True) is not False,
        "hotkey_label": str(data.get("hotkey_label") or DEFAULT_HOTKEY_LABEL),
    }


def save_prefs(
    base_dir: Path = APP_DIR,
    *,
    theme: str | None = None,
    close_after_module: bool | None = None,
    hotkey_label: str | None = None,
) -> dict:
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = "dark" if theme == "dark" else "light"
    if close_after_module is not None:
        current["close_after_module"] = bool(close_after_module)
    if hotkey_label is not None:
        current["hotkey_label"] = str(hotkey_label)
    path = _prefs_path(base_dir)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_prefs.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt wfx_panel/__init__.py wfx_panel/prefs.py tests/__init__.py tests/test_prefs.py
git commit -m "feat(panel): prefs module for account + preferences"
```

---

## Task 2: Log bridge helpers

**Files:**
- Create: `wfx_panel/log_bridge.py`, `tests/test_log_bridge.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `wfx_panel.log_bridge.js_string(value: str) -> str` — trả literal JS an toàn (đã bọc dấu nháy), nhúng thẳng vào `evaluate_js` được.
  - `wfx_panel.log_bridge.format_log_line(message: str) -> str` — thêm tiền tố `[HH:MM:SS] ` vào message (giữ nguyên nếu đã có tiền tố thời gian dạng `[HH:MM:SS]`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_bridge.py`:

```python
import json
import re

from wfx_panel import log_bridge


def test_js_string_escapes_quotes_and_newlines():
    out = log_bridge.js_string('he said "hi"\nline2\\end')
    # Kết quả phải parse lại được bằng JSON để đảm bảo escape đúng.
    assert json.loads(out) == 'he said "hi"\nline2\\end'


def test_js_string_handles_unicode():
    assert json.loads(log_bridge.js_string("Đăng nhập")) == "Đăng nhập"


def test_format_log_line_adds_timestamp():
    line = log_bridge.format_log_line("[SESSION] ok")
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] \[SESSION\] ok$", line)


def test_format_log_line_keeps_existing_timestamp():
    original = "[10:11:12] already stamped"
    assert log_bridge.format_log_line(original) == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_log_bridge.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `wfx_panel/log_bridge.py`**

```python
from __future__ import annotations

import json
import re
import time

_TIMESTAMP_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]")


def js_string(value: str) -> str:
    """JSON-encode a string so it can be embedded directly in evaluate_js."""
    return json.dumps(str(value), ensure_ascii=False)


def format_log_line(message: str) -> str:
    text = str(message)
    if _TIMESTAMP_RE.match(text):
        return text
    return f"[{time.strftime('%H:%M:%S')}] {text}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_log_bridge.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/log_bridge.py tests/test_log_bridge.py
git commit -m "feat(panel): log bridge helpers (js escape + timestamp)"
```

---

## Task 3: Constants (categories + modules)

**Files:**
- Create: `wfx_panel/constants.py`, `tests/test_constants.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `wfx_panel.constants.CATEGORIES: dict[str, str]`
  - `wfx_panel.constants.MODULE_GROUPS: list[dict]` — mỗi group `{"name": str, "accent": str, "modules": [{"name": str, "id": str, "icon": str}]}`
  - `wfx_panel.constants.MODULE_BY_ID: dict[str, dict]` — tra cứu module theo id (thêm khoá `xpath`).
  - `wfx_panel.constants.xpath_for(module_id: str) -> str` → `//*[@id="{module_id}"]/a`

- [ ] **Step 1: Write the failing test**

Create `tests/test_constants.py`:

```python
from wfx_panel import constants


def test_categories_match_spec():
    assert constants.CATEGORIES["Apparel"] == "01"
    assert constants.CATEGORIES["Textiles/Fabric"] == "03"
    assert len(constants.CATEGORIES) == 6


def test_module_groups_counts():
    counts = {g["name"]: len(g["modules"]) for g in constants.MODULE_GROUPS}
    assert counts == {"Operation": 7, "Finance": 3, "Admin": 5}


def test_module_lookup_and_xpath():
    catalog = constants.MODULE_BY_ID["0003_6200"]
    assert catalog["name"] == "Catalog"
    assert constants.xpath_for("0003_6200") == '//*[@id="0003_6200"]/a'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_constants.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `wfx_panel/constants.py`**

```python
from __future__ import annotations

CATEGORIES = {
    "Apparel": "01",
    "Fixed Asset": "04",
    "Miscellaneous": "12",
    "Services": "06",
    "Textiles/Fabric": "03",
    "Trims": "05",
}

MODULE_GROUPS = [
    {
        "name": "Operation",
        "accent": "cyan",
        "modules": [
            {"name": "Catalog", "id": "0003_6200", "icon": "CA"},
            {"name": "OC List", "id": "0004_0050_0020", "icon": "OC"},
            {"name": "Sample List", "id": "0004_0056_4070", "icon": "SL"},
            {"name": "Sale ASN", "id": "0004_0070_0020", "icon": "AS"},
            {"name": "RMPO List", "id": "0005_0050_0020", "icon": "RM"},
            {"name": "Indent List", "id": "0005_0080_0020", "icon": "IN"},
            {"name": "QA List", "id": "0063_0030_0020", "icon": "QA"},
        ],
    },
    {
        "name": "Finance",
        "accent": "violet",
        "modules": [
            {"name": "Advance PR List", "id": "0065_0880_0010_0020", "icon": "PR"},
            {"name": "Supplier Inv List", "id": "0065_0880_0020_0020", "icon": "SI"},
            {"name": "Expense Inv List", "id": "0065_0880_0030_0020", "icon": "EI"},
        ],
    },
    {
        "name": "Admin",
        "accent": "amber",
        "modules": [
            {"name": "Org Structure", "id": "0090_0001", "icon": "OR"},
            {"name": "System Coding", "id": "0090_0250", "icon": "SC"},
            {"name": "Company Setup", "id": "0090_0007", "icon": "CO"},
            {"name": "Buyer List", "id": "0004_0010_1720", "icon": "BU"},
            {"name": "Supplier List", "id": "0005_0010_1290", "icon": "SU"},
        ],
    },
]


def xpath_for(module_id: str) -> str:
    return f'//*[@id="{module_id}"]/a'


MODULE_BY_ID = {
    module["id"]: {**module, "group": group["name"], "accent": group["accent"], "xpath": xpath_for(module["id"])}
    for group in MODULE_GROUPS
    for module in group["modules"]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_constants.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/constants.py tests/test_constants.py
git commit -m "feat(panel): category + module constants"
```

---

## Task 4: PanelAPI (bridge to login.py)

**Files:**
- Create: `wfx_panel/panel_api.py`, `tests/test_panel_api.py`

**Interfaces:**
- Consumes: `wfx_panel.prefs`, `wfx_panel.log_bridge`, `wfx_panel.constants`, and a login module (default `import login`).
- Produces — class `PanelAPI`:
  - `PanelAPI(login_module=None, prefs_module=None, base_dir=None)`
  - `.set_log_sink(sink: Callable[[str], None]) -> None`
  - `.get_initial_state() -> dict` → `{"user_id","theme","close_after_module","hotkey_label","logs"}`
  - `.login() -> dict`
  - `.check_session() -> dict`
  - `.open_module(module_id: str) -> dict`
  - `.prepare_catalog(category_name: str) -> dict`
  - `.find_code(category_name: str, code: str, destination: str | None = None) -> dict`
  - `.find_buyer_reference(category_name: str, query: str, destination: str | None = None) -> dict`
  - `.save_account(user_id: str, password: str) -> dict`
  - `.set_theme(theme: str) -> dict`
  - `.set_close_after_module(value: bool) -> dict`
  - `.clear_log() -> dict`
  - Each login-backed method passes `self._log` as the `log=` callback to `login.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_panel_api.py`:

```python
from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self):
        self.calls = []

    def run(self, user_id, password, company_id="psh", log=print):
        self.calls.append(("run", user_id, password, company_id))
        log("[SESSION] fake login")
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    def check_session(self, log=print):
        self.calls.append(("check_session",))
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "no"}

    def open_module(self, module_name, xpath, log=print):
        self.calls.append(("open_module", module_name, xpath))
        return {"ok": True, "code": "MODULE_OPENED", "message": module_name}

    def set_catalog_category(self, category_name, category_value, log=print):
        self.calls.append(("set_catalog_category", category_name, category_value))
        return {"ok": True, "code": "CATEGORY_SELECTED", "message": category_name}

    def quick_find_catalog(self, category_name, category_value, filter_kind, query,
                           user_id, password, company_id="psh", log=print, destination=None):
        self.calls.append(("quick_find_catalog", category_name, category_value,
                           filter_kind, query, destination))
        return {"ok": True, "code": "RESULT_OPENED", "message": query, "codes": [query]}


def make_api(tmp_path):
    fake = FakeLogin()
    api = PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path)
    return api, fake


def test_find_code_calls_quick_find(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    result = api.find_code("Apparel", "ABC123", destination="bom")
    assert result["code"] == "RESULT_OPENED"
    assert ("quick_find_catalog", "Apparel", "01", "code", "ABC123", "bom") in fake.calls


def test_find_buyer_reference_uses_buyer_kind(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    api.find_buyer_reference("Apparel", "PO-9")
    assert ("quick_find_catalog", "Apparel", "01", "buyer_reference", "PO-9", None) in fake.calls


def test_open_module_builds_xpath(tmp_path):
    api, fake = make_api(tmp_path)
    api.open_module("0004_0050_0020")
    assert ("open_module", "OC List", '//*[@id="0004_0050_0020"]/a') in fake.calls


def test_prepare_catalog_opens_then_selects(tmp_path):
    api, fake = make_api(tmp_path)
    api.prepare_catalog("Apparel")
    names = [c[0] for c in fake.calls]
    assert names == ["open_module", "set_catalog_category"]


def test_log_sink_receives_lines(tmp_path):
    prefs.save_account("u", "p", base_dir=tmp_path)
    api, fake = make_api(tmp_path)
    lines = []
    api.set_log_sink(lines.append)
    api.login()
    assert any("fake login" in line for line in lines)


def test_get_initial_state(tmp_path):
    prefs.save_account("bob", "pw", base_dir=tmp_path)
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    api, _ = make_api(tmp_path)
    state = api.get_initial_state()
    assert state["user_id"] == "bob"
    assert state["theme"] == "dark"
    assert state["hotkey_label"] == "Ctrl + Shift + X"


def test_save_account_persists(tmp_path):
    api, _ = make_api(tmp_path)
    api.save_account("carol", "s3cret")
    assert prefs.load_account(base_dir=tmp_path)["user_id"] == "carol"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_panel_api.py -v`
Expected: FAIL (ModuleNotFoundError: wfx_panel.panel_api).

- [ ] **Step 3: Implement `wfx_panel/panel_api.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from wfx_panel import constants, log_bridge, prefs as prefs_default


class PanelAPI:
    def __init__(self, login_module=None, prefs_module=None, base_dir: Path | None = None):
        if login_module is None:
            import login as login_module  # imported lazily so tests can inject a fake
        self._login = login_module
        self._prefs = prefs_module or prefs_default
        self._base_dir = base_dir or self._prefs.APP_DIR
        self._logs: list[str] = []
        self._sink: Callable[[str], None] | None = None

    # -- logging -----------------------------------------------------------
    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def _log(self, message: str) -> None:
        line = log_bridge.format_log_line(message)
        self._logs.append(line)
        if len(self._logs) > 300:
            self._logs = self._logs[-300:]
        if self._sink is not None:
            try:
                self._sink(line)
            except Exception:
                pass

    def _account(self) -> dict:
        return self._prefs.load_account(base_dir=self._base_dir)

    # -- state -------------------------------------------------------------
    def get_initial_state(self) -> dict:
        account = self._account()
        preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        return {
            "user_id": account["user_id"],
            "theme": preferences["theme"],
            "close_after_module": preferences["close_after_module"],
            "hotkey_label": preferences["hotkey_label"],
            "logs": list(self._logs),
        }

    # -- automation --------------------------------------------------------
    def login(self) -> dict:
        account = self._account()
        return self._login.run(account["user_id"], account["password"],
                               self._login.COMPANY_ID, self._log)

    def check_session(self) -> dict:
        return self._login.check_session(self._log)

    def open_module(self, module_id: str) -> dict:
        module = constants.MODULE_BY_ID.get(module_id)
        if module is None:
            return {"ok": False, "code": "MODULE_UNKNOWN", "message": f"Module lạ: {module_id}"}
        return self._login.open_module(module["name"], module["xpath"], self._log)

    def prepare_catalog(self, category_name: str) -> dict:
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN", "message": f"Category lạ: {category_name}"}
        opened = self._login.open_module("Catalog", self._login.CATALOG_XPATH, self._log)
        if not opened.get("ok"):
            return opened
        return self._login.set_catalog_category(category_name, value, self._log)

    def find_code(self, category_name: str, code: str, destination: str | None = None) -> dict:
        return self._quick(category_name, "code", code, destination)

    def find_buyer_reference(self, category_name: str, query: str, destination: str | None = None) -> dict:
        return self._quick(category_name, "buyer_reference", query, destination)

    def _quick(self, category_name: str, filter_kind: str, query: str, destination):
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN", "message": f"Category lạ: {category_name}"}
        account = self._account()
        return self._login.quick_find_catalog(
            category_name, value, filter_kind, query,
            account["user_id"], account["password"], self._login.COMPANY_ID,
            self._log, destination=destination,
        )

    # -- settings ----------------------------------------------------------
    def save_account(self, user_id: str, password: str) -> dict:
        self._prefs.save_account(user_id, password, base_dir=self._base_dir)
        self._log("[SETTINGS] Đã lưu tài khoản")
        return {"ok": True, "code": "ACCOUNT_SAVED", "message": "Đã lưu tài khoản", "user_id": user_id}

    def set_theme(self, theme: str) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, theme=theme)
        return {"ok": True, "code": "THEME_SAVED", "message": "Đã đổi giao diện", "theme": saved["theme"]}

    def set_close_after_module(self, value: bool) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, close_after_module=bool(value))
        return {"ok": True, "code": "PREF_SAVED", "message": "Đã lưu",
                "close_after_module": saved["close_after_module"]}

    def clear_log(self) -> dict:
        self._logs = []
        return {"ok": True, "code": "LOG_CLEARED", "message": "Đã xóa nhật ký"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_panel_api.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/panel_api.py tests/test_panel_api.py
git commit -m "feat(panel): PanelAPI bridging webview to login.py"
```

---

## Task 5: UI assets — style.css + index.html

**Files:**
- Create: `wfx_panel/ui/style.css`, `wfx_panel/ui/index.html`, `tests/test_ui_assets.py`
- Reference source: `chrome-extension/dist/WFX-Smart-Chrome-Extension/main.js` (STYLES `2779`→end of the `String.raw` block ~`3095`; template `2484`–`2606`; `buildModuleMarkup` `2457`–`2476`).

**Interfaces:**
- Consumes: nothing at runtime (static assets; `index.html` references `style.css` and `panel.js`).
- Produces: DOM contract for Task 6 (`panel.js`) — these selectors/classes MUST exist:
  `.panel`, `.panel-header`, `.brand`, `.icon-button.log-button`, `.icon-button.settings-button`,
  `.icon-button.close-button`, `.catalog-card`, `select.catalog-category`,
  `[data-catalog-action="prepare"|"code-find"|"code-costsheet"|"code-bom"|"buyer-find"|"buyer-costsheet"|"buyer-bom"]`,
  `input.catalog-code`, `input.catalog-buyer-reference`, `.search-box input`, `.module-list`,
  `.empty-state`, `.footer-status`, `.footer-status-text`, `.footer-meta`,
  `.settings-overlay` (account form: `.user-input`, `.password-input`, `.toggle-password`,
  `.hotkey-button`, `.close-module-input`, `.seg-button[data-theme-choice]`, `.save-button`,
  `.settings-close-button`), `.log-overlay` (`.catalog-log`, `.catalog-log-copy`, `.log-close-button`).

- [ ] **Step 1: Create `wfx_panel/ui/style.css`**

Copy the CSS inside the `const STYLES = String.raw\`` … \`` block from `main.js` (starts line 2779, ends at the closing backtick of that template literal, ~line 3095). Then apply these edits so it works outside a shadow root:
- Replace every `:host` with `:root` (including `:host([data-theme="dark"])` → `:root[data-theme="dark"]`).
- Delete the rules for `.launcher`, `.launcher-pulse`, and the `@keyframes` used only by the launcher pulse (they have no element in this app).
- Append at the very top:

```css
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: transparent; }
body { overflow: hidden; }
.panel { position: static !important; inset: auto !important; transform: none !important;
         width: 100vw !important; height: 100vh !important; max-width: 100vw !important;
         max-height: 100vh !important; border-radius: 0 !important; }
.panel-header { -webkit-app-region: drag; }
.panel-header button, .header-actions { -webkit-app-region: no-drag; }
.pywebview-drag-region { -webkit-app-region: drag; }
```

(The panel in the extension floats inside the page; here the OS window IS the panel, so it fills the viewport and the header is the drag handle.)

- [ ] **Step 2: Create `wfx_panel/ui/index.html`**

Build the document below. The `<aside class="panel">` inner markup is copied from `main.js` template lines `2496`–`2603` (everything from `<header class="panel-header">` through the closing `</div>` of `.log-overlay`), i.e. the whole panel WITHOUT the `.panel-glow`/launcher and WITHOUT the `<div class="toast-stack">`. Leave `.module-list` EMPTY — `panel.js` fills it. Categories in the `<select>` are listed statically.

```html
<!doctype html>
<html lang="vi" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFX Smart</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <aside class="panel" aria-label="WFX Smart Automation">
    <header class="panel-header">
      <div class="brand">
        <div class="brand-logo">
          <svg viewBox="0 0 28 28" aria-hidden="true"><path d="M5.2 6.7 14 2.4l8.8 4.3v10.6L14 25.6l-8.8-8.3V6.7Z"/><path class="brand-mark" d="m8.6 9.2 2.6 9.2 2.8-6.2 2.8 6.2 2.6-9.2"/></svg>
        </div>
        <div><strong>WFX Smart</strong><span>Automation workspace</span></div>
      </div>
      <div class="header-actions">
        <button class="icon-button log-button" type="button" aria-label="Trạng thái hoạt động" title="Trạng thái hoạt động">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7h11M8 12h11M8 17h7"/><path d="M4 7h.01M4 12h.01M4 17h.01"/></svg>
          <span class="log-alert" aria-hidden="true"></span>
        </button>
        <button class="icon-button settings-button" type="button" aria-label="Mở cài đặt" title="Cài đặt">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.3a3.3 3.3 0 1 0 0-6.6 3.3 3.3 0 0 0 0 6.6Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V21h-4v-.08A1.7 1.7 0 0 0 8.95 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.58 15 1.7 1.7 0 0 0 3 14H3v-4h.08A1.7 1.7 0 0 0 4.6 8.95a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.58 1.7 1.7 0 0 0 10 3V3h4v.08A1.7 1.7 0 0 0 15.05 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.42 9 1.7 1.7 0 0 0 21 10h.08v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>
        </button>
        <button class="icon-button close-button" type="button" aria-label="Đóng panel" title="Đóng">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
        </button>
      </div>
    </header>

    <div class="panel-body">
      <section class="catalog-card">
        <div class="catalog-heading"><strong>Catalog Control</strong></div>
        <div class="catalog-category-row">
          <span>Category</span>
          <select class="catalog-category">
            <option value="Apparel">Apparel</option>
            <option value="Fixed Asset">Fixed Asset</option>
            <option value="Miscellaneous">Miscellaneous</option>
            <option value="Services">Services</option>
            <option value="Textiles/Fabric">Textiles/Fabric</option>
            <option value="Trims">Trims</option>
          </select>
          <button class="catalog-open-button" type="button" data-catalog-action="prepare">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h6l2 2h8v12H4V5Z"/><path d="m9 14 2 2 4-5"/></svg>
            Mở Catalog
          </button>
        </div>
        <div class="catalog-query-row">
          <label><span>Code</span><input class="catalog-code" type="text" autocomplete="off" placeholder="Nhập article code..." /></label>
          <div class="catalog-query-actions">
            <button type="button" data-catalog-action="code-find">Tìm</button>
            <button class="destination-button" type="button" data-catalog-action="code-costsheet">Costsheet</button>
            <button class="destination-button" type="button" data-catalog-action="code-bom">BOM</button>
          </div>
        </div>
        <div class="catalog-query-row">
          <label><span>Buyer Reference</span><input class="catalog-buyer-reference" type="text" autocomplete="off" placeholder="Nhập buyer reference..." /></label>
          <div class="catalog-query-actions">
            <button type="button" data-catalog-action="buyer-find">Tìm</button>
            <button class="destination-button" type="button" data-catalog-action="buyer-costsheet">Costsheet</button>
            <button class="destination-button" type="button" data-catalog-action="buyer-bom">BOM</button>
          </div>
        </div>
      </section>

      <label class="search-box">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
        <input type="search" placeholder="Tìm nhanh module..." autocomplete="off" />
        <kbd class="hotkey-label">Ctrl + Shift + X</kbd>
      </label>

      <div class="modules-scroll">
        <div class="module-list"></div>
        <div class="empty-state" hidden>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <strong>Không tìm thấy module</strong><span>Thử một từ khóa khác</span>
        </div>
      </div>
    </div>

    <footer class="panel-footer">
      <span class="footer-status" data-tone="neutral"><i></i><b class="footer-status-text">Đang kiểm tra...</b></span>
      <span class="footer-meta">WFX Panel · v1.0.0</span>
    </footer>

    <div class="settings-overlay" aria-label="Thiết lập WFX">
      <div class="settings-sheet">
        <div class="sheet-handle"></div>
        <div class="sheet-heading"><div><strong>Thiết lập thông minh</strong><span>Lưu riêng trên máy này</span></div><button class="icon-button settings-close-button" type="button" aria-label="Đóng cài đặt"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>
        <div class="form-grid">
          <label><span>User ID</span><input class="user-input" type="text" autocomplete="username" placeholder="WFX User ID" /></label>
          <label class="password-field"><span>Password</span><div><input class="password-input" type="password" autocomplete="current-password" placeholder="WFX Password" /><button class="toggle-password" type="button">Hiện</button></div></label>
        </div>
        <div class="setting-row hotkey-row"><div><strong>Hotkey mở panel</strong><span>Cố định trong bản này</span></div><button class="hotkey-button" type="button" disabled>Ctrl + Shift + X</button></div>
        <label class="setting-row toggle-row"><div><strong>Đóng panel sau khi mở module</strong><span>Giữ màn hình làm việc gọn hơn</span></div><input class="close-module-input" type="checkbox" checked /><i></i></label>
        <div class="setting-row appearance-row"><div><strong>Giao diện</strong><span>Chọn nền sáng hoặc tối</span></div>
          <div class="segmented" role="group" aria-label="Giao diện">
            <button class="seg-button" type="button" data-theme-choice="light" aria-pressed="true"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>Sáng</button>
            <button class="seg-button" type="button" data-theme-choice="dark" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 13.5A8 8 0 1 1 10.5 4a6.3 6.3 0 0 0 9.5 9.5Z"/></svg>Tối</button>
          </div>
        </div>
        <button class="save-button" type="button">Lưu thiết lập &amp; kết nối</button>
      </div>
    </div>

    <div class="settings-overlay log-overlay" aria-label="Nhật ký hệ thống">
      <div class="settings-sheet log-sheet">
        <div class="sheet-handle"></div>
        <div class="sheet-heading">
          <div><strong>Trạng thái hoạt động</strong><span>Sao chép để lấy log kỹ thuật</span></div>
          <div class="log-heading-actions">
            <button class="catalog-log-copy" type="button">Sao chép log</button>
            <button class="icon-button log-close-button" type="button" aria-label="Đóng nhật ký"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
          </div>
        </div>
        <pre class="catalog-log">Chưa có nhật ký hệ thống.</pre>
      </div>
    </div>
  </aside>
  <script src="panel.js"></script>
</body>
</html>
```

- [ ] **Step 3: Write the smoke test**

Create `tests/test_ui_assets.py`:

```python
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def test_style_css_exists_and_scoped_to_root():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".panel" in css
    assert ".accent-cyan" in css
    assert ":host" not in css  # đã đổi hết sang :root


def test_index_html_has_contract_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="module-list"',
        'data-catalog-action="prepare"',
        'data-catalog-action="code-find"',
        'data-catalog-action="buyer-bom"',
        'class="catalog-code"',
        'class="catalog-buyer-reference"',
        'class="user-input"',
        'class="save-button"',
        'class="catalog-log"',
        'data-theme-choice="dark"',
        'src="panel.js"',
    ]:
        assert hook in html, hook
    assert "launcher" not in html
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_assets.py -v`
Expected: PASS (2 passed). If `:host` still present, finish the replacements in Step 1.

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/ui/style.css wfx_panel/ui/index.html tests/test_ui_assets.py
git commit -m "feat(panel): extract extension panel HTML/CSS as webview UI"
```

---

## Task 6: panel.js — render + wiring

**Files:**
- Create: `wfx_panel/ui/panel.js`, `tests/test_panel_js.py`

**Interfaces:**
- Consumes: `window.pywebview.api` (methods from Task 4) and the DOM contract from Task 5.
- Produces (globals Python calls via `evaluate_js`):
  `window.wfxPushLog(line)`, `window.wfxSetStatus(tone, label)`, `window.wfxSetBusy(bool)`,
  `window.wfxSetAccount(userId)`, `window.wfxApplyTheme(theme)`, `window.wfxBootstrap(state)`.

- [ ] **Step 1: Create `wfx_panel/ui/panel.js`**

```javascript
"use strict";
(() => {
  const MODULE_GROUPS = [
    { name: "Operation", accent: "cyan", modules: [
      { name: "Catalog", id: "0003_6200", icon: "CA" },
      { name: "OC List", id: "0004_0050_0020", icon: "OC" },
      { name: "Sample List", id: "0004_0056_4070", icon: "SL" },
      { name: "Sale ASN", id: "0004_0070_0020", icon: "AS" },
      { name: "RMPO List", id: "0005_0050_0020", icon: "RM" },
      { name: "Indent List", id: "0005_0080_0020", icon: "IN" },
      { name: "QA List", id: "0063_0030_0020", icon: "QA" },
    ]},
    { name: "Finance", accent: "violet", modules: [
      { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR" },
      { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI" },
      { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI" },
    ]},
    { name: "Admin", accent: "amber", modules: [
      { name: "Org Structure", id: "0090_0001", icon: "OR" },
      { name: "System Coding", id: "0090_0250", icon: "SC" },
      { name: "Company Setup", id: "0090_0007", icon: "CO" },
      { name: "Buyer List", id: "0004_0010_1720", icon: "BU" },
      { name: "Supplier List", id: "0005_0010_1290", icon: "SU" },
    ]},
  ];

  const $ = (sel) => document.querySelector(sel);
  const api = () => (window.pywebview && window.pywebview.api) || null;
  let busy = false;

  function buildModules() {
    $(".module-list").innerHTML = MODULE_GROUPS.map((group) => `
      <section class="module-group" data-group="${group.name}">
        <div class="group-heading"><span class="group-accent accent-${group.accent}"></span><span>${group.name}</span><span class="group-count">${group.modules.length}</span></div>
        <div class="module-grid">${group.modules.map((m) => `
          <button class="module-button" type="button" data-module-id="${m.id}" data-search="${m.name.toLowerCase()} ${group.name.toLowerCase()}">
            <span class="module-icon accent-${group.accent}">${m.icon}</span>
            <span class="module-name">${m.name}</span>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
          </button>`).join("")}</div>
      </section>`).join("");
  }

  function setBusy(value) {
    busy = value;
    document.body.classList.toggle("is-busy", value);
    document.querySelectorAll("button, select, input").forEach((el) => {
      if (el.closest(".settings-overlay")) return;
      el.disabled = value;
    });
  }
  window.wfxSetBusy = setBusy;

  function setStatus(tone, label) {
    const status = $(".footer-status");
    status.dataset.tone = tone || "neutral";
    $(".footer-status-text").textContent = label || "";
  }
  window.wfxSetStatus = setStatus;

  function pushLog(line) {
    const pre = $(".catalog-log");
    const current = pre.textContent === "Chưa có nhật ký hệ thống." ? "" : pre.textContent;
    pre.textContent = (current ? current + "\n" : "") + line;
    pre.scrollTop = pre.scrollHeight;
    if (/(?:ERROR|FAILED|TIMEOUT)/i.test(line) && !$(".log-overlay").classList.contains("open")) {
      $(".log-button").classList.add("has-alert");
    }
  }
  window.wfxPushLog = pushLog;

  function applyTheme(theme) {
    const value = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = value;
    document.querySelectorAll(".seg-button").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.themeChoice === value)));
  }
  window.wfxApplyTheme = applyTheme;

  function setAccount(userId) { $(".user-input").value = userId || ""; }
  window.wfxSetAccount = setAccount;

  function handleResult(result) {
    if (!result) return;
    setStatus(result.ok ? "success" : "error", result.message || "");
    if (result.user_id !== undefined) setAccount(result.user_id);
  }

  async function call(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng"); return;
    }
    setBusy(true);
    setStatus("neutral", "Đang xử lý...");
    try {
      handleResult(await bridge[method](...args));
    } catch (error) {
      setStatus("error", String(error));
    } finally {
      setBusy(false);
    }
  }

  const catalogActions = {
    "prepare": () => call("prepare_catalog", $(".catalog-category").value),
    "code-find": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), null),
    "code-costsheet": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), "costsheet"),
    "code-bom": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), "bom"),
    "buyer-find": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), null),
    "buyer-costsheet": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), "costsheet"),
    "buyer-bom": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), "bom"),
  };

  function filterModules(query) {
    const q = query.trim().toLowerCase();
    let visibleTotal = 0;
    document.querySelectorAll(".module-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".module-button").forEach((btn) => {
        const match = !q || btn.dataset.search.includes(q);
        btn.hidden = !match;
        if (match) visible += 1;
      });
      group.hidden = visible === 0;
      visibleTotal += visible;
    });
    $(".empty-state").hidden = visibleTotal !== 0;
  }

  function bind() {
    document.querySelectorAll("[data-catalog-action]").forEach((btn) =>
      btn.addEventListener("click", () => catalogActions[btn.dataset.catalogAction]?.()));
    $(".module-list").addEventListener("click", (event) => {
      const btn = event.target.closest(".module-button");
      if (btn) call("open_module", btn.dataset.moduleId);
    });
    $(".catalog-code").addEventListener("keydown", (e) => { if (e.key === "Enter") catalogActions["code-find"](); });
    $(".catalog-buyer-reference").addEventListener("keydown", (e) => { if (e.key === "Enter") catalogActions["buyer-find"](); });
    $(".search-box input").addEventListener("input", (e) => filterModules(e.target.value));

    $(".settings-button").addEventListener("click", () => $(".settings-overlay:not(.log-overlay)").classList.add("open"));
    $(".settings-close-button").addEventListener("click", () => $(".settings-overlay:not(.log-overlay)").classList.remove("open"));
    $(".log-button").addEventListener("click", () => { $(".log-overlay").classList.add("open"); $(".log-button").classList.remove("has-alert"); });
    $(".log-close-button").addEventListener("click", () => $(".log-overlay").classList.remove("open"));
    $(".close-button").addEventListener("click", () => api()?.hide_panel?.());

    $(".toggle-password").addEventListener("click", () => {
      const input = $(".password-input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      $(".toggle-password").textContent = show ? "Ẩn" : "Hiện";
    });
    $(".save-button").addEventListener("click", async () => {
      await call("save_account", $(".user-input").value.trim(), $(".password-input").value);
      $(".settings-overlay:not(.log-overlay)").classList.remove("open");
      call("login");
    });
    $(".close-module-input").addEventListener("change", (e) => api()?.set_close_after_module?.(e.target.checked));
    document.querySelectorAll(".seg-button").forEach((btn) =>
      btn.addEventListener("click", () => { applyTheme(btn.dataset.themeChoice); api()?.set_theme?.(btn.dataset.themeChoice); }));
    $(".catalog-log-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText($(".catalog-log").textContent); setStatus("success", "Đã sao chép log"); }
      catch { setStatus("error", "Không sao chép được"); }
    });
  }

  window.wfxBootstrap = (state) => {
    if (!state) return;
    setAccount(state.user_id);
    applyTheme(state.theme);
    $(".close-module-input").checked = state.close_after_module !== false;
    if (state.hotkey_label) { $(".hotkey-label").textContent = state.hotkey_label; $(".hotkey-button").textContent = state.hotkey_label; }
    (state.logs || []).forEach(pushLog);
  };

  function init() {
    buildModules();
    bind();
    const ready = () => api()?.get_initial_state?.().then(window.wfxBootstrap);
    if (api()) ready();
    else window.addEventListener("pywebviewready", ready);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
```

- [ ] **Step 2: Write the smoke test**

Create `tests/test_panel_js.py`:

```python
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "wfx_panel" / "ui" / "panel.js").read_text(encoding="utf-8")


def test_exposes_python_callable_globals():
    for name in ["wfxPushLog", "wfxSetStatus", "wfxSetBusy", "wfxApplyTheme", "wfxBootstrap"]:
        assert f"window.{name}" in JS


def test_wires_all_catalog_actions():
    for action in ["prepare", "code-find", "code-costsheet", "code-bom",
                   "buyer-find", "buyer-costsheet", "buyer-bom"]:
        assert f'"{action}"' in JS


def test_module_groups_present():
    assert JS.count("accent:") == 3
    assert "0003_6200" in JS and "0090_0250" in JS
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_panel_js.py -v`
Expected: PASS (3 passed).

- [ ] **Step 4: Commit**

```bash
git add wfx_panel/ui/panel.js tests/test_panel_js.py
git commit -m "feat(panel): panel.js render + api wiring"
```

---

## Task 7: App icon (W logo)

**Files:**
- Create: `wfx_panel/assets/generate_icon.py`, `wfx_panel/assets/wfx.ico`, `tests/test_icon.py`

**Interfaces:**
- Consumes: Pillow.
- Produces: `wfx_panel/assets/wfx.ico` (multi-size ICO) used by window/tray/exe; and
  `wfx_panel.assets.generate_icon.build_icon(path: Path) -> Path`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_icon.py`:

```python
from pathlib import Path

from PIL import Image

from wfx_panel.assets.generate_icon import build_icon


def test_build_icon_creates_valid_ico(tmp_path: Path):
    out = build_icon(tmp_path / "wfx.ico")
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "ICO"
```

Also create empty `wfx_panel/assets/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_icon.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `wfx_panel/assets/generate_icon.py`**

Draw the extension's W-in-hexagon mark with Pillow (brand gradient approximated by a solid indigo hex + white W stroke):

```python
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Toạ độ chuẩn hoá theo SVG gốc (viewBox 0 0 28 28) của extension.
_HEX = [(5.2, 6.7), (14, 2.4), (22.8, 6.7), (22.8, 17.3), (14, 25.6), (5.2, 17.3)]
_W = [(8.6, 9.2), (11.2, 18.4), (14.0, 12.2), (16.8, 18.4), (19.4, 9.2)]
_BG = (99, 102, 241)      # indigo-500
_MARK = (255, 255, 255)


def _scaled(points, size):
    factor = size / 28.0
    return [(x * factor, y * factor) for x, y in points]


def build_icon(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    master = 256
    image = Image.new("RGBA", (master, master), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(_scaled(_HEX, master), fill=_BG)
    draw.line(_scaled(_W, master), fill=_MARK, width=max(2, master // 14), joint="curve")
    image.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    out = build_icon(Path(__file__).with_name("wfx.ico"))
    print(f"Wrote {out}")
```

- [ ] **Step 4: Generate the committed icon + run test**

Run:
```bash
python wfx_panel/assets/generate_icon.py
python -m pytest tests/test_icon.py -v
```
Expected: writes `wfx_panel/assets/wfx.ico`; test PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add wfx_panel/assets/__init__.py wfx_panel/assets/generate_icon.py wfx_panel/assets/wfx.ico tests/test_icon.py
git commit -m "feat(panel): generate W-logo app icon"
```

---

## Task 8: panel_app.py — window + hotkey + tray + auto-login

**Files:**
- Create: `wfx_panel/panel_app.py`
- Modify: `README.md` (mục "Chạy floating panel" + "Đóng gói exe")

**Interfaces:**
- Consumes: `webview`, `keyboard`, `pystray`, `PIL.Image`, `wfx_panel.panel_api.PanelAPI`,
  `wfx_panel.prefs`.
- Produces: `wfx_panel.panel_app.main()` entrypoint; adds `PanelAPI.hide_panel()` /
  `PanelAPI.show_panel()` used by JS close-button (extends Task 4 class at runtime via
  bound window — see Step 1).

> **Verification for this task is manual** (GUI + global hotkey + tray can't be unit-tested headless). Each step says exactly what to observe.

- [ ] **Step 1: Implement `wfx_panel/panel_app.py`**

```python
from __future__ import annotations

import threading

import keyboard
import pystray
import webview
from PIL import Image

from wfx_panel import prefs
from wfx_panel.assets.generate_icon import build_icon
from wfx_panel.panel_api import PanelAPI

HOTKEY = "ctrl+shift+x"
ICON_PATH = prefs.APP_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.APP_DIR / "wfx_panel" / "ui" / "index.html"


class PanelApp:
    def __init__(self):
        self.api = PanelAPI()
        self.window = None
        self.tray = None
        self._visible = True

    # -- window bridge -----------------------------------------------------
    def _push_log(self, line: str) -> None:
        if self.window is None:
            return
        from wfx_panel.log_bridge import js_string
        try:
            self.window.evaluate_js(f"window.wfxPushLog({js_string(line)})")
        except Exception:
            pass

    def hide_panel(self):
        if self.window and self._visible:
            self.window.hide()
            self._visible = False

    def show_panel(self):
        if self.window and not self._visible:
            self.window.show()
            self._visible = True

    def toggle(self):
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    # -- lifecycle ---------------------------------------------------------
    def on_loaded(self):
        # Chạy nền: bơm trạng thái ban đầu + auto-login, không chặn UI.
        threading.Thread(target=self._startup, daemon=True).start()

    def _startup(self):
        try:
            state = self.api.get_initial_state()
            from wfx_panel.log_bridge import js_string
            import json
            self.window.evaluate_js(f"window.wfxBootstrap({json.dumps(state, ensure_ascii=False)})")
            account = prefs.load_account()
            if account["user_id"] and account["password"]:
                self._push_log("[SESSION] Tự động đăng nhập...")
                result = self.api.login()
            else:
                result = self.api.check_session()
            tone = "success" if result.get("ok") else "warning"
            self.window.evaluate_js(
                f"window.wfxSetStatus({js_string(tone)}, {js_string(result.get('message',''))})"
            )
        except Exception as error:  # startup không được làm sập app
            self._push_log(f"[ERROR] Startup lỗi: {error}")

    def _build_tray(self):
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Hiện panel", lambda: self.show_panel(), default=True),
            pystray.MenuItem("Thoát", lambda: self.quit()),
        )
        self.tray = pystray.Icon("wfx-panel", image, "WFX Smart Panel", menu)
        self.tray.run()  # blocking → chạy trong thread riêng

    def quit(self):
        try:
            keyboard.remove_hotkey(HOTKEY)
        except (KeyError, ValueError):
            pass
        if self.tray:
            self.tray.stop()
        if self.window:
            self.window.destroy()

    def run(self):
        if not ICON_PATH.exists():
            build_icon(ICON_PATH)
        # js_api expose các method của PanelAPI + hide/show cho nút close.
        self.api.hide_panel = self.hide_panel   # type: ignore[attr-defined]
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
        self.api.set_log_sink(self._push_log)
        self.window = webview.create_window(
            "WFX Smart",
            url=str(UI_INDEX),
            js_api=self.api,
            width=440,
            height=620,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color="#0b1020",
        )
        self.window.events.loaded += self.on_loaded

        def background():
            try:
                keyboard.add_hotkey(HOTKEY, self.toggle)
            except Exception as error:
                self._push_log(f"[ERROR] Không đăng ký được hotkey: {error}")
            self._build_tray()

        webview.start(background, private_mode=False)


def main():
    PanelApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Install deps and generate icon**

Run:
```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python wfx_panel/assets/generate_icon.py
```
Expected: installs pywebview/keyboard/pystray/Pillow; icon written.

- [ ] **Step 3: Manual smoke — window + UI**

Run:
```bash
python -m wfx_panel.panel_app
```
Observe: a frameless always-on-top window (~440×620) shows the panel — brand W, Catalog Control, module groups with cyan/violet/amber icons, footer status. Confirm it visually matches the extension panel. Dragging the header moves the window.

- [ ] **Step 4: Manual smoke — hotkey + tray**

With the app running and Chrome focused, press `Ctrl+Shift+X`: the panel hides; press again: it shows. Click the panel's ✕ (close) button: it hides to tray. Find the W tray icon → "Hiện panel" shows it again; "Thoát" exits the process cleanly.

- [ ] **Step 5: Manual smoke — automation path**

In Settings, enter WFX User ID/Password → Save: it logs in (footer turns success). Click a module (e.g. OC List) → WFX automation opens it. Select Apparel + a Code → Tìm; try Costsheet/BOM. Toggle theme sáng/tối. Confirm logs stream into the log overlay and "Sao chép log" works.

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests from Tasks 1–7 PASS.

- [ ] **Step 7: Update README + commit**

Add to `README.md` a section:

```markdown
## WFX Floating Panel (Python, thay extension)

Chạy dev:
    python -m pip install -r requirements-dev.txt
    python -m playwright install chromium
    python -m wfx_panel.panel_app

- Hotkey toàn cục Ctrl+Shift+X: ẩn/hiện panel (kể cả khi focus ở Chrome).
- Nút đóng hoặc hotkey thu panel về system tray; tray có "Hiện panel" / "Thoát".
- Tài khoản lưu ở `.env`; theme/tuỳ chọn ở `prefs.json`.
- App cũ `app.py` (tkinter) vẫn giữ làm dự phòng.
```

Commit:
```bash
git add wfx_panel/panel_app.py README.md
git commit -m "feat(panel): pywebview window with global hotkey + system tray"
```

---

## Task 9: Package to .exe (PyInstaller)

**Files:**
- Create: `wfx_panel/wfx-panel.spec`, `build-panel.ps1`
- Modify: `README.md` (mục "Đóng gói exe")

**Interfaces:**
- Consumes: PyInstaller; all prior tasks.
- Produces: `dist/WFX-Panel/WFX-Panel.exe` (onedir).

> **Verification is manual** (build + launch on Windows).

- [ ] **Step 1: Create `wfx_panel/wfx-panel.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path.cwd()
a = Analysis(
    ["wfx_panel/panel_app.py"],
    pathex=[str(project)],
    binaries=[],
    datas=[
        ("wfx_panel/ui", "wfx_panel/ui"),
        ("wfx_panel/assets/wfx.ico", "wfx_panel/assets"),
    ],
    hiddenimports=["login", "pystray._win32", "keyboard"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WFX-Panel",
          console=False, icon="wfx_panel/assets/wfx.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="WFX-Panel")
```

Note: `login.py` sits at repo root and is imported by name; keep it beside the build (hiddenimport `login` + running PyInstaller from repo root covers it).

- [ ] **Step 2: Create `build-panel.ps1`**

```powershell
python -m pip install -r requirements-dev.txt
python wfx_panel/assets/generate_icon.py
python -m PyInstaller --noconfirm --clean wfx_panel/wfx-panel.spec
Write-Host "Build xong: dist/WFX-Panel/WFX-Panel.exe"
```

- [ ] **Step 3: Manual build + launch**

Run:
```bash
powershell -ExecutionPolicy Bypass -File build-panel.ps1
```
Then launch `dist/WFX-Panel/WFX-Panel.exe`. Observe the same behavior as Task 8 Steps 3–5: panel shows, hotkey toggles, tray works, automation runs. (WebView2 runtime is present by default on Windows 11.)

- [ ] **Step 4: Update README + commit**

Append to `README.md`:

```markdown
## Đóng gói exe

    powershell -ExecutionPolicy Bypass -File build-panel.ps1

Kết quả: `dist/WFX-Panel/WFX-Panel.exe` (onedir). Cần WebView2 Runtime (mặc định có trên
Windows 11). Không bundle Chromium — automation dùng Chrome hệ thống qua CDP như `login.py`.
```

Commit:
```bash
git add wfx_panel/wfx-panel.spec build-panel.ps1 README.md
git commit -m "build(panel): PyInstaller onedir exe packaging"
```

---

## Self-Review Notes

- **Spec coverage:** UI reuse (T5/T6), logo W (T7), always-on-top frameless (T8), Ctrl+Shift+X global (T8), tray hide (T8), PanelAPI→login.py all methods incl. Costsheet/BOM (T4), prefs/account (T1), friendly-ish log stream + copy (T2/T6/T8), theme (T1/T4/T6), exe packaging (T9), login.py unchanged & app.py kept (Global Constraints). All spec sections map to a task.
- **Types consistent:** `PanelAPI` method names in T4 match calls in `panel.js` (T6) and `evaluate_js` globals in T8. `build_icon` signature identical in T7 def and use in T8/T9. `prefs` function signatures consistent across T1/T4/T8.
- **v1 limitation (explicit):** hotkey is fixed `Ctrl+Shift+X`; the Settings hotkey button is disabled (rebinding is out of scope, noted in HTML copy and README).
```
