"""Nhận diện và chuyển Division, xác minh quyền module, và ảnh chẩn đoán.

CLAUDE.md: các probe chỉ đọc session/Division/quyền và ảnh chẩn đoán phải dùng
`bring_to_front=False` — không được kéo người dùng khỏi tab Costing đang làm.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.session as session
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError
from wfx_panel.constants import DIVISIONS


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, session)


def _division(index=0):
    return list(DIVISIONS.values())[index]


class Node:
    def __init__(self, *, count=1, title=None, text="", visible=True, error=None):
        self._count = count
        self.title = title
        self.text = text
        self.visible = visible
        self.error = error
        self.clicks = 0

    @property
    def first(self):
        return self

    def count(self):
        if self.error is not None:
            raise self.error
        return self._count

    def is_visible(self, **_kwargs):
        return self.visible

    def get_attribute(self, _name, **_kwargs):
        return self.title

    def inner_text(self, **_kwargs):
        return self.text

    def evaluate(self, _script, _arg=None):
        self.clicks += 1


class SessionFrame:
    def __init__(self, nodes=None, *, name="body", url="", broken=False):
        self.nodes = dict(nodes or {})
        self.name = name
        self.url = url
        self.broken = broken

    def locator(self, selector):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        return self.nodes.get(selector, Node(count=0))


class SessionPage:
    def __init__(self, *frames, clock=None, nodes=None, url="https://wfx.test/"):
        self.frames = list(frames)
        self.clock = clock
        self.nodes = dict(nodes or {})
        self.url = url
        self.screenshots: list[dict] = []

    def locator(self, selector):
        return self.nodes.get(selector, Node(count=0))

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)

    def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)


# --- đọc Division từ CompanyName ---------------------------------------


def test_the_division_is_read_from_the_company_name_title(clock):
    target = _division()
    page = SessionPage(
        SessionFrame({"#CompanyName": Node(title=f"  {target['name']}  ")}),
        clock=clock,
    )

    assert session._division_state_for_page(page)["current_division"] == (
        target["key"]
    )


def test_the_company_name_text_is_used_when_there_is_no_title(clock):
    target = _division()
    page = SessionPage(
        SessionFrame({"#CompanyName": Node(title=None, text=target["name"])}),
        clock=clock,
    )

    assert session._division_state_for_page(page)["division_label"] == (
        target["label"]
    )


def test_a_frame_that_detaches_does_not_stop_the_division_scan(clock):
    target = _division()
    page = SessionPage(
        SessionFrame(broken=True),
        SessionFrame({"#CompanyName": Node(title=target["name"])}),
        clock=clock,
    )

    assert session._division_state_for_page(page)["current_division"] == (
        target["key"]
    )


def test_a_page_without_a_company_name_reports_nothing_rather_than_guessing(
    clock,
):
    page = SessionPage(SessionFrame(), clock=clock)

    assert session._division_state_for_page(page) == {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


def test_a_company_name_that_matches_no_division_reports_nothing(clock):
    page = SessionPage(
        SessionFrame({"#CompanyName": Node(title="CONG TY LA")}), clock=clock
    )

    assert session._division_state_for_page(page)["current_division"] is None


# --- đọc Division từ route Base Setting --------------------------------


def _base_setting_url(division):
    return (
        "https://wfx.test/wfx/wfx_BaseSetting.aspx?ChangeBaseSetting=1"
        f"&MemberCompanyCode={division['member_company_code']}"
        f"&folderID={division['folder_id']}"
    )


def test_the_route_of_the_body_frame_also_identifies_the_division(clock):
    target = _division()
    page = SessionPage(
        SessionFrame(name="left", url=_base_setting_url(target)),
        SessionFrame(name="body", url=_base_setting_url(target)),
        clock=clock,
    )

    assert session._division_route_state_for_page(page)["current_division"] == (
        target["key"]
    )


def test_only_the_body_frame_route_counts(clock):
    target = _division()
    page = SessionPage(
        SessionFrame(name="left", url=_base_setting_url(target)), clock=clock
    )

    assert session._division_route_state_for_page(page) is None


def test_a_route_that_is_not_base_setting_identifies_nothing(clock):
    page = SessionPage(
        SessionFrame(name="body", url="https://wfx.test/wfx/default.aspx"),
        clock=clock,
    )

    assert session._division_route_state_for_page(page) is None


def test_a_route_with_unparseable_ids_identifies_nothing(clock):
    page = SessionPage(
        SessionFrame(
            name="body",
            url="https://wfx.test/wfx/wfx_BaseSetting.aspx?companyID=&folderID=",
        ),
        clock=clock,
    )

    assert session._division_route_state_for_page(page) is None


# --- chuyển Division ----------------------------------------------------


def _wire_switch(monkeypatch, page, *, current=None, states=None, routes=None):
    patch_automation(monkeypatch, session, "_chrome_is_ready", lambda: True)
    patch_automation(
        monkeypatch,
        session,
        "sync_playwright",
        lambda: type(
            "Factory",
            (),
            {
                "start": staticmethod(
                    lambda: type("Driver", (), {"stop": lambda _self: None})()
                )
            },
        )(),
    )
    patch_automation(
        monkeypatch,
        session,
        "_connect_to_chrome",
        lambda _playwright, **_kwargs: ("browser", page),
    )
    patch_automation(
        monkeypatch, session, "_attach_dialog_handler", lambda *_a: None
    )
    patch_automation(monkeypatch, session, "_session_is_active", lambda _p: True)
    values = list(states or [current or _empty_state()])
    patch_automation(
        monkeypatch,
        session,
        "_division_state_for_page",
        lambda _page: values.pop(0) if len(values) > 1 else values[0],
    )
    route_values = list(routes or [None])
    patch_automation(
        monkeypatch,
        session,
        "_division_route_state_for_page",
        lambda _page: route_values.pop(0)
        if len(route_values) > 1
        else route_values[0],
    )


def _empty_state():
    return {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


def _state(division):
    return {
        "current_division": division["key"],
        "division_label": division["label"],
        "division_name": division["name"],
    }


def test_an_unknown_division_key_is_refused(monkeypatch, clock):
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page)

    assert session.switch_division("khong-ton-tai")["code"] == "DIVISION_UNKNOWN"


def test_a_division_already_selected_is_not_switched_again(monkeypatch, clock):
    target = _division()
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page, current=_state(target))

    result = session.switch_division(target["key"])

    assert result["code"] == "DIVISION_ALREADY_ACTIVE"
    assert result["current_division"] == target["key"]


def test_a_division_link_wfx_does_not_show_is_reported(monkeypatch, clock):
    target = _division(1)
    page = SessionPage(SessionFrame(), clock=clock)
    _wire_switch(monkeypatch, page, current=_state(_division(0)))

    result = session.switch_division(target["key"])

    assert result["code"] == "DIVISION_OPTION_NOT_FOUND"
    assert target["label"] in result["message"]


def _link_selector(division):
    return (
        'a.hasbookmark[href*="ChangeBaseSetting=1"]'
        f'[href*="MemberCompanyCode={division["member_company_code"]}"]'
        f'[href*="folderID={division["folder_id"]}"]'
    )


def test_a_confirmed_division_change_reports_the_new_state(monkeypatch, clock):
    target = _division(1)
    link = Node()
    page = SessionPage(
        SessionFrame({_link_selector(target): link}), clock=clock
    )
    _wire_switch(
        monkeypatch,
        page,
        states=[_state(_division(0)), _state(target)],
    )
    lines: list[str] = []

    result = session.switch_division(target["key"], lines.append)

    assert result["code"] == "DIVISION_CHANGED"
    assert link.clicks == 1
    assert any("Đã chuyển sang" in line for line in lines)


def test_the_base_setting_route_confirms_the_change_when_the_header_lags(
    monkeypatch, clock
):
    target = _division(1)
    link = Node()
    page = SessionPage(
        SessionFrame({_link_selector(target): link}), clock=clock
    )
    _wire_switch(
        monkeypatch,
        page,
        states=[_state(_division(0))],
        routes=[_state(target)],
    )
    lines: list[str] = []

    result = session.switch_division(target["key"], lines.append)

    assert result["code"] == "DIVISION_CHANGED"
    assert any("qua Base Setting" in line for line in lines)


def test_a_slow_wfx_is_clicked_a_second_time_before_giving_up(
    monkeypatch, clock
):
    target = _division(1)
    link = Node()
    page = SessionPage(
        SessionFrame({_link_selector(target): link}), clock=clock
    )
    _wire_switch(monkeypatch, page, states=[_state(_division(0))])
    lines: list[str] = []

    result = session.switch_division(target["key"], lines.append)

    assert result["code"] == "DIVISION_CHANGE_NOT_CONFIRMED"
    assert link.clicks == 2, "phải thử lại đúng một lần"
    assert any("phản hồi chậm" in line for line in lines)


def test_a_frame_that_detaches_while_looking_for_the_link_is_skipped(
    monkeypatch, clock
):
    target = _division(1)
    link = Node()
    page = SessionPage(
        SessionFrame(broken=True),
        SessionFrame({_link_selector(target): link}),
        clock=clock,
    )
    _wire_switch(
        monkeypatch, page, states=[_state(_division(0)), _state(target)]
    )

    assert session.switch_division(target["key"])["code"] == "DIVISION_CHANGED"


def test_an_unexpected_error_while_switching_is_named(monkeypatch, clock):
    target = _division(1)
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page, current=_state(_division(0)))

    def explode(_page):
        raise ValueError("frame lạ")

    patch_automation(
        monkeypatch, session, "_division_route_state_for_page", explode
    )
    patch_automation(
        monkeypatch,
        session,
        "_division_state_for_page",
        lambda _page: _state(_division(0)),
    )
    page.frames = [SessionFrame({_link_selector(target): Node()})]

    result = session.switch_division(target["key"])

    assert result["code"] == "DIVISION_CHANGE_FAILED"
    assert "ValueError" in result["message"]


# --- nhận diện Division hiện tại ---------------------------------------


def test_reading_the_division_never_brings_chrome_to_the_front(
    monkeypatch, clock
):
    page = SessionPage(clock=clock)
    fronted: list[bool] = []
    _wire_switch(monkeypatch, page, current=_state(_division()))
    patch_automation(
        monkeypatch,
        session,
        "_connect_to_chrome",
        lambda _playwright, **kwargs: (
            fronted.append(kwargs.get("bring_to_front", True)),
            ("browser", page),
        )[1],
    )

    result = session.get_division_state(lambda _line: None)

    assert result["code"] == "DIVISION_DETECTED"
    assert fronted == [False]


def test_an_error_while_reading_still_returns_a_full_state(monkeypatch, clock):
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page)

    def explode(_page):
        raise ValueError("frame lạ")

    patch_automation(monkeypatch, session, "_division_state_for_page", explode)

    result = session.get_division_state(lambda _line: None)

    assert result["code"] == "DIVISION_DETECT_FAILED"
    assert set(result) >= {
        "current_division",
        "division_label",
        "division_name",
    }


# --- xác minh quyền module ---------------------------------------------


def test_checking_module_access_with_the_browser_closed_is_reported(
    monkeypatch,
):
    patch_automation(monkeypatch, session, "_chrome_is_ready", lambda: False)

    result = session.check_module_access([{"id": "a", "xpath": "//a"}])

    assert result["code"] == "CHROME_CLOSED"
    assert result["accessible_module_ids"] == []


def test_only_modules_whose_menu_anchor_exists_are_reported_accessible(
    monkeypatch, clock
):
    page = SessionPage(
        clock=clock,
        nodes={"xpath=//a[1]": Node(count=1), "xpath=//a[2]": Node(count=0)},
    )
    _wire_switch(monkeypatch, page)
    lines: list[str] = []

    result = session.check_module_access(
        [
            {"id": "co-quyen", "xpath": "//a[1]"},
            {"id": "khong-quyen", "xpath": "//a[2]"},
            {"id": "", "xpath": "//a[1]"},
            {"id": "thieu-xpath", "xpath": ""},
        ],
        lines.append,
    )

    assert result["accessible_module_ids"] == ["co-quyen"]
    assert any("1/4 module" in line for line in lines)


def test_a_menu_probe_that_throws_is_skipped_not_counted(monkeypatch, clock):
    page = SessionPage(
        clock=clock,
        nodes={
            "xpath=//a[1]": Node(error=PlaywrightError("node đã bị thay")),
            "xpath=//a[2]": Node(count=1),
        },
    )
    _wire_switch(monkeypatch, page)

    result = session.check_module_access(
        [
            {"id": "hong", "xpath": "//a[1]"},
            {"id": "tot", "xpath": "//a[2]"},
        ]
    )

    assert result["accessible_module_ids"] == ["tot"]


def test_an_unexpected_error_while_checking_access_is_named(monkeypatch, clock):
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page)

    def explode(_page):
        raise ValueError("phiên hỏng")

    patch_automation(monkeypatch, session, "_session_is_active", explode)

    result = session.check_module_access([{"id": "a", "xpath": "//a"}])

    assert result["code"] == "MODULE_ACCESS_CHECK_FAILED"
    assert result["accessible_module_ids"] == []


# --- ảnh chẩn đoán ------------------------------------------------------


def test_a_failure_screenshot_is_taken_without_fronting_chrome(
    monkeypatch, clock, tmp_path
):
    page = SessionPage(clock=clock)
    fronted: list[bool] = []
    _wire_switch(monkeypatch, page)
    patch_automation(
        monkeypatch,
        session,
        "_connect_to_chrome",
        lambda _playwright, **kwargs: (
            fronted.append(kwargs.get("bring_to_front", True)),
            ("browser", page),
        )[1],
    )
    target = tmp_path / "shot.png"

    def screenshot(**kwargs):
        target.write_bytes(b"png")
        page.screenshots.append(kwargs)

    page.screenshot = screenshot
    lines: list[str] = []

    assert session.capture_failure_screenshot(target, lines.append) is True
    assert fronted == [False]
    assert page.screenshots[0]["full_page"] is False


def test_a_screenshot_that_cannot_be_taken_is_logged_not_raised(
    monkeypatch, clock, tmp_path
):
    page = SessionPage(clock=clock)
    _wire_switch(monkeypatch, page)

    def explode(**_kwargs):
        raise RuntimeError("target đã đóng")

    page.screenshot = explode
    lines: list[str] = []

    assert (
        session.capture_failure_screenshot(tmp_path / "shot.png", lines.append)
        is False
    )
    assert any("Không chụp được ảnh lỗi" in line for line in lines)


# --- các nhánh chịu lỗi nhỏ --------------------------------------------


def test_the_auth_surface_probe_survives_a_frame_that_detaches(clock):
    class Broken(SessionPage):
        def locator(self, _selector):
            raise PlaywrightError("node đã bị thay")

    page = Broken(clock=clock)

    assert session._wait_for_auth_surface(page, 1) == "unknown"


def test_the_auth_surface_probe_reports_the_login_form(clock, monkeypatch):
    patch_automation(monkeypatch, session, "_session_is_active", lambda _p: False)
    page = SessionPage(clock=clock, nodes={"#txtUserID": Node()})

    assert session._wait_for_auth_surface(page, 5) == "login"


def test_a_base_setting_url_with_a_bad_query_identifies_nothing():
    assert (
        session._division_for_base_setting_url(
            "https://wfx.test/wfx/wfx_BaseSetting.aspx?ChangeBaseSetting=1"
            "&MemberCompanyCode=99999&folderID=99999"
        )
        is None
    )


def test_a_url_python_cannot_parse_identifies_nothing():
    assert session._division_for_base_setting_url("https://[khong-hop-le") is None


def test_a_body_frame_that_detaches_is_skipped_while_reading_the_route(clock):
    target = _division()

    class BrokenName(SessionFrame):
        @property
        def name(self):
            raise PlaywrightError("frame đã detach")

        @name.setter
        def name(self, _value):
            return None

    page = SessionPage(
        BrokenName(),
        SessionFrame(name="body", url=_base_setting_url(target)),
        clock=clock,
    )

    assert session._division_route_state_for_page(page)["current_division"] == (
        target["key"]
    )


# --- đăng nhập chậm -----------------------------------------------------


def _wire_login(monkeypatch, page, *, surfaces=("session",)):
    patch_automation(monkeypatch, session, "_chrome_is_ready", lambda: True)
    patch_automation(
        monkeypatch,
        session,
        "sync_playwright",
        lambda: type(
            "Factory",
            (),
            {
                "start": staticmethod(
                    lambda: type("Driver", (), {"stop": lambda _self: None})()
                )
            },
        )(),
    )
    patch_automation(
        monkeypatch,
        session,
        "_connect_to_chrome",
        lambda _playwright, **_kwargs: ("browser", page),
    )
    patch_automation(
        monkeypatch, session, "_attach_dialog_handler", lambda *_a: None
    )
    values = list(surfaces)
    patch_automation(
        monkeypatch,
        session,
        "_wait_for_auth_surface",
        lambda _page, _t: values.pop(0) if len(values) > 1 else values[0],
    )
    patch_automation(
        monkeypatch, session, "_start_persistent_chrome", lambda _log: None
    )
    patch_automation(
        monkeypatch,
        session,
        "_division_state_for_page",
        lambda _page: _state(_division()),
    )


class TimingOutPage(SessionPage):
    """Form đăng nhập không phản hồi trong thời gian chờ."""

    def goto(self, *_args, **_kwargs):
        raise session.PlaywrightTimeoutError("WFX không phản hồi")

    def locator(self, _selector):
        raise session.PlaywrightTimeoutError("WFX không phản hồi")


def test_a_slow_wfx_that_did_log_in_after_all_is_reported_as_success(
    monkeypatch, clock
):
    page = TimingOutPage(clock=clock)
    # Lượt đầu thấy màn đăng nhập nên flow đi điền form; lượt kiểm lại trong
    # handler timeout thấy phiên đã sống.
    _wire_login(monkeypatch, page, surfaces=("login", "session"))
    lines: list[str] = []

    result = session.run("tester", "mat-khau", log=lines.append)

    assert result["code"] == "LOGGED_IN_AFTER_DELAY"
    assert result["session_user_id"] == "tester"
    assert any("phản hồi trễ" in line for line in lines)


def test_a_timeout_that_really_failed_is_reported_as_a_timeout(
    monkeypatch, clock
):
    page = TimingOutPage(clock=clock)
    _wire_login(monkeypatch, page, surfaces=("login", "login"))
    lines: list[str] = []

    result = session.run("tester", "mat-khau", log=lines.append)

    assert result["code"] == "LOGIN_TIMEOUT"
    assert "WFX không phản hồi" in result["message"]
    assert lines[-1] == result["message"]


def test_an_unexpected_error_while_logging_in_names_its_type(monkeypatch, clock):
    class BrokenPage(SessionPage):
        def goto(self, *_args, **_kwargs):
            raise ValueError("URL WFX sai")

    page = BrokenPage(clock=clock)
    _wire_login(monkeypatch, page, surfaces=("login",))
    lines: list[str] = []

    result = session.run("tester", "mat-khau", log=lines.append)

    assert result["code"] == "LOGIN_FAILED"
    assert result["message"].startswith("ValueError: ")
    assert lines[-1] == result["message"]
