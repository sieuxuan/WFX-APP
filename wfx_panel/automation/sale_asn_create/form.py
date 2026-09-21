"""Mở/refresh form Sale ASN New và đặt giá trị control.

Frame WFXSalesASN.aspx đang mở phải được reload trước mỗi lượt, kể cả khi
đang trống, để không dùng datasource PO stale."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _ensure_select_value,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.modules import _click_module_menu_on_page
from wfx_panel.automation.sale_asn_create.values import (
    _best_dropdown_label,
    _best_factory_label,
)

_SET_CONTROL_JS = r"""spec => {
    const clean = value => String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en');
    const shown = element => {
        if (!element || !element.isConnected || element.disabled || element.readOnly) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const hosts = [...document.querySelectorAll(spec.selector)];
    const host = hosts.find(shown) || hosts[0] || null;
    if (!host) return {ok: false, reason: 'host-not-found'};
    let control = ['INPUT', 'SELECT', 'TEXTAREA'].includes(host.tagName) ? host : null;
    control = control || [...host.querySelectorAll('input, select, textarea')]
        .find(item => item.type !== 'hidden' && !item.disabled);
    if (!control) {
        const action = host.querySelector('.lblEditable, [contenteditable="true"], span, div:nth-child(2)') || host;
        action.click();
        control = [...host.querySelectorAll('input, select, textarea')]
            .find(item => item.type !== 'hidden' && !item.disabled)
            || [...document.querySelectorAll('select')]
                .filter(item => shown(item)).at(-1);
        if (!control && ['exact', 'first', 'options'].includes(spec.mode)) {
            const choices = [...document.querySelectorAll(
                '[role="option"], .select2-results__option, li.clsMultiSelectContent'
            )].filter(shown);
            if (spec.mode === 'options') {
                return {
                    ok: false,
                    reason: 'option-not-found',
                    options: choices.map(item => clean(item.textContent)).slice(0, 500),
                };
            }
            const chosen = spec.mode === 'first'
                ? choices[0]
                : choices.find(item => fold(item.textContent) === fold(spec.value)
                    || fold(item.getAttribute('data-value')) === fold(spec.value));
            if (chosen) {
                chosen.click();
                return {ok: true, value: clean(chosen.textContent), tag: chosen.tagName};
            }
        }
        control = control || [...document.querySelectorAll('input, textarea')]
            .filter(item => shown(item) && item.type !== 'hidden').at(-1);
    }
    if (!control) return {ok: false, reason: 'editor-not-found'};
    const wanted = clean(spec.value);
    if (control.tagName === 'SELECT') {
        const choices = [...control.options].filter(option => !option.disabled
            && clean(option.value) && !/^\[?select\]?$/i.test(clean(option.textContent)));
        if (spec.mode === 'options') {
            control.dispatchEvent(new MouseEvent(
                'mousedown', {bubbles: true, cancelable: true, view: window}
            ));
            return {
                ok: false,
                reason: 'option-not-found',
                options: choices.map(item => clean(item.textContent)).slice(0, 500),
            };
        }
        let option = null;
        if (spec.mode === 'first') option = choices[0] || null;
        else option = choices.find(item => fold(item.textContent) === fold(wanted)
            || fold(item.value) === fold(wanted)) || null;
        if (!option) {
            control.dispatchEvent(new MouseEvent(
                'mousedown', {bubbles: true, cancelable: true, view: window}
            ));
            return {
                ok: false,
                reason: 'option-not-found',
                options: choices.map(item => clean(item.textContent)).slice(0, 30),
            };
        }
        control.value = option.value;
        option.selected = true;
    } else if (spec.mode === 'options') {
        return {ok: false, reason: 'option-not-found', options: []};
    } else if (control.isContentEditable) {
        control.textContent = wanted;
    } else {
        const prototype = control.tagName === 'TEXTAREA'
            ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        if (setter) setter.call(control, wanted); else control.value = wanted;
    }
    control.dispatchEvent(new Event('input', {bubbles: true}));
    control.dispatchEvent(new Event('change', {bubbles: true}));
    control.dispatchEvent(new Event('blur', {bubbles: true}));
    return {ok: true, value: clean(control.value || control.textContent), tag: control.tagName};
}"""


def _frame_with_selector(context: Any, selector: str, timeout_s: float = 20) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    locator = frame.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        return page, frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 120)
    raise PlaywrightTimeoutError(f"Không tìm thấy vùng Sale ASN: {selector}")


def _open_new_form(page: Page, xpath: str, log: Callable[[str], None]) -> Frame:
    _click_module_menu_on_page(page, "Sale ASN > New", xpath, log)
    _ensure_select_value(page, "#ddlASNType", "1", "ASN Type", log)
    _ensure_select_value(page, "#ddlASNAgainst", "BuyerOrderDispatch", "ASN Against", log)
    _page, frame = _frame_with_selector(page.context, "#Cell_Buyer")
    return frame


def _refresh_existing_new_form(page: Page, log: Callable[[str], None]) -> Frame | None:
    """Reload form Sale ASN New đang mở để bỏ Buyer/datasource cũ."""

    try:
        existing_page, frame = _frame_with_selector(
            page.context,
            "#Cell_Buyer",
            timeout_s=1,
        )
    except (PlaywrightError, PlaywrightTimeoutError):
        return None
    if "wfxsalesasn" not in frame.url.casefold():
        return None
    try:
        frame.goto(
            frame.url,
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        _ensure_select_value(
            existing_page,
            "#ddlASNType",
            "1",
            "ASN Type",
            log,
        )
        _ensure_select_value(
            existing_page,
            "#ddlASNAgainst",
            "BuyerOrderDispatch",
            "ASN Against",
            log,
        )
        _page, refreshed = _frame_with_selector(
            page.context,
            "#Cell_Buyer",
            timeout_s=15,
        )
    except (PlaywrightError, PlaywrightTimeoutError):
        _write_log(
            log,
            "[SALE ASN] Không refresh được form New đang mở; sẽ mở lại từ menu.",
        )
        return None
    _write_log(
        log,
        "[SALE ASN] Đã refresh form New đang mở trước khi chọn Buyer.",
    )
    return refreshed


def _set_control(
    frame: Frame,
    selector: str,
    value: str,
    mode: str,
    timeout_s: float = 3,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {"ok": False, "reason": "not-found"}
    requested_mode = mode
    selected_value = value
    selected_mode = (
        "options"
        if requested_mode in {"closest", "factory_first"}
        else requested_mode
    )
    while time.monotonic() < deadline:
        try:
            last = frame.evaluate(
                _SET_CONTROL_JS,
                {
                    "selector": selector,
                    "value": selected_value,
                    "mode": selected_mode,
                },
            )
            if last.get("ok"):
                return last
            if selected_mode == "options" and requested_mode in {
                "closest",
                "factory_first",
            }:
                matcher = (
                    _best_factory_label
                    if requested_mode == "factory_first"
                    else _best_dropdown_label
                )
                matched = matcher(last.get("options") or (), value)
                if matched:
                    selected_value = matched
                    selected_mode = "exact"
                    continue
        except PlaywrightError:
            last = {"ok": False, "reason": "document-changed"}
        _wait(frame, 120)
    return last
