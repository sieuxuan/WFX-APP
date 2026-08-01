"""Chuẩn bị form New/Copy Style Apparel từ một dòng Excel.

Ranh giới an toàn của module này là form Article đã được điền. Module tuyệt đối
không click Save; người dùng kiểm tra và tự Save trên WFX trước khi chạy dòng kế.
"""

from __future__ import annotations

import re
from typing import Any

from wfx_panel.automation._common import (
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.catalog import open_catalog_folder
from wfx_panel.automation.modules import _active_wfx_page

NEW_STYLE_XPATH = "/html/body/form/table/tbody/tr[3]/td/input"
COPY_CODE_XPATH = "/html/body/form/table/tbody/tr[8]/td/input"
COPY_BUYER_REFERENCE_XPATH = "/html/body/form/table/tbody/tr[10]/td/input"
COPY_SEARCH_XPATH = "/html/body/form/table/tbody/tr[12]/td/input"
COPY_COSTSHEET_XPATH = (
    '//*[@id="wfx_ArticleEdit"]/form/table[3]/tbody/tr/td[1]/table/'
    "tbody/tr[2]/td[4]/input"
)
COPY_AS_VARIANT_XPATH = (
    '//*[@id="wfx_ArticleEdit"]/form/table[3]/tbody/tr/td[2]/table/'
    "tbody/tr/td[2]/input"
)

_COPY_RESULTS_JS = """() => {
    const root = document.querySelector('#wfx_ArticleEdit') || document;
    const form = root.querySelector(':scope > form') || root.querySelector('form');
    const tables = form ? [...form.children].filter(node => node.tagName === 'TABLE') : [];
    const resultTable = tables.length >= 4 ? tables[3] : null;
    if (!resultTable) return [];
    const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const rows = [...resultTable.querySelectorAll('tr')];
    return rows.map((row, rowIndex) => {
        const action = [...row.querySelectorAll(
            'input[type="radio"], input[type="checkbox"], '
            + 'input[type="button"], a[onclick], button'
        )].find(shown);
        if (!action) return null;
        const cells = [...row.querySelectorAll('td')].map(cell => clean(
            cell.querySelector('input')?.value || cell.textContent
        ));
        const text = cells.filter(Boolean).join(' | ');
        const code = (text.match(/\b(?:SWN|SKN)[A-Z0-9._/-]*\b/i) || [])[0] || '';
        return {
            choice_index: rowIndex,
            article_code: clean(code),
            buyer_reference: clean(cells.find(value => value && value !== code) || ''),
            label: text.slice(0, 240),
        };
    }).filter(Boolean);
}"""

_CLICK_COPY_RESULT_JS = """index => {
    const root = document.querySelector('#wfx_ArticleEdit') || document;
    const form = root.querySelector(':scope > form') || root.querySelector('form');
    const tables = form ? [...form.children].filter(node => node.tagName === 'TABLE') : [];
    const resultTable = tables.length >= 4 ? tables[3] : null;
    const row = resultTable?.querySelectorAll('tr')?.[Number(index)];
    if (!row) return false;
    const action = row.querySelector(
        'input[type="radio"], input[type="checkbox"], '
        + 'input[type="button"], a[onclick], button'
    );
    if (!action) return false;
    if ('checked' in action && !action.checked) action.click();
    else action.click();
    return true;
}"""

_SET_STYLE_FIELD_JS = """spec => {
    const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const folded = value => clean(value).toLocaleLowerCase('en');
    const visibleControl = element => element
        && !element.disabled && !element.readOnly
        && !['button', 'submit', 'hidden'].includes(folded(element.type));
    let control = null;
    for (const id of spec.ids || []) {
        const candidate = document.getElementById(id);
        if (candidate && visibleControl(candidate)) {
            control = candidate;
            break;
        }
    }
    if (!control) {
        const labelKey = value => folded(value).replace(/[:*]+$/g, '').trim();
        const aliases = new Set((spec.labels || []).map(labelKey));
        const labels = [...document.querySelectorAll('label, td, th, span')]
            .filter(node => aliases.has(labelKey(node.textContent)));
        for (const label of labels) {
            const forId = label.getAttribute('for');
            const byFor = forId ? document.getElementById(forId) : null;
            if (visibleControl(byFor)) {
                control = byFor;
                break;
            }
            let host = label.closest('tr') || label.parentElement;
            for (let depth = 0; host && depth < 3; depth += 1) {
                const candidates = [...host.querySelectorAll('select, input, textarea')]
                    .filter(visibleControl);
                if (candidates.length) {
                    control = candidates.find(item => !label.contains(item))
                        || candidates[0];
                    break;
                }
                host = host.parentElement;
            }
            if (control) break;
        }
    }
    if (!control) return {ok: false, reason: 'not-found'};
    const wanted = clean(spec.value);
    if (control.tagName === 'SELECT') {
        const options = [...control.options];
        const exact = options.filter(option =>
            folded(option.textContent) === folded(wanted)
            || folded(option.value) === folded(wanted)
        );
        if (exact.length !== 1) {
            return {
                ok: false,
                reason: exact.length ? 'ambiguous-option' : 'option-not-found',
                options: options.map(option => clean(option.textContent)).filter(Boolean).slice(0, 30),
            };
        }
        control.value = exact[0].value;
        exact[0].selected = true;
    } else if (['radio', 'checkbox'].includes(folded(control.type))) {
        const group = control.name
            ? [...document.querySelectorAll(`input[name="${CSS.escape(control.name)}"]`)]
            : [control];
        const exact = group.filter(item =>
            folded(item.value) === folded(wanted)
            || folded(item.title) === folded(wanted)
            || folded(item.parentElement?.textContent) === folded(wanted)
        );
        if (exact.length !== 1) {
            return {ok: false, reason: 'option-not-found'};
        }
        if (!exact[0].checked) exact[0].click();
        control = exact[0];
    } else {
        const prototype = control.tagName === 'TEXTAREA'
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        if (setter) setter.call(control, wanted);
        else control.value = wanted;
    }
    control.dispatchEvent(new Event('input', {bubbles: true}));
    control.dispatchEvent(new Event('change', {bubbles: true}));
    control.dispatchEvent(new Event('blur', {bubbles: true}));
    return {
        ok: true,
        id: control.id || '',
        tag: control.tagName,
        value: clean(control.value),
    };
}"""


STYLE_FIELDS = (
    (
        "material_type",
        "Material Type",
        ("ddlMaterialType", "ddlFabricType", "ddlArticleType"),
        ("Material Type",),
    ),
    ("buyer", "Buyer", ("ddlBuyer",), ("Buyer",)),
    ("division", "Division", ("ddlDivision",), ("Division",)),
    (
        "product_group",
        "Product Group",
        ("ddlProductGroup", "ddlProductCategory"),
        ("Product Group",),
    ),
    (
        "sub_category",
        "Sub-Category",
        ("ddlProductSubCat", "ddlProductSubCategory", "ddlSubCategory"),
        ("Sub-Category", "Sub Category"),
    ),
    ("color_card", "Color Card", ("ddlColorCard",), ("Color Card",)),
    (
        "size_range",
        "Size Range",
        ("ddlSizeWidthRange", "ddlSizeRange"),
        ("Size Range", "Size/Width Range"),
    ),
    ("season", "Season", ("ddlSeason",), ("Season",)),
    (
        "buyer_style_ref",
        "Buyer Style Ref.",
        ("txtBuyerStyleRef", "txtBuyerReference", "txtBuyerStyleReference"),
        ("Buyer Style Ref.", "Buyer Style Ref", "Buyer Reference"),
    ),
    (
        "internal_style_ref",
        "Internal Style Ref",
        ("txtInternalStyleRef", "txtArticleName", "txtInternalReference"),
        ("Internal Style Ref", "Internal Style Reference"),
    ),
)

FIXED_STYLE_FIELDS = (
    (
        "Purchase UOM",
        "Pcs",
        ("ddlStorageUOM",),
        ("Purchase UOM", "Storage UOM"),
    ),
    (
        "Price Per",
        "Article",
        ("ddlPricePer",),
        ("Price Per",),
    ),
    (
        "Color Definition",
        "Single Colors",
        ("ddlColorDefinition", "ddlColourDefinition"),
        ("Color Definition", "Colour Definition"),
    ),
)


def _frame_with_visible_locator(
    context: Any,
    selector: str,
    timeout_s: float,
) -> tuple[Page, Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    locator = frame.locator(selector)
                    for index in range(locator.count()):
                        candidate = locator.nth(index)
                        if candidate.is_visible():
                            return page, frame, candidate
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 120)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _article_left_frame(context: Any, timeout_s: float = 20) -> Frame:
    _page, frame, _locator = _frame_with_visible_locator(
        context,
        f"xpath={NEW_STYLE_XPATH}",
        timeout_s,
    )
    return frame


def _style_editor_frame(context: Any, timeout_s: float = 35) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    title = frame.locator("#titlebarArticle")
                    buyer = frame.locator(
                        "#ddlBuyer, #select2-ddlBuyer-container"
                    )
                    if title.count() and buyer.count():
                        return frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 150)
    raise PlaywrightTimeoutError("Form Article chưa sẵn sàng.")


