"""Vỏ 5 entry point Costing và luật chọn đúng tab Costing đang làm việc.

`costing.py` ở mức 24%: phần dựng plan/inventory đã có test, nhưng năm hàm tự
mở Playwright (`apply_costing_plan`, `scan_open_costing`,
`scan_active_open_costing`, `clear_active_costing_dependencies`,
`inspect_active_costing`) thì chưa từng chạy. Chính các vỏ đó quyết định những
ràng buộc CLAUDE.md đắt tiền nhất của module:

* "Import và Apply chỉ được bật khi Costing hiện tại có status chính xác là
  `Open`; nếu status khác `Open` hoặc chưa có Costing, app dừng với
  `COSTING_NOT_OPEN`."
* "Khi có nhiều tab/popup Costing, phải ưu tiên target đang hoạt động gần nhất,
  **không dùng thứ tự tạo trong `context.pages`**."
* "`Clear All Dependency` ... chỉ chạy với tab CostSheet `Open`, click toàn bộ
  link trùng id `#lnkClearDependency` trong đúng frame Costing rồi Save một lần."
* Apply là ranh giới ghi dữ liệu: khi hỏng, message tuyệt đối không được nói là
  đã Save thành công.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import (
    FakeContext,
    FakeFrame,
    FakePage,
    WfxWorld,
    wire_automation,
)
from tests.fakes.wfx_dom import FakeNode, install_fake_clock, patch_automation
from wfx_panel.automation import _common, costing

CLEAR_SELECTOR = '[id="lnkClearDependency"]'
TITLE_BAR_SELECTOR = "#titlebarCostSheet .clsPageTitleBarTitle"
TREE_TITLE_SELECTOR = "#treeCostSheet .clsTreeSelectedNode"
STYLE_CONTROLS_SELECTOR = ",".join(costing._STYLE_CODE_CONTROL_SELECTORS)


@pytest.fixture
def clock(monkeypatch):
    # `_sleep()` đọc `_common.time`, còn deadline của `_costing_frame()` đọc
    # `costing.time`; phải cùng một đồng hồ thì vòng chờ mới tiến đúng.
    return install_fake_clock(monkeypatch, costing, _common)


def _quiet():
    return lambda _line: None


def _text(value: str) -> FakeNode:
    node = FakeNode()
    node.text = value
    return node


def _frame(
    clock,
    *,
    tree_text: str = "",
    article_label: str = "",
    clear_links: int = 0,
    has_grid: bool = True,
    selected_title: str = "",
) -> FakeFrame:
    """Frame WFX khai báo đúng những selector mà costing.py thật sự dùng."""
    nodes: dict[str, list[FakeNode]] = {}
    empty: set[str] = set()

    def put(selector: str, items: list[FakeNode]) -> None:
        if items:
            nodes[selector] = items
        else:
            empty.add(selector)

    put(costing.COSTING_GRID_SELECTOR, [FakeNode()] if has_grid else [])
    put(costing.COSTING_DETAIL_SELECTOR, [])
    put(costing.COSTING_TREE_SELECTOR, [_text(tree_text)] if tree_text else [])
    put(costing.COSTING_NEW_SELECTOR, [])
    put(TITLE_BAR_SELECTOR, [])
    put(TREE_TITLE_SELECTOR, [_text(selected_title)] if selected_title else [])
    put(CLEAR_SELECTOR, [FakeNode() for _ in range(clear_links)])
    put("#lblArticleNameValue", [_text(article_label)] if article_label else [])
    put(STYLE_CONTROLS_SELECTOR, [])
    return FakeFrame(
        clock,
        name="body",
        url="https://wfx.test/wfx/WFX_CostSheet.aspx",
        nodes=nodes,
        empty_selectors=empty,
    )


def _plain_frame(clock) -> FakeFrame:
    """Tab WFX bình thường: không mang dấu hiệu Costing nào."""
    return FakeFrame(
        clock,
        name="body",
        url="https://wfx.test/wfx/default.aspx",
        empty_selectors={
            costing.COSTING_GRID_SELECTOR,
            costing.COSTING_DETAIL_SELECTOR,
            costing.COSTING_TREE_SELECTOR,
            costing.COSTING_NEW_SELECTOR,
            TITLE_BAR_SELECTOR,
            TREE_TITLE_SELECTOR,
            CLEAR_SELECTOR,
            "#lblArticleNameValue",
            STYLE_CONTROLS_SELECTOR,
        },
    )


def _page(clock, frames, *, visible: bool = True, focused: bool = False) -> FakePage:
    return FakePage(
        clock,
        frames,
        url="https://wfx.test/wfx/CatalogDetail.aspx",
        title="WFX",
        scripts={
            "document.visibilityState": {"visible": visible, "focused": focused},
            "window.opener": "",
        },
        empty_selectors={"#lblArticleNameValue"},
    )


def _costing_page(
    clock,
    *,
    status: str = "Open",
    code: str = "SKN0000188",
    clear_links: int = 0,
    visible: bool = True,
    focused: bool = False,
) -> tuple[FakePage, FakeFrame]:
    frame = _frame(
        clock,
        tree_text=f"Cost Sheet {status}" if status else "Cost Sheet",
        article_label=f"({code}/ACEL JACKET)" if code else "",
        clear_links=clear_links,
    )
    return _page(clock, [frame], visible=visible, focused=focused), frame


# --- Chọn đúng tab Costing đang làm việc --------------------------------


class _CdpSession:
    def __init__(self, context: _CdpContext, page: FakePage) -> None:
        self.context = context
        self.page = page
        self.detached = False

    def send(self, method: str, params=None):
        self.context.sent.append(method)
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": self.context.ids[id(self.page)]}}
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {"targetId": target_id, "type": "page"}
                    for target_id in self.context.recency
                ]
            }
        raise AssertionError(f"CDP giả chưa hỗ trợ: {method}")

    def detach(self) -> None:
        self.detached = True


class _CdpContext(FakeContext):
    """Context có CDP, trả target theo thứ tự hoạt động gần nhất của Chrome."""

    def __init__(self, pages, recency) -> None:
        super().__init__(pages)
        self.ids = {id(page): f"T{index}" for index, page in enumerate(pages)}
        self.recency = [self.ids[id(page)] for page in recency]
        self.sent: list[str] = []
        self.sessions: list[_CdpSession] = []

    def new_cdp_session(self, page: FakePage) -> _CdpSession:
        session = _CdpSession(self, page)
        self.sessions.append(session)
        return session


def test_a_tab_without_costing_is_never_chosen(clock):
    world = WfxWorld(clock, [_page(clock, [_plain_frame(clock)])])

    with pytest.raises(PlaywrightTimeoutError, match="COSTING_ACTIVE_TAB_NOT_FOUND"):
        costing._active_costing_page(world.context)


def test_a_hidden_costing_tab_is_never_chosen(clock):
    hidden, _unused = _costing_page(clock, visible=False)
    world = WfxWorld(clock, [hidden])

    with pytest.raises(PlaywrightTimeoutError, match="COSTING_ACTIVE_TAB_NOT_FOUND"):
        costing._active_costing_page(world.context)


def test_the_only_visible_costing_tab_is_chosen(clock):
    other = _page(clock, [_plain_frame(clock)])
    wanted, _unused = _costing_page(clock)
    world = WfxWorld(clock, [other, wanted])

    assert costing._active_costing_page(world.context) is wanted


def test_the_focused_tab_wins_over_another_visible_one(clock):
    background, _f1 = _costing_page(clock, focused=False)
    foreground, _f2 = _costing_page(clock, focused=True)
    world = WfxWorld(clock, [background, foreground])

    assert costing._active_costing_page(world.context) is foreground


def test_the_most_recent_target_wins_over_the_creation_order(clock):
    """CLAUDE.md: ưu tiên target hoạt động gần nhất, không theo `context.pages`."""
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    # Chrome báo tab tạo sau mới là tab hoạt động gần nhất.
    context = _CdpContext([first, second], recency=[second, first])

    assert costing._active_costing_page(context) is second, (
        "Lấy theo thứ tự tạo tab sẽ ghi Costing vào đúng style user vừa rời"
    )


def test_the_creation_order_is_not_silently_reversed_either(clock):
    """Dựng ngược lại để chắc kết quả đến từ CDP, không từ index cố định."""
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    context = _CdpContext([first, second], recency=[first, second])

    assert costing._active_costing_page(context) is first


def test_every_cdp_session_is_detached_after_ranking(clock):
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    context = _CdpContext([first, second], recency=[second, first])

    costing._active_costing_page(context)

    assert context.sessions and all(item.detached for item in context.sessions)


def test_two_costing_tabs_without_cdp_are_reported_as_ambiguous(clock):
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    world = WfxWorld(clock, [first, second])

    with pytest.raises(PlaywrightTimeoutError, match="COSTING_ACTIVE_TAB_AMBIGUOUS"):
        costing._active_costing_page(world.context)


def test_choosing_a_tab_never_brings_it_to_front(clock):
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    context = _CdpContext([first, second], recency=[second, first])

    costing._active_costing_page(context)

    assert first.bring_to_front_calls == 0
    assert second.bring_to_front_calls == 0
    assert "Target.activateTarget" not in context.sent


# --- Apply: điều kiện vào ----------------------------------------------


def test_a_plan_that_still_needs_a_new_costsheet_is_refused():
    error = costing._validate_costing_apply_request(
        "SKN0000188",
        {"new_required": True},
        None,
    )

    assert error is not None
    assert error["code"] == "COSTING_NOT_OPEN"


@pytest.mark.parametrize(
    "key",
    ["additions", "cost_line_additions", "splits", "deletes"],
)
def test_article_mutations_without_server_side_source_are_refused(key):
    error = costing._validate_costing_apply_request(
        "SKN0000188",
        {key: [{"item_key": "F1"}]},
        None,
    )

    assert error is not None
    assert error["code"] == "COSTING_SOURCE_REQUIRED"


def test_article_mutations_with_a_source_document_are_allowed():
    assert (
        costing._validate_costing_apply_request(
            "SKN0000188",
            {"additions": [{"item_key": "F1"}]},
            {"items": []},
        )
        is None
    )


def test_a_field_only_plan_needs_no_source_document():
    assert (
        costing._validate_costing_apply_request(
            "SKN0000188",
            {"fields_to_set": [{"key": "qty"}]},
            None,
        )
        is None
    )


# --- Ánh xạ lỗi quét ----------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "COSTING_ACTIVE_TAB_NOT_FOUND",
        "COSTING_ACTIVE_TAB_AMBIGUOUS",
        "COSTING_CONTEXT_NOT_FOUND",
    ],
)
def test_a_known_scan_failure_keeps_its_own_code(code):
    result = costing._costing_scan_error(
        PlaywrightTimeoutError(code),
        "SKN0000188",
        _quiet(),
    )

    assert result["code"] == code
    assert result["article_code"] == "SKN0000188"
    assert code not in result["message"], "Người dùng không đọc mã kỹ thuật"


def test_an_unknown_scan_failure_falls_back_and_is_logged():
    lines: list[str] = []

    result = costing._costing_scan_error(
        ValueError("WFX đổi DOM"),
        "SKN0000188",
        lines.append,
    )

    assert result["code"] == "COSTING_SCAN_FAILED"
    assert "ValueError" in result["message"]
    assert lines, "Lỗi lạ phải để lại dấu vết trong Log kỹ thuật"


# --- Vỏ entry point: ranh giới trình duyệt ------------------------------


def _entry_points():
    return {
        "apply_costing_plan": lambda: costing.apply_costing_plan(
            "SKN0000188",
            {"fields_to_set": [{"key": "qty"}]},
            log=_quiet(),
        ),
        "scan_open_costing": lambda: costing.scan_open_costing(
            "SKN0000188",
            log=_quiet(),
        ),
        "scan_active_open_costing": lambda: costing.scan_active_open_costing(
            log=_quiet(),
        ),
        "clear_active_costing_dependencies": (
            lambda: costing.clear_active_costing_dependencies(log=_quiet())
        ),
        "inspect_active_costing": lambda: costing.inspect_active_costing(log=_quiet()),
    }


@pytest.mark.parametrize("name", sorted(_entry_points()))
def test_a_closed_browser_is_reported_before_playwright_starts(
    monkeypatch,
    clock,
    name,
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world, chrome_ready=False)

    result = _entry_points()[name]()

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0, "Chrome đã đóng thì không dựng driver làm gì"


@pytest.mark.parametrize("name", sorted(_entry_points()))
def test_an_expired_session_always_releases_the_driver(monkeypatch, clock, name):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world, logged_in=False)

    result = _entry_points()[name]()

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_starts == 1
    assert world.driver_stops == 1, "Rò driver Playwright sẽ giữ CDP attach mãi"


# --- scan_open_costing --------------------------------------------------


@pytest.mark.parametrize("article_code", ["", "   ", None])
def test_a_scan_without_a_style_never_opens_the_browser(
    monkeypatch,
    clock,
    article_code,
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)

    result = costing.scan_open_costing(article_code, log=_quiet())

    assert result["code"] == "CATALOG_RESULT_REQUIRED"
    assert world.driver_starts == 0


@pytest.mark.parametrize("status", ["Approved", "Closed", "Cancelled"])
def test_only_an_open_costsheet_may_be_exported_for_import(
    monkeypatch,
    clock,
    status,
):
    """CLAUDE.md: status khác `Open` thì dừng với `COSTING_NOT_OPEN`."""
    page, _unused = _costing_page(clock, status=status)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.scan_open_costing(
        "SKN0000188",
        style_status={"internal_costsheet_status": status},
        log=_quiet(),
    )

    assert result["code"] == "COSTING_NOT_OPEN"
    assert result["costing_status"] == status
    assert result["style_name"] == "ACEL JACKET"


def test_a_style_without_any_costsheet_is_refused_for_import(monkeypatch, clock):
    page, _unused = _costing_page(clock, status="")
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.scan_open_costing("SKN0000188", log=_quiet())

    assert result["code"] == "COSTING_NOT_OPEN"
    assert result["costing_status"] == "Unknown"


def test_export_is_allowed_at_any_status(monkeypatch, clock):
    """CLAUDE.md: "Export được phép ở mọi Costing status"."""
    page, _unused = _costing_page(clock, status="Approved")
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)
    patch_automation(
        monkeypatch, costing,
        "_inventory_costing_frame",
        lambda *_a, **_k: {"sections": [{"key": "fabric"}], "items": [], "fields": []},
    )

    result = costing.scan_open_costing(
        "SKN0000188",
        require_open=False,
        log=_quiet(),
    )

    assert result["code"] == "COSTING_SCANNED"


def test_an_open_costsheet_is_scanned(monkeypatch, clock):
    page, _unused = _costing_page(clock)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)
    patch_automation(
        monkeypatch, costing,
        "_inventory_costing_frame",
        lambda *_a, **_k: {"sections": [{"key": "fabric"}], "items": [], "fields": []},
    )

    result = costing.scan_open_costing("SKN0000188", log=_quiet())

    assert result["code"] == "COSTING_SCANNED"
    assert result["section_count"] == 1
    assert world.driver_stops == 1


def test_an_unexpected_scan_failure_is_translated_for_the_user(monkeypatch, clock):
    page, _unused = _costing_page(clock)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi grid")

    patch_automation(monkeypatch, costing, "_scan_open_costing_context", boom)

    result = costing.scan_open_costing("SKN0000188", log=_quiet())

    assert result["code"] == "COSTING_SCAN_FAILED"
    assert world.driver_stops == 1


def test_a_costsheet_that_never_loads_is_not_exported(monkeypatch, clock):
    """Không được xuất workbook rỗng khi WFX chưa bind xong grid."""
    page, _unused = _costing_page(clock)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)
    patch_automation(
        monkeypatch, costing,
        "_inventory_costing_frame",
        lambda *_a, **_k: {"sections": [], "items": [], "fields": []},
    )

    result = costing.scan_open_costing("SKN0000188", log=_quiet())

    assert result["code"] == "COSTING_OPEN_NOT_LOADED"


# --- scan_active_open_costing / inspect_active_costing ------------------


def test_an_active_tab_without_a_style_code_stops(monkeypatch, clock):
    page, _unused = _costing_page(clock, code="")
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.scan_active_open_costing(log=_quiet())

    assert result["code"] == "COSTING_STYLE_NOT_DETECTED"
    assert world.driver_stops == 1


def test_the_active_tab_is_scanned_without_searching_again(monkeypatch, clock):
    wanted, _f1 = _costing_page(clock, focused=True)
    other, _f2 = _costing_page(clock, code="ABC9999999", visible=False)
    world = WfxWorld(clock, [other, wanted])
    wire_automation(monkeypatch, costing, world)
    scanned: list[str] = []

    def inventory(_frame_, article_code, **_kwargs):
        scanned.append(article_code)
        return {"sections": [{"key": "fabric"}], "items": [], "fields": []}

    patch_automation(monkeypatch, costing, "_inventory_costing_frame", inventory)

    result = costing.scan_active_open_costing(log=_quiet())

    assert result["code"] == "COSTING_SCANNED"
    assert scanned == ["SKN0000188"]
    assert other.bring_to_front_calls == 0
    assert wanted.bring_to_front_calls == 0


def test_scanning_two_visible_costing_tabs_stops_instead_of_guessing(
    monkeypatch,
    clock,
):
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, code="ABC9999999", focused=True)
    world = WfxWorld(clock, [first, second])
    wire_automation(monkeypatch, costing, world)
    patch_automation(
        monkeypatch, costing,
        "_inventory_costing_frame",
        lambda *_a, **_k: pytest.fail("Chưa rõ tab nào thì không được quét"),
    )

    result = costing.scan_active_open_costing(log=_quiet())

    assert result["code"] == "COSTING_ACTIVE_TAB_AMBIGUOUS"
    assert result["article_code"] == "", "Chưa chọn được tab thì chưa có style"
    assert world.driver_stops == 1


def test_inspecting_the_active_tab_reports_style_and_status(monkeypatch, clock):
    page, _unused = _costing_page(clock, status="Approved")
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.inspect_active_costing(log=_quiet())

    assert result["ok"] is True
    assert result["code"] == "COSTING_CONTEXT_INSPECTED"
    assert result["article_code"] == "SKN0000188"
    assert result["style_name"] == "ACEL JACKET"
    assert result["costing_status"] == "Approved", (
        "Export được phép ở mọi status nên inspect phải báo đúng status thật"
    )


def test_inspecting_a_tab_without_a_style_code_stops(monkeypatch, clock):
    page, _unused = _costing_page(clock, code="")
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.inspect_active_costing(log=_quiet())

    assert result["code"] == "COSTING_STYLE_NOT_DETECTED"


def test_two_visible_costing_tabs_ask_the_user_to_pick_one(monkeypatch, clock):
    first, _f1 = _costing_page(clock, focused=True)
    second, _f2 = _costing_page(clock, focused=True)
    world = WfxWorld(clock, [first, second])
    wire_automation(monkeypatch, costing, world)

    result = costing.inspect_active_costing(log=_quiet())

    assert result["code"] == "COSTING_ACTIVE_TAB_AMBIGUOUS"
    assert world.driver_stops == 1


# --- Clear All Dependency ----------------------------------------------


@pytest.fixture
def saves(monkeypatch):
    calls: list[tuple] = []
    patch_automation(
        monkeypatch, costing,
        "_save_costing",
        lambda page, frame, log: calls.append((page, frame)),
    )
    return calls


@pytest.mark.parametrize("status", ["Approved", "Closed", ""])
def test_clear_dependency_refuses_a_costsheet_that_is_not_open(
    monkeypatch,
    clock,
    saves,
    status,
):
    page, frame = _costing_page(clock, status=status, clear_links=3)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert result["code"] == "COSTING_NOT_OPEN"
    assert saves == [], "Không Open thì tuyệt đối không được Save"
    assert all(node.clicks == 0 for node in frame.nodes[CLEAR_SELECTOR])


def test_a_costsheet_without_dependency_links_succeeds_without_saving(
    monkeypatch,
    clock,
    saves,
):
    page, _unused = _costing_page(clock, clear_links=0)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert result["ok"] is True
    assert result["code"] == "COSTING_DEPENDENCIES_ALREADY_CLEAR"
    assert result["cleared_section_count"] == 0
    assert saves == []


def test_every_dependency_link_is_clicked_once_then_saved_once(
    monkeypatch,
    clock,
    saves,
):
    page, frame = _costing_page(clock, clear_links=3)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert result["code"] == "COSTING_DEPENDENCIES_CLEARED"
    assert result["cleared_section_count"] == 3
    assert [node.clicks for node in frame.nodes[CLEAR_SELECTOR]] == [1, 1, 1]
    assert len(saves) == 1, "CLAUDE.md: Save đúng một lần sau khi clear hết"
    assert saves[0] == (page, frame)


class _Dialog:
    """Hộp xác nhận WFX bật ra sau mỗi lần bấm Clear Dependency."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True


