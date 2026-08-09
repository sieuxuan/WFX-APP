from types import SimpleNamespace
from unittest.mock import MagicMock

from wfx_panel.automation import reports


def _report_page(url: str):
    page = MagicMock()
    page.url = url
    page.is_closed.return_value = False
    return page


def test_open_report_reuses_ready_matching_page_without_navigation(monkeypatch):
    report = reports.REPORTS["shipment_summary"]
    main = _report_page("https://example.test/wfx/default.aspx")
    target = _report_page(
        f"https://example.test/WFXBICustomReportView.aspx?BICustomReportID="
        f"{report['custom_report_id']}"
    )
    context = SimpleNamespace(pages=[main, target], new_page=MagicMock())
    main.context = context
    monkeypatch.setattr(reports, "_report_page_ready", lambda page: page is target)
    monkeypatch.setattr(reports, "_wait", lambda *_args: None)

    opened = reports._open_report(main, report)

    assert opened is target
    target.bring_to_front.assert_called_once_with()
    target.goto.assert_not_called()
    context.new_page.assert_not_called()


def test_open_report_reuses_other_report_tab_when_switching(monkeypatch):
    report = reports.REPORTS["shipment_summary"]
    main = _report_page("https://example.test/wfx/default.aspx")
    other = _report_page(
        "https://example.test/WFXBICustomReportView.aspx?"
        "BICustomReportID=other"
    )
    context = SimpleNamespace(pages=[main, other], new_page=MagicMock())
    main.context = context
    monkeypatch.setattr(reports, "_wait", lambda *_args: None)

    opened = reports._open_report(main, report)

    assert opened is other
    other.goto.assert_called_once_with(
        reports._report_url(report),
        wait_until="domcontentloaded",
        timeout=45_000,
    )
    other.bring_to_front.assert_called_once_with()
    context.new_page.assert_not_called()


def test_open_report_creates_tab_only_when_no_report_tab_exists(monkeypatch):
    report = reports.REPORTS["shipment_summary"]
    main = _report_page("https://example.test/wfx/default.aspx")
    created = _report_page("about:blank")
    context = SimpleNamespace(
        pages=[main],
        new_page=MagicMock(return_value=created),
    )
    main.context = context
    monkeypatch.setattr(reports, "_wait", lambda *_args: None)

    opened = reports._open_report(main, report)

    assert opened is created
    context.new_page.assert_called_once_with()
    created.goto.assert_called_once()


def test_report_export_returns_completed_native_download_path(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "Shipment Summary.xlsx"
    target.write_bytes(b"xlsx")
    playwright = SimpleNamespace(stop=lambda: None)
    page = object()

    monkeypatch.setattr(reports, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(
        reports,
        "sync_playwright",
        lambda: SimpleNamespace(start=lambda: playwright),
    )
    monkeypatch.setattr(
        reports,
        "_connect_to_chrome",
        lambda *_args, **_kwargs: (object(), page),
    )
    monkeypatch.setattr(reports, "_attach_dialog_handler", lambda *_args: None)
    monkeypatch.setattr(reports, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(reports, "_open_report", lambda *_args: page)
    monkeypatch.setattr(reports, "_set_parameters", lambda *_args: None)
    monkeypatch.setattr(reports, "_click_view_report", lambda _page: None)
    monkeypatch.setattr(reports, "_wait_report_ready", lambda *_args: None)
    monkeypatch.setattr(reports, "_export_excel", lambda _page: target)

    result = reports.export_report_excel("shipment_summary", {})

    assert result["ok"] is True
    assert result["file_name"] == target.name
    assert result["download_path"] == str(target)
    assert result["message"] == f"Đã tải xong {target.name}."


def test_set_parameters_waits_for_postback_after_select(monkeypatch):
    page = MagicMock()
    locator = MagicMock()
    page.locator.return_value.first = locator
    locator.count.return_value = 1
    locator.is_visible.return_value = True
    locator.evaluate.side_effect = ["SELECT", False]
    locator.get_attribute.return_value = None
    settled = MagicMock()
    monkeypatch.setattr(reports, "_wait_postback_settled", settled)

    reports._set_parameters(page, {"division": "division-id"})

    locator.select_option.assert_called_once_with("division-id")
    # Một lần ngay sau control và một lần chốt trước View Report.
    assert settled.call_count == 2


def test_click_view_report_waits_then_uses_exact_reportviewer_button(monkeypatch):
    page = MagicMock()
    button = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 1
    locator.first = button
    button.is_visible.return_value = True
    button.is_enabled.return_value = True
    page.locator.return_value = locator
    settled = MagicMock()
    monkeypatch.setattr(reports, "_wait_postback_settled", settled)

    reports._click_view_report(page)

    settled.assert_called_once_with(page)
    page.locator.assert_called_once_with("#rptCustomReportViewer_ctl04_ctl00")
    button.click.assert_called_once_with(timeout=3_000)
