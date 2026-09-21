from __future__ import annotations

import ast
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.wfx_dom import (
    BUYER_REFERENCE_FILTER,
    CODE_FILTER,
    FakeCatalogGrid,
    FakeCatalogTree,
    FakePage,
    FilterNode,
    MasterNode,
    StyleRow,
    install_fake_clock,
)
from wfx_panel.automation import catalog


class _CatalogAnchor:
    def __init__(self, href: str):
        self.href = href

    def get_attribute(self, name: str):
        return self.href if name == "href" else None


class _BodyElement:
    first = None

    def __init__(self):
        self.first = self
        self.waited = False
        self.navigation = None

    def wait_for(self, **_kwargs):
        self.waited = True

    def evaluate(self, _script, value):
        self.navigation = value


class _Page:
    url = "https://example.test/wfx/default.aspx"

    def __init__(self):
        self.body = _BodyElement()

    def locator(self, selector: str):
        assert selector == 'frame[name="body"], iframe[name="body"]'
        return self.body


def test_catalog_direct_url_uses_same_origin_redir_url():
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack"
        "&RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )

    assert catalog._catalog_direct_url(page, anchor) == (
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1"
    )


@pytest.mark.parametrize(
    "href",
    [
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack",
        (
            "wfx_BaseSetting.aspx?RedirURL="
            "https%3A%2F%2Fevil.test%2Fwfx%2FWFX_CatalogMain.aspx"
        ),
        "wfx_BaseSetting.aspx?RedirURL=AnotherModule.aspx",
    ],
)
def test_catalog_direct_url_rejects_missing_or_unsafe_targets(href):
    assert catalog._catalog_direct_url(_Page(), _CatalogAnchor(href)) is None


def test_catalog_menu_falls_back_to_direct_url_when_wrapper_does_not_load(
    monkeypatch,
):
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?MenuName=mnuTechpack"
        "&RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )
    expected_frame = object()
    waits = []
    clicked = []
    logs = []

    def wait_for_tree(_page, previous_frame=None, timeout_s=10):
        waits.append((previous_frame, timeout_s))
        if len(waits) == 1:
            raise catalog.PlaywrightTimeoutError("wrapper did not load")
        return expected_frame

    monkeypatch.setattr(catalog, "_catalog_left_frame", wait_for_tree)
    monkeypatch.setattr(catalog, "_click", lambda target: clicked.append(target))

    result = catalog._open_catalog_menu_on_page(
        page,
        anchor,
        logs.append,
        previous_frame="old-frame",
    )

    assert result is expected_frame
    assert clicked == [anchor]
    assert waits == [("old-frame", 3), ("old-frame", 30)]
    assert page.body.waited is True
    assert page.body.navigation == (
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1"
    )
    assert any("mở trực tiếp" in line for line in logs)


def test_catalog_menu_keeps_normal_navigation_when_wrapper_loads(monkeypatch):
    page = _Page()
    anchor = _CatalogAnchor(
        "wfx_BaseSetting.aspx?RedirURL=WFX_CatalogMain.aspx%3FCatalogType=1"
    )
    expected_frame = object()

    monkeypatch.setattr(catalog, "_click", lambda _target: None)
    monkeypatch.setattr(
        catalog,
        "_catalog_left_frame",
        lambda _page, previous_frame=None, timeout_s=10: expected_frame,
    )

    result = catalog._open_catalog_menu_on_page(page, anchor, lambda _line: None)

    assert result is expected_frame
    assert page.body.navigation is None


def test_catalog_tree_rejects_supplier_category_frame():
    class Locator:
        def count(self):
            return 1

    class Candidate:
        def __init__(self, url):
            self.url = url

        def locator(self, _selector):
            return Locator()

    supplier = Candidate(
        "https://example.test/WFXPartyGroup.aspx?PartyType=2"
    )
    catalog_tree = Candidate(
        "https://example.test/WFXArticleCatalog.aspx?CatalogType=1"
    )

    assert catalog._is_catalog_tree_frame(supplier) is False
    assert catalog._is_catalog_tree_frame(catalog_tree) is True


def test_catalog_left_accepts_same_frame_after_in_place_reload(monkeypatch):
    frame = object()
    monkeypatch.setattr(
        catalog,
        "_catalog_tree_frame_now",
        lambda _page: frame,
    )

    assert catalog._catalog_left_frame(
        object(),
        previous_frame=frame,
        timeout_s=0.1,
    ) is frame