def _copy_result_frame(context: Any, timeout_s: float = 25) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    candidates = frame.evaluate(_COPY_RESULTS_JS)
                    if candidates:
                        return frame
                    if frame.locator(f"xpath={COPY_AS_VARIANT_XPATH}").count():
                        return frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 150)
    raise PlaywrightTimeoutError("Kết quả tìm Style nguồn chưa sẵn sàng.")


def _set_field(
    context: Any,
    label: str,
    value: str,
    ids: tuple[str, ...],
    labels: tuple[str, ...],
    log: Callable[[str], None],
) -> dict[str, Any]:
    deadline = time.monotonic() + 18
    last: dict[str, Any] = {"ok": False, "reason": "not-found"}
    while time.monotonic() < deadline:
        frame = _style_editor_frame(context, timeout_s=2)
        try:
            last = frame.evaluate(
                _SET_STYLE_FIELD_JS,
                {"ids": list(ids), "labels": list(labels), "value": value},
            )
            if last.get("ok"):
                _write_log(log, f"[STYLE] Đã điền {label}.")
                _wait(frame, 350)
                return last
            if last.get("reason") in {"option-not-found", "ambiguous-option"}:
                break
        except PlaywrightError:
            pass
        if context.pages:
            _wait(context.pages[0], 150)
    detail = ", ".join(last.get("options") or [])
    raise RuntimeError(
        f"STYLE_FIELD_NOT_AVAILABLE:{label}"
        + (f":{detail}" if detail else "")
    )


