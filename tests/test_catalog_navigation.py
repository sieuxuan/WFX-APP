"""Mở cây Catalog, chọn Category và click đúng node Master.

CLAUDE.md nói rõ: chỉ click node có action trực tiếp và text đúng bằng "Master",
không click icon collapse hay container; và nếu trang trung gian
`wfx_BaseSetting.aspx` không tạo frame cây thì mới được mở thẳng `RedirURL`,
với điều kiện URL cùng origin và đích đúng `WFX_CatalogMain.aspx`.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.catalog.navigation as navigation
from tests.fakes.mini_dom import Element, MiniFrame
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError

HOME = "https://wfx.test/wfx/default.aspx"
CATALOG_URL = "https://wfx.test/wfx/WFX_CatalogMain.aspx"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, navigation)


class TreeFrame(MiniFrame):
    """Frame cây Catalog; `reload()` mô phỏng WFX thay document tại chỗ."""

    def __init__(self, *args, goto_error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.goto_error = goto_error
        self.goto_calls: list[str] = []

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error


def _select(value="01", options=(("Apparel", "01"),)):
    """`option` phải là phần tử con thật thì `locator('option[...]')` mới thấy."""
    return Element(
        "select",
        id="ddlCategory",
        value=value,
        options=options,
        children=[
            Element("option", text=label, attrs={"value": option_value})
            for label, option_value in options
        ],
    )


def _tree(clock, *, value="01", url=CATALOG_URL, options=(("Apparel", "01"),), **kwargs):
    return TreeFrame(
        Element("body", children=[_select(value, options)]),
        url=url,
        clock=clock,
        **kwargs,
    )


class NavPage:
    def __init__(self, *frames, clock=None, url=HOME, named=None, nodes=None):
        self.frames = list(frames)
        self.clock = clock
        self.url = url
        self._named = dict(named or {})
        self.nodes = dict(nodes or {})

    def frame(self, name=None):
        return self._named.get(name)

    def locator(self, selector):
        return self.nodes[selector]

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


# --- nhận diện frame cây ------------------------------------------------


def test_a_module_tree_from_another_screen_is_not_the_catalog_tree(clock):
    supplier = _tree(clock, url="https://wfx.test/wfx/WFX_SupplierMain.aspx")

    assert navigation._is_catalog_tree_frame(supplier) is False


def test_a_catalog_url_without_the_category_dropdown_is_not_the_tree(clock):
    empty = TreeFrame(Element("body"), url=CATALOG_URL, clock=clock)

    assert navigation._is_catalog_tree_frame(empty) is False


def test_a_frame_that_throws_while_being_probed_is_not_the_tree():
    class Broken:
        url = CATALOG_URL

        def locator(self, _selector):
            raise PlaywrightError("frame đã detach")

    assert navigation._is_catalog_tree_frame(Broken()) is False


def test_the_frame_named_left_is_probed_first_but_is_not_trusted_blindly(clock):
    wrong = _tree(clock, url="https://wfx.test/wfx/WFX_SupplierMain.aspx")
    right = _tree(clock)
    page = NavPage(wrong, right, clock=clock, named={"left": wrong})

    assert navigation._catalog_tree_frame_now(page) is right


def test_a_page_without_any_catalog_tree_yields_nothing(clock):
    page = NavPage(
        _tree(clock, url="https://wfx.test/wfx/Other.aspx"), clock=clock
    )

    assert navigation._catalog_tree_frame_now(page) is None


def test_waiting_for_the_tree_gives_up_with_a_readable_message(clock):
    page = NavPage(clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="#ddlCategory"):
        navigation._catalog_left_frame(page, timeout_s=1)


def test_waiting_for_the_tree_returns_it_once_wfx_renders_it(clock):
    tree = _tree(clock)
    page = NavPage(clock=clock)

    def appear(_milliseconds):
        clock.advance(0.25)
        page.frames.append(tree)

    page.wait_for_timeout = appear

    assert navigation._catalog_left_frame(page, timeout_s=5) is tree


# --- mở thẳng trang Catalog --------------------------------------------


class MenuLink:
    def __init__(self, href, *, error=None):
        self.href = href
        self.error = error

    def get_attribute(self, _name):
        if self.error is not None:
            raise self.error
        return self.href


def _redirect(target=CATALOG_URL):
    return f"/wfx/wfx_BaseSetting.aspx?RedirURL={target}"


def test_the_direct_url_is_taken_from_the_menu_redirect(clock):
    page = NavPage(clock=clock)

    assert navigation._catalog_direct_url(page, MenuLink(_redirect())) == (
        CATALOG_URL
    )


@pytest.mark.parametrize(
    "href",
    [
        "",
        "/wfx/wfx_BaseSetting.aspx",
        _redirect("https://evil.example/wfx/WFX_CatalogMain.aspx"),
        _redirect("http://wfx.test/wfx/WFX_CatalogMain.aspx"),
        _redirect("https://wfx.test/wfx/WFX_SupplierMain.aspx"),
    ],
)
def test_a_redirect_that_is_not_the_catalog_page_on_this_origin_is_refused(
    clock, href
):
    page = NavPage(clock=clock)

    assert navigation._catalog_direct_url(page, MenuLink(href)) is None


def test_a_menu_link_that_cannot_be_read_yields_no_direct_url(clock):
    page = NavPage(clock=clock)
    link = MenuLink("", error=PlaywrightError("node đã bị thay"))

    assert navigation._catalog_direct_url(page, link) is None


class BodyElement:
    def __init__(self):
        self.assigned: list[str] = []

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        return None

    def evaluate(self, _script, url):
        self.assigned.append(url)


def test_navigating_the_body_frame_is_preferred_over_assigning_src(clock):
    body = _tree(clock)
    element = BodyElement()
    page = NavPage(
        clock=clock,
        named={"body": body},
        nodes={'frame[name="body"], iframe[name="body"]': element},
    )

    navigation._navigate_catalog_body_direct(page, CATALOG_URL)

    assert body.goto_calls == [CATALOG_URL]
    assert element.assigned == []


def test_a_navigation_that_times_out_is_left_to_the_tree_waiter(clock):
    body = _tree(clock, goto_error=PlaywrightTimeoutError("cold load"))
    element = BodyElement()
    page = NavPage(
        clock=clock,
        named={"body": body},
        nodes={'frame[name="body"], iframe[name="body"]': element},
    )

    navigation._navigate_catalog_body_direct(page, CATALOG_URL)

    assert element.assigned == [], "timeout không phải lý do để gán src"


def test_a_body_frame_that_refuses_to_navigate_falls_back_to_the_src(clock):
    body = _tree(clock, goto_error=PlaywrightError("frame đã detach"))
    element = BodyElement()
    page = NavPage(
        clock=clock,
        named={"body": body},
        nodes={'frame[name="body"], iframe[name="body"]': element},
    )

    navigation._navigate_catalog_body_direct(page, CATALOG_URL)

    assert element.assigned == [CATALOG_URL]


def test_a_page_object_without_a_frame_resolver_still_assigns_the_src(clock):
    element = BodyElement()
    page = NavPage(
        clock=clock, nodes={'frame[name="body"], iframe[name="body"]': element}
    )
    page.frame = None

    navigation._navigate_catalog_body_direct(page, CATALOG_URL)

    assert element.assigned == [CATALOG_URL]


# --- mở menu Catalog ----------------------------------------------------


def test_a_menu_that_answers_quickly_needs_no_direct_navigation(
    clock, monkeypatch
):
    tree = _tree(clock)
    page = NavPage(tree, clock=clock)
    clicked: list[str] = []
    patch_automation(
        monkeypatch, navigation, "_click", lambda _target: clicked.append("click")
    )
    patch_automation(
        monkeypatch,
        navigation,
        "_navigate_catalog_body_direct",
        lambda *_a: pytest.fail("Menu đã phản hồi thì không được mở thẳng URL"),
    )

    assert navigation._open_catalog_menu_on_page(
        page, MenuLink(_redirect()), print
    ) is tree
    assert clicked == ["click"]


def test_a_menu_that_hangs_falls_back_to_the_direct_catalog_url(
    clock, monkeypatch
):
    tree = _tree(clock)
    page = NavPage(clock=clock)
    patch_automation(monkeypatch, navigation, "_click", lambda _target: None)

    def navigate(_page, url):
        assert url == CATALOG_URL
        page.frames.append(tree)

    patch_automation(
        monkeypatch, navigation, "_navigate_catalog_body_direct", navigate
    )
    lines: list[str] = []

    assert navigation._open_catalog_menu_on_page(
        page, MenuLink(_redirect()), lines.append
    ) is tree
    assert any("mở trực tiếp trang Catalog" in line for line in lines)


def test_a_menu_that_hangs_without_a_usable_redirect_reports_the_timeout(
    clock, monkeypatch
):
    page = NavPage(clock=clock)
    patch_automation(monkeypatch, navigation, "_click", lambda _target: None)

    with pytest.raises(PlaywrightTimeoutError):
        navigation._open_catalog_menu_on_page(page, MenuLink(""), print)


# --- click Master -------------------------------------------------------


class MasterFrame(TreeFrame):
    def __init__(self, *args, outcomes=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = list(outcomes)
        self.master_queries = 0

    def get_by_text(self, text, exact=False):
        assert (text, exact) == ("Master", True)
        self.master_queries += 1
        outcome = (
            self.outcomes.pop(0)
            if len(self.outcomes) > 1
            else (self.outcomes[0] if self.outcomes else None)
        )
        return _MasterNode(outcome)


class _MasterNode:
    def __init__(self, outcome):
        self.outcome = outcome
        self.clicks: list[str] = []

    def wait_for(self, **_kwargs):
        if isinstance(self.outcome, BaseException):
            raise self.outcome

    def evaluate(self, script):
        self.clicks.append(script)


def _master_page(clock, *outcomes):
    frame = MasterFrame(
        Element("body", children=[Element("select", id="ddlCategory")]),
        url=CATALOG_URL,
        clock=clock,
        outcomes=list(outcomes),
    )
    return NavPage(frame, clock=clock), frame


def test_master_is_clicked_through_its_own_onclick_node(clock):
    page, frame = _master_page(clock, None)
    lines: list[str] = []

    navigation._click_catalog_master(page, lines.append)

    assert frame.master_queries == 1
    assert any("Đã tìm thấy Master" in line for line in lines)


def test_a_tree_that_reloads_mid_click_is_retried_not_abandoned(clock):
    page, frame = _master_page(
        clock, PlaywrightError("Execution context was destroyed"), None
    )

    navigation._click_catalog_master(page, print)

    assert frame.master_queries == 2


def test_a_master_that_never_appears_reports_the_last_error(clock):
    page, _frame = _master_page(clock, PlaywrightTimeoutError("không thấy node"))

    with pytest.raises(PlaywrightTimeoutError, match="Không click được Master"):
        navigation._click_catalog_master(page, print)


# --- chọn Category ------------------------------------------------------


def test_a_category_already_selected_is_not_touched_again(clock):
    tree = _tree(clock, value="01")
    page = NavPage(tree, clock=clock)
    lines: list[str] = []

    navigation._select_catalog_category_on_page(page, "Apparel", "01", lines.append)

    assert any("Đã ở sẵn Category" in line for line in lines)
    assert tree.root.children[0].dispatched == []


def test_changing_the_category_opens_the_dropdown_then_confirms_the_value(
    clock,
):
    tree = _tree(clock, value="02", options=(("Apparel", "01"), ("Trims", "03")))
    page = NavPage(tree, clock=clock)
    lines: list[str] = []

    navigation._select_catalog_category_on_page(page, "Apparel", "01", lines.append)

    select = tree.root.children[0]
    assert select.dispatched == ["mousedown"]
    assert select.selected == ["01"]
    assert any("Đã chọn: Apparel" in line for line in lines)


def test_a_category_wfx_never_confirms_is_reported(clock):
    tree = _tree(clock, value="02")
    select = tree.root.children[0]

    def refuse(value=None, **_kwargs):
        # WFX nhận thao tác nhưng không đổi giá trị thật.
        select.selected.append(value)

    select.select_option = refuse
    page = NavPage(tree, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="không xác nhận Category"):
        navigation._select_catalog_category_on_page(page, "Apparel", "01", print)


# --- mở cây và chọn Category -------------------------------------------


def test_an_already_open_tree_is_reused_instead_of_clicking_the_menu(
    clock, monkeypatch
):
    tree = _tree(clock)
    page = NavPage(tree, clock=clock)
    patch_automation(
        monkeypatch,
        navigation,
        "_open_catalog_menu_on_page",
        lambda *_a, **_k: pytest.fail("Cây đã mở thì không được click menu"),
    )
    lines: list[str] = []

    assert navigation._open_catalog_tree_on_page(
        page, "Apparel", "01", lines.append
    ) is tree
    assert any("dùng lại context hiện tại" in line for line in lines)


def test_a_closed_catalog_is_opened_from_the_menu_then_the_category_is_set(
    clock, monkeypatch
):
    tree = _tree(clock, value="02", options=(("Apparel", "01"),))
    link = MenuLink(_redirect())
    page = NavPage(clock=clock, nodes={f"xpath={navigation.CATALOG_XPATH}": link})
    link.wait_for = lambda **_kwargs: None
    opened: list[str] = []

    def open_menu(_page, _catalog, _log, previous_frame=None):
        opened.append("menu")
        page.frames.append(tree)
        return tree

    patch_automation(
        monkeypatch, navigation, "_open_catalog_menu_on_page", open_menu
    )
    lines: list[str] = []

    assert navigation._open_catalog_tree_on_page(
        page, "Apparel", "01", lines.append
    ) is tree
    assert opened == ["menu"]
    assert tree.root.children[0].selected == ["01"]
    assert any("Đang mở cây thư mục" in line for line in lines)


def test_a_tree_that_detaches_while_the_category_is_confirmed_is_retried(clock):
    tree = _tree(clock, value="02")
    select = tree.root.children[0]
    page = NavPage(tree, clock=clock)
    reads = {"n": 0}
    real_input_value = select.input_value

    def flaky(timeout=None):
        reads["n"] += 1
        if reads["n"] == 2:
            # Lần đọc xác nhận đầu tiên rơi đúng lúc WFX thay document.
            raise PlaywrightError("Execution context was destroyed")
        return real_input_value(timeout)

    select.input_value = flaky

    navigation._select_catalog_category_on_page(page, "Apparel", "01", print)

    assert reads["n"] >= 3
