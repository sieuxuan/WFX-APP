"""Kiểm thử luồng đăng nhập WFX: từ lớp automation tới bảng điều khiển.

Nửa đầu phủ ``automation/session.py`` — đăng nhập, phiên, Division,
quyền module và danh tính chủ phiên. Nửa sau đi theo đúng thứ tự người
dùng bấm: lưu tài khoản, đăng nhập, màn tổng quan, rồi các công tắc
trong Cài đặt. Nhóm cuối khẳng định tĩnh trên panel.js cho các lỗi chỉ
lộ ra ở lớp giao diện.
"""

from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

from wfx_panel import constants, panel_api, prefs, secret
from wfx_panel.automation import session
from wfx_panel.controllers import settings as settings_controller
from wfx_panel.panel_api import PanelAPI


class FakeLocator:
    """Locator tối giản đủ cho các thao tác session.py thật sự dùng."""

    def __init__(self, page, selector, *, count=1, visible=True, value=""):
        self.page = page
        self.selector = selector
        self._count = count
        self._visible = visible
        self._value = value

    # -- truy vấn -------------------------------------------------------
    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible

    def input_value(self, timeout=None):
        return self._value

    def inner_text(self, timeout=None):
        return self._value

    def get_attribute(self, name):
        return self._value if name == "title" else None

    # -- hành động ------------------------------------------------------
    def wait_for(self, state=None, timeout=None):
        self.page.actions.append(("wait_for", self.selector, state))

    def fill(self, value):
        self.page.actions.append(("fill", self.selector, value))
        self._value = value

    def click(self, timeout=None):
        self.page.actions.append(("click", self.selector))

    def evaluate(self, script, *args):
        self.page.actions.append(("evaluate", self.selector))
        return None

    def select_option(self, **kwargs):  # pragma: no cover - không dùng ở đây
        raise AssertionError("session.py không được select_option trực tiếp")


class FakePage:
    def __init__(self, *, locators=None, url="https://wfx.test/wfx/default.aspx"):
        self.url = url
        self.actions: list[tuple] = []
        self.frames: list = []
        self._locators = dict(locators or {})
        self.screenshots: list[str] = []

    def goto(self, url, wait_until=None, timeout=None):
        self.actions.append(("goto", url))
        self.url = url

    def locator(self, selector):
        spec = self._locators.get(selector, {})
        return FakeLocator(self, selector, **spec)

    def frame(self, name=None):  # pragma: no cover - không dùng ở đây
        return None

    def screenshot(self, path=None, full_page=False):
        self.screenshots.append(str(path))
        with open(path, "wb") as handle:
            handle.write(b"png")

    def wait_for_timeout(self, ms):
        self.actions.append(("wait", ms))


class FakeFrame:
    def __init__(self, name, url="", locators=None):
        self.name = name
        self.url = url
        self.page = FakePage()
        self._locators = dict(locators or {})

    def locator(self, selector):
        if selector not in self._locators:
            return FakeLocator(self.page, selector, count=0, visible=False)
        return FakeLocator(self.page, selector, **self._locators[selector])


@pytest.fixture
def playwright_stub(monkeypatch):
    """Thay sync_playwright bằng stub và khẳng định luôn được stop()."""
    stopped: list[bool] = []

    def install(page):
        monkeypatch.setattr(
            session,
            "sync_playwright",
            lambda: types.SimpleNamespace(
                start=lambda: types.SimpleNamespace(
                    stop=lambda: stopped.append(True)
                )
            ),
        )
        monkeypatch.setattr(
            session,
            "_connect_to_chrome",
            lambda _pw, **kwargs: (object(), page),
        )
        monkeypatch.setattr(session, "_attach_dialog_handler", lambda *_a: None)
        monkeypatch.setattr(session, "_start_persistent_chrome", lambda _log: None)
        monkeypatch.setattr(session, "_chrome_is_ready", lambda: True)
        return stopped

    return install


# ======================================================================
# login(): chuỗi điền form
# ======================================================================


def test_login_fills_the_wfx_form_in_the_exact_order():
    page = FakePage(
        locators={
            "#txtUserID": {},
            "#txtCompany": {},
            "#txtPassword": {},
            "#btlLogin[value='Next']": {},
            "#btlLogin[value='Log In']": {},
            f"xpath={session.CATALOG_XPATH}": {},
        }
    )

    session.login(page, "userA", "secretA", "psh")

    assert page.actions[0] == ("goto", session.URL)
    filled = [item for item in page.actions if item[0] == "fill"]
    assert filled == [
        ("fill", "#txtUserID", "userA"),
        ("fill", "#txtCompany", "psh"),
        ("fill", "#txtPassword", "secretA"),
    ]
    clicked = [item[1] for item in page.actions if item[0] == "click"]
    assert clicked == [
        "#btlLogin[value='Next']",
        "#btlLogin[value='Log In']",
    ]
    # Điều kiện xác nhận đăng nhập là menu Catalog phổ thông, không phải một
    # menu Admin mà tài khoản thường không được cấp.
    assert (
        "wait_for",
        f"xpath={session.CATALOG_XPATH}",
        "attached",
    ) in page.actions


def test_login_waits_for_the_password_field_before_typing():
    page = FakePage(
        locators={
            "#txtUserID": {},
            "#txtCompany": {},
            "#txtPassword": {},
            "#btlLogin[value='Next']": {},
            "#btlLogin[value='Log In']": {},
            f"xpath={session.CATALOG_XPATH}": {},
        }
    )

    session.login(page, "userA", "secretA")

    order = [item for item in page.actions if item[1] == "#txtPassword"]
    assert order[0][0] == "wait_for"
    assert order[1][0] == "fill"