def test_catalog_direct_navigation_prefers_live_body_frame():
    navigations = []

    class BodyFrame:
        def goto(self, url, **options):
            navigations.append((url, options))

    class Page:
        def frame(self, *, name):
            assert name == "body"
            return BodyFrame()

        def locator(self, _selector):
            raise AssertionError("DOM src fallback should not be used")

    catalog._navigate_catalog_body_direct(
        Page(),
        "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1",
    )

    assert navigations == [
        (
            "https://example.test/wfx/WFX_CatalogMain.aspx?CatalogType=1",
            {"wait_until": "domcontentloaded", "timeout": 15_000},
        )
    ]



@pytest.fixture
def clock(monkeypatch):
    """Đồng hồ ảo cho mọi deadline/stability window trong catalog.py."""
    return install_fake_clock(monkeypatch, catalog)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _grid_page(clock, grid: FakeCatalogGrid) -> FakePage:
    return FakePage(clock=clock, frames=[grid])


def _code_filter(**kwargs) -> FilterNode:
    return FilterNode(CODE_FILTER, **kwargs)


def _filter_flow(grid: FakeCatalogGrid, query: str, kind: str = "code") -> dict:
    lines, log = _logs()
    return catalog._filter_grid_and_maybe_open(grid, kind, query, log)


# --- Tiêu chí 1: Master ------------------------------------------------


def test_master_is_reclicked_on_the_same_actionable_node_after_tree_reloads(clock):
    """Click Master lần đầu chỉ reload cây; phải lấy lại document và click lại.

    Đặc tả cấm click IMG collapse hoặc container LI chỉ vì nó chứa chữ Master.
    ``FakeCatalogTree`` raise AssertionError cho mọi selector ngoài
    ``#ddlCategory``, nên test này đỏ ngay nếu ai đó thêm nhánh dò IMG/LI.
    """
    tree = FakeCatalogTree(clock, master=MasterNode(fail_wait_times=1))
    page = FakePage(clock=clock, frames=[tree], named_frames={"left": tree})
    lines, log = _logs()

    catalog._click_catalog_master(page, log)

    assert tree.master.clicks == 1
    assert tree.master.wait_calls == 2, "phải thử lại đúng node Master lần hai"
    assert tree.text_queries == [("Master", True), ("Master", True)]
    assert set(tree.selectors) == {"#ddlCategory"}
    assert any("Master" in line for line in lines)


def test_master_click_gives_up_with_a_timeout_instead_of_looping_forever(clock):
    tree = FakeCatalogTree(clock, master=MasterNode(fail_wait_times=10_000))
    page = FakePage(clock=clock, frames=[tree], named_frames={"left": tree})
    _lines, log = _logs()

    with pytest.raises(PlaywrightTimeoutError):
        catalog._click_catalog_master(page, log)

    assert tree.master.clicks == 0


# --- Tiêu chí 2: GRID_DATA_SETTLED -------------------------------------


def test_grid_data_ready_rejects_a_phantom_empty_grid(clock):
    """rawRows=0 mà không có no-rows overlay thì KHÔNG được coi là sẵn sàng."""
    grid = FakeCatalogGrid(clock, rows=[], loading=False, no_rows=False)

    with pytest.raises(PlaywrightTimeoutError):
        catalog._wait_catalog_grid_data_ready(grid, timeout_seconds=3)

    assert grid.poll_count > 1, "phải tiếp tục poll chứ không kết luận ngay"


def test_grid_data_ready_waits_longer_for_no_rows_than_for_real_rows(clock):
    """No-rows overlay dễ nhấp nháy nên cần cửa sổ ổn định dài hơn."""
    with_rows = FakeCatalogGrid(clock, rows=[StyleRow("ABC123")])
    started = clock.monotonic()
    catalog._wait_catalog_grid_data_ready(with_rows, timeout_seconds=10)
    rows_elapsed = clock.monotonic() - started

    empty = FakeCatalogGrid(clock, rows=[], no_rows=True)
    started = clock.monotonic()
    catalog._wait_catalog_grid_data_ready(empty, timeout_seconds=10)
    no_rows_elapsed = clock.monotonic() - started

    assert rows_elapsed == pytest.approx(0.6, abs=0.25)
    assert no_rows_elapsed == pytest.approx(1.8, abs=0.25)
    assert no_rows_elapsed > rows_elapsed


