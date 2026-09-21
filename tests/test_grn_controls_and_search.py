"""Control form GRN và luồng Tìm GRN.

`grn/controls.py` (17%) và `grn/search.py` (16%) là hai file GRN chưa từng chạy
thân hàm. CLAUDE.md đặc tả rất cụ thể cho chính hai file này:

* "Tìm GRN … nhận Invoice ở `#row_txtDocNum` (checkbox `#chk_8` + ô
  `#txtDocNum`) hoặc RMPO/Order No. ở `#row_txtOrderNum` …, luôn bỏ tích Date ở
  dòng `#row_txtFromGRNDate` (checkbox `#chk_6`), Search trong `#ctrlRpt > table`
  (không phụ thuộc số thứ tự dòng)."
* "Bảng kết quả có hai hàng header; không click link `No.` gọi
  `ReOrder('GRNNum')`. Phải click link GRN của dòng dữ liệu có
  `onclick="PrintGRN(...)"` và chỉ trả thành công sau khi popup/document GRN mới
  đã thực sự mở."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.grn import controls as grn_controls
from wfx_panel.automation.grn import search as grn_search


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(
        monkeypatch, grn_controls, grn_search, _common
    )


def _quiet():
    return lambda _line: None


# --- _set_exact -----------------------------------------------------------


def test_set_exact_logs_once_the_control_accepted_the_value(monkeypatch):
    frame = MiniFrame(Element("body"))
    monkeypatch.setattr(
        grn_controls, "_set_control", lambda *a, **kw: {"ok": True}
    )
    logs: list[str] = []

    grn_controls._set_exact(frame, "#ddl", "ASN", "Receipt Type", logs.append)

    assert logs == ["[GRN] Đã chọn Receipt Type."]


def test_set_exact_raises_with_the_reason_wfx_gave(monkeypatch):
    frame = MiniFrame(Element("body"))
    monkeypatch.setattr(
        grn_controls,
        "_set_control",
        lambda *a, **kw: {"ok": False, "reason": "option_not_found"},
    )

    with pytest.raises(PlaywrightTimeoutError, match="option_not_found"):
        grn_controls._set_exact(frame, "#ddl", "ASN", "Receipt Type", _quiet())


# --- _click_action --------------------------------------------------------


def test_click_action_prefers_the_actionable_child():
    anchor = element("a", id="go")
    frame = MiniFrame(
        Element(
            "body",
            children=[Element("div", id="titlebar", children=[anchor])],
        )
    )

    grn_controls._click_action(frame, "#titlebar", "New")

    assert anchor.clicks == 1


def test_click_action_falls_back_to_the_container_itself():
    container = Element("div", id="titlebar")
    frame = MiniFrame(Element("body", children=[container]))

    grn_controls._click_action(frame, "#titlebar", "New")

    assert container.clicks == 1


def test_click_action_reports_a_missing_container():
    frame = MiniFrame(Element("body"))

    with pytest.raises(PlaywrightTimeoutError, match="Không tìm thấy nút New"):
        grn_controls._click_action(frame, "#titlebar", "New")


# --- _read_control_options ------------------------------------------------


def _options_frame(clock, payloads):
    queue = list(payloads)

    def read(spec):
        read.calls.append(dict(spec))
        return queue[0] if len(queue) == 1 else queue.pop(0)

    read.calls = []
    frame = MiniFrame(Element("body"), clock=clock)
    frame.scripts = {"spec.selector": read}
    frame.read = read
    return frame


def test_control_options_are_cleaned_and_deduped(clock):
    frame = _options_frame(clock, [["  Site   A ", "Site A", "Site B", "  "]])

    assert grn_controls._read_control_options(frame, "#CellID11") == [
        "Site A",
        "Site B",
    ]


def test_control_options_open_the_control_only_on_the_first_read(clock):
    frame = _options_frame(clock, [[], ["Site A"]])

    grn_controls._read_control_options(frame, "#CellID11")

    assert [call["open"] for call in frame.read.calls] == [True, False]


def test_control_options_return_empty_after_the_timeout(clock):
    frame = _options_frame(clock, [[]])

    assert grn_controls._read_control_options(frame, "#x", timeout_s=0.5) == []


def test_control_options_survive_a_script_failure(clock):
    frame = MiniFrame(Element("body"), clock=clock)
    frame.scripts = {
        "spec.selector": lambda _spec: (_ for _ in ()).throw(
            PlaywrightError("frame rơi")
        )
    }

    assert grn_controls._read_control_options(frame, "#x", timeout_s=0.5) == []


# --- _select_po_row -------------------------------------------------------


def test_select_po_row_uses_the_section_script():
    section = Element(
        "div",
        id="sectionOrderShipment",
        scripts={"PO": lambda rmpo: {"ok": rmpo == "RMPO-1"}},
    )
    frame = MiniFrame(Element("body", children=[section]))

    grn_controls._select_po_row(frame, "#sectionOrderShipment", "RMPO-1")


def test_select_po_row_reports_what_the_script_refused():
    section = Element(
        "div",
        id="sectionOrderShipment",
        scripts={"PO": lambda _rmpo: {"ok": False, "reason": "not_unique", "count": 3}},
    )
    frame = MiniFrame(Element("body", children=[section]))

    with pytest.raises(PlaywrightTimeoutError) as error:
        grn_controls._select_po_row(frame, "#sectionOrderShipment", "RMPO-1")

    assert "not_unique" in str(error.value)
    assert "count=3" in str(error.value)


def test_select_po_row_reports_a_missing_section():
    frame = MiniFrame(Element("body"))

    with pytest.raises(PlaywrightTimeoutError, match="Không tìm thấy bảng"):
        grn_controls._select_po_row(frame, "#sectionOrderShipment", "RMPO-1")


# --- _select_imported -----------------------------------------------------


def test_imported_is_ticked_through_the_host_script():
    host = Element("div", id="CellID14", scripts={"checkbox": lambda _a: True})
    frame = MiniFrame(Element("body", children=[host]))
    logs: list[str] = []

    grn_controls._select_imported(frame, logs.append)

    assert logs == ["[GRN] Đã chọn Imported."]


def test_imported_reports_when_wfx_never_confirms():
    host = Element("div", id="CellID14", scripts={"checkbox": lambda _a: False})
    frame = MiniFrame(Element("body", children=[host]))

    with pytest.raises(PlaywrightTimeoutError, match="chưa xác nhận Imported"):
        grn_controls._select_imported(frame, _quiet())


def test_imported_reports_a_missing_host():
    frame = MiniFrame(Element("body"))

    with pytest.raises(PlaywrightTimeoutError, match="Không tìm thấy lựa chọn"):
        grn_controls._select_imported(frame, _quiet())


# --- _wait_loading_finished ----------------------------------------------


def _loading_frame(clock, *, busy_until=0):
    overlay = Element("div", css_class="ag-overlay-loading-wrapper", visible=True)
    frame = MiniFrame(Element("body", children=[overlay]), clock=clock)
    frame.overlay = overlay
    frame.reads = 0
    original = frame.locator

    def locator(selector):
        if "ag-overlay-loading-wrapper" in selector:
            frame.reads += 1
            overlay.visible = frame.reads <= busy_until
        return original(selector)

    frame.locator = locator
    return frame


def test_loading_returns_once_the_overlay_stays_gone(clock):
    frame = _loading_frame(clock, busy_until=2)

    grn_controls._wait_loading_finished(frame)

    assert frame.reads > 2


def test_loading_times_out_while_the_overlay_stays(clock):
    frame = _loading_frame(clock, busy_until=10_000)

    with pytest.raises(PlaywrightTimeoutError, match="chưa tải xong"):
        grn_controls._wait_loading_finished(frame, timeout_s=1)


def test_loading_treats_a_broken_frame_as_still_busy(clock):
    frame = MiniFrame(Element("body"), clock=clock)

    def locator(_selector):
        raise PlaywrightError("frame rơi")

    frame.locator = locator

    with pytest.raises(PlaywrightTimeoutError):
        grn_controls._wait_loading_finished(frame, timeout_s=0.6)


# --- form tìm GRN ---------------------------------------------------------


class _SearchCheckbox(Element):
    """Checkbox WFX: chỉ tự tick khi ô cùng dòng có giá trị (hàm ChkIt)."""

    def __init__(self, field: Element) -> None:
        super().__init__("input", id="chk", attrs={"type": "checkbox"})
        self._field = field

    def is_checked(self, timeout=None):
        return bool(self._field.value)


def _search_frame(clock, *, results=(), report=True):
    doc_field = element("input", id="txtDocNum", attrs={"type": "text"})
    order_field = element("input", id="txtOrderNum", attrs={"type": "text"})
    doc_checkbox = _SearchCheckbox(doc_field)
    doc_checkbox.id = "chk_8"
    order_checkbox = _SearchCheckbox(order_field)
    order_checkbox.id = "chk_9"
    date_checkbox = Element(
        "input",
        id="chk_6",
        attrs={"type": "checkbox"},
        checked=True,
        scripts={
            "element.checked": lambda _a: date_checkbox.__setattr__(
                "checked", False
            )
            or False
        },
    )
    search_button = element(
        "input", id="btnSearch", attrs={"type": "button", "value": "Search"}
    )
    children = [
        doc_checkbox,
        doc_field,
        order_checkbox,
        order_field,
        date_checkbox,
        Element(
            "table",
            css_class="clsTable",
            children=[
                Element(
                    "tr",
                    css_class="clsDataLabel",
                    text=text,
                    children=[
                        element(
                            "a",
                            id=f"grn{index}",
                            attrs={"onclick": "PrintGRN('X')"},
                        )
                    ],
                )
                for index, text in enumerate(results)
            ],
        ),
    ]
    if report:
        children.insert(
            0,
            Element("div", id="ctrlRpt", children=[
                Element("table", children=[search_button])
            ]),
        )
    frame = MiniFrame(Element("body", children=children), clock=clock)
    frame.doc_field = doc_field
    frame.order_field = order_field
    frame.date_checkbox = date_checkbox
    frame.search_button = search_button
    return frame


def test_search_filter_fills_the_field_then_lets_wfx_sync_the_checkbox(clock):
    frame = _search_frame(clock)

    grn_search._set_grn_search_filter(frame, "invoice", "INV-1", enabled=True)

    assert frame.doc_field.fills == ["INV-1"]
    assert frame.doc_field.dispatched == ["change"]


def test_search_filter_reports_when_wfx_dropped_the_value(clock):
    frame = _search_frame(clock)
    frame.doc_field.on_fill = lambda node, _value: setattr(node, "value", "")

    with pytest.raises(PlaywrightTimeoutError, match="chưa xác nhận điều kiện"):
        grn_search._set_grn_search_filter(frame, "invoice", "INV-1", enabled=True)


def test_search_filter_reports_a_checkbox_wfx_did_not_sync(clock):
    frame = _search_frame(clock)

    with pytest.raises(PlaywrightTimeoutError, match="chưa đồng bộ checkbox"):
        grn_search._set_grn_search_filter(frame, "invoice", "INV-1", enabled=False)


def test_search_button_is_found_inside_the_report_block(clock):
    frame = _search_frame(clock)

    grn_search._click_grn_search(frame)

    assert frame.search_button.clicks == 1


def test_search_button_reports_a_missing_report_block(clock):
    frame = _search_frame(clock, report=False)

    with pytest.raises(PlaywrightTimeoutError, match="#ctrlRpt"):
        grn_search._click_grn_search(frame)


def test_search_button_reports_a_report_block_without_the_button(clock):
    frame = MiniFrame(
        Element("body", children=[Element("div", id="ctrlRpt")]), clock=clock
    )

    with pytest.raises(PlaywrightTimeoutError, match="nút Search"):
        grn_search._click_grn_search(frame)


# --- xác nhận cửa sổ GRN đã mở -------------------------------------------


class _ResultPage:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.bring_to_front_calls = 0

    def bring_to_front(self):
        self.bring_to_front_calls += 1

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


class _ResultContext:
    def __init__(self, pages):
        self.pages = list(pages)


def _result_frame(clock, url="https://wfx.test/PrintGRN.aspx"):
    frame = MiniFrame(Element("body"), url=url, clock=clock)
    return frame


def test_result_is_confirmed_when_a_new_document_appears(clock, monkeypatch):
    frame = _result_frame(clock)
    page = _ResultPage(clock, [frame])
    frame.page = page
    context = _ResultContext([page])
    monkeypatch.setattr(grn_search, "_context_frames", lambda _ctx: [frame])
    monkeypatch.setattr(grn_search, "_document_changed", lambda _f, _s: True)

    grn_search._wait_grn_result_opened(context, set(), {id(frame): (frame, "old")})

    assert page.bring_to_front_calls == 1


def test_a_blank_new_tab_is_not_accepted_as_the_grn_window(clock, monkeypatch):
    frame = _result_frame(clock, url="about:blank")
    page = _ResultPage(clock, [frame])
    frame.page = page
    context = _ResultContext([page])
    monkeypatch.setattr(grn_search, "_context_frames", lambda _ctx: [frame])

    with pytest.raises(PlaywrightTimeoutError, match="chưa mở cửa sổ GRN"):
        grn_search._wait_grn_result_opened(context, set(), {}, timeout_s=0.5)


def test_an_unchanged_document_is_not_accepted(clock, monkeypatch):
    frame = _result_frame(clock)
    page = _ResultPage(clock, [frame])
    frame.page = page
    context = _ResultContext([page])
    monkeypatch.setattr(grn_search, "_context_frames", lambda _ctx: [frame])
    monkeypatch.setattr(grn_search, "_document_changed", lambda _f, _s: False)

    with pytest.raises(PlaywrightTimeoutError):
        grn_search._wait_grn_result_opened(
            context, {id(page)}, {id(frame): (frame, "old")}, timeout_s=0.5
        )


# --- entry point ----------------------------------------------------------


@pytest.mark.parametrize("filter_kind", ["", "style", "buyer"])
def test_search_grn_refuses_an_unknown_filter(clock, filter_kind):
    assert (
        grn_search.search_grn_receipt(filter_kind, "X")["code"] == "INVALID_FILTER"
    )


@pytest.mark.parametrize(
    ("filter_kind", "label"),
    [("invoice", "Số Invoice"), ("rmpo", "RMPO No.")],
)
def test_search_grn_requires_a_query_with_the_right_label(
    clock, filter_kind, label
):
    result = grn_search.search_grn_receipt(filter_kind, "   ")

    assert result["code"] == "QUERY_REQUIRED"
    assert label in result["message"]


def _wire_search(monkeypatch, clock, frame, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, grn_search, world, chrome_ready=chrome_ready, clock=clock
    )
    monkeypatch.setattr(grn_search, "_open_menu_form", lambda *a, **kw: frame)
    monkeypatch.setattr(grn_search, "_context_frames", lambda _ctx: [frame])
    monkeypatch.setattr(
        grn_search, "_snapshot_context", lambda _ctx, _tag: (set(), {})
    )
    monkeypatch.setattr(grn_search, "_wait_grn_result_opened", lambda *a, **kw: None)
    return world


def test_search_grn_clears_the_other_condition_before_filling_its_own(
    clock, monkeypatch
):
    frame = _search_frame(clock, results=["GRN-1 INV-1"])
    world = _wire_search(monkeypatch, clock, frame)

    result = grn_search.search_grn_receipt("invoice", " INV-1 ", _quiet())

    assert result["code"] == "GRN_SEARCH_OPENED"
    assert result["filter_kind"] == "invoice"
    # Ô RMPO bị xóa trước, ô Invoice được điền sau.
    assert frame.order_field.fills == [""]
    assert frame.doc_field.fills == ["", "INV-1"]
    assert frame.date_checkbox.checked is False
    assert world.driver_stops == 1


def test_search_grn_clicks_only_the_print_grn_link(clock, monkeypatch):
    frame = _search_frame(clock, results=["GRN-1 INV-1"])
    _wire_search(monkeypatch, clock, frame)
    link = frame.locator("#grn0").node

    grn_search.search_grn_receipt("invoice", "INV-1", _quiet())

    assert link.clicks == 1


def test_search_grn_reports_no_result(clock, monkeypatch):
    frame = _search_frame(clock, results=[])
    _wire_search(monkeypatch, clock, frame)

    result = grn_search.search_grn_receipt("rmpo", "RMPO-9", _quiet())

    assert result["code"] == "GRN_SEARCH_NO_RESULTS"


def test_search_grn_still_opens_when_the_row_does_not_echo_the_query(
    clock, monkeypatch
):
    frame = _search_frame(clock, results=["Một dòng không có số"])
    _wire_search(monkeypatch, clock, frame)
    logs: list[str] = []

    result = grn_search.search_grn_receipt("invoice", "INV-1", logs.append)

    assert result["code"] == "GRN_SEARCH_OPENED"
    assert any("không hiển thị lại điều kiện" in line for line in logs)


def test_search_grn_reports_a_date_checkbox_it_could_not_untick(
    clock, monkeypatch
):
    frame = _search_frame(clock, results=["GRN-1"])
    frame.date_checkbox.scripts = {"element.checked": lambda _a: True}
    _wire_search(monkeypatch, clock, frame)

    result = grn_search.search_grn_receipt("invoice", "INV-1", _quiet())

    assert result["code"] == "GRN_SEARCH_FAILED"
    assert "Date" in result["message"]


def test_search_grn_maps_a_closed_browser_to_the_shared_boundary(
    clock, monkeypatch
):
    frame = _search_frame(clock)
    _wire_search(monkeypatch, clock, frame, chrome_ready=False)

    result = grn_search.search_grn_receipt("invoice", "INV-1", _quiet())

    assert result["code"] == "CHROME_CLOSED"


# --- nhánh chịu lỗi khi WFX thay frame giữa chừng -----------------------


def test_a_result_window_that_cannot_be_fronted_is_still_accepted(
    clock, monkeypatch
):
    """Cửa sổ GRN đã mở là đủ; không đưa được lên trước không phải lỗi."""
    frame = _result_frame(clock)

    class StubbornPage(_ResultPage):
        def bring_to_front(self):
            raise grn_search.PlaywrightError("target đã đóng")

    page = StubbornPage(clock, [frame])
    frame.page = page
    context = _ResultContext([page])
    monkeypatch.setattr(grn_search, "_context_frames", lambda _ctx: [frame])
    monkeypatch.setattr(grn_search, "_document_changed", lambda _f, _s: True)

    grn_search._wait_grn_result_opened(context, set(), {})


def test_a_filter_that_cannot_be_cleared_does_not_stop_the_search(
    clock, monkeypatch
):
    frame = _search_frame(clock, results=["GRN-1 INV-1"])
    _wire_search(monkeypatch, clock, frame)
    original = grn_search._set_grn_search_filter
    seen: list[tuple] = []

    def flaky(target, kind, query, *, enabled):
        seen.append((kind, enabled))
        if not enabled and kind == "rmpo":
            raise grn_search.PlaywrightError("ô RMPO đã biến mất")
        return original(target, kind, query, enabled=enabled)

    monkeypatch.setattr(grn_search, "_set_grn_search_filter", flaky)

    result = grn_search.search_grn_receipt("invoice", "INV-1", _quiet())

    assert result["code"] == "GRN_SEARCH_OPENED"
    assert ("rmpo", False) in seen


def test_a_frame_that_detaches_while_the_results_are_scanned_is_skipped(
    clock, monkeypatch
):
    frame = _search_frame(clock, results=["GRN-1 INV-1"])
    _wire_search(monkeypatch, clock, frame)

    class Detached:
        url = "https://wfx.test/detached"

        def locator(self, _selector):
            raise grn_search.PlaywrightError("frame đã detach")

    monkeypatch.setattr(
        grn_search, "_context_frames", lambda _ctx: [Detached(), frame]
    )

    assert (
        grn_search.search_grn_receipt("invoice", "INV-1", _quiet())["code"]
        == "GRN_SEARCH_OPENED"
    )


def test_a_row_that_cannot_be_read_back_does_not_stop_the_click(
    clock, monkeypatch
):
    from tests.fakes.mini_dom import Locator

    frame = _search_frame(clock, results=["GRN-1 INV-1"])
    _wire_search(monkeypatch, clock, frame)
    real_locator = Locator.locator

    def flaky(self, selector):
        if selector.startswith("xpath=ancestor::tr"):
            raise grn_search.PlaywrightError("dòng đã bị thay")
        return real_locator(self, selector)

    monkeypatch.setattr(Locator, "locator", flaky)

    assert (
        grn_search.search_grn_receipt("invoice", "INV-1", _quiet())["code"]
        == "GRN_SEARCH_OPENED"
    )