def test_each_clear_confirmation_is_accepted_and_reported(monkeypatch, clock, saves):
    page, frame = _costing_page(clock, clear_links=2)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)
    dialogs: list[_Dialog] = []

    def arm(index: int, node: FakeNode) -> None:
        original = node.evaluate

        def click(script, arg=None):
            dialog = _Dialog(f"Clear dependency of section {index + 1}?")
            dialogs.append(dialog)
            for event, handler in list(page.dialog_handlers):
                if event == "dialog":
                    handler(dialog)
            return original(script, arg)

        node.evaluate = click

    for index, node in enumerate(frame.nodes[CLEAR_SELECTOR]):
        arm(index, node)

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert len(dialogs) == 2
    assert all(dialog.accepted for dialog in dialogs), (
        "Không accept thì WFX đứng ở confirm và không section nào được clear"
    )
    assert result["confirmations"] == [dialog.message for dialog in dialogs]


def test_the_clear_dialog_listener_is_always_removed(monkeypatch, clock, saves):
    page, _unused = _costing_page(clock, clear_links=2)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    costing.clear_active_costing_dependencies(log=_quiet())

    assert page.dialog_handlers == [], (
        "Handler còn sót sẽ tự accept dialog nghiệp vụ của lượt chạy sau"
    )