def test_grid_that_starts_loading_is_only_accepted_after_it_settles(clock):
    def bind_datasource(grid: FakeCatalogGrid, poll: int) -> None:
        if poll == 3:
            grid.loading = False
            grid.rows = [StyleRow("ABC123")]

    grid = FakeCatalogGrid(clock, rows=[], loading=True, on_poll=bind_datasource)

    catalog._wait_catalog_grid_data_ready(grid, timeout_seconds=10)

    assert grid.poll_count >= 6, "không được chấp nhận ngay lát đầu sau khi bind"


# --- Tiêu chí 3: FILTER_VISIBLE ----------------------------------------


def test_floating_filter_is_switched_on_when_the_row_is_hidden(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[_code_filter()],
        filter_row_visible=False,
    )
    page = _grid_page(clock, grid)
    lines, log = _logs()

    resolved = catalog._show_catalog_floating_filter(page, log, timeout_seconds=10)

    assert resolved is grid
    assert grid.show_filter_clicks == 1
    assert grid.filter_row_active() is True
    assert any("Floating Filter" in line for line in lines)


def test_visible_floating_filter_is_never_toggled_off_again(clock):
    """#showfloatingfilter là toggle: click lại sẽ TẮT filter đang dùng được."""
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[_code_filter()],
        filter_row_visible=True,
    )
    page = _grid_page(clock, grid)
    _lines, log = _logs()

    resolved = catalog._show_catalog_floating_filter(page, log, timeout_seconds=10)

    assert resolved is grid
    assert grid.show_filter_clicks == 0


def test_prepare_does_not_report_ready_while_the_grid_has_no_data(clock):
    """FILTER_VISIBLE chỉ hợp lệ SAU GRID_DATA_SETTLED, không phải trước."""
    grid = FakeCatalogGrid(
        clock,
        rows=[],
        filters=[_code_filter()],
        filter_row_visible=True,
        loading=False,
        no_rows=False,
    )
    page = _grid_page(clock, grid)
    _lines, log = _logs()

    with pytest.raises(PlaywrightTimeoutError):
        catalog._show_catalog_floating_filter(
            page,
            log,
            require_data_ready=True,
            timeout_seconds=2,
        )

    assert grid.poll_count > 1


# --- Tiêu chí 4: đếm unique Code ---------------------------------------


def test_thirty_two_cloned_row_nodes_count_as_one_unique_code(clock):
    """AG Grid giữ buffer/pinned/clone; UI thấy 1 Code thì kết quả phải là 1."""
    grid = FakeCatalogGrid(
        clock,
        rows=[
            StyleRow("ABC123", season="SS27", costsheet_status="Open")
            for _ in range(32)
        ],
        filters=[_code_filter()],
        filter_row_visible=True,
    )

    result = _filter_flow(grid, "ABC123")

    assert result["code"] == "RESULT_OPENED"
    assert result["codes"] == ["ABC123"]
    assert result["season"] == "SS27"
    assert result["internal_costsheet_status"] == "Open"
    assert grid.clicked_codes == ["ABC123"]


# --- Tiêu chí 5: FILTER_VALUE_CONFIRMED --------------------------------


def test_filter_value_not_confirmed_when_wfx_drops_the_typed_query(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[_code_filter(accepts_fill=False)],
        filter_row_visible=True,
    )

    result = _filter_flow(grid, "ABC123")

    assert result["ok"] is False
    assert result["code"] == "FILTER_VALUE_NOT_CONFIRMED"
    assert grid.poll_count == 0, "không được đọc kết quả khi giá trị chưa vào ô"
    assert grid.clicked_codes == []


# --- Grid rỗng giả trong lúc lọc: áp dụng lại bộ lọc đúng một lần ------


def test_phantom_empty_grid_is_recovered_by_reapplying_the_filter(clock):
    """Grid không loading, không no-rows, không row: WFX chưa nhận filter.

    Đúng một lần clear + điền lại; nếu không, người dùng nhận NO_RESULTS sai
    cho một Code có thật.
    """
    code = _code_filter()

    def rows_appear_only_after_refill(grid: FakeCatalogGrid, _poll: int) -> None:
        if code.fills.count("ABC123") >= 2:
            grid.rows = [StyleRow("ABC123", season="SS27")]

    grid = FakeCatalogGrid(
        clock,
        rows=[],
        filters=[code],
        filter_row_visible=True,
        on_poll=rows_appear_only_after_refill,
    )
    lines, log = _logs()

    result = catalog._filter_grid_and_maybe_open(grid, "code", "ABC123", log)

    assert result["code"] == "RESULT_OPENED"
    assert code.fills == ["ABC123", "", "ABC123"], "phải clear rồi điền lại"
    assert any("áp dụng lại bộ lọc" in line for line in lines)
    assert grid.clicked_codes == ["ABC123"]