# ======================================================================
# run(): danh tính phiên
# ======================================================================


def _prepare_run(monkeypatch, playwright_stub, page, auth_surface):
    stopped = playwright_stub(page)
    monkeypatch.setattr(
        session, "_wait_for_auth_surface", lambda *_a: auth_surface
    )
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: session._division_state_for_page_placeholder(),
    )
    return stopped


def test_run_reuses_a_session_owned_by_the_same_user(
    monkeypatch, playwright_stub
):
    page = FakePage()
    stopped = _prepare_run(monkeypatch, playwright_stub, page, "session")
    monkeypatch.setattr(
        session, "login", lambda *a, **k: pytest.fail("không được login lại")
    )

    result = session.run(
        "userA", "secretA", log=lambda _line: None, session_owner="USERA"
    )

    assert result["code"] == "SESSION_REUSED"
    assert result["session_user_id"] == "USERA"
    assert stopped == [True]


def test_run_relogs_when_the_browser_holds_another_account(
    monkeypatch, playwright_stub
):
    """Đây là lỗi 'Đổi tài khoản không đổi được tài khoản'."""
    page = FakePage()
    _prepare_run(monkeypatch, playwright_stub, page, "session")
    monkeypatch.setattr(session, "_reopen_login_form", lambda *_a: True)
    logged: list[tuple] = []
    monkeypatch.setattr(
        session, "login", lambda _page, *args: logged.append(args)
    )

    result = session.run(
        "userB", "secretB", log=lambda _line: None, session_owner="userA"
    )

    assert result["code"] == "LOGGED_IN"
    assert result["session_user_id"] == "userB"
    assert logged == [("userB", "secretB", "psh")]


def test_run_refuses_to_work_as_the_wrong_user_when_wfx_keeps_the_session(
    monkeypatch, playwright_stub
):
    page = FakePage()
    _prepare_run(monkeypatch, playwright_stub, page, "session")
    monkeypatch.setattr(session, "_reopen_login_form", lambda *_a: False)
    monkeypatch.setattr(
        session, "login", lambda *a, **k: pytest.fail("không được login")
    )

    result = session.run(
        "userB", "secretB", log=lambda _line: None, session_owner="userA"
    )

    assert result["ok"] is False
    assert result["code"] == "SESSION_USER_MISMATCH"
    assert result["session_user_id"] == "userA"


def test_run_without_a_known_owner_keeps_reusing_the_session(
    monkeypatch, playwright_stub
):
    page = FakePage()
    _prepare_run(monkeypatch, playwright_stub, page, "session")

    result = session.run("userB", "secretB", log=lambda _line: None)

    assert result["code"] == "SESSION_REUSED"
    assert result["session_user_id"] is None


def test_run_reports_missing_credentials_before_touching_the_form(
    monkeypatch, playwright_stub
):
    page = FakePage()
    _prepare_run(monkeypatch, playwright_stub, page, "login")
    monkeypatch.delenv("WFX_USER_ID", raising=False)
    monkeypatch.delenv("WFX_PASSWORD", raising=False)
    monkeypatch.setattr(
        session, "login", lambda *a, **k: pytest.fail("không được login")
    )

    result = session.run("", "", log=lambda _line: None)

    assert result["code"] == "MISSING_CREDENTIALS"


def test_run_records_the_new_owner_after_a_normal_login(
    monkeypatch, playwright_stub
):
    page = FakePage()
    _prepare_run(monkeypatch, playwright_stub, page, "login")
    monkeypatch.setattr(session, "login", lambda *a, **k: None)

    result = session.run("userA", "secretA", log=lambda _line: None)

    assert result["code"] == "LOGGED_IN"
    assert result["session_user_id"] == "userA"


def test_reopen_login_form_returns_false_when_wfx_keeps_the_session(
    monkeypatch,
):
    page = FakePage()
    monkeypatch.setattr(session, "_wait_for_auth_surface", lambda *_a: "session")

    assert session._reopen_login_form(page, lambda _line: None) is False
    assert page.actions[0] == ("goto", session.URL)


def test_reopen_login_form_survives_a_navigation_error(monkeypatch):
    class Broken(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            raise session.PlaywrightError("navigation failed")

    logs: list[str] = []

    assert session._reopen_login_form(Broken(), logs.append) is False
    assert any("đăng nhập" in line for line in logs)


# ======================================================================
# check_session / get_division_state / check_module_access
# ======================================================================


def test_check_session_reports_chrome_closed_without_starting_playwright(
    monkeypatch,
):
    monkeypatch.setattr(session, "_chrome_is_ready", lambda: False)
    monkeypatch.setattr(
        session,
        "sync_playwright",
        lambda: pytest.fail("không được khởi động Playwright"),
    )

    result = session.check_session(log=lambda _line: None)

    assert result["code"] == "CHROME_CLOSED"


def test_check_session_never_activates_the_wfx_tab(
    monkeypatch, playwright_stub
):
    """Keepalive chạy mỗi bốn phút; kéo tab WFX lên là cướp màn hình của user."""
    page = FakePage()
    playwright_stub(page)
    seen: list[dict] = []

    def connect(_pw, **kwargs):
        seen.append(kwargs)
        return object(), page

    monkeypatch.setattr(session, "_connect_to_chrome", connect)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: {
            "current_division": "woven",
            "division_label": "WOVEN",
            "division_name": "PRO SPORTS - WOVEN HANOI",
        },
    )

    result = session.check_session(log=lambda _line: None)

    assert result["code"] == "SESSION_ACTIVE"
    assert result["division_label"] == "WOVEN"
    assert seen == [{"bring_to_front": False}]