def test_a_dependency_link_that_disappears_mid_run_stops_the_flow(
    monkeypatch,
    clock,
    saves,
):
    page, frame = _costing_page(clock, clear_links=3)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)
    links = frame.nodes[CLEAR_SELECTOR]
    original = links[0].evaluate

    def vanish(script, arg=None):
        frame.set_nodes(CLEAR_SELECTOR, links[:1])
        return original(script, arg)

    links[0].evaluate = vanish

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert result["code"] == "COSTING_CLEAR_DEPENDENCY_TARGET_CHANGED"
    assert saves == [], "Chưa clear hết section thì không được Save"
    assert page.dialog_handlers == []


def test_an_unexpected_clear_failure_never_claims_a_save(monkeypatch, clock):
    page, _unused = _costing_page(clock, clear_links=1)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, costing, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi titlebar")

    patch_automation(monkeypatch, costing, "_save_costing", boom)

    result = costing.clear_active_costing_dependencies(log=_quiet())

    assert result["ok"] is False
    assert result["code"] == "COSTING_CLEAR_FAILED"
    assert result["article_code"] == "SKN0000188"
    assert "chưa xác nhận Save" in result["message"]
    assert world.driver_stops == 1


# --- apply_costing_plan -------------------------------------------------


def _apply(plan=None):
    return costing.apply_costing_plan(
        "SKN0000188",
        {"fields_to_set": [{"key": "qty"}]} if plan is None else plan,
        log=_quiet(),
    )


