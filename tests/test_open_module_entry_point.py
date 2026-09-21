"""Nút `List` của mọi module generic — QA List, Indent List, User Indent…

CLAUDE.md: mọi flow `List` chỉ được trả `MODULE_OPENED` sau khi WFX đổi
page/frame/document thật; một cú click menu đơn thuần không tính. Phần phân loại
lỗi của `open_module` (`MODULE_OPEN_NOT_CONFIRMED` / `MODULE_NOT_FOUND` /
`CHROME_CLOSED` / `NOT_LOGGED_IN`) trước đây chưa có test nào chạy qua.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.wfx_dom import FakeNode, install_fake_clock
from wfx_panel import constants
from wfx_panel.automation import modules

QA_LIST = constants.MODULE_BY_ID["0063_0030_0020"]
INDENT_LIST = constants.MODULE_BY_ID["0005_0080_0020"]
USER_INDENT = constants.MODULE_BY_ID["user_indent_list"]


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, modules)


@pytest.fixture
def world(clock):
    world = WfxWorld(clock)
    # Form đăng nhập không hiển thị -> phiên còn sống.
    world.page.nodes["#txtUserID"] = [FakeNode(visible=False)]
    return world


def _open(module=QA_LIST):
    return modules.open_module(module["name"], module["xpath"], lambda _line: None)


def _menu(monkeypatch, *, confirmed=True, cache_hit=False):
    seen: list[tuple[str, str]] = []

    def fake_menu(_page, module_name, xpath, _log):
        seen.append((module_name, xpath))
        return modules._MenuOpenResult(confirmed, cache_hit)

    monkeypatch.setattr(modules, "_open_module_menu", fake_menu)
    return seen


@pytest.mark.parametrize("module", [QA_LIST, INDENT_LIST, USER_INDENT])
def test_a_confirmed_navigation_opens_the_module(monkeypatch, world, module):
    wire_automation(monkeypatch, modules, world)
    seen = _menu(monkeypatch)

    result = modules.open_module(
        module["name"], module["xpath"], lambda _line: None
    )

    assert result["code"] == "MODULE_OPENED"
    assert result["module"] == module["name"]
    assert seen == [(module["name"], module["xpath"])]
    assert world.driver_stops == 1, "Flow phải nhả driver Playwright"


def test_a_silent_menu_click_is_not_an_opened_module(monkeypatch, world):
    """Click menu mà WFX không đổi page/frame/document thì phải báo rõ."""
    wire_automation(monkeypatch, modules, world)
    _menu(monkeypatch, confirmed=False)

    result = _open()

    assert result["ok"] is False
    assert result["code"] == "MODULE_OPEN_NOT_CONFIRMED"
    # Người dùng không được thấy tiền tố kỹ thuật trong thông điệp.
    assert "MODULE_OPEN_NOT_CONFIRMED:" not in result["message"]
    assert "QA List" in result["message"]


def test_a_missing_menu_node_is_reported_as_not_found(monkeypatch, world):
    wire_automation(monkeypatch, modules, world)

    def missing(*_args):
        raise PlaywrightTimeoutError("Locator không tìm thấy node menu")

    monkeypatch.setattr(modules, "_open_module_menu", missing)

    result = _open()

    assert result["code"] == "MODULE_NOT_FOUND"
    assert result["module"] == "QA List"


def test_a_closed_browser_never_starts_a_driver(monkeypatch, world):
    wire_automation(monkeypatch, modules, world, chrome_ready=False)
    monkeypatch.setattr(
        modules,
        "_open_module_menu",
        lambda *_a: pytest.fail("Chrome đã đóng thì không được chạm menu"),
    )

    result = _open()

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


def test_a_visible_login_form_stops_before_touching_the_menu(monkeypatch, world):
    wire_automation(monkeypatch, modules, world)
    world.page.nodes["#txtUserID"] = [FakeNode(visible=True)]
    monkeypatch.setattr(
        modules,
        "_open_module_menu",
        lambda *_a: pytest.fail("Chưa đăng nhập thì không được click menu"),
    )

    result = _open()

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_stops == 1


def test_the_result_says_whether_the_route_cache_was_used(monkeypatch, world):
    wire_automation(monkeypatch, modules, world)
    _menu(monkeypatch, cache_hit=True)

    assert _open()["menu_cache_hit"] is True