def test_check_session_reports_a_lost_session(monkeypatch, playwright_stub):
    page = FakePage()
    stopped = playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: False)

    result = session.check_session(log=lambda _line: None)

    assert result["code"] == "NOT_LOGGED_IN"
    assert stopped == [True]


def test_check_session_wraps_unexpected_errors(monkeypatch, playwright_stub):
    page = FakePage()
    playwright_stub(page)
    monkeypatch.setattr(
        session,
        "_session_is_active",
        lambda _p: (_ for _ in ()).throw(RuntimeError("cdp gone")),
    )

    result = session.check_session(log=lambda _line: None)

    assert result["code"] == "SESSION_CHECK_FAILED"
    assert "RuntimeError" in result["message"]


def test_get_division_state_reads_without_navigating(
    monkeypatch, playwright_stub
):
    page = FakePage()
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: {
            "current_division": "knit",
            "division_label": "KNIT",
            "division_name": "PRO SPORTS - KNIT",
        },
    )

    result = session.get_division_state(log=lambda _line: None)

    assert result["code"] == "DIVISION_DETECTED"
    assert result["current_division"] == "knit"
    assert not [item for item in page.actions if item[0] == "goto"]


def test_get_division_state_requires_a_session(monkeypatch, playwright_stub):
    playwright_stub(FakePage())
    monkeypatch.setattr(session, "_session_is_active", lambda _p: False)

    result = session.get_division_state(log=lambda _line: None)

    assert result["code"] == "NOT_LOGGED_IN"
    assert result["current_division"] is None


def test_check_module_access_only_reads_menu_anchors(
    monkeypatch, playwright_stub
):
    page = FakePage(
        locators={
            "xpath=//*[@id='granted']/a": {"count": 1},
            "xpath=//*[@id='denied']/a": {"count": 0},
        }
    )
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)

    result = session.check_module_access(
        [
            {"id": "granted", "xpath": "//*[@id='granted']/a"},
            {"id": "denied", "xpath": "//*[@id='denied']/a"},
            {"id": "", "xpath": ""},
        ],
        log=lambda _line: None,
    )

    assert result["code"] == "MODULE_ACCESS_CHECKED"
    assert result["accessible_module_ids"] == ["granted"]
    assert not [item for item in page.actions if item[0] == "click"]


def test_check_module_access_without_a_session(monkeypatch, playwright_stub):
    playwright_stub(FakePage())
    monkeypatch.setattr(session, "_session_is_active", lambda _p: False)

    result = session.check_module_access([], log=lambda _line: None)

    assert result["code"] == "NOT_LOGGED_IN"
    assert result["accessible_module_ids"] == []


def test_capture_failure_screenshot_writes_next_to_the_run(
    tmp_path, monkeypatch, playwright_stub
):
    page = FakePage()
    playwright_stub(page)
    target = tmp_path / "shots" / "run.png"

    assert session.capture_failure_screenshot(target, lambda _line: None) is True
    assert target.is_file()


def test_capture_failure_screenshot_is_silent_without_chrome(monkeypatch):
    monkeypatch.setattr(session, "_chrome_is_ready", lambda: False)

    assert session.capture_failure_screenshot("x.png", lambda _l: None) is False


# ======================================================================
# switch_division
# ======================================================================


def _division_page(bookmark_found=True):
    target = session.DIVISIONS["knit"]
    selector = (
        'a.hasbookmark[href*="ChangeBaseSetting=1"]'
        f'[href*="MemberCompanyCode={target["member_company_code"]}"]'
        f'[href*="folderID={target["folder_id"]}"]'
    )
    frame = FakeFrame(
        "body",
        locators={selector: {"count": 1 if bookmark_found else 0}},
    )
    page = FakePage()
    page.frames = [frame]
    return page, selector


def test_switch_division_rejects_an_unknown_key():
    result = session.switch_division("khong-co", log=lambda _line: None)

    assert result["code"] == "DIVISION_UNKNOWN"


def test_switch_division_returns_early_when_already_active(
    monkeypatch, playwright_stub
):
    page, _ = _division_page()
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: {
            "current_division": "knit",
            "division_label": "KNIT",
            "division_name": "PRO SPORTS - KNIT",
        },
    )

    result = session.switch_division("knit", log=lambda _line: None)

    assert result["code"] == "DIVISION_ALREADY_ACTIVE"


def test_switch_division_clicks_the_exact_bookmark(
    monkeypatch, playwright_stub
):
    page, selector = _division_page()
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)
    states = iter(
        [
            {
                "current_division": "woven",
                "division_label": "WOVEN",
                "division_name": "W",
            },
            {
                "current_division": "knit",
                "division_label": "KNIT",
                "division_name": "PRO SPORTS - KNIT",
            },
        ]
    )
    monkeypatch.setattr(
        session, "_division_state_for_page", lambda _p: next(states)
    )
    monkeypatch.setattr(session, "_wait", lambda *_a: None)

    result = session.switch_division("knit", log=lambda _line: None)

    assert result["code"] == "DIVISION_CHANGED"
    assert result["current_division"] == "knit"
    assert ("evaluate", selector) in page.frames[0].page.actions


