"""Phủ test cho chính lớp đăng nhập/phiên WFX (``automation/session.py``).

Trước đây module này chỉ được phủ 27%: ``login``, ``check_session``,
``switch_division``, ``check_module_access`` và ``get_division_state`` — tức
những hàm chạy mỗi lần khởi động và mỗi bốn phút — không có test nào.
"""

from __future__ import annotations

import types

import pytest

from wfx_panel.automation import session


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