def test_filter_is_reapplied_at_most_once_before_giving_up(clock):
    code = _code_filter()
    grid = FakeCatalogGrid(
        clock,
        rows=[],
        filters=[code],
        filter_row_visible=True,
    )
    _lines, log = _logs()

    result = catalog._filter_grid_and_maybe_open(grid, "code", "ABC123", log)

    assert result["ok"] is False
    assert result["code"] == "FILTER_RESULTS_NOT_READY"
    assert code.fills.count("") == 1, "chỉ được áp dụng lại bộ lọc một lần"


def test_reapplied_filter_that_wfx_drops_reports_value_not_confirmed(clock):
    class DroppingFilter(FilterNode):
        def fill(self, value, timeout=None):
            self.fills.append(value)
            # WFX nhận lần điền đầu rồi mất giá trị khi grid re-render.
            self.value = value if len(self.fills) == 1 else ""

    grid = FakeCatalogGrid(
        clock,
        rows=[],
        filters=[DroppingFilter(CODE_FILTER)],
        filter_row_visible=True,
    )
    _lines, log = _logs()

    result = catalog._filter_grid_and_maybe_open(grid, "code", "ABC123", log)

    assert result["ok"] is False
    assert result["code"] == "FILTER_VALUE_NOT_CONFIRMED"


def test_result_polling_starts_immediately_after_the_query_is_typed(clock):
    """Không được chờ cứng 1 giây trước lát poll đầu tiên."""
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[_code_filter()],
        filter_row_visible=True,
    )
    started = clock.monotonic()

    _filter_flow(grid, "ABC123")

    assert grid.poll_times, "phải có ít nhất một lát đọc kết quả"
    assert grid.poll_times[0] - started < 0.5


# --- Tiêu chí 6: 0 / 1 / nhiều Code ------------------------------------


def test_two_codes_stay_open_for_the_user_and_are_never_clicked(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC1"), StyleRow("ABC2")],
        filters=[_code_filter()],
        filter_row_visible=True,
    )

    result = _filter_flow(grid, "ABC")

    assert result["ok"] is True
    assert result["code"] == "MULTIPLE_RESULTS"
    assert result["codes"] == ["ABC1", "ABC2"]
    assert grid.clicked_codes == []


def test_no_rows_overlay_returns_no_results_without_clicking(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[],
        no_rows=True,
        filters=[_code_filter()],
        filter_row_visible=True,
    )

    result = _filter_flow(grid, "KHONGCO")

    assert result["ok"] is False
    assert result["code"] == "NO_RESULTS"
    assert grid.clicked_codes == []


def test_exact_code_opens_even_when_the_grid_still_renders_similar_codes(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123"), StyleRow("ABC1234")],
        filters=[_code_filter()],
        filter_row_visible=True,
    )

    result = _filter_flow(grid, "ABC123")

    assert result["code"] == "RESULT_OPENED"
    assert result["article_code"] == "ABC123"
    assert grid.clicked_codes == ["ABC123"]


# --- Tiêu chí 7: RESULT_DETACHED ---------------------------------------


def test_row_detached_right_before_the_click_returns_result_detached(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[_code_filter()],
        filter_row_visible=True,
        style_buttons_detached=True,
    )

    result = _filter_flow(grid, "ABC123")

    assert result["ok"] is False
    assert result["code"] == "RESULT_DETACHED"
    assert grid.clicked_codes == []


# --- Tiêu chí 8: quét ngang cột bị virtualize --------------------------