def test_switch_division_reports_a_missing_bookmark(
    monkeypatch, playwright_stub
):
    page, _ = _division_page(bookmark_found=False)
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: True)
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: session._division_state_for_page_placeholder(),
    )

    result = session.switch_division("knit", log=lambda _line: None)

    assert result["code"] == "DIVISION_OPTION_NOT_FOUND"


def test_switch_division_requires_a_session(monkeypatch, playwright_stub):
    page, _ = _division_page()
    playwright_stub(page)
    monkeypatch.setattr(session, "_session_is_active", lambda _p: False)

    result = session.switch_division("knit", log=lambda _line: None)

    assert result["code"] == "NOT_LOGGED_IN"


UI = Path(panel_api.__file__).resolve().parent / "ui"
PANEL_JS = (UI / "panel.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_credential_env(monkeypatch):
    monkeypatch.delenv("WFX_USER_ID", raising=False)
    monkeypatch.delenv("WFX_PASSWORD", raising=False)


class FakeLogin:
    """Login module giả lập, ghi lại mọi lời gọi để khẳng định thứ tự flow."""

    COMPANY_ID = "psh"

    def __init__(self, *, session_alive=False, admin_modules=None):
        self.calls: list[tuple] = []
        self.session_alive = session_alive
        self.admin_modules = list(admin_modules or [])
        self.run_results: list[dict] | None = None
        self.action_results: list[dict] = []
        self.chrome_result = {
            "ok": True,
            "code": "CHROME_OPENED",
            "message": "opened",
            "chrome_alive": True,
            "browser_name": "Chrome",
        }

    # -- login ---------------------------------------------------------
    def run(self, user_id, password, company_id="psh", log=print):
        self.calls.append(("run", user_id, password))
        if self.run_results:
            return self.run_results.pop(0)
        self.session_alive = True
        return {
            "ok": True,
            "code": "LOGGED_IN",
            "message": "Đăng nhập thành công.",
            "current_division": "woven",
            "division_label": "WOVEN",
            "division_name": "PRO SPORTS - WOVEN HANOI",
        }

    def check_session(self, log=print):
        self.calls.append(("check_session",))
        if self.session_alive:
            return {
                "ok": True,
                "code": "SESSION_ACTIVE",
                "message": "Đã kết nối phiên WFX đang mở.",
                "current_division": "woven",
                "division_label": "WOVEN",
                "division_name": "PRO SPORTS - WOVEN HANOI",
            }
        return {
            "ok": False,
            "code": "NOT_LOGGED_IN",
            "message": "Chưa có phiên WFX đăng nhập.",
        }

    def start_chrome(self, log=print):
        self.calls.append(("start_chrome",))
        return dict(self.chrome_result)

    def browser_status(self):
        return {
            "chrome_alive": True,
            "browser_available": True,
            "browser_name": "Chrome",
        }

    def check_module_access(self, specs, log=print):
        self.calls.append(("check_module_access",))
        return {
            "ok": True,
            "code": "MODULE_ACCESS_CHECKED",
            "accessible_module_ids": list(self.admin_modules),
        }

    def switch_division(self, key, log=print):
        self.calls.append(("switch_division", key))
        division = constants.DIVISIONS[key]
        return {
            "ok": True,
            "code": "DIVISION_CHANGED",
            "message": f"Đã chuyển sang Division {division['label']}.",
            "current_division": key,
            "division_label": division["label"],
            "division_name": division["name"],
        }

    def capture_failure_screenshot(self, path, log=print):
        return False


def make_api(tmp_path, login=None, **account):
    login = login or FakeLogin()
    if account:
        prefs.save_account(
            account.get("user_id", "userA"),
            account.get("password", "secretA"),
            base_dir=tmp_path,
        )
    return PanelAPI(login, prefs, tmp_path), login


def collect_results(api):
    seen: list[tuple[str, dict]] = []
    api.set_result_sink(lambda method, result, elapsed: seen.append((method, result)))
    return seen


# ======================================================================
# A. FLOW ĐĂNG NHẬP
# ======================================================================


def test_flow_a1_save_account_persists_and_encrypts_at_rest(tmp_path):
    api, _ = make_api(tmp_path)

    saved = api.save_account("  userA  ", "secretA")

    assert saved["ok"] and saved["code"] == "ACCOUNT_SAVED"
    assert saved["user_id"] == "userA"
    assert saved["has_credentials"] is True
    account = prefs.load_account(base_dir=tmp_path)
    assert account == {"user_id": "userA", "password": "secretA"}
    raw = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "secretA" not in raw
    if os.name == "nt":
        assert "WFX_PASSWORD_ENC=" in raw
        assert secret.is_protected(
            raw.split("WFX_PASSWORD_ENC=", 1)[1].split("\n")[0].strip('"')
        )


def test_flow_a1b_save_account_keeps_unrelated_env_keys(tmp_path):
    (tmp_path / ".env").write_text(
        'WFX_WEBHOOK_URL="https://n8n.example/hook"\nWFX_USER_ID="old"\n',
        encoding="utf-8",
    )
    api, _ = make_api(tmp_path)

    api.save_account("userA", "secretA")

    raw = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "WFX_WEBHOOK_URL=" in raw
    assert raw.count("WFX_USER_ID=") == 1


def test_flow_a2_blank_password_keeps_stored_one_for_the_same_user(tmp_path):
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")

    saved = api.save_account("  userA  ", "   ")

    assert saved["ok"] is True
    assert prefs.load_account(base_dir=tmp_path) == {
        "user_id": "userA",
        "password": "secretA",
    }


def test_flow_a2b_changing_user_id_requires_its_own_password(tmp_path):
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")

    saved = api.save_account("userB", "")

    assert saved["code"] == "PASSWORD_REQUIRED"
    assert prefs.load_account(base_dir=tmp_path)["user_id"] == "userA"


def test_flow_a3_missing_inputs_are_rejected(tmp_path):
    api, _ = make_api(tmp_path)

    assert api.save_account("", "secret")["code"] == "USER_ID_REQUIRED"
    assert api.save_account("userA", "")["code"] == "PASSWORD_REQUIRED"


def test_flow_a4_login_marks_session_division_and_admin(tmp_path):
    api, login = make_api(
        tmp_path, FakeLogin(admin_modules=list(constants.ADMIN_MODULE_IDS)[:1]),
        user_id="userA", password="secretA",
    )
    seen = collect_results(api)

    result = api.login()

    assert result["ok"] and result["code"] == "LOGGED_IN"
    assert result["session_active"] is True
    assert result["current_division"] == "woven"
    assert result["admin_access"] is True
    assert ("run", "userA", "secretA") in login.calls
    assert seen and seen[0][0] == "login"
    status = api.get_status()
    assert status["session_active"] is True
    assert status["last_login_at"]


def test_flow_a5_login_without_credentials_reports_missing(tmp_path):
    login = FakeLogin()
    login.run_results = [
        {
            "ok": False,
            "code": "MISSING_CREDENTIALS",
            "message": "Chưa lưu User ID và Password trong Settings.",
        }
    ]
    api, _ = make_api(tmp_path, login)

    result = api.login()

    assert result["code"] == "MISSING_CREDENTIALS"
    assert result["session_active"] is False
    assert result["admin_access"] is False


def test_flow_a6_check_session_without_login(tmp_path):
    api, _ = make_api(tmp_path)

    result = api.check_session()

    assert result["code"] == "NOT_LOGGED_IN"
    assert result["session_active"] is False
    assert api.should_maintain_session() is False


def test_flow_a7_heartbeat_is_quiet_when_healthy(tmp_path):
    api, login = make_api(
        tmp_path, FakeLogin(session_alive=True), user_id="userA", password="secretA"
    )
    api.check_session()
    seen = collect_results(api)

    assert api.should_maintain_session() is True
    result = api.maintain_session()

    assert result["code"] == "SESSION_ACTIVE"
    assert seen == []  # không đẩy kết quả -> footer không đổi
    assert not [line for line in api._logs if "maintain_session" in line]


def test_flow_a7b_heartbeat_relogs_expired_session(tmp_path):
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    api.check_session()
    login.session_alive = False

    result = api.maintain_session()

    assert result["code"] == "SESSION_RESTORED"
    assert result["session_active"] is True
    assert ("run", "userA", "secretA") in login.calls


def test_flow_a7c_failed_heartbeat_leaves_one_history_row(tmp_path):
    """Heartbeat nền hỏng thì phải tra lại được, nhưng không ghi khi khỏe."""
    from wfx_panel import job_history

    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    api.check_session()
    api.maintain_session()  # lượt khỏe: im lặng
    assert [
        job for job in job_history.list_jobs(tmp_path, 20)
        if job["method"] == "maintain_session"
    ] == []

    login.session_alive = False
    login.run_results = [
        {"ok": False, "code": "LOGIN_TIMEOUT", "message": "WFX phản hồi chậm."}
    ]
    seen = collect_results(api)

    result = api.maintain_session()

    assert result["code"] == "LOGIN_TIMEOUT"
    assert [method for method, _ in seen] == ["maintain_session"]
    recorded = [
        job for job in job_history.list_jobs(tmp_path, 20)
        if job["method"] == "maintain_session"
    ]
    assert len(recorded) == 1
    assert recorded[0]["code"] == "LOGIN_TIMEOUT"


def test_flow_a8_user_action_relogs_and_retries_once(tmp_path):
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    attempts = []

    def action():
        attempts.append(1)
        if len(attempts) == 1:
            return {"ok": False, "code": "NOT_LOGGED_IN", "message": "hết phiên"}
        return {"ok": True, "code": "MODULE_OPENED", "message": "ok"}

    result = api._run("open_module", action)

    assert result["code"] == "MODULE_OPENED"
    assert len(attempts) == 2
    assert ("run", "userA", "secretA") in login.calls


def test_flow_a8b_relogin_is_attempted_only_once(tmp_path):
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    attempts = []

    def action():
        attempts.append(1)
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "hết phiên"}

    result = api._run("open_module", action)

    assert result["code"] == "NOT_LOGGED_IN"
    assert len(attempts) == 2
    assert [call for call in login.calls if call[0] == "run"] == [
        ("run", "userA", "secretA")
    ]


