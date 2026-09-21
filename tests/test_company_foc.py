"""Company Setup: đổi nơi áp dụng FOC giữa ASN và GRN.

`wfx_panel/automation/modules/company.py` ở mức 13%. CLAUDE.md nói:

* "`Đổi FOC` tự mở Company Setup nếu context hiện tại đã đổi sang module khác,
  rồi mới mở Miscellaneous Settings."
* "Search và Đổi FOC không được trả `*_LIST_NOT_OPEN` hay hướng dẫn bấm List.
  Nếu đã tự mở nhưng List/search vẫn không sẵn sàng, trả lỗi kỹ thuật cụ thể."

Đây là một thao tác GHI dữ liệu công ty, nên phần đắt nhất là xác nhận WFX đã
lưu thật: chỉ đổi checkbox thôi chưa đủ.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.modules import company

CHECKBOX_ID = "chkAllowToMarkFOCQtyOnRMPOASN"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, company, _common)


def _quiet():
    return lambda _line: None


class _Response:
    def __init__(self, url, method="POST", status=200, ok=True):
        self.url = url
        self.status = status
        self.ok = ok
        self.request = type("Request", (), {"method": method})()


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.listeners: list[tuple] = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        self.listeners.remove((event, handler))

    def emit_response(self, response):
        for event, handler in list(self.listeners):
            if event == "response":
                handler(response)


# --- bộ lọc response ------------------------------------------------------


def test_only_a_write_request_to_the_company_page_is_recorded():
    seen: list[dict] = []
    handler = company._company_save_response_handler(seen)

    handler(_Response("https://wfx.test/WFX_MyCompanySite.aspx"))
    handler(_Response("https://wfx.test/WFX_MyCompanySite.aspx", method="GET"))
    handler(_Response("https://wfx.test/other.aspx"))

    assert [row["url"] for row in seen] == [
        "https://wfx.test/WFX_MyCompanySite.aspx"
    ]


def test_a_failing_save_is_recorded_with_its_status():
    seen: list[dict] = []
    handler = company._company_save_response_handler(seen)

    handler(
        _Response(
            "https://wfx.test/wfx_mycompanysite.aspx", status=500, ok=False
        )
    )

    assert seen == [
        {"ok": False, "status": 500, "url": "https://wfx.test/wfx_mycompanysite.aspx"}
    ]


def test_a_broken_response_object_never_breaks_the_handler():
    seen: list[dict] = []
    handler = company._company_save_response_handler(seen)

    handler(object())  # không raise

    assert seen == []


# --- thông điệp khi chưa xác nhận được ------------------------------------


def test_an_unconfirmed_save_never_claims_success():
    result = company._unsaved_company_foc_result("FOC cho GRN", True, [])

    assert result["ok"] is False
    assert result["code"] == "COMPANY_FOC_SAVE_NOT_CONFIRMED"
    assert result["saved"] is False
    assert result["foc_mode"] == "FOC cho ASN"


def test_an_unconfirmed_save_reports_the_last_http_status():
    result = company._unsaved_company_foc_result(
        "FOC cho GRN",
        None,
        [{"ok": False, "status": 500}, {"ok": False, "status": 502}],
    )

    assert "HTTP 502" in result["message"]
    assert result["foc_mode"] == "FOC cho GRN"


def test_an_unconfirmed_save_reports_the_observed_state_when_it_is_false():
    result = company._unsaved_company_foc_result("FOC cho ASN", False, [])

    assert result["foc_mode"] == "FOC cho GRN"
    assert result["foc_enabled"] is False


# --- chờ xác nhận ---------------------------------------------------------


class _Checkbox(Element):
    def __init__(self, checked: bool) -> None:
        super().__init__(
            "input", id=CHECKBOX_ID, attrs={"type": "checkbox"}, checked=checked
        )

    def set_checked(self, value, timeout=None):
        self.checked = bool(value)


def _company_frame(clock, *, checked=False, save=True, misc=True):
    checkbox = _Checkbox(checked)
    children = [checkbox]
    if save:
        children.append(
            Element(
                "td",
                css_class="clsBtnOff",
                attrs={"title": "Save"},
                children=[
                    element(
                        "a",
                        id="lnkSave",
                        css_class="clsNavLink",
                        attrs={"onclick": "ChangeAction('SAVE')"},
                    )
                ],
            )
        )
    if misc:
        children.append(
            element(
                "a",
                id="misc",
                css_class="clsDataLabel",
                attrs={
                    "onclick": (
                        "OpenPage('wfx_MyCompanySite.aspx?"
                        "CurrentTab=4&CurrentItem=12')"
                    )
                },
            )
        )
    frame = MiniFrame(Element("body", children=children), clock=clock)
    frame.checkbox = checkbox
    return frame


def test_the_save_is_confirmed_by_a_successful_write_request(clock):
    frame = _company_frame(clock, checked=True)
    page = _Page(clock, [frame])

    confirmed, state = company._wait_company_foc_saved(
        page, True, (frame, "old"), [{"ok": True, "status": 200}]
    )

    assert confirmed is True
    assert state is True


def test_the_save_is_confirmed_when_the_document_reloaded(clock, monkeypatch):
    frame = _company_frame(clock, checked=True)
    page = _Page(clock, [frame])
    monkeypatch.setattr(company, "_document_changed", lambda _f, _s: True)

    confirmed, _state = company._wait_company_foc_saved(
        page, True, (frame, "old"), []
    )

    assert confirmed is True


def test_the_right_checkbox_state_without_any_save_signal_is_not_enough(clock):
    """Chỉ nhìn checkbox thì không phân biệt được 'đã lưu' với 'chưa lưu'."""
    frame = _company_frame(clock, checked=True)
    page = _Page(clock, [frame])
    snapshot = _common._mark_document(frame, "company-foc-save")

    confirmed, state = company._wait_company_foc_saved(page, True, snapshot, [])

    assert confirmed is False
    assert state is True


def test_a_failing_write_request_never_confirms_the_save(clock):
    frame = _company_frame(clock, checked=True)
    page = _Page(clock, [frame])
    snapshot = _common._mark_document(frame, "company-foc-save")

    confirmed, _state = company._wait_company_foc_saved(
        page, True, snapshot, [{"ok": False, "status": 500}]
    )

    assert confirmed is False


def test_a_checkbox_that_disappears_is_reported_as_unconfirmed(clock):
    page = _Page(clock, [MiniFrame(Element("body"), clock=clock)])

    confirmed, state = company._wait_company_foc_saved(page, True, (None, ""), [])

    assert confirmed is False
    assert state is None


# --- đổi và lưu -----------------------------------------------------------


def _toggle_world(clock, monkeypatch, *, checked=False, save=True, saves_ok=True):
    frame = _company_frame(clock, checked=checked, save=save)
    page = _Page(clock, [frame])
    save_link = frame.locator("#lnkSave")
    if save:
        save_link.node.on_click = lambda _n: page.emit_response(
            _Response("https://wfx.test/wfx_mycompanysite.aspx", ok=saves_ok,
                      status=200 if saves_ok else 500)
        )
    monkeypatch.setattr(company, "_document_changed", lambda _f, _s: False)
    return frame, page


def test_toggling_flips_the_checkbox_saves_and_reports_the_new_mode(
    clock, monkeypatch
):
    frame, page = _toggle_world(clock, monkeypatch, checked=False)
    logs: list[str] = []

    result = company._toggle_company_foc_setting(page, logs.append)

    assert result["code"] == "COMPANY_FOC_CHANGED"
    assert result["previous_foc_mode"] == "FOC cho GRN"
    assert result["foc_mode"] == "FOC cho ASN"
    assert result["saved"] is True
    assert frame.checkbox.checked is True
    assert page.listeners == []
    assert any("Đang bấm Save" in line for line in logs)


def test_toggling_the_other_way_reports_the_reverse_modes(clock, monkeypatch):
    _frame, page = _toggle_world(clock, monkeypatch, checked=True)

    result = company._toggle_company_foc_setting(page, _quiet())

    assert result["previous_foc_mode"] == "FOC cho ASN"
    assert result["foc_mode"] == "FOC cho GRN"


def test_a_checkbox_wfx_refuses_to_flip_stops_before_saving(clock, monkeypatch):
    frame, page = _toggle_world(clock, monkeypatch)
    frame.checkbox.set_checked = lambda _value, timeout=None: None

    with pytest.raises(PlaywrightTimeoutError, match="chưa đổi trạng thái"):
        company._toggle_company_foc_setting(page, _quiet())

    assert frame.locator("#lnkSave").node.clicks == 0


def test_a_save_that_fails_reports_the_unconfirmed_result(clock, monkeypatch):
    _frame, page = _toggle_world(clock, monkeypatch, saves_ok=False)

    result = company._toggle_company_foc_setting(page, _quiet())

    assert result["code"] == "COMPANY_FOC_SAVE_NOT_CONFIRMED"
    assert result["saved"] is False
    assert "HTTP 500" in result["message"]
    assert page.listeners == []


# --- entry point ----------------------------------------------------------


def _wire(monkeypatch, clock, page, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, company, world, chrome_ready=chrome_ready, clock=clock
    )
    world.pages[0] = page
    world.context.pages = [page]
    monkeypatch.setattr(
        company,
        "_active_wfx_page",
        lambda _playwright, _log: (world.browser, page),
    )
    return world


def test_foc_uses_the_company_setup_screen_that_is_already_open(
    clock, monkeypatch
):
    frame, page = _toggle_world(clock, monkeypatch)
    _wire(monkeypatch, clock, page)
    opened: list[str] = []
    monkeypatch.setattr(
        company,
        "_click_module_menu_on_page",
        lambda *a: opened.append("menu"),
    )

    result = company.toggle_company_foc('//*[@id="x"]/a', _quiet())

    assert result["code"] == "COMPANY_FOC_CHANGED"
    assert opened == []
    assert frame.locator("#misc").node.clicks == 1


def test_foc_opens_company_setup_itself_when_another_module_is_open(
    clock, monkeypatch
):
    """Không được bắt người dùng bấm List trước."""
    empty = MiniFrame(Element("body"), clock=clock)
    ready, ready_page = _toggle_world(clock, monkeypatch)
    page = _Page(clock, [empty])
    _wire(monkeypatch, clock, page)

    def open_menu(_page, _name, _xpath, _log):
        page.frames.append(ready)

    monkeypatch.setattr(company, "_click_module_menu_on_page", open_menu)
    ready.locator("#lnkSave").node.on_click = lambda _n: page.emit_response(
        _Response("https://wfx.test/wfx_mycompanysite.aspx")
    )
    logs: list[str] = []

    result = company.toggle_company_foc('//*[@id="x"]/a', logs.append)

    assert result["code"] == "COMPANY_FOC_CHANGED"
    assert any("đang tự mở List" in line for line in logs)


def test_foc_reports_a_technical_error_when_its_own_open_failed(
    clock, monkeypatch
):
    page = _Page(clock, [MiniFrame(Element("body"), clock=clock)])
    _wire(monkeypatch, clock, page)
    monkeypatch.setattr(company, "_click_module_menu_on_page", lambda *a: None)

    result = company.toggle_company_foc('//*[@id="x"]/a', _quiet())

    assert result["code"] == "COMPANY_LIST_OPEN_FAILED"
    assert "LIST_NOT_OPEN" not in result["code"]


def test_foc_maps_a_timeout_to_its_own_not_ready_code(clock, monkeypatch):
    frame, page = _toggle_world(clock, monkeypatch)
    _wire(monkeypatch, clock, page)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Miscellaneous Settings không mở")

    monkeypatch.setattr(company, "_toggle_company_foc_setting", slow)

    result = company.toggle_company_foc('//*[@id="x"]/a', _quiet())

    assert result["code"] == "COMPANY_FOC_NOT_READY"


def test_foc_maps_any_other_failure_to_its_own_failed_code(clock, monkeypatch):
    frame, page = _toggle_world(clock, monkeypatch)
    _wire(monkeypatch, clock, page)
    monkeypatch.setattr(
        company,
        "_toggle_company_foc_setting",
        lambda *a: (_ for _ in ()).throw(ValueError("DOM lạ")),
    )

    result = company.toggle_company_foc('//*[@id="x"]/a', _quiet())

    assert result["code"] == "COMPANY_FOC_FAILED"
    assert "ValueError" in result["message"]


def test_foc_maps_a_closed_browser_through_the_shared_boundary(
    clock, monkeypatch
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, company, world, chrome_ready=False, clock=clock)

    result = company.toggle_company_foc('//*[@id="x"]/a', _quiet())

    assert result["code"] == "CHROME_CLOSED"