def test_an_empty_plan_is_reported_without_saving(monkeypatch, clock):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)
    patch_automation(
        monkeypatch, costing,
        "_open_costing_apply_session",
        lambda *_a, **_k: costing._CostingApplySession(
            article_code="SKN0000188",
            browser=world.browser,
            context=world.context,
            costing_page=world.page,
            frame=None,
            scoped_pages=None,
            live={},
            working_plan={},
            source_document=None,
            log=_quiet(),
        ),
    )
    patch_automation(
        monkeypatch, costing,
        "_save_costing",
        lambda *_a: pytest.fail("Plan rỗng thì không được Save"),
    )

    result = _apply(plan={})

    assert result["ok"] is True
    assert result["no_changes"] is True
    assert result["applied_count"] == 0
    assert "không cần Save" in result["message"]


def test_a_stale_plan_stops_before_writing(monkeypatch, clock):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)
    stale = costing._result(
        False,
        "COSTING_PLAN_STALE",
        "Costing đã thay đổi sau dry-run.",
    )

    def abort(*_args, **_kwargs):
        raise costing.CostingApplyAbort(stale)

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", abort)

    result = _apply()

    assert result is stale
    assert world.driver_stops == 1


def test_a_costsheet_that_left_open_stops_the_apply(monkeypatch, clock):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)

    def abort(*_args, **_kwargs):
        raise costing.CostingApplyAbort(
            costing._result(
                False,
                "COSTING_NOT_OPEN",
                "CostSheet không còn ở trạng thái Open.",
                article_code="SKN0000188",
            )
        )

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", abort)

    assert _apply()["code"] == "COSTING_NOT_OPEN"


