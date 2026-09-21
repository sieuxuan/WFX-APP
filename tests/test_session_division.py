"""Phiên WFX và Division: ai đang sở hữu phiên, và đổi Division có chắc không.

`wfx_panel/automation/session.py` ở mức 73%. CLAUDE.md đặt ra ràng buộc bảo mật
mạnh nhất của cả app ngay trong phần chưa chạy:

* "`session.run` nhận `session_owner`: trùng User ID thì mới được trả
  `SESSION_REUSED`, khác thì phải mở lại màn đăng nhập WFX và đăng nhập bằng
  tài khoản mới. Nếu WFX không nhả phiên cũ, trả `SESSION_USER_MISMATCH` và
  dừng — tuyệt đối không chạy tiếp automation bằng tài khoản người khác."
* Đổi Division phải được WFX xác nhận, qua `#CompanyName` hoặc qua chính route
  Base Setting; "WFX phản hồi chậm" chỉ được thử lại đúng một lần.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation import session as wfx_session
from wfx_panel.constants import DIVISIONS


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, wfx_session, _common)


def _quiet():
    return lambda _line: None


def _division(index=0) -> dict:
    return list(DIVISIONS.values())[index]


class _Page:
    def __init__(self, clock, frames, *, url="https://wfx.test/wfx/default.aspx"):
        self.clock = clock
        self.frames = list(frames)
        self.url = url
        self.goto_calls: list[str] = []
        self.goto_error: Exception | None = None

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector):
        return self.frames[0].locator(selector)

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error


def _frame(clock, *, name="body", url="https://wfx.test/x.aspx", children=()):
    return MiniFrame(
        Element("body", children=list(children)), name=name, url=url, clock=clock
    )


def _menu_frame(clock, *, logged_in=True, login_form=False, company=""):
    children = []
    xpaths = {}
    if logged_in:
        catalog = element("a", id="catalog")
        xpaths['//*[@id="0003_6200"]/a'] = [catalog]
    else:
        xpaths['//*[@id="0003_6200"]/a'] = []
    if login_form:
        children.append(element("input", id="txtUserID"))
    if company:
        children.append(
            element("span", id="CompanyName", attrs={"title": company})
        )
    frame = MiniFrame(
        Element("body", children=children), name="", clock=clock, xpaths=xpaths
    )
    return frame


# --- phiên còn sống hay không --------------------------------------------


def test_the_catalog_menu_is_the_proof_of_a_live_session(clock):
    page = _Page(clock, [_menu_frame(clock)])

    assert wfx_session._session_is_active(page) is True


def test_no_catalog_menu_means_no_session(clock):
    page = _Page(clock, [_menu_frame(clock, logged_in=False)])

    assert wfx_session._session_is_active(page) is False


def test_a_broken_page_is_treated_as_no_session(clock):
    class Broken:
        def locator(self, _selector):
            raise PlaywrightError("tab rơi")

    assert wfx_session._session_is_active(Broken()) is False


@pytest.mark.parametrize(
    ("logged_in", "login_form", "expected"),
    [
        (True, False, "session"),
        (False, True, "login"),
        (False, False, "unknown"),
    ],
)
def test_the_auth_surface_is_classified(clock, logged_in, login_form, expected):
    page = _Page(
        clock, [_menu_frame(clock, logged_in=logged_in, login_form=login_form)]
    )

    assert wfx_session._wait_for_auth_surface(page, 1) == expected


# --- nhận diện Division ---------------------------------------------------


def test_a_company_name_is_matched_to_its_division():
    division = _division()

    assert wfx_session._division_for_text(
        f"  {division['name'].upper()}  "
    ) == {
        "current_division": division["key"],
        "division_label": division["label"],
        "division_name": division["name"],
    }


@pytest.mark.parametrize("value", ["", "   ", "Công ty lạ", None])
def test_an_unknown_company_name_matches_no_division(value):
    assert wfx_session._division_for_text(value) is None


def test_the_base_setting_route_identifies_the_division():
    division = _division()
    url = (
        "https://wfx.test/WFX_BaseSetting.aspx?ChangeBaseSetting=1"
        f"&MemberCompanyCode={division['member_company_code']}"
        f"&FolderID={division['folder_id']}"
    )

    assert wfx_session._division_for_base_setting_url(url) == {
        "current_division": division["key"],
        "division_label": division["label"],
        "division_name": division["name"],
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://wfx.test/wfx/default.aspx?ChangeBaseSetting=1",
        "https://wfx.test/WFX_BaseSetting.aspx",
        "https://wfx.test/WFX_BaseSetting.aspx?ChangeBaseSetting=0",
        "https://wfx.test/WFX_BaseSetting.aspx?ChangeBaseSetting=1&FolderID=999",
        "",
        None,
    ],
)
def test_any_other_route_identifies_nothing(url):
    assert wfx_session._division_for_base_setting_url(url) is None


def test_only_the_body_frame_route_is_read(clock):
    division = _division()
    url = (
        "https://wfx.test/WFX_BaseSetting.aspx?ChangeBaseSetting=1"
        f"&MemberCompanyCode={division['member_company_code']}"
        f"&FolderID={division['folder_id']}"
    )
    other = _frame(clock, name="left", url=url)
    body = _frame(clock, name="body", url=url)

    assert wfx_session._division_route_state_for_page(
        _Page(clock, [other])
    ) is None
    assert wfx_session._division_route_state_for_page(_Page(clock, [body]))[
        "current_division"
    ] == division["key"]


def test_the_division_is_read_from_company_name_in_any_frame(clock):
    division = _division()
    page = _Page(
        clock,
        [
            _frame(clock, name="left"),
            _menu_frame(clock, company=division["name"]),
        ],
    )

    assert wfx_session._division_state_for_page(page)["current_division"] == (
        division["key"]
    )


def test_a_page_without_a_company_name_reports_no_division(clock):
    page = _Page(clock, [_frame(clock)])

    assert wfx_session._division_state_for_page(page) == {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


def test_the_placeholder_state_has_every_key_the_panel_reads():
    assert wfx_session._division_state_for_page_placeholder() == {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


# --- so sánh chủ phiên ----------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "same"),
    [
        ("psh45", "PSH45", True),
        ("  psh45 ", "psh45", True),
        ("psh45", "psh46", False),
        (None, "", True),
        ("psh45", None, False),
    ],
)
def test_session_owner_comparison_ignores_case_and_spacing(left, right, same):
    assert wfx_session._same_user(left, right) is same


# --- mở lại màn đăng nhập -------------------------------------------------


def test_reopening_the_login_form_succeeds_when_wfx_lets_go(clock):
    page = _Page(clock, [_menu_frame(clock, logged_in=False, login_form=True)])

    assert wfx_session._reopen_login_form(page, _quiet()) is True
    assert page.goto_calls == [wfx_session.URL]


def test_reopening_fails_when_wfx_keeps_the_old_session(clock):
    """Phiên cũ còn sống thì tuyệt đối không được dùng tiếp."""
    page = _Page(clock, [_menu_frame(clock)])

    assert wfx_session._reopen_login_form(page, _quiet()) is False


def test_a_navigation_failure_is_reported_as_not_reopened(clock):
    page = _Page(clock, [_menu_frame(clock, logged_in=False, login_form=True)])
    page.goto_error = PlaywrightError("tab rơi")
    logs: list[str] = []

    assert wfx_session._reopen_login_form(page, logs.append) is False
    assert any("Không mở lại được" in line for line in logs)


# --- run(): quyết định dùng lại hay đăng nhập lại ------------------------


class _Driver:
    def stop(self):
        return None


class _Starter:
    def start(self):
        return _Driver()


def _wire_run(monkeypatch, page, *, logins=None):
    monkeypatch.setattr(wfx_session, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(
        wfx_session, "_start_persistent_chrome", lambda _log: None
    )
    monkeypatch.setattr(
        wfx_session,
        "_connect_to_chrome",
        lambda _playwright, **_kw: (object(), page),
    )
    monkeypatch.setattr(wfx_session, "_attach_dialog_handler", lambda *a: None)
    sink = logins if logins is not None else []
    monkeypatch.setattr(
        wfx_session,
        "login",
        lambda _page, user, password, company: sink.append((user, company)),
    )
    return sink


def test_a_session_owned_by_the_same_user_is_reused(clock, monkeypatch):
    page = _Page(clock, [_menu_frame(clock)])
    logins = _wire_run(monkeypatch, page)

    result = wfx_session.run("psh45", "pw", session_owner="PSH45", log=_quiet())

    assert result["code"] == "SESSION_REUSED"
    assert result["session_user_id"] == "PSH45"
    assert logins == []
    assert page.goto_calls == []


def test_a_session_of_another_user_is_replaced_by_a_fresh_login(
    clock, monkeypatch
):
    frame = _menu_frame(clock)
    page = _Page(clock, [frame])
    logins = _wire_run(monkeypatch, page)

    def reopen(_page, _log):
        frame.xpaths['//*[@id="0003_6200"]/a'] = []
        frame.root.append(element("input", id="txtUserID"))
        return True

    monkeypatch.setattr(wfx_session, "_reopen_login_form", reopen)

    result = wfx_session.run("psh45", "pw", session_owner="psh99", log=_quiet())

    assert result["code"] == "LOGGED_IN"
    assert result["session_user_id"] == "psh45"
    assert logins == [("psh45", wfx_session.COMPANY_ID)]


def test_a_session_wfx_refuses_to_release_stops_the_flow(clock, monkeypatch):
    """CLAUDE.md: tuyệt đối không chạy tiếp bằng tài khoản người khác."""
    page = _Page(clock, [_menu_frame(clock)])
    logins = _wire_run(monkeypatch, page)
    monkeypatch.setattr(wfx_session, "_reopen_login_form", lambda *a: False)

    result = wfx_session.run("psh45", "pw", session_owner="psh99", log=_quiet())

    assert result["code"] == "SESSION_USER_MISMATCH"
    assert result["session_user_id"] == "psh99"
    assert logins == []


def test_switching_account_without_a_password_is_refused(clock, monkeypatch):
    page = _Page(clock, [_menu_frame(clock)])
    logins = _wire_run(monkeypatch, page)

    result = wfx_session.run("psh45", "", session_owner="psh99", log=_quiet())

    assert result["code"] == "MISSING_CREDENTIALS"
    assert logins == []


def test_an_unknown_owner_never_triggers_a_forced_relogin(clock, monkeypatch):
    """`session_owner=None` nghĩa là không biết, không phải là khác tài khoản."""
    page = _Page(clock, [_menu_frame(clock)])
    _wire_run(monkeypatch, page)

    result = wfx_session.run("psh45", "pw", session_owner=None, log=_quiet())

    assert result["code"] == "SESSION_REUSED"
    assert page.goto_calls == []


def test_a_login_form_with_no_credentials_is_refused(clock, monkeypatch):
    page = _Page(clock, [_menu_frame(clock, logged_in=False, login_form=True)])
    logins = _wire_run(monkeypatch, page)

    result = wfx_session.run("", "", log=_quiet())

    assert result["code"] == "MISSING_CREDENTIALS"
    assert logins == []


def test_an_unknown_surface_is_still_logged_into(clock, monkeypatch):
    page = _Page(clock, [_menu_frame(clock, logged_in=False)])
    logins = _wire_run(monkeypatch, page)
    logs: list[str] = []

    result = wfx_session.run("psh45", "pw", log=logs.append)

    assert result["code"] == "LOGGED_IN"
    assert logins == [("psh45", wfx_session.COMPANY_ID)]
    assert any("Trang cũ không phản hồi" in line for line in logs)


def test_a_slow_wfx_that_did_log_in_is_reported_as_success(clock, monkeypatch):
    frame = _menu_frame(clock, logged_in=False, login_form=True)
    page = _Page(clock, [frame])
    _wire_run(monkeypatch, page)

    def slow_login(_page, _user, _password, _company):
        frame.xpaths['//*[@id="0003_6200"]/a'] = [element("a")]
        raise PlaywrightTimeoutError("WFX chậm")

    monkeypatch.setattr(wfx_session, "login", slow_login)
    logs: list[str] = []

    result = wfx_session.run("psh45", "pw", log=logs.append)

    assert result["code"] == "LOGGED_IN_AFTER_DELAY"
    assert result["session_user_id"] == "psh45"
    assert any("phản hồi trễ" in line for line in logs)


def test_the_company_id_is_passed_through(clock, monkeypatch):
    page = _Page(clock, [_menu_frame(clock, logged_in=False, login_form=True)])
    logins = _wire_run(monkeypatch, page)

    wfx_session.run("psh45", "pw", company_id="abc", log=_quiet())

    assert logins == [("psh45", "abc")]


# --- đổi Division ---------------------------------------------------------


def _division_world(clock, monkeypatch, *, states, routes=None):
    frame = _menu_frame(clock)
    page = _Page(clock, [frame])
    action = element("a", id="division")
    state_queue = list(states)
    route_queue = list(routes or [None])
    monkeypatch.setattr(wfx_session, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(wfx_session, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(
        wfx_session,
        "_connect_to_chrome",
        lambda _playwright, **_kw: (object(), page),
    )
    monkeypatch.setattr(wfx_session, "_attach_dialog_handler", lambda *a: None)
    monkeypatch.setattr(
        wfx_session,
        "_division_state_for_page",
        lambda _page: (
            state_queue.pop(0) if len(state_queue) > 1 else state_queue[0]
        ),
    )
    monkeypatch.setattr(
        wfx_session,
        "_division_route_state_for_page",
        lambda _page: (
            route_queue.pop(0) if len(route_queue) > 1 else route_queue[0]
        ),
    )
    monkeypatch.setattr(
        wfx_session, "_division_actionable", lambda *a, **kw: action, raising=False
    )
    return page, action


def _state(division=None):
    if division is None:
        return {
            "current_division": None,
            "division_label": None,
            "division_name": None,
        }
    return {
        "current_division": division["key"],
        "division_label": division["label"],
        "division_name": division["name"],
    }


def test_an_unknown_division_key_is_refused(clock, monkeypatch):
    monkeypatch.setattr(wfx_session, "_chrome_is_ready", lambda: True)

    assert wfx_session.switch_division("khong-co", _quiet())["code"] in {
        "DIVISION_UNKNOWN",
        "DIVISION_CHANGE_FAILED",
    }


def test_a_closed_browser_blocks_a_division_change(clock, monkeypatch):
    monkeypatch.setattr(wfx_session, "_chrome_is_ready", lambda: False)

    result = wfx_session.switch_division(_division()["key"], _quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert result["current_division"] is None


def test_reading_the_division_needs_an_open_browser(clock, monkeypatch):
    monkeypatch.setattr(wfx_session, "_chrome_is_ready", lambda: False)

    result = wfx_session.get_division_state(_quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert result["division_label"] is None
