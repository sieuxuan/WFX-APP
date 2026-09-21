"""Report Viewer: mở tab report, đọc/đặt tham số, View Report và export Excel.

`wfx_panel/automation/reports.py` ở mức 33%. CLAUDE.md đặt ra đúng những ràng
buộc mà phần chưa chạy đang giữ:

* "Reports chỉ dùng một tab report riêng ngoài tab WFX chính. Nếu đúng report
  đang mở và bảng tham số còn sẵn sàng thì phải tái sử dụng DOM hiện tại; khi
  đổi report, điều hướng tab report đó thay vì tạo thêm tab. Probe stale/lỗi
  phải fallback về reload đầy đủ, không được trả thành công từ context cũ."
* "Các probe chỉ đọc … phải dùng `bring_to_front=False`, không được kéo user
  khỏi tab Costing."
* Download phải đi qua `snapshot_downloads()`/`wait_for_native_download()` —
  không dùng artifact tạm của Playwright.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common, reports

PARAM_TABLE_ID = "ParameterTable_rptCustomReportViewer_ctl04"
VIEW_BUTTON_ID = "rptCustomReportViewer_ctl04_ctl00"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, reports, _common)


def _quiet():
    return lambda _line: None


class _Page(MiniFrame):
    """Tab Chrome giả dựng trên mini_dom."""

    def __init__(self, clock, root=None, *, url="https://wfx.test/other.aspx"):
        super().__init__(root or Element("body"), url=url, clock=clock)
        self.closed = False
        self.bring_to_front_calls = 0
        self.goto_calls: list[str] = []
        self.listeners: list[tuple] = []
        self.context = None

    def _install(self, root):
        self.root = root
        self._document = Element("#document", children=[root])

    def is_closed(self):
        return self.closed

    def bring_to_front(self):
        self.bring_to_front_calls += 1

    def goto(self, url, **_kwargs):
        """Navigation thật: thay hẳn document bằng DOM của trang đích."""
        self.goto_calls.append(url)
        self.url = url
        if "wfxbicustomreportview.aspx" in url.casefold():
            self._install(
                Element(
                    "body",
                    children=[_parameter_table([element("input", id="p1")])],
                )
            )

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)
        self.listeners: list[tuple] = []
        self.new_pages = 0
        for page in self.pages:
            page.context = self

    def new_page(self):
        self.new_pages += 1
        page = _Page(self.pages[0].clock)
        page.context = self
        self.pages.append(page)
        return page

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))


def _report_id() -> str:
    return next(iter(reports.REPORTS))


def _report() -> dict:
    return reports.REPORTS[_report_id()]


def _report_url() -> str:
    """URL thật của report — `_open_report` goto đúng chuỗi này."""
    return str(_report()["url"])


def _report_page_url() -> str:
    return (
        "https://wfx.test/WFXBICustomReportView.aspx?BICustomReportID="
        + str(_report()["custom_report_id"])
    )


def _parameter_table(controls=(), scripts=None) -> Element:
    return Element(
        "table",
        id=PARAM_TABLE_ID,
        children=[Element("tbody", children=list(controls))],
        scripts=scripts,
    )


def _report_page(clock, *, controls=(), url=None, extra=(), scripts=None) -> _Page:
    root = Element(
        "body", children=[_parameter_table(controls, scripts), *extra]
    )
    return _Page(clock, root, url=url or _report_page_url())


# --- danh mục -------------------------------------------------------------


def test_the_catalog_exposes_id_name_and_kind_for_every_report():
    catalog = reports.report_catalog()

    assert catalog
    assert all({"id", "name", "kind"} <= set(row) for row in catalog)
    assert {row["id"] for row in catalog} == set(reports.REPORTS)


def test_an_unknown_report_id_resolves_to_nothing():
    assert reports._report("  ") is None
    assert reports._report("khong-co") is None
    assert reports._report(_report_id()) is not None


# --- nhận diện tab report -------------------------------------------------


def test_a_report_page_is_recognised_by_its_custom_report_id(clock):
    page = _report_page(clock)

    assert reports._is_report_page(page, _report()) is True
    assert reports._is_any_report_page(page) is True


def test_another_report_is_not_this_report(clock):
    page = _Page(
        clock,
        url="https://wfx.test/WFXBICustomReportView.aspx?BICustomReportID=other",
    )

    assert reports._is_report_page(page, _report()) is False
    assert reports._is_any_report_page(page) is True


def test_the_main_wfx_tab_is_never_a_report_page(clock):
    page = _Page(clock, url="https://wfx.test/wfx/default.aspx")

    assert reports._is_any_report_page(page) is False


# --- probe "còn dùng được" ------------------------------------------------


def test_a_report_page_with_a_visible_control_is_reusable(clock):
    page = _report_page(clock, controls=[element("input", id="p1")])

    assert reports._report_page_ready(page) is True


def test_a_closed_report_page_is_never_reusable(clock):
    page = _report_page(clock, controls=[element("input", id="p1")])
    page.closed = True

    assert reports._report_page_ready(page) is False


def test_a_report_page_without_the_parameter_table_is_not_reusable(clock):
    assert reports._report_page_ready(_Page(clock)) is False


def test_a_report_page_whose_controls_are_hidden_is_not_reusable(clock):
    page = _report_page(clock, controls=[element("input", id="p1", visible=False)])

    assert reports._report_page_ready(page) is False


def test_a_report_page_that_throws_is_not_reusable(clock):
    page = _report_page(clock)

    def boom(_selector):
        raise PlaywrightError("tab rơi")

    page.locator = boom

    assert reports._report_page_ready(page) is False


# --- mở report ------------------------------------------------------------


def test_an_open_ready_report_is_reused_without_navigating(clock):
    main = _Page(clock, url="https://wfx.test/wfx/default.aspx")
    report_page = _report_page(clock, controls=[element("input", id="p1")])
    _Context([main, report_page])

    assert reports._open_report(main, _report()) is report_page
    assert report_page.goto_calls == []
    assert report_page.bring_to_front_calls == 1


def test_a_stale_report_tab_is_reloaded_instead_of_trusted(clock):
    main = _Page(clock, url="https://wfx.test/wfx/default.aspx")
    report_page = _report_page(clock)  # bảng tham số rỗng → stale
    report_page.root.children[0].children[0].append(element("input", id="p1"))
    _Context([main, report_page])
    report_page.root.children[0].children[0].children.clear()

    reports._open_report(main, _report())

    assert report_page.goto_calls == [_report_url()]


def test_switching_report_navigates_the_existing_report_tab(clock):
    main = _Page(clock, url="https://wfx.test/wfx/default.aspx")
    other = _report_page(
        clock,
        controls=[element("input", id="p1")],
        url="https://wfx.test/WFXBICustomReportView.aspx?BICustomReportID=other",
    )
    context = _Context([main, other])

    assert reports._open_report(main, _report()) is other
    assert other.goto_calls == [_report_url()]
    assert context.new_pages == 0


def test_a_first_report_opens_a_new_tab_beside_the_wfx_tab(clock):
    main = _Page(clock, url="https://wfx.test/wfx/default.aspx")
    context = _Context([main])

    opened = reports._open_report(main, _report())

    assert context.new_pages == 1
    assert opened is not main
    assert opened.goto_calls == [_report_url()]


# --- postback -------------------------------------------------------------


def _busy_page(clock, busy_reads):
    page = _Page(clock)
    queue = list(busy_reads)
    page.scripts = {
        "get_isInAsyncPostBack": lambda _a: (
            queue.pop(0) if len(queue) > 1 else queue[0]
        )
    }
    return page


def test_postback_returns_once_the_page_stays_idle(clock):
    page = _busy_page(clock, [True, True, False])

    reports._wait_postback_settled(page)


def test_postback_times_out_while_the_page_stays_busy(clock):
    page = _busy_page(clock, [True])

    with pytest.raises(PlaywrightTimeoutError, match="chưa nạp xong"):
        reports._wait_postback_settled(page, timeout_s=1)


def test_postback_treats_an_evaluate_failure_as_still_busy(clock):
    page = _Page(clock)
    page.scripts = {
        "get_isInAsyncPostBack": lambda _a: (_ for _ in ()).throw(
            PlaywrightError("tab rơi")
        )
    }

    with pytest.raises(PlaywrightTimeoutError):
        reports._wait_postback_settled(page, timeout_s=1)


# --- đọc select -----------------------------------------------------------


def test_select_options_are_read_from_the_live_control(clock):
    control = Element(
        "select",
        id="ddl",
        children=[
            element("option", text="Hà Nội", attrs={"value": "HAN"}),
            element("option", text="  ", attrs={"value": "X"}),
        ],
    )
    page = _Page(clock, Element("body", children=[control]))
    page.scripts = {}

    assert reports.read_select_options(page, "ddl") == [
        {"value": "HAN", "label": "Hà Nội"}
    ]


def test_select_options_of_a_blank_control_id_are_empty(clock):
    assert reports.read_select_options(_Page(clock), "") == []
    assert reports.read_select_value(_Page(clock), "") == ""


def test_a_quote_in_the_control_id_is_stripped_before_it_reaches_a_selector(
    clock,
):
    control = Element("select", id="ddl", value="HAN")
    page = _Page(clock, Element("body", children=[control]))

    assert reports.read_select_value(page, 'dd"l') == "HAN"


# --- ngày -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("09/21/2026", "2026-09-21"),
        ("9/21/26", "2026-09-21"),
        ("2026-09-21", "2026-09-21"),
        ("không phải ngày", "không phải ngày"),
        ("", ""),
    ],
)
def test_dates_are_normalised_to_iso_or_left_alone(raw, expected):
    assert reports._date_to_iso(raw) == expected


# --- đặt tham số ----------------------------------------------------------


class _Input(Element):
    def __init__(self, **kwargs):
        super().__init__("input", **kwargs)

    def set_checked(self, value, timeout=None):
        self.checked = bool(value)


def _set_page(clock, controls, *, busy=False):
    page = _Page(clock, Element("body", children=list(controls)))
    page.scripts = {"get_isInAsyncPostBack": lambda _a: busy}
    return page


def test_a_plain_text_parameter_is_filled(clock):
    control = _Input(id="txt")
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"txt": "INV-1"})

    assert control.fills == ["INV-1"]


def test_an_iso_date_is_rewritten_to_the_us_format_wfx_expects(clock):
    control = _Input(id="dt", css_class="hasDatepicker")
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"dt": "2026-09-21"})

    assert control.fills == ["9/21/2026"]


def test_a_readonly_datepicker_is_set_through_input_and_change_events(clock):
    events: list[str] = []
    control = _Input(
        id="dt",
        css_class="hasDatepicker",
        attrs={"readonly": "readonly"},
        scripts={"removeAttribute('readonly')": lambda value: events.append(value)},
    )

    def refuse(_value, timeout=None, **_kwargs):
        raise PlaywrightError("readonly")

    control.fill = refuse
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"dt": "2026-09-21"})

    assert events == ["9/21/2026"]


def test_a_select_parameter_is_chosen_then_the_postback_is_awaited(clock):
    control = Element("select", id="ddl")
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"ddl": "HAN"})

    assert control.selected == ["HAN"]


def test_a_select_parameter_accepts_a_list_of_values(clock):
    control = Element("select", id="ddl")
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"ddl": ["A", "B"]})

    assert control.selected == ["['A', 'B']"]


def test_a_checkbox_parameter_is_set_by_state_not_by_clicking(clock):
    control = _Input(id="chk", attrs={"type": "checkbox"}, checked=True)
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"chk": False})

    assert control.checked is False
    assert control.clicks == 0


def test_a_parameter_that_is_not_on_the_page_is_skipped(clock):
    page = _set_page(clock, [])

    reports._set_parameters(page, {"khong-co": "X"})  # không raise


def test_a_hidden_parameter_is_skipped(clock):
    control = _Input(id="txt", visible=False)
    page = _set_page(clock, [control])

    reports._set_parameters(page, {"txt": "X"})

    assert control.fills == []


def _popup_world(clock, *, multi, options, select_all_checked=True):
    text = _Input(
        id="p_txtValue", attrs={"readonly": "readonly", "type": "text"}
    )
    button = _Input(id="p_ddDropDownButton", attrs={"type": "image"})
    checkboxes = [
        _Input(id="opt_all", attrs={"type": "checkbox"}, checked=select_all_checked)
    ] + [
        _Input(id=name, attrs={"type": "checkbox"}) for name in options
    ]
    dropdown = Element("div", id="p_divDropDown", children=checkboxes)
    page = _set_page(clock, [text, button, dropdown])
    return page, button, checkboxes


def test_a_multiselect_popup_unticks_select_all_then_ticks_the_wanted_rows(
    clock,
):
    page, button, checkboxes = _popup_world(
        clock, multi=True, options=["opt_a", "opt_b"]
    )

    reports._set_parameters(page, {"p_txtValue": ["opt_b"]})

    assert checkboxes[0].checked is False
    assert checkboxes[1].checked is False
    assert checkboxes[2].checked is True
    # Mở rồi đóng lại đúng một lượt.
    assert button.clicks == 2


def test_a_single_select_popup_ticks_exactly_one_row(clock):
    page, button, checkboxes = _popup_world(
        clock, multi=False, options=["opt_a", "opt_b"]
    )

    reports._set_parameters(page, {"p_txtValue": "opt_b"})

    assert checkboxes[2].checked is True
    assert button.clicks == 2


def test_a_single_select_popup_without_its_button_is_skipped(clock):
    text = _Input(id="p_txtValue", attrs={"readonly": "readonly"})
    page = _set_page(clock, [text])

    reports._set_parameters(page, {"p_txtValue": "opt_b"})  # không raise


# --- View Report ----------------------------------------------------------


def _view_page(clock, *, button=None, busy=False):
    children = [] if button is None else [button]
    page = _set_page(clock, children, busy=busy)
    return page


def test_view_report_clicks_the_first_usable_button(clock):
    button = _Input(id=VIEW_BUTTON_ID, attrs={"type": "submit", "value": "View Report"})
    page = _view_page(clock, button=button)

    reports._click_view_report(page)

    assert button.clicks == 1


def test_view_report_reports_a_button_that_never_becomes_usable(clock):
    button = _Input(
        id=VIEW_BUTTON_ID,
        attrs={"type": "submit", "value": "View Report"},
        visible=False,
    )
    page = _view_page(clock, button=button)

    with pytest.raises(RuntimeError, match="REPORT_VIEW_BUTTON_NOT_READY"):
        reports._click_view_report(page)


def test_view_report_reports_a_missing_button(clock):
    page = _view_page(clock)

    with pytest.raises(RuntimeError, match="REPORT_VIEW_BUTTON_NOT_FOUND"):
        reports._click_view_report(page)


# --- chờ report tải xong --------------------------------------------------


def _ready_page(clock, *, export_visible=True, export_enabled=True, busy=False,
                image_src="export.png"):
    export = _Input(
        id="rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink",
        visible=export_visible,
        enabled=export_enabled,
    )
    image = _Input(
        id="rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonImg",
        attrs={"src": image_src},
    )
    page = _Page(clock, Element("body", children=[export, image]))
    page.scripts = {"get_isInAsyncPostBack": lambda _a: busy}
    page.export = export
    return page


def test_a_report_is_ready_once_export_stays_enabled(clock):
    page = _ready_page(clock)
    logs: list[str] = []

    reports._wait_report_ready(page, logs.append, timeout_s=30)

    assert any("đã tải xong" in line for line in logs)


def test_a_report_is_not_ready_while_the_export_icon_is_disabled(clock):
    page = _ready_page(clock, image_src="export_Disabled.png")

    with pytest.raises(PlaywrightTimeoutError, match="chưa tải xong"):
        reports._wait_report_ready(page, _quiet(), timeout_s=5)


def test_a_report_is_not_ready_while_an_async_postback_runs(clock):
    page = _ready_page(clock, busy=True)

    with pytest.raises(PlaywrightTimeoutError):
        reports._wait_report_ready(page, _quiet(), timeout_s=5)


def test_a_long_report_logs_progress_without_giving_up(clock):
    page = _ready_page(clock, export_visible=False)
    logs: list[str] = []

    with pytest.raises(PlaywrightTimeoutError):
        reports._wait_report_ready(page, logs.append, timeout_s=40)

    assert any("Vẫn đang tải báo cáo" in line for line in logs)


def test_the_timeout_label_is_written_in_minutes_when_it_divides(clock):
    page = _ready_page(clock, export_visible=False)
    logs: list[str] = []

    with pytest.raises(PlaywrightTimeoutError):
        reports._wait_report_ready(page, logs.append, timeout_s=120)

    assert any("tối đa 2 phút" in line for line in logs)


# --- export Excel ---------------------------------------------------------


def _export_page(clock):
    export = _Input(id="rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink")
    excel = element(
        "a",
        id="excel",
        attrs={"title": "Excel", "onclick": "exportReport('EXCELOPENXML')"},
    )
    menu = Element(
        "div",
        id="rptCustomReportViewer_ctl05_ctl04_ctl00_Menu",
        children=[excel],
    )
    page = _Page(clock, Element("body", children=[export, menu]))
    context = _Context([page])
    page.export = export
    page.excel = excel
    page.context = context
    return page


def test_export_uses_the_native_download_snapshot(clock, monkeypatch, tmp_path):
    page = _export_page(clock)
    saved = tmp_path / "report.xlsx"
    saved.write_bytes(b"x")
    monkeypatch.setattr(reports, "snapshot_downloads", lambda: {"before"})
    monkeypatch.setattr(reports, "claim_download", lambda _download: None)
    monkeypatch.setattr(
        reports,
        "wait_for_native_download",
        lambda _before, suggested_name, timeout: saved,
    )
    monkeypatch.setattr(reports, "native_download_candidate", lambda *a, **kw: None)

    class Download:
        suggested_filename = "report.xlsx"

    page.excel.on_click = lambda _n: [
        handler(Download())
        for event, handler in page.listeners
        if event == "download"
    ]

    assert reports._export_excel(page) == saved
    assert page.listeners == []
    assert page.context.listeners == []


def test_export_accepts_a_file_chrome_saved_without_a_cdp_event(
    clock, monkeypatch, tmp_path
):
    page = _export_page(clock)
    saved = tmp_path / "report.xlsx"
    saved.write_bytes(b"x")
    monkeypatch.setattr(reports, "snapshot_downloads", lambda: set())
    monkeypatch.setattr(
        reports,
        "native_download_candidate",
        lambda *a, **kw: (saved, (1, 2)),
    )

    assert reports._export_excel(page) == saved


def test_export_reports_when_no_download_ever_appears(clock, monkeypatch):
    page = _export_page(clock)
    monkeypatch.setattr(reports, "snapshot_downloads", lambda: set())
    monkeypatch.setattr(reports, "native_download_candidate", lambda *a, **kw: None)
    monkeypatch.setattr(reports, "REPORT_DOWNLOAD_TIMEOUT_SECONDS", 1)

    with pytest.raises(RuntimeError, match="REPORT_DOWNLOAD_NOT_STARTED"):
        reports._export_excel(page)

    assert page.listeners == []


# --- entry point ----------------------------------------------------------


def _wire(monkeypatch, clock, page, *, chrome_ready=True, logged_in=True):
    monkeypatch.setattr(reports, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(reports, "_chrome_is_ready", lambda: chrome_ready)
    monkeypatch.setattr(
        reports,
        "_connect_to_chrome",
        lambda _playwright, **kwargs: (_Browser(page), page),
    )
    monkeypatch.setattr(reports, "_attach_dialog_handler", lambda *a: None)
    monkeypatch.setattr(reports, "_session_is_active", lambda _page: logged_in)


class _Driver:
    stops = 0

    def stop(self):
        type(self).stops += 1


class _Starter:
    def start(self):
        return _Driver()


class _Browser:
    def __init__(self, page):
        self.contexts = [page.context]


def test_loading_parameters_never_fronts_the_main_wfx_tab(clock, monkeypatch):
    main = _Page(clock, url="https://wfx.test/wfx/default.aspx")
    report_page = _report_page(clock, controls=[element("input", id="p1")])
    _Context([main, report_page])
    _wire(monkeypatch, clock, main)
    seen: list[dict] = []
    monkeypatch.setattr(
        reports,
        "_connect_to_chrome",
        lambda _playwright, **kwargs: seen.append(kwargs) or (_Browser(main), main),
    )
    monkeypatch.setattr(reports, "_read_parameters", lambda _page: [{"key": "p1"}])

    result = reports.load_report_parameters(_report_id(), _quiet())

    assert result["code"] == "REPORT_PARAMETERS_LOADED"
    assert result["parameters"] == [{"key": "p1"}]
    assert seen == [{"bring_to_front": False}]


def test_loading_parameters_refuses_an_unknown_report(clock):
    assert reports.load_report_parameters("khong-co")["code"] == "REPORT_UNKNOWN"


def test_loading_parameters_reports_a_closed_browser(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main, chrome_ready=False)

    assert reports.load_report_parameters(_report_id())["code"] == "CHROME_CLOSED"


def test_loading_parameters_reports_an_expired_session(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main, logged_in=False)

    assert reports.load_report_parameters(_report_id())["code"] == "NOT_LOGGED_IN"


def test_loading_parameters_maps_a_timeout_to_its_own_code(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main)
    monkeypatch.setattr(
        reports,
        "_open_report",
        lambda *a: (_ for _ in ()).throw(PlaywrightTimeoutError("chậm")),
    )

    result = reports.load_report_parameters(_report_id(), _quiet())

    assert result["code"] == "REPORT_PARAMETERS_NOT_READY"


def test_loading_parameters_maps_any_other_failure(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main)
    monkeypatch.setattr(
        reports,
        "_open_report",
        lambda *a: (_ for _ in ()).throw(ValueError("URL lạ")),
    )

    result = reports.load_report_parameters(_report_id(), _quiet())

    assert result["code"] == "REPORT_LOAD_FAILED"
    assert "ValueError" in result["message"]


def test_exporting_runs_the_whole_chain_and_returns_the_file(
    clock, monkeypatch, tmp_path
):
    main = _Page(clock)
    report_page = _report_page(clock, controls=[element("input", id="p1")])
    _Context([main, report_page])
    _wire(monkeypatch, clock, main)
    order: list[str] = []
    monkeypatch.setattr(
        reports, "_set_parameters", lambda *a: order.append("params")
    )
    monkeypatch.setattr(
        reports, "_click_view_report", lambda *a: order.append("view")
    )
    monkeypatch.setattr(
        reports, "_wait_report_ready", lambda *a, **kw: order.append("ready")
    )
    saved = tmp_path / "Shipment.xlsx"
    saved.write_bytes(b"x")
    monkeypatch.setattr(
        reports, "_export_excel", lambda *a: order.append("export") or saved
    )

    result = reports.export_report_excel(_report_id(), {"p1": "X"}, _quiet())

    assert result["code"] == "REPORT_EXPORTED"
    assert result["file_name"] == "Shipment.xlsx"
    assert result["download_path"] == str(saved)
    assert order == ["params", "view", "ready", "export"]


def test_exporting_refuses_an_unknown_report(clock):
    assert reports.export_report_excel("khong-co", {})["code"] == "REPORT_UNKNOWN"


def test_exporting_reports_a_closed_browser(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main, chrome_ready=False)

    assert reports.export_report_excel(_report_id(), {})["code"] == "CHROME_CLOSED"


def test_exporting_reports_an_expired_session(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main, logged_in=False)

    assert reports.export_report_excel(_report_id(), {})["code"] == "NOT_LOGGED_IN"


def test_exporting_reports_a_failure_with_its_type(clock, monkeypatch):
    main = _Page(clock)
    _Context([main])
    _wire(monkeypatch, clock, main)
    monkeypatch.setattr(
        reports,
        "_open_report",
        lambda *a: (_ for _ in ()).throw(RuntimeError("REPORT_DOWNLOAD_NOT_STARTED")),
    )

    result = reports.export_report_excel(_report_id(), {}, _quiet())

    assert result["code"] == "REPORT_EXPORT_FAILED"
    assert "REPORT_DOWNLOAD_NOT_STARTED" in result["message"]


def test_the_download_path_is_a_real_path_object(clock, monkeypatch, tmp_path):
    assert isinstance(Path(str(tmp_path / "a.xlsx")), Path)


# --- đọc tham số ----------------------------------------------------------


def _params_page(clock, descriptors, *, controls=(), extra=()):
    """Trang report có sẵn bảng tham số; đoạn JS đọc bảng được khai báo."""
    page = _report_page(
        clock,
        controls=list(controls),
        extra=list(extra),
        scripts={"toIsoDate": lambda _a: [dict(row) for row in descriptors]},
    )
    page.scripts = {"get_isInAsyncPostBack": lambda _a: False}
    return page


def test_parameters_are_returned_as_the_browser_read_them(clock):
    page = _params_page(
        clock,
        [{"key": "p1", "label": "Buyer", "type": "text", "value": "A", "options": []}],
        controls=[element("input", id="p1")],
    )

    assert reports._read_parameters(page) == [
        {"key": "p1", "label": "Buyer", "type": "text", "value": "A", "options": []}
    ]


def test_a_control_with_a_calendar_icon_is_promoted_to_a_date(clock):
    cell = Element(
        "td",
        children=[
            element("input", id="p1"),
            element("img", id="calendarTrigger", attrs={"src": "/img/calendar.gif"}),
        ],
    )
    page = _params_page(
        clock,
        [{"key": "p1", "label": "Từ ngày", "type": "text", "value": "09/21/2026"}],
        controls=[cell],
    )

    descriptor = reports._read_parameters(page)[0]

    assert descriptor["type"] == "date"
    assert descriptor["value"] == "2026-09-21"


def test_the_two_wfx_ship_date_controls_are_always_dates(clock):
    page = _params_page(
        clock,
        [
            {
                "key": "rpt_ctl05_txtValue",
                "label": "Ship Date from",
                "type": "text",
                "value": "09/01/2026",
            }
        ],
        controls=[element("input", id="rpt_ctl05_txtValue")],
    )

    descriptor = reports._read_parameters(page)[0]

    assert descriptor["type"] == "date"
    assert descriptor["value"] == "2026-09-01"


def _popup_parameter(clock, kind, *, options, checked=()):
    text = element("input", id="p_txtValue", attrs={"readonly": "readonly"})
    button = element(
        "input",
        id="p_ddDropDownButton",
        attrs={"type": "image", "src": "MultiValueSelect.png"},
    )
    rows = [
        Element(
            "label",
            text=f"({name})" if name == "Select All" else name,
            children=[
                element(
                    "input",
                    id=f"opt_{name}",
                    attrs={"type": "checkbox"},
                    checked=name in set(checked),
                )
            ],
        )
        for name in options
    ]
    dropdown = Element("div", id="p_divDropDown", children=rows)
    page = _params_page(
        clock,
        [
            {
                "key": "p_txtValue",
                "label": "Buyer",
                "type": kind,
                "value": "",
                "options": [],
            }
        ],
        controls=[text, button],
        extra=[dropdown],
    )
    return page, button, rows


def test_a_multiselect_popup_is_opened_read_and_closed_again(clock):
    page, button, _rows = _popup_parameter(
        clock, "multiselect", options=["A", "B"], checked=["B"]
    )

    descriptor = reports._read_parameters(page)[0]

    assert descriptor["options"] == [
        {"value": "opt_A", "label": "A"},
        {"value": "opt_B", "label": "B"},
    ]
    assert descriptor["value"] == ["opt_B"]
    assert button.clicks == 2


def test_a_single_select_popup_keeps_only_the_first_selected_value(clock):
    page, _button, _rows = _popup_parameter(
        clock, "select_popup", options=["A", "B"], checked=["B"]
    )

    assert reports._read_parameters(page)[0]["value"] == "opt_B"


def test_a_single_select_popup_with_nothing_ticked_is_empty(clock):
    page, _button, _rows = _popup_parameter(
        clock, "select_popup", options=["A"], checked=[]
    )

    assert reports._read_parameters(page)[0]["value"] == ""


def test_a_popup_button_of_a_plain_parameter_is_ignored(clock):
    page, button, _rows = _popup_parameter(
        clock, "text", options=["A"], checked=["A"]
    )

    assert reports._read_parameters(page)[0]["options"] == []
    assert button.clicks == 0


def test_a_hidden_popup_button_is_never_clicked(clock):
    page, button, _rows = _popup_parameter(
        clock, "multiselect", options=["A"], checked=[]
    )
    button.visible = False

    reports._read_parameters(page)

    assert button.clicks == 0