def _fill_style_editor(
    context: Any,
    row: dict[str, Any],
    log: Callable[[str], None],
) -> list[str]:
    kind = str(row.get("type") or "").strip().casefold()
    filled: list[str] = []
    for key, label, ids, labels in STYLE_FIELDS:
        value = str(row.get(key) or "").strip()
        if not value:
            if kind == "new":
                raise RuntimeError(f"STYLE_REQUIRED_FIELD_MISSING:{label}")
            continue
        _set_field(context, label, value, ids, labels, log)
        filled.append(label)
    for label, value, ids, labels in FIXED_STYLE_FIELDS:
        _set_field(context, label, value, ids, labels, log)
        filled.append(label)
    return filled


def _prepare_copy(
    context: Any,
    frame: Frame,
    row: dict[str, Any],
    copy_choice: int | None,
    log: Callable[[str], None],
) -> dict[str, Any] | None:
    source = str(row.get("style_copy") or "").strip()
    code_search = bool(re.match(r"^(?:SWN|SKN)", source, re.IGNORECASE))
    input_xpath = COPY_CODE_XPATH if code_search else COPY_BUYER_REFERENCE_XPATH
    search_input = frame.locator(f"xpath={input_xpath}").first
    search_input.wait_for(state="visible", timeout=5_000)
    search_input.fill(source)
    search = frame.locator(f"xpath={COPY_SEARCH_XPATH}").first
    search.wait_for(state="visible", timeout=5_000)
    search.click()
    _write_log(
        log,
        "[STYLE COPY] Đang tìm bằng "
        + ("Article Code." if code_search else "Buyer Reference."),
    )
    result_frame = _copy_result_frame(context)
    choices = list(result_frame.evaluate(_COPY_RESULTS_JS) or [])
    if not choices:
        raise RuntimeError("STYLE_COPY_NOT_FOUND")
    if len(choices) > 1 and copy_choice is None:
        return _result(
            True,
            "STYLE_COPY_MULTIPLE_RESULTS",
            f"Có {len(choices)} Style nguồn. Hãy chọn đúng một Style trong app.",
            choices=choices,
            source_row=int(row.get("source_row") or 0),
        )
    selected_index = (
        int(choices[0]["choice_index"])
        if len(choices) == 1
        else int(copy_choice if copy_choice is not None else -1)
    )
    allowed = {int(choice["choice_index"]) for choice in choices}
    if selected_index not in allowed:
        raise RuntimeError("STYLE_COPY_CHOICE_INVALID")
    if not result_frame.evaluate(_CLICK_COPY_RESULT_JS, selected_index):
        raise RuntimeError("STYLE_COPY_RESULT_DETACHED")

    costsheet = result_frame.locator(f"xpath={COPY_COSTSHEET_XPATH}").first
    costsheet.wait_for(state="attached", timeout=5_000)
    if not costsheet.is_checked():
        costsheet.check()
    variant = result_frame.locator(f"xpath={COPY_AS_VARIANT_XPATH}").first
    variant.wait_for(state="visible", timeout=5_000)
    variant.click()
    _write_log(log, "[STYLE COPY] Đã chọn CostSheet và Copy as Variant.")
    return None