def test_flow_a9_closed_chrome_is_reopened_then_retried(tmp_path):
    login = FakeLogin()
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    attempts = []

    def action():
        attempts.append(1)
        if len(attempts) == 1:
            return {"ok": False, "code": "CHROME_CLOSED", "message": "đã đóng"}
        return {"ok": True, "code": "MODULE_OPENED", "message": "ok"}

    result = api._run("open_module", action)

    assert result["code"] == "MODULE_OPENED"
    assert [call[0] for call in login.calls][:2] == ["start_chrome", "run"]


def test_flow_a9b_login_itself_never_auto_retries(tmp_path):
    login = FakeLogin()
    login.run_results = [
        {"ok": False, "code": "NOT_LOGGED_IN", "message": "no"},
    ]
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")

    result = api.login()

    assert result["code"] == "NOT_LOGGED_IN"
    assert len([call for call in login.calls if call[0] == "run"]) == 1


def test_flow_a10_concurrent_flow_is_refused_not_queued(tmp_path):
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")
    captured = {}

    def outer():
        captured["inner"] = api._run("check_session", lambda: {"ok": True, "code": "X"})
        return {"ok": True, "code": "MODULE_OPENED", "message": "ok"}

    # run_composite giữ khóa; _run lồng trên CÙNG thread phải tái nhập được.
    assert api.run_composite(outer)["code"] == "MODULE_OPENED"
    assert captured["inner"]["code"] == "X"