def test_code_filter_outside_the_viewport_is_found_and_stale_filters_cleared(clock):
    """Layout cột lưu theo user: Code có thể nằm ngoài viewport ngang.

    Điều kiện cũ ở cột đang bị virtualize cũng phải được xóa, nếu không kết quả
    lần tìm mới bị chồng filter cũ.
    """
    code = _code_filter(visible_from=600)
    stale = FilterNode(
        BUYER_REFERENCE_FILTER,
        value="PO-CU",
        visible_from=0,
        visible_to=400,
    )
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[code, stale],
        filter_row_visible=True,
        scroll_current=0,
        scroll_maximum=800,
        scroll_viewport=800,
    )

    resolved = catalog._resolve_catalog_filter(
        grid,
        catalog._CATALOG_FILTER_SPECS["code"],
    )

    assert resolved.node is code
    assert stale.value == "", "filter cũ ngoài viewport vẫn phải được xóa"
    assert stale.fills == [""]
    assert 600 in grid.scroll_history, "phải quét qua các vị trí scroll ngang"
    assert code.is_visible() is True, "phải dừng ở vị trí thấy được cột Code"


def test_missing_filter_column_raises_instead_of_filtering_the_wrong_column(clock):
    grid = FakeCatalogGrid(
        clock,
        rows=[StyleRow("ABC123")],
        filters=[FilterNode(BUYER_REFERENCE_FILTER)],
        filter_row_visible=True,
    )

    with pytest.raises(PlaywrightTimeoutError):
        catalog._resolve_catalog_filter(
            grid,
            catalog._CATALOG_FILTER_SPECS["code"],
        )


# --- Grid cũ còn trong page.frames -------------------------------------


def test_grid_inside_a_hidden_pane_is_not_accepted_as_the_live_grid(clock):
    """User chuyển module: Chromium còn giữ frame Catalog cũ vài giây."""
    hidden = FakeCatalogGrid(clock, rows=[StyleRow("ABC123")], frame_element_visible=False)
    page = _grid_page(clock, hidden)

    with pytest.raises(PlaywrightTimeoutError):
        catalog._catalog_grid_frame(page, timeout_seconds=1)

    assert hidden.frame_elements, "phải kiểm tra HTMLFrameElement ở document cha"
    assert all(node.disposed for node in hidden.frame_elements)


def test_visible_grid_frame_is_returned(clock):
    live = FakeCatalogGrid(clock, rows=[StyleRow("ABC123")], frame_element_visible=True)
    page = _grid_page(clock, live)

    assert catalog._catalog_grid_frame(page, timeout_seconds=1) is live


def test_detached_grid_frame_is_skipped(clock):
    stale = FakeCatalogGrid(clock, detached=True)
    live = FakeCatalogGrid(clock, rows=[StyleRow("ABC123")])
    page = FakePage(clock=clock, frames=[stale, live])

    assert catalog._catalog_grid_frame(page, timeout_seconds=1) is live


# --- Ràng buộc tĩnh: mọi flow mở Master mới đều phải chờ dữ liệu -------

# Hai fast-path được phép bỏ qua `require_data_ready` vì chúng KHÔNG mở Master
# mới: `_find_in_open_catalog` dùng lại grid user đang mở (readiness do vòng
# `_wait_catalog_grid_rows` lo), còn `filter_and_open_catalog_code` là entry
# point cũ chỉ còn re-export cho tương thích ngược, không nằm trong luồng app.
_FAST_PATHS_WITHOUT_DATA_READY = {
    "_find_in_open_catalog",
    "filter_and_open_catalog_code",
}


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    best = "<module>"
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        end = candidate.end_lineno or candidate.lineno
        if candidate.lineno <= node.lineno <= end:
            best = candidate.name
    return best


def test_every_flow_that_opens_master_waits_for_grid_data():
    """Đặc tả: FILTER_VISIBLE chỉ được báo sau GRID_DATA_SETTLED.

    Test hành vi phủ được một lời gọi; ràng buộc này nói về *mọi* call site nên
    phải quét AST, giống `test_cancellation_contract.py`.
    """
    tree = ast.parse(
        Path(catalog.__file__).read_text(encoding="utf-8"),
        filename=catalog.__file__,
    )
    offenders = []
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not isinstance(target, ast.Name):
            continue
        if target.id != "_show_catalog_floating_filter":
            continue
        owner = _enclosing_function(tree, node)
        if owner in _FAST_PATHS_WITHOUT_DATA_READY:
            continue
        checked += 1
        waits = any(
            keyword.arg == "require_data_ready"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
        if not waits:
            offenders.append(f"{owner} (dòng {node.lineno})")

    assert checked >= 5, "AST scan không còn thấy call site nào — test đã mục"
    assert not offenders, (
        "Các flow sau mở Master nhưng không chờ dữ liệu grid: "
        + ", ".join(offenders)
    )