def prepare_catalog_style_row(
    category_value: str,
    group_id: str,
    row: dict[str, Any],
    copy_choice: int | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chuẩn bị đúng một Style và dừng trước Save."""
    kind = str(row.get("type") or "").strip().casefold()
    if kind not in {"new", "copy"}:
        return _result(False, "STYLE_TYPE_INVALID", "Type phải là New hoặc Copy.")
    group_id = str(group_id or "").strip()
    if not group_id.isdigit():
        return _result(
            False,
            "STYLE_GROUP_REQUIRED",
            "Hãy chọn đúng một Group Apparel trước khi chuẩn bị Style.",
        )

    opened = open_catalog_folder("Apparel", category_value, group_id, log)
    if not opened.get("ok"):
        return opened
    if str((opened.get("folder") or {}).get("kind") or "") != "group":
        return _result(
            False,
            "STYLE_GROUP_REQUIRED",
            "Vị trí đã chọn không phải Group. Hãy chọn một Group Apparel.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        _page, _frame, new_link = _frame_with_visible_locator(
            context,
            "a.clsNavLinkNew",
            12,
        )
        new_link.click()
        _write_log(log, "[STYLE] Đã mở New trong Group đã chọn.")
        choice_frame = _article_left_frame(context)

        if kind == "new":
            new_button = choice_frame.locator(f"xpath={NEW_STYLE_XPATH}").first
            new_button.click()
        else:
            pending = _prepare_copy(
                context,
                choice_frame,
                row,
                copy_choice,
                log,
            )
            if pending is not None:
                return pending

        _style_editor_frame(context)
        filled = _fill_style_editor(context, row, log)
        page.bring_to_front()
        source_row = int(row.get("source_row") or 0)
        return _result(
            True,
            "STYLE_FORM_READY",
            (
                f"Đã chuẩn bị dòng {source_row} trên WFX và dừng trước Save. "
                "Hãy kiểm tra rồi tự bấm Save."
            ),
            source_row=source_row,
            style_type="New" if kind == "new" else "Copy",
            filled_fields=filled,
            requires_manual_save=True,
        )
    except RuntimeError as exc:
        raw = str(exc)
        code, _, detail = raw.partition(":")
        messages = {
            "STYLE_COPY_NOT_FOUND": "Không tìm thấy Style nguồn để Copy.",
            "STYLE_COPY_CHOICE_INVALID": "Lựa chọn Style nguồn không còn hợp lệ.",
            "STYLE_COPY_RESULT_DETACHED": "Dòng Style nguồn đã đổi trước khi chọn.",
            "STYLE_REQUIRED_FIELD_MISSING": (
                f"Dòng New còn thiếu trường bắt buộc: {detail}."
            ),
            "STYLE_FIELD_NOT_AVAILABLE": (
                f"Không điền được trường {detail.split(':', 1)[0] or 'Style'} "
                "trên form WFX."
            ),
        }
        if code in messages:
            return _result(False, code, messages[code])
        message = f"Không chuẩn bị được Style: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_PREPARE_FAILED", message)
    except PlaywrightTimeoutError as exc:
        message = f"Màn hình Tạo Style chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_FORM_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "STYLE_PREPARE_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
