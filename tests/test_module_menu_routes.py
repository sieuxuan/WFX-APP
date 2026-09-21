"""Mở menu WFX: xác nhận navigation thật, và route cache cùng origin.

CLAUDE.md: một cú click menu KHÔNG được coi là `MODULE_OPENED`. Nếu click im
lặng sau 5 giây thì mới được mở thẳng `href` trong frame `target`, và route đó
chỉ được cache khi cùng origin — cache tự xoá khi login/Division đổi.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.modules.menu as menu
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError

HOME = "https://wfx.test/wfx/default.aspx"
TARGET = "https://wfx.test/wfx/WFX_OCList.aspx"
XPATH = '//*[@id="0004_0070_0010"]/a'


@pytest.fixture(autouse=True)
def clean_route_cache():
    menu._MENU_ROUTE_CACHE.clear()
    yield
    menu._MENU_ROUTE_CACHE.clear()


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, menu)


class MenuFrame:
    def __init__(self, name="body", *, url=HOME, goto_error=None):
        self.name = name
        self.url = url
        self.goto_error = goto_error
        self.goto_calls: list[str] = []
        self.markers: dict[str, str] = {}

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error

    def evaluate(self, script, arg=None):
        name = "__wfxPanelDocumentMarker"
        if name in script:
            if "=" in script.split(name, 1)[1][:4]:
                self.markers[name] = str(arg)
                return None
            return self.markers.get(name, "")
        raise AssertionError(f"script lạ: {script[:60]}")


class MenuPage:
    def __init__(self, *frames, url=HOME, clock=None, href=TARGET):
        self.frames = list(frames)
        self.url = url
        self.clock = clock
        self.href = href
        self.context = self

    @property
    def pages(self):
        return [self]

    def locator(self, _selector):
        return _MenuLink(self.href)

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class _MenuLink:
    def __init__(self, href):
        self.href = href

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        return None

    def get_attribute(self, name, **_kwargs):
        return {"href": self.href, "target": "body"}.get(name, "")

    def evaluate(self, script):
        if "href" in script:
            return self.href
        if "target" in script:
            return "body"
        raise AssertionError(f"script lạ: {script[:60]}")


# --- cùng origin --------------------------------------------------------


@pytest.mark.parametrize(
    ("page_url", "target_url", "same"),
    [
        (HOME, TARGET, True),
        (HOME, "https://evil.example/wfx/a.aspx", False),
        (HOME, "http://wfx.test/wfx/a.aspx", False),
        ("ftp://wfx.test/a", "ftp://wfx.test/b", False),
        ("", TARGET, False),
    ],
)
def test_only_a_same_origin_https_route_is_accepted(page_url, target_url, same):
    assert menu._same_origin(page_url, target_url) is same


def test_a_url_python_cannot_parse_is_refused():
    assert menu._same_origin(HOME, "https://[khong-hop-le") is False


# --- mở href trong frame target ----------------------------------------


def test_the_href_is_opened_in_the_frame_the_menu_named(clock):
    body = MenuFrame("body")
    page = MenuPage(MenuFrame("left"), body, clock=clock)

    assert menu._open_menu_href_in_target_frame(page, TARGET, "body") is True
    assert body.goto_calls == [TARGET]


@pytest.mark.parametrize(
    ("href", "frame_name"),
    [
        ("", "body"),
        (TARGET, ""),
        ("https://evil.example/wfx/a.aspx", "body"),
    ],
)
def test_a_route_without_a_usable_href_or_frame_is_refused(
    clock, href, frame_name
):
    page = MenuPage(MenuFrame("body"), clock=clock)

    assert (
        menu._open_menu_href_in_target_frame(page, href, frame_name) is False
    )


def test_a_frame_the_page_does_not_have_is_refused(clock):
    page = MenuPage(MenuFrame("left"), clock=clock)

    assert menu._open_menu_href_in_target_frame(page, TARGET, "body") is False


def test_a_navigation_that_fails_is_reported_as_not_opened(clock):
    body = MenuFrame("body", goto_error=PlaywrightError("navigation bị hủy"))
    page = MenuPage(body, clock=clock)

    assert menu._open_menu_href_in_target_frame(page, TARGET, "body") is False


# --- xác nhận navigation ------------------------------------------------


def test_a_brand_new_page_counts_as_navigation(clock, monkeypatch):
    page = MenuPage(MenuFrame("body"), clock=clock)
    patch_automation(
        monkeypatch, menu, "_context_pages", lambda _page: [page, page]
    )

    assert menu._wait_for_module_navigation(page, (), set(), 1, timeout_s=1)


def test_a_brand_new_frame_counts_as_navigation(clock):
    page = MenuPage(MenuFrame("body"), clock=clock)

    assert menu._wait_for_module_navigation(page, (), set(), 1, timeout_s=1)


def test_a_document_swap_inside_the_same_frame_counts_as_navigation(clock):
    body = MenuFrame("body")
    page = MenuPage(body, clock=clock)
    snapshot = menu._mark_document(body, "menu-test")
    body.markers.clear()

    assert menu._wait_for_module_navigation(
        page, [snapshot], {id(body)}, 1, timeout_s=2
    )


def test_a_menu_click_that_changes_nothing_is_not_navigation(clock):
    body = MenuFrame("body")
    page = MenuPage(body, clock=clock)
    snapshot = menu._mark_document(body, "menu-test")

    assert (
        menu._wait_for_module_navigation(
            page, [snapshot], {id(body)}, 1, timeout_s=1
        )
        is False
    )


def test_a_frame_that_detaches_is_itself_evidence_of_navigation(clock):
    class Detaching(MenuPage):
        @property
        def frames(self):
            raise PlaywrightError("frame đã detach")

        @frames.setter
        def frames(self, _value):
            return None

    page = Detaching(clock=clock)

    assert menu._wait_for_module_navigation(page, (), set(), 1, timeout_s=1)


# --- route cache --------------------------------------------------------


def _wire_open(monkeypatch, *, navigated, direct=True):
    calls: list[str] = []
    patch_automation(
        monkeypatch, menu, "_click", lambda _target: calls.append("click")
    )
    patch_automation(
        monkeypatch,
        menu,
        "_wait_for_module_navigation",
        lambda *_a, **_k: navigated,
    )
    patch_automation(
        monkeypatch,
        menu,
        "_open_menu_href_in_target_frame",
        lambda _page, href, name: calls.append(f"direct:{href}") or direct,
    )
    patch_automation(
        monkeypatch, menu, "_context_pages", lambda _page: [_page]
    )
    return calls


def test_a_menu_that_answers_the_click_is_not_cached(monkeypatch, clock):
    page = MenuPage(MenuFrame("body"), clock=clock)
    calls = _wire_open(monkeypatch, navigated=True)

    outcome = menu._open_module_menu(page, "OC List", XPATH, lambda _line: None)

    assert (outcome.confirmed, outcome.cache_hit) == (True, False)
    assert calls == ["click"]
    assert menu._MENU_ROUTE_CACHE == {}


def test_a_silent_menu_falls_back_to_the_direct_route_and_caches_it(
    monkeypatch, clock
):
    page = MenuPage(MenuFrame("body"), clock=clock)
    calls = _wire_open(monkeypatch, navigated=False)
    lines: list[str] = []

    outcome = menu._open_module_menu(page, "OC List", XPATH, lines.append)

    assert (outcome.confirmed, outcome.cache_hit) == (True, False)
    assert calls == ["click", f"direct:{TARGET}"]
    assert menu._MENU_ROUTE_CACHE[XPATH] == (TARGET, "body")
    assert any("route trực tiếp" in line for line in lines)


def test_a_cross_origin_route_is_used_once_but_never_cached(
    monkeypatch, clock
):
    page = MenuPage(MenuFrame("body"), clock=clock, href="https://evil.example/a.aspx")
    _wire_open(monkeypatch, navigated=False)

    menu._open_module_menu(page, "OC List", XPATH, lambda _line: None)

    assert menu._MENU_ROUTE_CACHE == {}


def test_a_direct_route_that_also_fails_reports_the_menu_as_unopened(
    monkeypatch, clock
):
    page = MenuPage(MenuFrame("body"), clock=clock)
    _wire_open(monkeypatch, navigated=False, direct=False)

    outcome = menu._open_module_menu(page, "OC List", XPATH, lambda _line: None)

    assert outcome.confirmed is False
    assert menu._MENU_ROUTE_CACHE == {}


def test_a_cached_route_skips_the_five_second_wait_entirely(monkeypatch, clock):
    page = MenuPage(MenuFrame("body"), clock=clock)
    menu._MENU_ROUTE_CACHE[XPATH] = (TARGET, "body")
    calls = _wire_open(monkeypatch, navigated=True)
    lines: list[str] = []

    outcome = menu._open_module_menu(page, "OC List", XPATH, lines.append)

    assert (outcome.confirmed, outcome.cache_hit) == (True, True)
    assert calls == [f"direct:{TARGET}"], "không được click menu lần nữa"
    assert any("route cache" in line for line in lines)


def test_a_cached_route_that_stopped_working_is_dropped_and_clicked_again(
    monkeypatch, clock
):
    page = MenuPage(MenuFrame("body"), clock=clock)
    menu._MENU_ROUTE_CACHE[XPATH] = (TARGET, "body")
    outcomes = [False, True]
    calls: list[str] = []
    patch_automation(
        monkeypatch, menu, "_click", lambda _target: calls.append("click")
    )
    patch_automation(
        monkeypatch, menu, "_wait_for_module_navigation", lambda *_a, **_k: True
    )
    patch_automation(
        monkeypatch,
        menu,
        "_open_menu_href_in_target_frame",
        lambda *_a: outcomes.pop(0) if outcomes else True,
    )
    patch_automation(monkeypatch, menu, "_context_pages", lambda _page: [_page])

    outcome = menu._open_module_menu(page, "OC List", XPATH, lambda _line: None)

    assert outcome.cache_hit is False
    assert calls == ["click"]
    assert XPATH not in menu._MENU_ROUTE_CACHE


# --- dấu hiệu xác nhận màn New -----------------------------------------


def test_the_destination_page_is_the_last_aspx_in_the_menu_href(clock):
    page = MenuPage(
        clock=clock,
        href=(
            "https://wfx.test/wfx/wfx_BaseSetting.aspx"
            "?RedirURL=WFX_OCNew.aspx&MenuName=OC_New"
        ),
    )

    markers = menu._menu_target_markers(page, XPATH)

    assert "wfx_ocnew.aspx" in markers
    assert "menuname=oc_new" in markers


def test_a_menu_link_that_cannot_be_read_yields_no_marker(clock):
    class Broken(MenuPage):
        def locator(self, _selector):
            raise PlaywrightError("node đã bị thay")

    assert menu._menu_target_markers(Broken(clock=clock), XPATH) == ()


def test_a_menu_link_without_any_aspx_yields_no_page_marker(clock):
    page = MenuPage(clock=clock, href="javascript:void(0)")

    assert menu._menu_target_markers(page, XPATH) == ()


# --- entry point open_module -------------------------------------------


class LoginField:
    def __init__(self, *, visible=False, count=1):
        self.visible = visible
        self._count = count

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self, **_kwargs):
        return self.visible

    def wait_for(self, **_kwargs):
        return None


class EntryPage(MenuPage):
    def __init__(self, *frames, login_visible=False, **kwargs):
        super().__init__(*frames, **kwargs)
        self.login_visible = login_visible

    def locator(self, selector):
        if selector == "#txtUserID":
            return LoginField(visible=self.login_visible)
        return _MenuLink(self.href)


def _wire_entry(monkeypatch, page, *, chrome_ready=True, **overrides):
    class Driver:
        def stop(self):
            return None

    patch_automation(
        monkeypatch, menu, "_chrome_is_ready", lambda: chrome_ready
    )
    patch_automation(
        monkeypatch,
        menu,
        "sync_playwright",
        lambda: type("Factory", (), {"start": staticmethod(Driver)})(),
    )
    patch_automation(
        monkeypatch,
        menu,
        "_connect_to_chrome",
        lambda _playwright, **_kwargs: ("browser", page),
    )
    patch_automation(
        monkeypatch, menu, "_attach_dialog_handler", lambda *_a: None
    )
    for name, value in overrides.items():
        patch_automation(monkeypatch, menu, name, value)


def test_opening_a_module_with_the_browser_closed_is_reported(
    monkeypatch, clock
):
    page = EntryPage(clock=clock)
    _wire_entry(monkeypatch, page, chrome_ready=False)

    assert menu.open_module("OC List", XPATH)["code"] == "CHROME_CLOSED"


def test_an_expired_session_is_seen_from_the_login_form(monkeypatch, clock):
    page = EntryPage(clock=clock, login_visible=True)
    _wire_entry(monkeypatch, page)

    assert menu.open_module("OC List", XPATH)["code"] == "NOT_LOGGED_IN"


def test_a_module_that_wfx_never_navigated_to_is_not_reported_as_opened(
    monkeypatch, clock
):
    page = EntryPage(clock=clock)
    _wire_entry(
        monkeypatch,
        page,
        _open_module_menu=lambda *_a: menu._MenuOpenResult(False, False),
    )
    lines: list[str] = []

    result = menu.open_module("OC List", XPATH, lines.append)

    assert result["code"] == "MODULE_OPEN_NOT_CONFIRMED"
    assert "OC List" in result["message"]
    assert result["module"] == "OC List"


def test_a_module_that_did_navigate_is_reported_with_its_cache_hit(
    monkeypatch, clock
):
    page = EntryPage(clock=clock)
    _wire_entry(
        monkeypatch,
        page,
        _open_module_menu=lambda *_a: menu._MenuOpenResult(True, True),
    )

    result = menu.open_module("OC List", XPATH, lambda _line: None)

    assert result["code"] == "MODULE_OPENED"
    assert result["menu_cache_hit"] is True
    assert result["url"] == HOME


def test_opening_catalog_also_clicks_master_and_shows_the_floating_filter(
    monkeypatch, clock
):
    grid = MenuFrame("grid", url="https://wfx.test/wfxcataloglist.aspx")
    page = EntryPage(grid, clock=clock)
    steps: list[str] = []
    _wire_entry(
        monkeypatch,
        page,
        _catalog_tree_frame_now=lambda _page: "left-frame",
        _open_catalog_menu_on_page=(
            lambda _page, _target, _log, previous_frame=None: steps.append(
                f"menu:{previous_frame}"
            )
        ),
        _click_catalog_master=(
            lambda _page, _log, previous_frame=None: steps.append(
                f"master:{previous_frame}"
            )
        ),
        _show_catalog_floating_filter=(
            lambda _page, _log, previous_frame=None: steps.append(
                f"filter:{previous_frame.name}"
            )
        ),
    )
    lines: list[str] = []

    result = menu.open_module("Catalog", XPATH, lines.append)

    assert result["code"] == "MODULE_OPENED"
    assert result["message"] == "Đã mở Catalog > Master và Floating Filter."
    assert result["menu_cache_hit"] is False
    assert steps == ["menu:left-frame", "master:left-frame", "filter:grid"]


def test_a_timeout_that_is_not_a_navigation_problem_is_a_missing_module(
    monkeypatch, clock
):
    page = EntryPage(clock=clock)

    def explode(*_args, **_kwargs):
        raise menu.PlaywrightTimeoutError("Không thấy node menu")

    _wire_entry(monkeypatch, page, _open_module_menu=explode)
    lines: list[str] = []

    result = menu.open_module("OC List", XPATH, lines.append)

    assert result["code"] == "MODULE_NOT_FOUND"
    assert "Không thấy node menu" in result["message"]
    assert lines[-1] == result["message"]


def test_an_unexpected_error_while_opening_names_its_type(monkeypatch, clock):
    page = EntryPage(clock=clock)

    def explode(*_args, **_kwargs):
        raise ValueError("selector lạ")

    _wire_entry(monkeypatch, page, _open_module_menu=explode)

    result = menu.open_module("OC List", XPATH, lambda _line: None)

    assert result["code"] == "MODULE_FAILED"
    assert result["message"].startswith("ValueError: ")


# --- tab WFX đang hoạt động --------------------------------------------


def test_the_active_page_helper_refuses_a_closed_browser(monkeypatch, clock):
    patch_automation(monkeypatch, menu, "_chrome_is_ready", lambda: False)

    with pytest.raises(RuntimeError, match="CHROME_CLOSED"):
        menu._active_wfx_page("driver", lambda _line: None)


def test_the_active_page_helper_refuses_an_expired_session(monkeypatch, clock):
    page = EntryPage(clock=clock, login_visible=True)
    _wire_entry(monkeypatch, page)

    with pytest.raises(RuntimeError, match="NOT_LOGGED_IN"):
        menu._active_wfx_page("driver", lambda _line: None)


def test_the_active_page_helper_returns_the_live_tab(monkeypatch, clock):
    page = EntryPage(clock=clock)
    _wire_entry(monkeypatch, page)

    assert menu._active_wfx_page("driver", lambda _line: None) == (
        "browser",
        page,
    )