# ---- Các phát hiện về đổi tài khoản / xác thực danh tính --------------


def test_flow_a11_session_reuse_never_verifies_who_is_logged_in(monkeypatch):
    """session.run() trả SESSION_REUSED mà không đối chiếu User ID."""
    stopped = []
    monkeypatch.setattr(session, "_start_persistent_chrome", lambda _log: None)
    monkeypatch.setattr(
        session,
        "sync_playwright",
        lambda: types.SimpleNamespace(
            start=lambda: types.SimpleNamespace(stop=lambda: stopped.append(1))
        ),
    )
    page = types.SimpleNamespace(url="https://wfx.example/wfx/default.aspx")
    monkeypatch.setattr(
        session, "_connect_to_chrome", lambda _pw: (object(), page)
    )
    monkeypatch.setattr(session, "_attach_dialog_handler", lambda *_a: None)
    monkeypatch.setattr(session, "_wait_for_auth_surface", lambda *_a: "session")
    monkeypatch.setattr(
        session,
        "_division_state_for_page",
        lambda _p: session._division_state_for_page_placeholder(),
    )
    called = []
    monkeypatch.setattr(
        session, "login", lambda *a, **k: called.append(a)
    )

    result = session.run("userB", "secretB", log=lambda _line: None)

    assert result["code"] == "SESSION_REUSED"
    assert called == []  # KHÔNG hề đăng nhập lại bằng userB


def test_flow_a12_changing_account_resets_the_derived_session_state(tmp_path):
    """Chrome vẫn giữ phiên của tài khoản cũ, nên app không được báo 'đã đăng
    nhập' cho tài khoản mới vừa lưu."""
    login = FakeLogin(
        session_alive=True, admin_modules=list(constants.ADMIN_MODULE_IDS)[:1]
    )
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    api.login()
    assert api.get_status()["session_active"] is True

    saved = api.save_account("userB", "secretB")

    assert saved["ok"] is True
    assert saved["session_active"] is None
    assert saved["current_division"] is None
    assert saved["admin_access"] is False
    status = api.get_status()
    assert status["session_active"] is None
    assert status["current_division"] is None
    assert api.should_maintain_session() is False


def test_flow_a12b_login_after_an_account_change_switches_the_browser_session(
    tmp_path,
):
    """Flow đầy đủ: lưu tài khoản mới -> login phải đổi hẳn phiên trên Chrome."""

    class SessionAwareLogin(FakeLogin):
        def run(
            self, user_id, password, company_id="psh", log=print,
            session_owner=None,
        ):
            self.calls.append(("run", user_id, password, session_owner))
            if session_owner and session_owner.casefold() != user_id.casefold():
                return {
                    "ok": True,
                    "code": "LOGGED_IN",
                    "message": "Đã đổi tài khoản.",
                    "session_user_id": user_id,
                }
            if self.session_alive:
                return {
                    "ok": True,
                    "code": "SESSION_REUSED",
                    "message": "Dùng lại phiên.",
                    "session_user_id": session_owner,
                }
            return {
                "ok": True,
                "code": "LOGGED_IN",
                "message": "ok",
                "session_user_id": user_id,
            }

    login = SessionAwareLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    api.login()
    assert api._session_user_id == "userA"

    api.save_account("userB", "secretB")
    result = api.login()

    assert result["code"] == "LOGGED_IN"
    assert api._session_user_id == "userB"
    assert [call for call in login.calls if call[0] == "run"][-1] == (
        "run", "userB", "secretB", "userA",
    )


def test_flow_a12c_legacy_login_modules_still_work(tmp_path):
    """Login module không có tham số session_owner vẫn phải gọi được."""
    api, login = make_api(
        tmp_path, FakeLogin(), user_id="userA", password="secretA"
    )

    assert api.login()["code"] == "LOGGED_IN"
    assert ("run", "userA", "secretA") in login.calls


def test_flow_a12d_session_owner_survives_an_app_restart(tmp_path):
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")
    api.login()

    reopened = PanelAPI(FakeLogin(), prefs, tmp_path)

    assert reopened._session_user_id == "userA"


def test_flow_a13_password_never_reaches_the_process_environment(tmp_path):
    api, _ = make_api(tmp_path)

    api.save_account("userA", "secretA")

    # Chrome được khởi chạy như tiến trình con nên kế thừa environment này.
    assert "WFX_PASSWORD" not in os.environ


def test_flow_a14_rejected_credentials_stop_the_auto_relogin_loop(tmp_path):
    """WFX khóa tài khoản sau vài lần sai; không được thử lại mãi."""
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    login.run_results = [
        {"ok": False, "code": "LOGIN_FAILED", "message": "sai mật khẩu"},
        {"ok": False, "code": "LOGIN_FAILED", "message": "sai mật khẩu"},
    ]

    def action():
        return {"ok": False, "code": "NOT_LOGGED_IN", "message": "hết phiên"}

    first = api._run("open_module", action)
    second = api._run("open_module", action)

    assert first["code"] == "LOGIN_FAILED"
    assert second["code"] == "LOGIN_FAILED"
    # Chỉ đúng MỘT lần gửi credential sang WFX cho cả hai cú bấm.
    assert len([call for call in login.calls if call[0] == "run"]) == 1
    assert "Cài đặt" in second["message"]


