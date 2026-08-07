"""Luồng báo cáo WFX: đọc tham số, chạy report và tải Excel native."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from wfx_panel.automation._common import (
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.runtime import checkpoint, snapshot_downloads
from wfx_panel.automation.session import _session_is_active

REPORTS = {
    "shipment_summary": {
        "id": "shipment_summary",
        "name": "Shipment Summary",
        "kind": "simple",
        "custom_report_id": "e440760c-8324-4715-bb21-0e23f6cfb46a",
        "url": (
            "https://prosports.worldfashionexchange.com/WFXBase4.0/"
            "WFXBICustomReportView.aspx?BICustomReportID="
            "e440760c-8324-4715-bb21-0e23f6cfb46a&Path="
            "/WFXPSHLIVE/Production%20Reports/Shipment%20Report_Summary&"
            "LoginID=psh45&GUID=f4a2054a-9cba-4cc8-a314-2a098e700ed6&ReportParams="
        ),
    },
    "color_combination_production": {
        "id": "color_combination_production",
        "name": "Color Combination - Production",
        "kind": "cascade_batch",
        "custom_report_id": "0864e93b-ee5d-4dbc-840e-c83a1b44d728",
        "url": (
            "https://prosports.worldfashionexchange.com/WFXBase4.0/"
            "WFXBICustomReportView.aspx?BICustomReportID="
            "0864e93b-ee5d-4dbc-840e-c83a1b44d728&Path="
            "/WFXPSHLIVE/Production%20Reports/"
            "Color%20combination%20cost%20sheet_Production&"
            "LoginID=psh45&GUID=cc0170bb-4722-47fa-928e-8d5d6e4c6c03&"
            "ReportParams="
        ),
    },
}
PARAMETER_TABLE = "#ParameterTable_rptCustomReportViewer_ctl04"
REPORT_READY_TIMEOUT_SECONDS = 300
REPORT_DOWNLOAD_TIMEOUT_SECONDS = 60
REPORT_EXPORT_BUTTON = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink, "
    'a[title="Export drop down menu"]'
)
REPORT_EXPORT_IMAGE = "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonImg"
REPORT_EXCEL_ACTION = (
    'a[onclick*="EXCELOPENXML"], a[href*="EXCELOPENXML"], '
    '[data-format="EXCELOPENXML"]'
)


def report_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "kind": item.get("kind", "simple"),
        }
        for item in REPORTS.values()
    ]


def _report_url(report: Mapping[str, str]) -> str:
    # Không ghi URL vào log: query WFX có thể kèm giá trị theo phiên.
    return str(report["url"])


def _report(report_id: str) -> dict[str, str] | None:
    return REPORTS.get(str(report_id or "").strip())


def _is_report_page(page: Page, report: Mapping[str, str]) -> bool:
    url = str(page.url or "")
    return (
        "wfxbicustomreportview.aspx" in url.casefold()
        and str(report["custom_report_id"]).casefold() in url.casefold()
    )


def _open_report(page: Page, report: Mapping[str, str]) -> Page:
    """Mở/chạy report trong tab riêng, tuyệt đối không điều hướng tab WFX chính."""
    context = page.context
    report_page = next(
        (item for item in reversed(context.pages) if _is_report_page(item, report)),
        None,
    )
    if report_page is None:
        report_page = context.new_page()
    report_page.goto(
        _report_url(report), wait_until="domcontentloaded", timeout=45_000
    )
    report_page.locator(PARAMETER_TABLE).wait_for(state="attached", timeout=30_000)
    # ReportViewer gắn class ``hasDatepicker`` và icon lịch bằng javascript
    # sau khi bảng tham số đã attach. Chờ control hiển thị và cho script WFX
    # hoàn tất trước khi đọc metadata, nếu không ngày bị coi là ô text.
    report_page.locator(
        f'{PARAMETER_TABLE} input[id$="_txtValue"]'
    ).first.wait_for(state="visible", timeout=30_000)
    _wait(report_page, 350)
    report_page.bring_to_front()
    return report_page


POSTBACK_SETTLE_SECONDS = 0.5


def _wait_postback_settled(page: Page, timeout_s: float = 45.0) -> None:
    """Chờ async postback của ReportViewer xong và ổn định trước khi đọc lại."""
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    while time.monotonic() < deadline:
        checkpoint()
        now = time.monotonic()
        try:
            busy = bool(
                page.evaluate(
                    """() => {
                      const manager = window.Sys?.WebForms?.PageRequestManager
                        ?.getInstance?.();
                      if (manager?.get_isInAsyncPostBack?.()) return true;
                      return [...document.querySelectorAll(
                        '[id*="AsyncWait"], [aria-busy="true"]'
                      )].some(element => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none' &&
                          style.visibility !== 'hidden' &&
                          rect.width > 0 && rect.height > 0;
                      });
                    }"""
                )
            )
            if busy:
                stable_since = 0.0
            elif not stable_since:
                stable_since = now
            elif now - stable_since >= POSTBACK_SETTLE_SECONDS:
                return
        except PlaywrightError:
            stable_since = 0.0
        _wait(page, 100)
    raise PlaywrightTimeoutError(
        f"Tham số báo cáo chưa nạp xong sau {int(timeout_s)} giây."
    )


def resolve_controls(page: Page) -> dict[str, str]:
    """Map nhãn tham số sang element id; id đổi sau mỗi postback nên đọc lại."""
    return page.locator(PARAMETER_TABLE).evaluate(
        """table => {
          const controls = {};
          for (const element of table.querySelectorAll('input, select')) {
            if (!element.id || element.type === 'hidden') continue;
            const valueCell = element.closest('td, th');
            const label = (valueCell?.previousElementSibling?.textContent || '')
              .replace(/\\s+/g, ' ').trim();
            if (label && !(label in controls)) controls[label] = element.id;
          }
          return controls;
        }"""
    )


def read_select_options(page: Page, control_id: str) -> list[dict[str, str]]:
    cleaned = str(control_id or "").replace(chr(34), "")
    if not cleaned:
        return []
    return page.locator(f'[id="{cleaned}"]').evaluate(
        """element => [...(element.options || [])].map(option => ({
          value: option.value,
          label: (option.textContent || option.value).trim(),
        })).filter(option => option.label)"""
    )


def read_select_value(page: Page, control_id: str) -> str:
    cleaned = str(control_id or "").replace(chr(34), "")
    if not cleaned:
        return ""
    return str(
        page.locator(f'[id="{cleaned}"]').evaluate("element => element.value || ''")
    )


def _date_to_iso(value: Any) -> str:
    cleaned = str(value or "").strip()
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def _read_parameters(page: Page) -> list[dict[str, Any]]:
    """Đọc control ReportViewer, gồm multiselect popup và datepicker WFX."""
    parameters = page.locator(PARAMETER_TABLE).evaluate(
        """table => {
          const toIsoDate = value => {
            const match = String(value || '').trim().match(
              new RegExp('^(\\\\d{1,2})/(\\\\d{1,2})/(\\\\d{4})$')
            );
            return match
              ? `${match[3]}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}`
              : String(value || '');
          };
          return [...table.querySelectorAll('input, select, textarea')]
          .filter(el => el.id && el.type !== 'hidden' &&
             !['submit', 'button', 'reset', 'image'].includes((el.type || '').toLowerCase()))
          .map((el, index) => {
            const valueCell = el.closest('td, th');
            const labelCell = valueCell?.previousElementSibling;
            const calendarTrigger = valueCell?.querySelector(
              'img.ui-datepicker-trigger, input[type="image"][src*="calendar" i], img[src*="calendar" i], [id*="calendar" i]'
            );
            const dateIdLabel = /ctl05_txtValue$/.test(el.id)
              ? 'Ship Date from'
              : (/ctl07_txtValue$/.test(el.id) ? 'Ship Date To' : '');
            const label = (dateIdLabel || labelCell?.textContent ||
              el.getAttribute('aria-label') || el.name || `Tham số ${index + 1}`)
              .replace(/\\s+/g, ' ').trim();
            const rawType = (el.type || 'text').toLowerCase();
            const dropButton = el.parentElement?.querySelector(
              'input[type="image"][id$="_ddDropDownButton"]'
            );
            const isDate = rawType === 'date' ||
              el.classList.contains('hasDatepicker') || Boolean(calendarTrigger) ||
              /\bdate\b|ngày/i.test(label) || dateIdLabel !== '';
            const popupType = /MultiValueSelect/i.test(dropButton?.src || '')
              ? 'multiselect' : 'select_popup';
            const type = el.tagName === 'SELECT' ? 'select' :
              (el.readOnly && dropButton ? popupType : (isDate ? 'date' : rawType));
            const rawValue = type === 'checkbox' ? Boolean(el.checked) : (el.value || '');
            return {
              key: el.id,
              label,
              type,
              value: type === 'date' ? toIsoDate(rawValue) : rawValue,
              required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
              options: el.tagName === 'SELECT' ? [...el.options].map(option => ({
                value: option.value, label: (option.textContent || option.value).trim(),
              })).filter(option => option.label) : [],
            };
          });
        }"""
    )
    by_key = {str(item.get("key") or ""): item for item in parameters}
    for key, descriptor in by_key.items():
        control = page.locator(f'[id="{key.replace(chr(34), "")}"]').first
        is_date_control = bool(
            control.evaluate(
                """element => element.classList.contains('hasDatepicker') ||
                Boolean(element.closest('td, th')?.querySelector(
                  'img.ui-datepicker-trigger, input[type="image"][src*="calendar" i], img[src*="calendar" i], [id*="calendar" i]'))"""
            )
        )
        if is_date_control or str(descriptor.get("key") or "").endswith(
            ("ctl05_txtValue", "ctl07_txtValue")
        ):
            descriptor["type"] = "date"
            descriptor["value"] = _date_to_iso(descriptor.get("value"))
    buttons = page.locator(
        f'{PARAMETER_TABLE} input[type="image"][id$="_ddDropDownButton"]'
    )
    for index in range(buttons.count()):
        button = buttons.nth(index)
        if not button.is_visible():
            continue
        text_key = button.evaluate(
            "element => element.previousElementSibling?.id || ''"
        )
        descriptor = by_key.get(str(text_key or ""))
        if descriptor is None or descriptor.get("type") not in {
            "multiselect",
            "select_popup",
        }:
            continue
        button_id = str(button.get_attribute("id") or "")
        root_id = button_id.removesuffix("_ddDropDownButton") + "_divDropDown"
        button.click()
        _wait(page, 100)
        options = page.locator(
            f'#{root_id} input[type="checkbox"], #{root_id} input[type="radio"]'
        )
        option_rows = options.evaluate_all(
            """elements => elements.map(element => ({
              value: element.id,
              label: (element.parentElement?.textContent || '').replace(/\\s+/g, ' ').trim(),
              selected: Boolean(element.checked),
            })).filter(option => option.value && option.label && option.label !== '(Select All)')"""
        )
        descriptor["options"] = [
            {"value": item["value"], "label": item["label"]}
            for item in option_rows
        ]
        selected_values = [
            item["value"] for item in option_rows if item.get("selected")
        ]
        descriptor["value"] = (
            selected_values
            if descriptor.get("type") == "multiselect"
            else (selected_values[0] if selected_values else "")
        )
        button.click()
        _wait(page, 50)
    return parameters


def load_report_parameters(
    report_id: str, log: Callable[[str], None] = print
) -> dict[str, Any]:
    report = _report(report_id)
    if report is None:
        return _result(False, "REPORT_UNKNOWN", "Báo cáo không được hỗ trợ.")
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        _write_log(log, f"[REPORT] Đang tải tham số {report['name']}...")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        parameters = _read_parameters(report_page)
        _write_log(log, f"[REPORT] Đã đọc {len(parameters)} tham số.")
        return _result(
            True,
            "REPORT_PARAMETERS_LOADED",
            f"Đã tải tham số cho {report['name']}.",
            report_id=report["id"],
            report_name=report["name"],
            parameters=parameters,
        )
    except PlaywrightTimeoutError:
        return _result(
            False,
            "REPORT_PARAMETERS_NOT_READY",
            "WFX chưa tải xong tham số báo cáo. Hãy thử lại.",
        )
    except Exception as exc:
        return _result(False, "REPORT_LOAD_FAILED", f"{type(exc).__name__}: {exc}")
    finally:
        if playwright is not None:
            playwright.stop()


def _set_parameters(page: Page, values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        checkpoint()
        locator = page.locator(f'[id="{str(key).replace(chr(34), "")}"]').first
        if not locator.count() or not locator.is_visible():
            continue
        tag = (locator.evaluate("element => element.tagName") or "").upper()
        input_type = (locator.get_attribute("type") or "text").casefold()
        is_date_input = bool(
            locator.evaluate(
                """element => element.type === 'date' ||
                element.classList.contains('hasDatepicker') ||
                Boolean(element.closest('td, th')?.querySelector(
                  'img.ui-datepicker-trigger, input[type="image"][src*="calendar" i], img[src*="calendar" i], [id*="calendar" i]'))"""
            )
        )
        if is_date_input:
            cleaned = str(value or "")
            parts = cleaned.split("-")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                cleaned = f"{int(parts[1])}/{int(parts[2])}/{parts[0]}"
            try:
                locator.fill(cleaned)
            except PlaywrightError:
                # Một số bản ReportViewer đặt readonly và chỉ nhận giá trị
                # sau khi picker phát input/change; mô phỏng đúng hai event.
                locator.evaluate(
                    """(element, nextValue) => {
                      const readonly = element.hasAttribute('readonly');
                      element.removeAttribute('readonly');
                      element.value = nextValue;
                      element.dispatchEvent(new Event('input', {bubbles: true}));
                      element.dispatchEvent(new Event('change', {bubbles: true}));
                      if (readonly) element.setAttribute('readonly', 'readonly');
                    }""",
                    cleaned,
                )
            continue
        if tag == "SELECT":
            locator.select_option(
                [str(item) for item in value]
                if isinstance(value, list)
                else str(value)
            )
        elif isinstance(value, list) and locator.get_attribute("readonly") is not None:
            button_id = str(key).removesuffix("_txtValue") + "_ddDropDownButton"
            root_id = str(key).removesuffix("_txtValue") + "_divDropDown"
            button = page.locator(f'#{button_id}')
            button.click()
            _wait(page, 100)
            options = page.locator(f'#{root_id} input[type="checkbox"]')
            if options.count():
                select_all = options.first
                if select_all.is_checked():
                    select_all.uncheck()
                selected = {str(item) for item in value}
                for index in range(1, options.count()):
                    option = options.nth(index)
                    option.set_checked(
                        str(option.get_attribute("id") or "") in selected
                    )
            button.click()
        elif locator.get_attribute("readonly") is not None:
            button_id = str(key).removesuffix("_txtValue") + "_ddDropDownButton"
            button = page.locator(f'#{button_id}')
            if button.count() and button.is_visible():
                button.click()
                _wait(page, 100)
                target = page.locator(f'[id="{str(value).replace(chr(34), "")}"]')
                if target.count():
                    target.set_checked(True)
                button.click()
        elif input_type == "checkbox":
            locator.set_checked(bool(value))
        else:
            cleaned = str(value or "")
            locator.fill(cleaned)


def _click_view_report(page: Page) -> None:
    candidates = (
        'input[type="submit"][value*="View"]',
        'input[type="button"][value*="View"]',
        'button:has-text("View Report")',
        'a:has-text("View Report")',
    )
    for selector in candidates:
        locator = page.locator(selector)
        try:
            if locator.count() and locator.first.is_visible():
                locator.first.click()
                return
        except PlaywrightError:
            continue
    raise RuntimeError("REPORT_VIEW_BUTTON_NOT_FOUND")


def _wait_report_ready(
    page: Page,
    log: Callable[[str], None],
    timeout_s: float = REPORT_READY_TIMEOUT_SECONDS,
) -> None:
    """Chờ ReportViewer hoàn tất postback tới deadline cấu hình."""
    started = time.monotonic()
    deadline = started + timeout_s
    maximum_seconds = max(1, int(timeout_s))
    maximum_label = (
        f"{maximum_seconds // 60} phút"
        if maximum_seconds % 60 == 0
        else f"{maximum_seconds} giây"
    )
    stable_since = 0.0
    next_progress = started + 15
    _write_log(
        log,
        f"[REPORT] Đang chờ báo cáo tải xong (tối đa {maximum_label})...",
    )
    while time.monotonic() < deadline:
        checkpoint()
        now = time.monotonic()
        try:
            async_busy = bool(
                page.evaluate(
                    """() => {
                      const manager = window.Sys?.WebForms?.PageRequestManager
                        ?.getInstance?.();
                      return Boolean(manager?.get_isInAsyncPostBack?.());
                    }"""
                )
            )
            loading = page.locator(
                '[id*="AsyncWait"][style*="display: block"], '
                '[id*="AsyncWait"][aria-hidden="false"], [aria-busy="true"]'
            )
            has_loading = any(
                loading.nth(index).is_visible()
                for index in range(loading.count())
            )
            export = page.locator(REPORT_EXPORT_BUTTON).first
            image = page.locator(REPORT_EXPORT_IMAGE).first
            image_disabled = False
            if image.count():
                image_disabled = "disabled" in str(
                    image.get_attribute("src") or ""
                ).casefold()
            ready = (
                now - started >= 1.5
                and export.count()
                and export.is_visible()
                and export.is_enabled()
                and not image_disabled
                and not async_busy
                and not has_loading
            )
            if ready:
                if not stable_since:
                    stable_since = now
                elif now - stable_since >= 1:
                    _write_log(log, "[REPORT] Báo cáo đã tải xong.")
                    return
            else:
                stable_since = 0.0
        except PlaywrightError:
            stable_since = 0.0
        if now >= next_progress:
            elapsed = min(int(now - started), maximum_seconds)
            _write_log(
                log,
                f"[REPORT] Vẫn đang tải báo cáo... "
                f"({elapsed}/{maximum_seconds} giây)",
            )
            next_progress = now + 15
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Report Viewer chưa tải xong sau {maximum_label}."
    )


def _export_excel(page: Page) -> str:
    downloads: list[Any] = []
    attached_pages: list[Page] = []
    downloads_before_click = snapshot_downloads()

    def received(download: Any) -> None:
        downloads.append(download)

    def attach(current: Page) -> None:
        if current in attached_pages:
            return
        attached_pages.append(current)
        current.on("download", received)

    for current in page.context.pages:
        attach(current)
    page.context.on("page", attach)
    try:
        export = page.locator(REPORT_EXPORT_BUTTON).first
        export.wait_for(state="visible", timeout=10_000)
        export.evaluate("element => element.click()")
        excel = page.locator(REPORT_EXCEL_ACTION).first
        excel.wait_for(state="attached", timeout=10_000)
        # ReportViewer giữ link Excel trong menu display:none. DOM click gọi
        # exportReport('EXCELOPENXML') ổn định hơn việc chờ menu animation.
        excel.evaluate("element => element.click()")
        deadline = time.monotonic() + REPORT_DOWNLOAD_TIMEOUT_SECONDS
        stable_file: tuple[Any, tuple[int, int]] | None = None
        while time.monotonic() < deadline:
            if downloads:
                return str(downloads[0].suggested_filename or "report.xlsx")
            # Chrome chạy với download native có thể đã lưu file nhưng CDP
            # không phát event ``download``. Đối chiếu snapshot để không báo
            # lỗi giả khi file thực tế đã nằm trong Downloads.
            current_downloads = snapshot_downloads()
            candidates = [
                (path, state)
                for path, state in current_downloads.items()
                if path.suffix.casefold() in {".xls", ".xlsx"}
                and downloads_before_click.get(path) != state
            ]
            if candidates:
                candidate = max(
                    candidates,
                    key=lambda item: item[1][1],
                )
                if stable_file == candidate:
                    return candidate[0].name
                stable_file = candidate
            else:
                stable_file = None
            _wait(page, 100)
        raise RuntimeError("REPORT_DOWNLOAD_NOT_STARTED")
    finally:
        for current in attached_pages:
            try:
                current.remove_listener("download", received)
            except Exception:
                pass
        try:
            page.context.remove_listener("page", attach)
        except Exception:
            pass


def export_report_excel(
    report_id: str,
    values: Mapping[str, Any] | None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    report = _report(report_id)
    if report is None:
        return _result(False, "REPORT_UNKNOWN", "Báo cáo không được hỗ trợ.")
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
        report_page = _open_report(page, report)
        _attach_dialog_handler(report_page, log)
        _set_parameters(report_page, values or {})
        _write_log(log, f"[REPORT] Đang chạy {report['name']}...")
        _click_view_report(report_page)
        _wait_report_ready(report_page, log)
        _write_log(log, "[REPORT] Đang export Excel...")
        filename = _export_excel(report_page)
        return _result(
            True,
            "REPORT_EXPORTED",
            f"Đã tải {filename}. Chrome sẽ hiển thị file để bạn lưu hoặc mở.",
            report_id=report["id"],
            report_name=report["name"],
            file_name=filename,
        )
    except Exception as exc:
        return _result(False, "REPORT_EXPORT_FAILED", f"{type(exc).__name__}: {exc}")
    finally:
        if playwright is not None:
            playwright.stop()