def test_a_plan_error_keeps_its_own_code_and_data(monkeypatch, clock):
    """`CostingPlanError` đã mang sẵn mã + chi tiết cho UI; không được nuốt."""
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)

    def boom(*_args, **_kwargs):
        raise costing.CostingPlanError(
            "COSTING_ARTICLE_AMBIGUOUS",
            "Có nhiều Article khớp; hãy chọn Article Code.",
            candidates=["F-001", "F-002"],
        )

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", boom)

    result = _apply()

    assert result["code"] == "COSTING_ARTICLE_AMBIGUOUS"
    assert result["candidates"] == ["F-001", "F-002"]
    assert world.driver_stops == 1


def test_a_field_that_cannot_be_filled_names_the_field_and_article(
    monkeypatch,
    clock,
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)

    def boom(*_args, **_kwargs):
        raise costing.CostingFieldApplyError(
            field_key="fabric.qty",
            item_key="F-001",
            reason="control read-only",
        )

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", boom)

    result = _apply()

    assert result["code"] == "COSTING_FIELD_APPLY_FAILED"
    assert result["failed_field"] == "fabric.qty"
    assert result["failed_item"] == "F-001"
    assert result["failure_reason"] == "control read-only"
    assert "fabric.qty" in result["message"]
    assert "F-001" in result["message"]


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        ("COSTING_PLAN_STALE", "COSTING_PLAN_STALE"),
        ("Timeout 30000ms exceeded", "COSTING_APPLY_FAILED"),
    ],
)
def test_a_timeout_keeps_a_costing_code_but_never_invents_one(
    monkeypatch,
    clock,
    raised,
    expected,
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)

    def boom(*_args, **_kwargs):
        raise PlaywrightTimeoutError(raised)

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", boom)

    assert _apply()["code"] == expected


def test_an_unexpected_apply_failure_never_claims_a_save(monkeypatch, clock):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, costing, world)
    lines: list[str] = []

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi editor")

    patch_automation(monkeypatch, costing, "_open_costing_apply_session", boom)

    result = costing.apply_costing_plan(
        "SKN0000188",
        {"fields_to_set": [{"key": "qty"}]},
        log=lines.append,
    )

    assert result["ok"] is False
    assert result["code"] == "COSTING_APPLY_FAILED"
    assert "chưa xác nhận Save thành công" in result["message"]
    assert lines, "Lỗi lạ khi ghi Costing phải vào Log kỹ thuật"
    assert world.driver_stops == 1