def test_flow_a15_saving_the_account_again_re_enables_auto_relogin(tmp_path):
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    login.run_results = [
        {"ok": False, "code": "LOGIN_FAILED", "message": "sai mật khẩu"}
    ]
    api._run("open_module", lambda: {"ok": False, "code": "NOT_LOGGED_IN", "message": "x"})
    assert api._rejected_credential is not None

    api.save_account("userA", "mat-khau-moi")

    assert api._rejected_credential is None


# ======================================================================
# B. FLOW TỔNG QUAN
# ======================================================================


def test_flow_b1_initial_state_contract(tmp_path):
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")

    state = api.get_initial_state()

    required = {
        "app_version", "user_id", "has_credentials", "theme", "hotkey",
        "hotkey_label", "autostart", "start_hidden", "toast_enabled",
        "focus_chrome_on_module", "always_on_top", "favorite_module_ids",
        "module_groups", "divisions", "jobs", "logs", "admin_access",
        "admin_mode", "session_active", "chrome_alive", "current_division",
    }
    assert required <= set(state)
    assert state["user_id"] == "userA"
    assert state["has_credentials"] is True
    assert state["session_active"] is None  # chưa probe -> "Chưa kiểm tra"
    assert [d["key"] for d in state["divisions"]] == ["woven", "knit", "pssg"]
    assert state["admin_access"] is False
    assert state["theme"] == "light"


def test_flow_b2_initial_state_without_account(tmp_path):
    api, _ = make_api(tmp_path)

    state = api.get_initial_state()

    assert state["user_id"] == ""
    assert state["has_credentials"] is False


def test_flow_b3_status_reflects_browser_and_session(tmp_path):
    api, login = make_api(
        tmp_path, FakeLogin(session_alive=True), user_id="userA", password="secretA"
    )

    before = api.get_status()
    api.check_session()
    after = api.get_status()

    assert before["session_active"] is None
    assert after["session_active"] is True
    assert after["chrome_alive"] is True
    assert after["division_label"] == "WOVEN"


def test_flow_b4_session_loss_clears_division(tmp_path):
    login = FakeLogin(session_alive=True)
    api, _ = make_api(tmp_path, login, user_id="userA", password="secretA")
    api.check_session()
    login.session_alive = False
    login.run_results = [
        {"ok": False, "code": "LOGIN_FAILED", "message": "sai mật khẩu"}
    ]

    api.maintain_session()

    status = api.get_status()
    assert status["session_active"] is False
    assert status["current_division"] is None


def test_flow_b5_switch_division_tracks_highlight(tmp_path):
    api, login = make_api(
        tmp_path, FakeLogin(session_alive=True), user_id="userA", password="secretA"
    )

    result = api.switch_division("knit")

    assert result["ok"] and result["current_division"] == "knit"
    assert api.get_status()["division_label"] == "KNIT"


def test_flow_b6_favorites_round_trip(tmp_path):
    api, _ = make_api(tmp_path)
    module_id = next(iter(constants.MODULE_BY_ID))

    pinned = api.set_module_favorite(module_id, True)
    assert pinned["favorite_module_ids"] == [module_id]
    assert api.get_initial_state()["favorite_module_ids"] == [module_id]

    unpinned = api.set_module_favorite(module_id, False)
    assert unpinned["favorite_module_ids"] == []
    assert api.set_module_favorite("khong-ton-tai", True)["code"] == "MODULE_UNKNOWN"


def test_flow_b7_admin_modules_hidden_without_wfx_grant(tmp_path):
    api, _ = make_api(tmp_path, FakeLogin(admin_modules=[]), user_id="a", password="b")
    api.login()

    denied = api.set_admin_mode(True)

    assert denied["code"] == "ADMIN_ACCESS_DENIED"
    assert denied["admin_mode"] is False
    assert api.get_initial_state()["admin_mode"] is False


# ======================================================================
# C. FLOW CÀI ĐẶT
# ======================================================================


@pytest.mark.parametrize(
    "method,value,key",
    [
        ("set_start_hidden", True, "start_hidden"),
        ("set_toast_enabled", False, "toast_enabled"),
        ("set_focus_chrome_on_module", False, "focus_chrome_on_module"),
        ("set_excel_file_after_download", False, "open_excel_file_after_download"),
    ],
)
def test_flow_c1_toggles_persist(tmp_path, method, value, key):
    api, _ = make_api(tmp_path)

    result = getattr(api, method)(value)

    assert result["ok"] and result[key] is value
    assert prefs.load_prefs(base_dir=tmp_path)[key] is value
    assert api.get_initial_state()[key] is value


def test_flow_c2_always_on_top_applies_to_the_window(tmp_path):
    api, _ = make_api(tmp_path)
    applied = []
    api.set_window_pref_appliers(on_top=applied.append)

    api.set_always_on_top(False)

    assert applied == [False]
    assert prefs.load_prefs(base_dir=tmp_path)["always_on_top"] is False


