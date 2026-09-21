"""Nhận đúng popup Article rồi mở Costsheet/BOM mà không dựng lại driver/CDP.

CLAUDE.md cấm recycle Playwright vô điều kiện tại ranh giới popup Article: mỗi
`connect_over_cdp` mới re-attach mọi tab và làm Chrome nhấp banner "đang bị điều
khiển". Chỉ khi probe trên CDP hiện tại timeout mới được recycle đúng một lần.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.catalog.article as article
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError


@pytest.fixture
def clock(monkeypatch):
    clock = install_fake_clock(monkeypatch, article)
    # `_sleep` của `_common` ngủ thật; ở đây chỉ cần đẩy đồng hồ ảo.
    patch_automation(monkeypatch, article, "_sleep", clock.sleep)
    return clock


class Node:
    def __init__(self, *, count=1, wait_error=None):
        self._count = count
        self.wait_error = wait_error
        self.clicks: list[str] = []

    def count(self):
        return self._count

    def wait_for(self, **_kwargs):
        if self.wait_error is not None:
            raise self.wait_error

    def evaluate(self, script):
        self.clicks.append(script)

    def evaluate_all(self, _script):
        raise AssertionError("không dùng ở đây")


class LabelNode:
    def __init__(self, values, *, error=None):
        self.values = list(values)
        self.error = error

    def evaluate_all(self, _script):
        if self.error is not None:
            raise self.error
        return list(self.values)


class ArticleFrame:
    def __init__(self, nodes=None, *, url="https://wfx.test/ArticleTop.aspx"):
        self.nodes = dict(nodes or {})
        self.url = url

    def locator(self, selector):
        return self.nodes.get(selector, Node(count=0))


class ArticlePage:
    def __init__(self, *, url="https://wfx.test/Article.aspx", top=None, frames=None):
        self.url = url
        self._top = top
        self.frames = list(frames if frames is not None else ([top] if top else []))
        self.fronted = 0
        self.front_error: BaseException | None = None

    def frame(self, name=None):
        assert name == "ArticleTop"
        return self._top

    def bring_to_front(self):
        self.fronted += 1
        if self.front_error is not None:
            raise self.front_error


class Context:
    def __init__(self, *pages):
        self.pages = list(pages)


class Driver:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class Browser:
    def __init__(self, context=None):
        self.contexts = [context or Context()]


def _label(code):
    return LabelNode([f"F0001 (JACKET/{code})"])


def _article_page(code="ACEL", *, selector="#CostSheet", node=None, url=None):
    top = ArticleFrame(
        {
            "#lblArticleNameValue": _label(code),
            selector: node if node is not None else Node(),
        },
        url=url or "https://wfx.test/ArticleTop.aspx",
    )
    return ArticlePage(top=top), top


# --- xác nhận đúng Article Code ----------------------------------------


def test_an_empty_expected_code_accepts_any_popup():
    assert article._article_page_has_code(ArticlePage(), "") is True


def test_the_code_must_stand_alone_inside_the_header():
    page, _top = _article_page()
    page.frames = [
        ArticleFrame({"#lblArticleNameValue": LabelNode(["F0001 (JACKET/ACEL)"])})
    ]

    assert article._article_page_has_code(page, "acel") is True
    # `ACEL` nằm trong `ACELX` không được tính là khớp.
    assert article._article_page_has_code(page, "ACE") is False


def test_a_frame_that_cannot_be_read_is_skipped_not_fatal():
    page = ArticlePage(
        frames=[
            ArticleFrame(
                {
                    "#lblArticleNameValue": LabelNode(
                        [], error=PlaywrightError("frame đã detach")
                    )
                }
            ),
            ArticleFrame({"#lblArticleNameValue": LabelNode(["F0001 (X/ACEL)"])}),
        ]
    )

    assert article._article_page_has_code(page, "ACEL") is True


def test_a_page_without_any_frame_never_matches():
    assert article._article_page_has_code(ArticlePage(frames=[]), "ACEL") is False


# --- ảnh chụp trạng thái popup -----------------------------------------


def test_the_snapshot_records_both_page_and_article_top_urls():
    page, top = _article_page()
    plain = ArticlePage(url="https://wfx.test/List.aspx")

    states = article._article_navigation_states(Context(page, plain))

    assert states == [
        (page, page.url, top.url),
        (plain, plain.url, ""),
    ]


def test_a_context_without_pages_yields_no_state():
    assert article._article_navigation_states(Context()) == []


# --- mở Costsheet/BOM ---------------------------------------------------


def test_an_unsupported_destination_is_refused_outright(clock):
    with pytest.raises(ValueError, match="không hỗ trợ"):
        article._open_article_destination(Context(), "ho_so", [], print)


def test_the_destination_is_clicked_once_the_code_is_confirmed(clock):
    node = Node()
    page, _top = _article_page(node=node)
    lines: list[str] = []

    assert article._open_article_destination(
        Context(page),
        "costsheet",
        [],
        lines.append,
        expected_article_code="ACEL",
    ) == "Costsheet"
    assert node.clicks
    assert any("Đã mở Costsheet" in line for line in lines)


def test_a_popup_showing_another_style_is_never_used(clock):
    page, _top = _article_page(code="KHAC")

    with pytest.raises(PlaywrightTimeoutError, match="Costsheet"):
        article._open_article_destination(
            Context(page),
            "costsheet",
            [],
            print,
            timeout_seconds=2,
            expected_article_code="ACEL",
        )


def test_a_page_without_article_top_is_skipped(clock):
    plain = ArticlePage(url="https://wfx.test/List.aspx")
    page, _top = _article_page()

    assert article._open_article_destination(
        Context(plain, page),
        "costsheet",
        [],
        print,
        expected_article_code="ACEL",
    ) == "Costsheet"


def test_a_brand_new_tab_is_activated_so_wfx_renders_article_top(clock):
    old = ArticlePage(url="https://wfx.test/List.aspx")
    fresh, _top = _article_page(selector="#BOMMaster")
    lines: list[str] = []

    article._open_article_destination(
        Context(old, fresh),
        "bom",
        [(old, old.url, "")],
        lines.append,
        expected_article_code="ACEL",
    )

    assert fresh.fronted >= 1
    assert any("nhận tab Article mới" in line for line in lines)


def test_a_tab_that_refuses_to_come_forward_is_skipped_for_now(clock):
    fresh, _top = _article_page()
    fresh.front_error = PlaywrightError("target đã đóng")
    old = ArticlePage(url="https://wfx.test/List.aspx")

    with pytest.raises(PlaywrightTimeoutError):
        article._open_article_destination(
            Context(old, fresh),
            "costsheet",
            [(old, old.url, "")],
            print,
            timeout_seconds=1,
            expected_article_code="ACEL",
        )


def test_reopening_the_same_style_waits_out_a_short_grace_period(clock):
    """Click lại đúng style đang mở thì URL không đổi; caller cũ không có code."""
    page, top = _article_page()
    states = [(page, page.url, top.url)]
    started = clock.monotonic()

    assert article._open_article_destination(
        Context(page), "costsheet", states, print
    ) == "Costsheet"
    assert clock.monotonic() - started >= 1.5


def test_a_destination_button_that_is_not_rendered_yet_is_waited_for(clock):
    node = Node(count=0)
    page, _top = _article_page(node=node)

    with pytest.raises(PlaywrightTimeoutError):
        article._open_article_destination(
            Context(page),
            "costsheet",
            [],
            print,
            timeout_seconds=1,
            expected_article_code="ACEL",
        )


def test_a_button_that_detaches_while_being_clicked_is_retried(clock):
    node = Node(wait_error=PlaywrightError("node đã bị thay"))
    page, _top = _article_page(node=node)

    with pytest.raises(PlaywrightTimeoutError):
        article._open_article_destination(
            Context(page),
            "costsheet",
            [],
            print,
            timeout_seconds=1,
            expected_article_code="ACEL",
        )


def test_a_slow_wfx_tells_the_user_it_is_still_waiting(clock):
    plain = ArticlePage(url="https://wfx.test/List.aspx")
    lines: list[str] = []

    with pytest.raises(PlaywrightTimeoutError):
        article._open_article_destination(
            Context(plain),
            "costsheet",
            [],
            lines.append,
            timeout_seconds=20,
            expected_article_code="ACEL",
        )

    notices = [line for line in lines if "đang tải chậm" in line]
    assert len(notices) == 1, "chỉ được nhắc một lần, không spam log"


# --- dựng lại driver khi popup bị bỏ lỡ ---------------------------------


def test_refreshing_the_context_recycles_exactly_one_driver(monkeypatch):
    calls: list[str] = []
    patch_automation(
        monkeypatch,
        article,
        "invalidate_browser",
        lambda browser: calls.append(f"invalidate:{browser}"),
    )
    patch_automation(
        monkeypatch,
        article,
        "recycle_playwright",
        lambda playwright: calls.append("recycle") or "driver-moi",
    )
    patch_automation(
        monkeypatch,
        article,
        "_connect_to_chrome",
        lambda playwright, **kwargs: (
            calls.append(f"connect:{kwargs.get('bring_to_front')}"),
            ("browser-moi", "page-moi"),
        )[1],
    )
    patch_automation(
        monkeypatch,
        article,
        "_attach_dialog_handler",
        lambda _page, _log: calls.append("dialog"),
    )
    lines: list[str] = []

    result = article._refresh_article_context(
        "driver-cu", "browser-cu", "page-cu", lines.append
    )

    assert result == ("driver-moi", "browser-moi", "page-moi")
    assert calls == [
        "invalidate:browser-cu",
        "recycle",
        "connect:False",
        "dialog",
    ]
    assert any("driver mới" in line for line in lines)


# --- entry point --------------------------------------------------------


def _wire_open(monkeypatch, *, chrome_ready=True, logged_in=True, **overrides):
    calls: list[str] = []
    patch_automation(
        monkeypatch, article, "_chrome_is_ready", lambda: chrome_ready
    )
    patch_automation(
        monkeypatch,
        article,
        "sync_playwright",
        lambda: type("Factory", (), {"start": staticmethod(Driver)})(),
    )
    patch_automation(
        monkeypatch,
        article,
        "_connect_to_chrome",
        lambda _playwright, **_kwargs: (Browser(), "page"),
    )
    patch_automation(
        monkeypatch, article, "_attach_dialog_handler", lambda *_a: None
    )
    patch_automation(
        monkeypatch, article, "_session_is_active", lambda _page: logged_in
    )
    patch_automation(
        monkeypatch,
        article,
        "_open_article_destination",
        lambda *_a, **_k: calls.append("open") or "Costsheet",
    )
    patch_automation(
        monkeypatch,
        article,
        "_refresh_article_context",
        lambda *_a: calls.append("refresh") or (Driver(), Browser(), "page"),
    )
    for name, value in overrides.items():
        patch_automation(monkeypatch, article, name, value)
    return calls


@pytest.mark.parametrize(
    ("code", "destination", "expected"),
    [
        ("  ", "costsheet", "CATALOG_RESULT_REQUIRED"),
        ("F0001", "ho_so", "ARTICLE_DESTINATION_UNKNOWN"),
    ],
)
def test_bad_input_is_refused_before_the_browser_is_probed(
    monkeypatch, code, destination, expected
):
    calls = _wire_open(monkeypatch)

    assert (
        article.open_catalog_destination(code, destination)["code"] == expected
    )
    assert calls == []


def test_a_closed_browser_is_reported_without_starting_a_driver(monkeypatch):
    calls = _wire_open(monkeypatch, chrome_ready=False)

    assert (
        article.open_catalog_destination("F0001", "costsheet")["code"]
        == "CHROME_CLOSED"
    )
    assert calls == []


def test_an_expired_session_is_reported_before_touching_the_popup(monkeypatch):
    calls = _wire_open(monkeypatch, logged_in=False)

    assert (
        article.open_catalog_destination("F0001", "costsheet")["code"]
        == "NOT_LOGGED_IN"
    )
    assert calls == []


def test_a_popup_the_current_cdp_can_see_is_used_without_any_recycle(
    monkeypatch,
):
    calls = _wire_open(monkeypatch)

    result = article.open_catalog_destination("F0001", "costsheet")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert result["article_code"] == "F0001"
    assert calls == ["open"], "không được dựng driver mới khi probe đã thấy popup"


def test_a_popup_the_current_cdp_lost_triggers_exactly_one_recycle(monkeypatch):
    attempts: list[int] = []

    def probe(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise PlaywrightTimeoutError("ArticleTop không thấy")
        return "BOM"

    calls = _wire_open(monkeypatch, _open_article_destination=probe)

    result = article.open_catalog_destination("F0001", "bom")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert calls == ["refresh"]
    assert len(attempts) == 2


def test_a_popup_that_is_gone_for_good_tells_the_user_to_search_again(
    monkeypatch,
):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("ArticleTop không thấy")

    _wire_open(monkeypatch, _open_article_destination=explode)

    result = article.open_catalog_destination("F0001", "costsheet")

    assert result["code"] == "CATALOG_RESULT_EXPIRED"
    assert "bấm Tìm lại" in result["message"]


def test_an_unexpected_failure_names_its_type(monkeypatch):
    def explode(*_args, **_kwargs):
        raise ValueError("selector lạ")

    _wire_open(monkeypatch, _open_article_destination=explode)
    lines: list[str] = []

    result = article.open_catalog_destination(
        "F0001", "costsheet", lines.append
    )

    assert result["code"] == "CATALOG_DESTINATION_FAILED"
    assert result["message"].startswith("ValueError: ")
    assert lines[-1] == result["message"]


# --- chờ đúng popup của một Style ---------------------------------------


def test_the_popup_for_a_style_is_returned_with_its_article_top(clock):
    page, top = _article_page()

    assert article._article_page_for_code(Context(page), "ACEL") == (page, top)


def test_a_popup_of_another_style_is_not_accepted(clock):
    page, _top = _article_page(code="KHAC")

    with pytest.raises(PlaywrightTimeoutError, match="ACEL"):
        article._article_page_for_code(Context(page), "ACEL", timeout_seconds=1)


def test_a_page_without_article_top_is_ignored_while_waiting(clock):
    plain = ArticlePage(url="https://wfx.test/List.aspx")
    page, top = _article_page()

    assert article._article_page_for_code(
        Context(plain, page), "ACEL"
    ) == (page, top)


def test_a_popup_whose_body_never_attaches_is_not_accepted(clock):
    page, top = _article_page()
    top.nodes["body"] = Node(wait_error=PlaywrightError("body chưa render"))

    with pytest.raises(PlaywrightTimeoutError):
        article._article_page_for_code(Context(page), "ACEL", timeout_seconds=1)