def test_flow_c3_theme_round_trip_and_garbage_is_refused(tmp_path):
    api, _ = make_api(tmp_path)

    assert api.set_theme("dark")["theme"] == "dark"
    assert api.set_theme("system")["theme"] == "system"

    rubbish = api.set_theme("<script>alert(1)</script>")

    # Không được báo "Đã đổi giao diện" rồi âm thầm nhảy về Sáng.
    assert rubbish["ok"] is False
    assert rubbish["code"] == "THEME_INVALID"
    assert rubbish["theme"] == "system"
    assert prefs.load_prefs(base_dir=tmp_path)["theme"] == "system"


@pytest.mark.skipif(
    os.name != "nt", reason="chỉ Windows mới mã hóa mật khẩu bằng DPAPI"
)
def test_flow_c9_unreadable_password_is_reported_as_such(tmp_path, monkeypatch):
    """Đổi máy/tài khoản Windows: blob DPAPI còn đó nhưng mở không ra."""
    api, _ = make_api(tmp_path, user_id="userA", password="secretA")
    assert api.get_initial_state()["credential_state"] == "ok"

    monkeypatch.setattr(secret, "unprotect", lambda _token: None)

    state = api.get_initial_state()

    assert state["credential_state"] == "unreadable"
    assert state["has_credentials"] is False


def test_flow_c4_hotkey_valid_invalid_and_rollback(tmp_path):
    api, _ = make_api(tmp_path)
    applied: list[str] = []
    api.set_hotkey_applier(lambda spec: applied.append(spec) or None)

    ok = api.set_hotkey("ctrl+alt+w")
    assert ok["ok"] and ok["hotkey"] == "ctrl+alt+w"
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+alt+w"

    assert api.set_hotkey("f")["code"] == "HOTKEY_INVALID"
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+alt+w"

    failures = []

    def failing(spec):
        failures.append(spec)
        return "Phím đang bị ứng dụng khác giữ." if len(failures) == 1 else None

    api.set_hotkey_applier(failing)
    rolled = api.set_hotkey("ctrl+shift+j")
    assert rolled["code"] == "HOTKEY_REGISTER_FAILED"
    assert rolled["hotkey"] == "ctrl+alt+w"
    assert failures == ["ctrl+shift+j", "ctrl+alt+w"]  # đã rollback
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+alt+w"


def test_flow_c5_autostart_reports_os_failure(tmp_path, monkeypatch):
    api, _ = make_api(tmp_path)
    monkeypatch.setattr(settings_controller.autostart, "sync", lambda wanted: False)

    result = api.set_autostart(True)

    assert result["ok"] is False and result["code"] == "AUTOSTART_FAILED"
    assert result["autostart"] is False
    assert prefs.load_prefs(base_dir=tmp_path)["autostart"] is False


def test_flow_c6_sale_asn_stage_prefs_never_persist_empty(tmp_path):
    api, _ = make_api(tmp_path)

    saved = api.set_sale_asn_stages([])

    assert saved["ok"] is True
    assert len(saved["sale_asn_stages"]) == 4
    assert api.set_sale_asn_stages("abc")["code"] == "SALE_ASN_CREATE_STEPS_INVALID"


def test_flow_c7_settings_survive_a_corrupt_prefs_file(tmp_path):
    (tmp_path / "prefs.json").write_text("{not json", encoding="utf-8")
    api, _ = make_api(tmp_path)

    state = api.get_initial_state()

    assert state["theme"] == "light"
    assert state["hotkey"] == "ctrl+shift+x"
    assert state["autostart"] is True


def test_flow_c8_settings_survive_an_unreadable_env(tmp_path):
    (tmp_path / ".env").write_text("rác\nWFX_USER_ID\n", encoding="utf-8")
    api, _ = make_api(tmp_path)

    state = api.get_initial_state()

    assert state["user_id"] == ""
    assert state["has_credentials"] is False


# ======================================================================
# D. LỚP GIAO DIỆN (khẳng định tĩnh trên panel.js)
# ======================================================================


def _handler_body(anchor: str, stop: str = "\n    $(") -> str:
    start = PANEL_JS.index(anchor)
    return PANEL_JS[start : PANEL_JS.index(stop, start + len(anchor))]


def test_flow_d1_open_chrome_button_reenables_itself_after_the_call():
    """Nút 'Mở trình duyệt' phải bật lại được sau khi flow chạy xong."""
    body = _handler_body('$(".open-chrome-button").addEventListener')

    assert "await call(" in body
    after_await = body[body.index("await call(") :]
    assert "event.currentTarget" not in after_await, (
        "event.currentTarget là null sau khi await -> ném TypeError và nút "
        "kẹt disabled vĩnh viễn."
    )


def test_flow_d2_successful_auto_relogin_clears_the_credential_prompt():
    start = PANEL_JS.index('["LOGGED_IN", "LOGGED_IN_AFTER_DELAY"')
    body = PANEL_JS[start : start + 200]

    assert "SESSION_RESTORED" in body, (
        "SESSION_RESTORED không nằm trong nhóm xoá prompt -> sheet tài khoản "
        "vẫn bị khoá sau khi app đã tự đăng nhập lại."
    )


def test_flow_d3_last_login_time_reaches_the_ui():
    """UI truyền last_login_at vào setSessionStatus nhưng hàm chỉ nhận 1 tham số."""
    assert "setSessionStatus(result.session_active, result.last_login_at)" in PANEL_JS
    signature = PANEL_JS[
        PANEL_JS.index("function setSessionStatus(") :
    ].split(")", 1)[0]

    assert "," in signature, (
        f"setSessionStatus chỉ nhận {signature!r} -> last_login_at bị bỏ rơi."
    )
