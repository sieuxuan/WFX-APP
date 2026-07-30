"""Khảo sát và thao tác Costing trong popup Article của WFX.

Module chỉ tin metadata vừa quét từ DOM hiện tại. Workbook không được truyền
selector/DOM index vào các hàm ghi dữ liệu.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _sleep,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint
from wfx_panel.automation.session import _session_is_active
from wfx_panel.costing_planner import (
    CostingPlanError,
    build_costing_plan,
    live_signature,
)
from wfx_panel.costing_workbook import FORMAT_VERSION, normalize_document

COSTING_DETAIL_SELECTOR = "#sectionCostSheetDetail"
COSTING_TREE_SELECTOR = "#sectionCostSheetTree"
COSTING_NEW_SELECTOR = "#sectionCostSheetTree #RowTool #imgNew"
COSTING_SAVE_SELECTOR = "#titlebarCostSheet"
COSTING_GRID_SELECTOR = "#gridCostSheetDetail_tblGridContent"
FIELD_CONTROL_SELECTOR = (
    "input:not([type='button']):not([type='submit']):not([type='image']),"
    "select,textarea,.lblEditable,"
    "span.clsGridLabelContent[id],span.clsSectionLabelContent[id]"
)
FORBIDDEN_CONTROL_IDS = frozenset(
    {
        "colBodyType",
        "imgDeleteSection",
        "imgEditSection",
        "imgCopySection",
    }
)
FORBIDDEN_ACTION_SELECTORS = frozenset(
    {
        "#colBodyType label span",
        "#imgDeleteSection",
        "#imgEditSection",
        "#imgCopySection",
    }
)

_KEY_CLEAN_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
_COSTING_STATUS_RE = re.compile(
    r"\b(open|approved|closed|cancelled|draft|pending)\b",
    re.IGNORECASE,
)
_COSTING_NO_OPEN_RE = re.compile(
    r"\b(not\s+open|no\s+(?:cost(?:ing)?|cost\s*sheet)|not\s+created)\b",
    re.IGNORECASE,
)
_STYLE_CODE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{2,8}[A-Z0-9_-]*\d{4,}[A-Z0-9_-]*)(?![A-Z0-9])",
    re.IGNORECASE,
)
_ARTICLE_LEFT_STYLE_RE = re.compile(
    r"\(\s*([A-Z]{2,8}[A-Z0-9_-]*\d{4,}[A-Z0-9_-]*)\s*/",
    re.IGNORECASE,
)
_ARTICLE_NAME_CODE_RE = re.compile(r"\(\s*([^()/]+?)\s*/")
_ARTICLE_NAME_VALUE_RE = re.compile(r"\([^()/]+/(.*?)\)\s*$")
_STYLE_CODE_CONTROL_SELECTORS = (
    "#lblArticleCode",
    "#txtArticleCode",
    "#lblStyleCode",
    "#txtStyleCode",
    "[name='ArticleCode']",
    "[name='StyleCode']",
)


class CostingFieldApplyError(RuntimeError):
    """Giữ context field khi WFX không mở hoặc không nhận editor."""

    def __init__(
        self,
        field_key: str,
        item_key: str,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.field_key = str(field_key or "")
        self.item_key = str(item_key or "")
        self.reason = str(reason or "")


_COSTING_INVENTORY_JS = r"""grid => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' &&
            Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
    };
    // WFX renders several numeric cells as a logical "upper" label plus a
    // visible sibling whose id ends in "~".  A newly inserted Article keeps
    // the clean value/editability on the zero-height upper label, while only
    // the sibling can be clicked.  Export one logical field and remember the
    // safe visible click target instead of exporting WFX's duplicate.
    const compositePrimaryIds = new Set([
        'lblConsQty', 'lblRate1', 'lblAmtorPer', 'lblValueInCSCurr'
    ]);
    const compositeClickTarget = element => {
        if (!compositePrimaryIds.has(clean(element?.id))) return null;
        const siblingId = `${element.id}~`;
        const sibling = [...(element.parentElement?.querySelectorAll('[id]') || [])]
            .find(candidate => candidate.id === siblingId);
        return shown(sibling) ? sibling : null;
    };
    const forbiddenIds = new Set([
        'colBodyType', 'imgDeleteSection', 'imgEditSection', 'imgCopySection'
    ]);
    const ignoredControlIds = new Set([
        'chkSelector', 'chkAllSelector', 'lblArticle', 'imgArticle',
        'lblBOMCodeTranslated', 'lblTitle',
        'CostSheetCMCosts_lblSupplierCompany',
        'CostSheetProdProcessDetails_lblProcessName'
    ]);
    const controlSelector =
        "input:not([type='button']):not([type='submit']):not([type='image'])," +
        "select,textarea,.lblEditable,.lblEditSelect," +
        "span.clsGridLabelContent[id],span.clsSectionLabelContent[id]";
    const root = grid.closest('#sectionCostSheetDetail') || document.body;
    const headerLabels = new Map(
        [...root.querySelectorAll(
            '#gridCostSheetDetail_tblGridHeader #gridCostSheetDetail_trHeader > *'
        )].map(cell => {
            const column = clean(cell.id).replace(
                /^gridCostSheetDetail_tblGridHeader_trHeader_td_/, ''
            );
            return [column, clean(cell.title || cell.textContent)];
        })
    );
    const humanize = value => clean(
        String(value || '')
            .replace(/^lbl|^txt|^ddl|^chk|Value$/g, '')
            .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
            .replace(/[_~]+/g, ' ')
    );
    const labelFor = element => {
        const aria = clean(element.getAttribute('aria-label'));
        if (aria) return aria;
        const id = clean(element.id);
        if (id === 'lblMinutes') return 'Minutes';
        const explicit = id
            ? document.querySelector(`label[for="${CSS.escape(id)}"]`)
            : null;
        if (explicit && clean(explicit.textContent)) return clean(explicit.textContent);
        const cell = element.closest('td,th');
        if (cell) {
            const columnLabel = headerLabels.get(clean(cell.id));
            if (columnLabel) return columnLabel;
        }
        const title = clean(element.getAttribute('title'));
        if (title && !/^-?\d+(?:\.\d+)?%?$/.test(title)) return title;
        return humanize(id || element.getAttribute('name'));
    };
    const controlValue = element => {
        const tag = element.tagName.toLowerCase();
        if (tag === 'select') {
            return clean(element.selectedOptions?.[0]?.textContent || element.value);
        }
        if (tag === 'input') {
            const type = clean(element.type).toLowerCase();
            if (type === 'checkbox' || type === 'radio') return Boolean(element.checked);
            return element.value ?? '';
        }
        if (tag === 'textarea') return element.value ?? '';
        const title = element.getAttribute('title');
        return clean(title || element.textContent);
    };
    const articleFromRow = row => {
        const articleText = clean(row.querySelector('#lblArticle')?.textContent);
        if (!articleText || articleText === '>>') return {code: '', name: ''};
        const codeMatch = articleText.match(/\(([A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*)\)\s*$/i);
        return {
            code: clean(codeMatch?.[1]),
            name: clean(
                codeMatch ? articleText.slice(0, codeMatch.index) : articleText
            )
        };
    };
    const rowIdentity = row => clean(
        row.querySelector('#CostSheetProdProcessDetails_lblProcessName')?.textContent ||
        row.querySelector('#CostSheetCMCosts_lblSupplierCompany')?.textContent ||
        row.querySelector('#lblTitle')?.textContent
    );
    const sectionHeader = row => {
        const classes = clean(row.className);
        return /\bcssGridRow(?:BOMCodeMainHeader|CMCostHeader|ProdProcessHeader|ICHeader)RowType\b/i
            .test(classes);
    };
    const sections = [];
    const fields = [];
    let domIndex = 0;
    let currentSection = null;
    const rows = [...grid.querySelectorAll(':scope > tbody > tr')];
    // Một Article WFX có thể chiếm nhiều DOM row: row đầu chứa "(Code)",
    // row tiếp theo chỉ hiện ">>". Không được gộp các row này vào cùng itemKey
    // vì Material Color/Size của row sau sẽ bị áp lên editor của row đầu.
    const effectiveArticleByRow = new Map();
    const articleRowCounts = new Map();
    let scanSectionKey = '';
    let scanSectionNumber = 0;
    let previousArticle = {code: '', name: ''};
    rows.forEach((row, rowIndex) => {
        if (sectionHeader(row)) {
            const name = clean(
                row.querySelector('#lblBOMCodeTranslated')?.textContent ||
                row.querySelector('#colArticle')?.textContent
            );
            if (name) {
                scanSectionNumber += 1;
                scanSectionKey = `section-${scanSectionNumber}-${name}`;
            }
            previousArticle = {code: '', name: ''};
            return;
        }
        const rawArticle = articleFromRow(row);
        const articleText = clean(
            row.querySelector('#lblArticle')?.textContent
        );
        if (rawArticle.code) previousArticle = rawArticle;
        const article = (
            !rawArticle.code && articleText === '>>' && previousArticle.code
                ? previousArticle
                : rawArticle
        );
        effectiveArticleByRow.set(rowIndex, article);
        if (scanSectionKey && article.code) {
            const countKey = (
                `${scanSectionKey}|${article.code}`
            ).toLowerCase();
            articleRowCounts.set(
                countKey,
                (articleRowCounts.get(countKey) || 0) + 1
            );
        }
    });
    const articleRowOrdinals = new Map();
    rows.forEach((row, rowIndex) => {
        if (sectionHeader(row)) {
            const name = clean(
                row.querySelector('#lblBOMCodeTranslated')?.textContent ||
                row.querySelector('#colArticle')?.textContent
            );
            if (name) {
                currentSection = {
                    sectionKey: `section-${sections.length + 1}-${name}`,
                    name,
                    rowOrder: rowIndex
                };
                sections.push(currentSection);
            }
            return;
        }
        if (!currentSection) return;
        const article = (
            effectiveArticleByRow.get(rowIndex) || articleFromRow(row)
        );
        const identity = rowIdentity(row);
        const selectorValue = clean(row.querySelector('#chkSelector')?.value);
        let itemKey = article.code || identity
            ? (article.code || (
                selectorValue && !['0', '-999'].includes(selectorValue)
                    ? selectorValue
                    : identity
            ))
            : '';
        if (article.code) {
            const countKey = (
                `${currentSection.sectionKey}|${article.code}`
            ).toLowerCase();
            if ((articleRowCounts.get(countKey) || 0) > 1) {
                const ordinal = (articleRowOrdinals.get(countKey) || 0) + 1;
                articleRowOrdinals.set(countKey, ordinal);
                const stableRow = (
                    selectorValue && !['0', '-999'].includes(selectorValue)
                        ? selectorValue
                        : 'row'
                );
                itemKey = `${article.code}::${stableRow}::${ordinal}`;
            }
        }
        if (!itemKey) return;
        const rowSignature = clean(
            [article.code, article.name, identity, selectorValue].join('|')
        );
        [...row.querySelectorAll(controlSelector)].forEach((element, rowControlIndex) => {
            const isShown = shown(element);
            const compositeTarget = isShown ? null : compositeClickTarget(element);
            if (!isShown && !compositeTarget) return;
            const cell = element.closest('td,th');
            const cellId = clean(cell?.id);
            const id = clean(element.id);
            if (
                !id ||
                id.endsWith('~') ||
                ignoredControlIds.has(id) ||
                forbiddenIds.has(id) ||
                cellId === 'colBodyType' ||
                /^(colSelector|colimg|colSplitterForUsage)$/.test(cellId) ||
                element.closest(
                    '#colBodyType, #imgDeleteSection, #imgEditSection, #imgCopySection'
                )
            ) return;
            const tag = element.tagName.toLowerCase();
            const type = clean(element.getAttribute('type')).toLowerCase();
            const numeric = element.getAttribute('numeric') === '1' ||
                type === 'number' ||
                /numeric|decimal|amount/i.test(element.className || '');
            const optionNodes = tag === 'select' ? [...element.options] : [];
            const editable = (
                ['input', 'select', 'textarea'].includes(tag)
                    ? !element.disabled && !element.readOnly &&
                        !['hidden', 'file'].includes(type)
                    : element.classList.contains('lblEditable') ||
                        element.classList.contains('lblEditSelect')
            );
            const value = controlValue(element);
            if (!editable && value === '') return;
            fields.push({
                domIndex: domIndex++,
                domId: id,
                clickDomId: clean(compositeTarget?.id || id),
                domName: clean(element.getAttribute('name')),
                dataField: cellId,
                tag,
                inputType: type,
                classes: clean(element.className),
                label: labelFor(element),
                value,
                editable,
                required: Boolean(element.required) ||
                    element.getAttribute('aria-required') === 'true' ||
                    element.classList.contains('lblMandatory') ||
                    element.classList.contains('clsMandatoryItem'),
                dataType: type === 'checkbox' || type === 'radio'
                    ? 'boolean'
                    : numeric ? 'number' : tag === 'select' ? 'select' : 'text',
                options: optionNodes.map(option => clean(option.textContent))
                    .filter(Boolean),
                optionValues: optionNodes.map(option => clean(option.value)),
                sectionKey: currentSection.sectionKey,
                sectionName: currentSection.name,
                itemKey,
                articleCode: article.code,
                articleName: article.name || identity,
                itemType: article.code ? 'article' : 'cost_line',
                rowOrder: rowIndex,
                visible: true,
                region: 'grid',
                rowIndex,
                rowControlIndex,
                cellId,
                rowSignature
            });
        });
    });

    [...document.querySelectorAll(controlSelector)].forEach(element => {
        if (grid.contains(element) || !shown(element)) return;
        const id = clean(element.id);
        const type = clean(element.getAttribute('type')).toLowerCase();
        if (
            !id ||
            id.endsWith('~') ||
            ignoredControlIds.has(id) ||
            forbiddenIds.has(id) ||
            ['file', 'hidden'].includes(type) ||
            element.closest(
                '#colBodyType, #imgDeleteSection, #imgEditSection, #imgCopySection'
            )
        ) return;
        const tag = element.tagName.toLowerCase();
        const numeric = element.getAttribute('numeric') === '1' ||
            type === 'number' || /numeric|decimal|amount/i.test(element.className || '');
        const optionNodes = tag === 'select' ? [...element.options] : [];
        const editable = (
            ['input', 'select', 'textarea'].includes(tag)
                ? !element.disabled && !element.readOnly
                : element.classList.contains('lblEditable') ||
                    element.classList.contains('lblEditSelect')
        );
        const value = controlValue(element);
        if (!editable && value === '') return;
        fields.push({
            domIndex: domIndex++,
            domId: id,
            domName: clean(element.getAttribute('name')),
            dataField: clean(element.closest('td,th')?.id),
            tag,
            inputType: type,
            classes: clean(element.className),
            label: labelFor(element),
            value,
            editable,
            required: Boolean(element.required) ||
                element.getAttribute('aria-required') === 'true' ||
                element.classList.contains('lblMandatory') ||
                element.classList.contains('clsMandatoryItem'),
            dataType: type === 'checkbox' || type === 'radio'
                ? 'boolean'
                : numeric ? 'number' : tag === 'select' ? 'select' : 'text',
            options: optionNodes.map(option => clean(option.textContent)).filter(Boolean),
            optionValues: optionNodes.map(option => clean(option.value)),
            sectionKey: '',
            sectionName: '',
            itemKey: '',
            articleCode: '',
            articleName: '',
            rowOrder: domIndex,
            visible: true,
            region: 'document',
            rowIndex: -1,
            rowControlIndex: -1,
            cellId: clean(element.closest('td,th')?.id),
            rowSignature: ''
        });
    });
    return {
        title: '',
        sections,
        fields
    };
}"""


def _clean_key(value: Any, fallback: str) -> str:
    cleaned = _KEY_CLEAN_RE.sub("_", str(value or "").strip()).strip("_")
    return cleaned or fallback


def _status_from_tree(frame: Frame) -> str:
    texts: list[str] = []
    for selector in (
        COSTING_TREE_SELECTOR,
        "#titlebarCostSheet .clsPageTitleBarTitle",
    ):
        locator = frame.locator(selector)
        try:
            for index in range(locator.count()):
                item = (
                    locator.nth(index)
                    if hasattr(locator, "nth")
                    else locator
                )
                text = item.inner_text(timeout=1_000).strip()
                if text:
                    texts.append(text)
        except PlaywrightError:
            continue
        text = " ".join(texts)
        no_open = _COSTING_NO_OPEN_RE.search(text)
        if no_open:
            return no_open.group(1).title()
        match = _COSTING_STATUS_RE.search(text)
        if match:
            return match.group(1).title()
    return ""


def _costing_frame(
    context: Any,
    timeout_seconds: float = 20,
    *,
    pages: Sequence[Page] | None = None,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_seconds
    fixed_pages = list(pages) if pages is not None else None
    while time.monotonic() < deadline:
        candidates: list[tuple[int, Page, Frame]] = []
        source_pages = fixed_pages if fixed_pages is not None else list(context.pages)
        for page in reversed(source_pages):
            for frame in page.frames:
                try:
                    grid_score = 0
                    grids = frame.locator(COSTING_GRID_SELECTOR)
                    for index in range(grids.count()):
                        if grids.nth(index).is_visible():
                            grid_score = 100
                            break
                    detail_score = 0
                    details = frame.locator(COSTING_DETAIL_SELECTOR)
                    for index in range(details.count()):
                        if details.nth(index).is_visible():
                            detail_score = 20
                            break
                    tree_score = 10 if frame.locator(COSTING_TREE_SELECTOR).count() else 0
                    new_score = 5 if frame.locator(COSTING_NEW_SELECTOR).count() else 0
                    score = grid_score + detail_score + tree_score + new_score
                    if score:
                        candidates.append((score, page, frame))
                except PlaywrightError:
                    continue
        if candidates:
            _score, page, frame = max(candidates, key=lambda candidate: candidate[0])
            return page, frame
        _sleep(0.2)
    raise PlaywrightTimeoutError("COSTING_CONTEXT_NOT_FOUND")


def _selected_costing_title(
    context: Any,
    *,
    pages: Sequence[Page] | None = None,
) -> str:
    """Đọc title node đang chọn trong Cost Sheet tree, không click."""
    matches: list[str] = []
    source_pages = list(pages) if pages is not None else list(context.pages)
    for page in reversed(source_pages):
        for frame in page.frames:
            try:
                selected = frame.locator(
                    "#treeCostSheet .clsTreeSelectedNode"
                )
                for index in range(selected.count()):
                    text = (selected.nth(index).inner_text() or "").strip()
                    if text:
                        matches.append(text)
            except PlaywrightError:
                continue
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else ""


def _page_activity(page: Page) -> tuple[bool, bool]:
    """Trả ``(visible, focused)`` mà không activate hoặc đổi tab."""
    try:
        state = page.evaluate(
            """() => ({
                visible: document.visibilityState === 'visible',
                focused: document.hasFocus()
            })"""
        )
    except PlaywrightError:
        return False, False
    return bool(state.get("visible")), bool(state.get("focused"))


def _page_has_costing_context(page: Page) -> bool:
    """Nhận diện Costing chỉ trong một Page, không thao tác lên DOM."""
    for frame in page.frames:
        try:
            if (
                frame.locator(COSTING_GRID_SELECTOR).count()
                or frame.locator(COSTING_DETAIL_SELECTOR).count()
                or frame.locator(COSTING_TREE_SELECTOR).count()
            ):
                return True
        except PlaywrightError:
            continue
    return False


def _active_costing_page(context: Any) -> Page:
    """Chọn duy nhất tab Costing đang hiển thị; tuyệt đối không focus tab."""
    candidates: list[tuple[Page, bool]] = []
    for page in list(context.pages):
        visible, focused = _page_activity(page)
        if visible and _page_has_costing_context(page):
            candidates.append((page, focused))
    focused = [page for page, has_focus in candidates if has_focus]
    if len(focused) == 1:
        return focused[0]
    if len(candidates) == 1:
        return candidates[0][0]
    if len(candidates) > 1:
        # document.hasFocus()/visibilityState không đáng tin với popup WFX:
        # Chrome có thể báo mọi popup trong cùng cửa sổ đều visible + focused.
        # Target.getTargets được Chrome trả theo thứ tự tab hoạt động gần nhất,
        # khác với context.pages vốn giữ thứ tự tạo tab và dễ chọn nhầm tab cũ.
        # Chỉ đọc metadata CDP; không activate target hoặc bring_to_front.
        pages = [page for page, _focused in candidates]
        try:
            target_ids: dict[int, str] = {}
            target_order: dict[str, int] = {}
            for page in pages:
                session = context.new_cdp_session(page)
                try:
                    info = session.send("Target.getTargetInfo")
                    target_id = str(
                        info.get("targetInfo", {}).get("targetId") or ""
                    )
                    if target_id:
                        target_ids[id(page)] = target_id
                    if not target_order:
                        targets = session.send("Target.getTargets")
                        target_order = {
                            str(item.get("targetId") or ""): index
                            for index, item in enumerate(
                                targets.get("targetInfos") or ()
                            )
                            if item.get("type") == "page"
                        }
                finally:
                    session.detach()
            ranked = [
                (target_order[target_ids[id(page)]], page)
                for page in pages
                if target_ids.get(id(page)) in target_order
            ]
            if ranked:
                ranked.sort(key=lambda item: item[0])
                if len(ranked) == 1 or ranked[0][0] != ranked[1][0]:
                    return ranked[0][1]
        except (AttributeError, KeyError, PlaywrightError):
            pass
        raise PlaywrightTimeoutError("COSTING_ACTIVE_TAB_AMBIGUOUS")
    raise PlaywrightTimeoutError("COSTING_ACTIVE_TAB_NOT_FOUND")


def _style_codes_from_text(value: Any) -> list[str]:
    return [
        match.group(1).upper()
        for match in _STYLE_CODE_RE.finditer(str(value or ""))
    ]


def _article_code_from_page(page: Page) -> str:
    """Đọc Style Code từ chính tab Article; không quét các tab khác."""
    # Đây là nguồn chính xác nhất. URL của WFX có GUID chứa các đoạn giống
    # Style Code (ví dụ BCA4-D53A...), nên không được ưu tiên URL trước header.
    for frame in getattr(page, "frames", ()) or ():
        try:
            controls = frame.locator("#lblArticleNameValue")
            for index in range(controls.count()):
                control = controls.nth(index)
                text = str(
                    control.get_attribute("title")
                    or control.inner_text(timeout=1_000)
                    or ""
                ).strip()
                match = _ARTICLE_NAME_CODE_RE.search(text)
                codes = _style_codes_from_text(match.group(1) if match else "")
                if len(codes) == 1:
                    return codes[0]
        except (AssertionError, PlaywrightError):
            continue

    trusted: list[str] = []
    try:
        trusted.extend(_style_codes_from_text(page.url))
        trusted.extend(_style_codes_from_text(page.title()))
    except PlaywrightError:
        pass
    for frame in page.frames:
        try:
            trusted.extend(_style_codes_from_text(frame.url))
        except PlaywrightError:
            continue
    unique_trusted = list(dict.fromkeys(trusted))
    if len(unique_trusted) == 1:
        return unique_trusted[0]

    # ArticleLeft là cây điều hướng riêng của đúng popup Article hiện tại. WFX
    # đặt Style Code trong header dạng "(SKN0000188/Tên style)", kể cả khi
    # page.title() và URL chỉ chứa ID nội bộ.
    for frame in page.frames:
        try:
            frame_name = str(getattr(frame, "name", "") or "").casefold()
            frame_url = str(getattr(frame, "url", "") or "").casefold()
            if "articleleft" not in frame_name and "articleleft" not in frame_url:
                continue
            body_text = frame.locator("body").inner_text(timeout=1_500)
        except (AttributeError, PlaywrightError):
            continue
        header_match = _ARTICLE_LEFT_STYLE_RE.search(str(body_text or ""))
        if header_match:
            return header_match.group(1).upper()
        left_codes = list(dict.fromkeys(_style_codes_from_text(body_text)))
        if len(left_codes) == 1:
            return left_codes[0]

    controls: list[str] = []
    selector = ",".join(_STYLE_CODE_CONTROL_SELECTORS)
    for frame in page.frames:
        try:
            values = frame.locator(selector).evaluate_all(
                """elements => elements.map(element => {
                    if (element.closest(
                        '#sectionCostSheetDetail,#sectionArticleList,#gridArticleList'
                    )) return '';
                    return String(
                        element.value || element.title || element.textContent || ''
                    ).trim();
                }).filter(Boolean)"""
            )
        except PlaywrightError:
            continue
        for value in values:
            controls.extend(_style_codes_from_text(value))
    unique_controls = list(dict.fromkeys(controls))
    if len(unique_controls) == 1:
        return unique_controls[0]

    # Fallback cuối: nút Style vừa mở trong Catalog của chính popup này.
    # Không dùng làm nguồn chính vì activeElement ở opener có thể đổi sau đó.
    try:
        opener_value = page.evaluate(
            """() => {
                try {
                    const opener = window.opener;
                    if (!opener || opener.closed) return '';
                    const element = opener.document.activeElement;
                    return String(
                        element?.value || element?.title ||
                        element?.textContent || ''
                    ).trim();
                } catch (_) {
                    return '';
                }
            }"""
        )
    except PlaywrightError:
        opener_value = ""
    opener_codes = list(dict.fromkeys(_style_codes_from_text(opener_value)))
    return opener_codes[0] if len(opener_codes) == 1 else ""


def _style_name_from_page(page: Page) -> str:
    """Lấy tên Style chuẩn sau dấu / trong ``#lblArticleNameValue``."""
    for frame in getattr(page, "frames", ()) or ():
        try:
            controls = frame.locator("#lblArticleNameValue")
            for index in range(controls.count()):
                control = controls.nth(index)
                text = str(
                    control.get_attribute("title")
                    or control.inner_text(timeout=1_000)
                    or ""
                ).strip()
                match = _ARTICLE_NAME_VALUE_RE.search(text)
                if match and match.group(1).strip():
                    return match.group(1).strip()
        except PlaywrightError:
            continue
    return ""


def _inventory_to_document(
    payload: Mapping[str, Any],
    article_code: str,
    *,
    costing_status: str = "",
    season: str = "",
    style_name: str = "",
) -> dict[str, Any]:
    raw_sections = [
        raw for raw in payload.get("sections") or () if isinstance(raw, Mapping)
    ]
    raw_fields = [
        raw for raw in payload.get("fields") or () if isinstance(raw, Mapping)
    ]
    sections: list[dict[str, Any]] = []
    section_names: dict[str, str] = {}
    for index, raw in enumerate(raw_sections):
        key = _clean_key(raw.get("sectionKey"), f"section-{index + 1}")
        if key in section_names:
            continue
        name = str(raw.get("name") or key).strip()
        section_names[key] = name
        sections.append(
            {
                "section_key": key,
                "name": name,
                "row_order": int(raw.get("rowOrder") or index),
            }
        )

    items: list[dict[str, Any]] = []
    item_seen: set[tuple[str, str]] = set()
    fields: list[dict[str, Any]] = []
    field_seen: dict[tuple[str, str, str, str], int] = {}

    for index, raw in enumerate(raw_fields):
        dom_id = str(raw.get("domId") or "").strip()
        if dom_id in FORBIDDEN_CONTROL_IDS:
            continue
        raw_section = str(raw.get("sectionKey") or "").strip()
        section_key = _clean_key(raw_section, "") if raw_section else ""
        if section_key and section_key not in section_names:
            section_name = str(raw.get("sectionName") or section_key).strip()
            section_names[section_key] = section_name
            sections.append(
                {
                    "section_key": section_key,
                    "name": section_name,
                    "row_order": len(sections),
                }
            )
        raw_item = str(raw.get("itemKey") or "").strip()
        item_key = _clean_key(raw_item, "") if raw_item else ""
        article_item = bool(
            item_key
            or str(raw.get("articleCode") or "").strip()
            or str(raw.get("articleName") or "").strip()
        )
        scope = "item" if article_item else "section" if section_key else "cost_sheet"
        if scope == "item":
            if not item_key:
                item_key = _clean_key(
                    raw.get("articleCode") or raw.get("articleName"),
                    f"item-{index + 1}",
                )
            composite_item = (section_key.casefold(), item_key.casefold())
            if composite_item not in item_seen:
                item_seen.add(composite_item)
                items.append(
                    {
                        "section_key": section_key,
                        "section_name": section_names.get(section_key, section_key),
                        "item_key": item_key,
                        "row_order": int(raw.get("rowOrder") or len(items)),
                        "action": "UPSERT",
                        "item_type": str(
                            raw.get("itemType") or "article"
                        ).strip().casefold(),
                        "article_code": str(raw.get("articleCode") or "").strip(),
                        "article_name": str(raw.get("articleName") or "").strip(),
                    }
                )
        base_key = _clean_key(
            raw.get("dataField")
            or raw.get("domName")
            or dom_id
            or raw.get("label"),
            f"field-{index + 1}",
        )
        composite = (
            scope,
            section_key.casefold(),
            item_key.casefold(),
            base_key.casefold(),
        )
        ordinal = field_seen.get(composite, 0) + 1
        field_seen[composite] = ordinal
        field_key = base_key if ordinal == 1 else f"{base_key}__{ordinal}"
        fields.append(
            {
                "scope": scope,
                "section_key": section_key if scope != "cost_sheet" else "",
                "item_key": item_key if scope == "item" else "",
                "field_key": field_key,
                "label": str(raw.get("label") or base_key).strip(),
                "value": raw.get("value", ""),
                "data_type": str(raw.get("dataType") or "text").casefold(),
                "editable": bool(raw.get("editable")),
                "required": bool(raw.get("required")),
                "options": list(raw.get("options") or ()),
                "row_order": int(raw.get("rowOrder") or index),
                # Live-only metadata; normalize_document drops these keys before
                # workbook export, nên selector không thể quay lại từ file.
                "_live": {
                    "dom_index": int(raw.get("domIndex") or index),
                    "dom_id": dom_id,
                    "click_dom_id": str(
                        raw.get("clickDomId") or dom_id
                    ).strip(),
                    "tag": str(raw.get("tag") or "").casefold(),
                    "input_type": str(raw.get("inputType") or "").casefold(),
                    "option_values": list(raw.get("optionValues") or ()),
                    "visible": bool(raw.get("visible")),
                    "region": str(raw.get("region") or ""),
                    "row_index": int(raw.get("rowIndex") or 0),
                    "row_control_index": int(raw.get("rowControlIndex") or 0),
                    "cell_id": str(raw.get("cellId") or ""),
                    "row_signature": str(raw.get("rowSignature") or ""),
                },
            }
        )

    document = {
        "format_version": FORMAT_VERSION,
        "style_code": str(article_code or "").strip(),
        "style_name": str(style_name or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "cost_sheet_status": str(costing_status or "").strip(),
        "cost_sheet_type": "Internal Cost Sheets",
        "order_execution_type": "Trading",
        "season": str(season or "").strip(),
        "template": "FOB",
        "sections": sections,
        "items": items,
        "fields": fields,
    }
    normalized = normalize_document(document)
    live_by_key = {
        (
            field["scope"],
            field["section_key"].casefold(),
            field["item_key"].casefold(),
            field["field_key"].casefold(),
        ): field.get("_live", {})
        for field in fields
    }
    for field in normalized["fields"]:
        field["_live"] = live_by_key.get(
            (
                field["scope"],
                field["section_key"].casefold(),
                field["item_key"].casefold(),
                field["field_key"].casefold(),
            ),
            {},
        )
    normalized["signature"] = live_signature(normalized)
    return normalized


def _inventory_costing_frame(
    frame: Frame,
    article_code: str,
    *,
    costing_status: str = "",
    season: str = "",
    title: str = "",
    style_name: str = "",
    scan_details: bool = False,
) -> dict[str, Any]:
    grid = _visible_costing_grid(frame)
    if grid is None:
        return normalize_document(
            {
                "format_version": FORMAT_VERSION,
                "style_code": article_code,
                "style_name": style_name,
                "title": title,
                "cost_sheet_status": costing_status,
                "cost_sheet_type": "Internal Cost Sheets",
                "order_execution_type": "Trading",
                "season": season,
                "template": "FOB",
                "sections": [],
                "items": [],
                "fields": [],
            }
        )
    payload = grid.evaluate(_COSTING_INVENTORY_JS)
    payload["title"] = title
    if not costing_status and (
        str(payload.get("title") or "").strip()
        or payload.get("sections")
        or payload.get("fields")
    ):
        # Khi grid/tree không cung cấp status nhưng detail thật có dữ liệu,
        # đây là Costing đang mở. Detail rỗng không được tự suy diễn là Open.
        costing_status = "Open"
    document = _inventory_to_document(
        payload,
        article_code,
        costing_status=costing_status,
        season=season,
        style_name=style_name,
    )
    _ensure_dependency_mapping_fields(document)
    if scan_details:
        _scan_costing_item_options(frame, document)
        _scan_costing_dependency_tables(frame, document)
        if _dependency_scan_incomplete(document):
            raise RuntimeError("COSTING_DEPENDENCY_SCAN_INCOMPLETE")
    document["signature"] = live_signature(document)
    return document


def _visible_costing_grid(frame: Frame) -> Any | None:
    grids = frame.locator(COSTING_GRID_SELECTOR)
    visible = []
    for index in range(grids.count()):
        candidate = grids.nth(index)
        try:
            if candidate.is_visible():
                visible.append(candidate)
        except PlaywrightError:
            continue
    return visible[0] if len(visible) == 1 else None


def _section_row_index(grid: Any, section_key: str) -> int:
    rows = grid.locator(":scope > tbody > tr")
    section_number = 0
    matches = []
    for index in range(rows.count()):
        row = rows.nth(index)
        classes = str(row.get_attribute("class") or "")
        if not re.search(
            r"\bcssGridRow(?:BOMCodeMainHeader|CMCostHeader|"
            r"ProdProcessHeader|ICHeader)RowType\b",
            classes,
            re.IGNORECASE,
        ):
            continue
        section_number += 1
        label = row.locator("#lblBOMCodeTranslated")
        if label.count():
            name = label.first.inner_text()
        else:
            name = row.locator("#colArticle").first.inner_text()
        live_key = _clean_key(
            f"section-{section_number}-{str(name or '').strip()}",
            f"section-{section_number}",
        )
        if live_key.casefold() == str(section_key or "").casefold():
            matches.append(index)
    if len(matches) != 1:
        raise RuntimeError(
            f"COSTING_SECTION_NOT_FOUND:{section_key}:{len(matches)}"
        )
    return matches[0]


def _section_action(
    frame: Frame,
    section_key: str,
    control_id: str,
) -> Any:
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_GRID_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    start = _section_row_index(grid, section_key)
    matches = []
    for index in range(start, rows.count()):
        if index > start:
            classes = str(rows.nth(index).get_attribute("class") or "")
            if re.search(
                r"\bcssGridRow(?:BOMCodeMainHeader|CMCostHeader|"
                r"ProdProcessHeader|ICHeader)RowType\b",
                classes,
                re.IGNORECASE,
            ):
                break
        candidates = rows.nth(index).locator(f'[id="{control_id}"]')
        for candidate_index in range(candidates.count()):
            candidate = candidates.nth(candidate_index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    matches.append(candidate)
            except PlaywrightError:
                continue
    if len(matches) != 1:
        raise RuntimeError(
            f"COSTING_SECTION_ACTION_NOT_UNIQUE:{section_key}:"
            f"{control_id}:{len(matches)}"
        )
    return matches[0]


def _material_search_frame(
    context: Any,
    timeout_seconds: float = 10,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        matches = []
        for page in reversed(list(context.pages)):
            for frame in page.frames:
                try:
                    code = frame.locator("#txtSearchArticleCode")
                    name = frame.locator("#txtSearchArticleName")
                    grid = frame.locator("#gridArticleList_tblGridContent")
                    if (
                        code.count() == 1
                        and name.count() == 1
                        and grid.count() == 1
                        and code.is_visible()
                        and name.is_visible()
                        and grid.is_visible()
                    ):
                        matches.append((page, frame))
                except PlaywrightError:
                    continue
        if len(matches) == 1:
            return matches[0]
        _sleep(0.1)
    raise PlaywrightTimeoutError("COSTING_MATERIAL_SEARCH_NOT_FOUND")


def _visible_unique(frame: Frame, selector: str, error_code: str) -> Any:
    matches = _visible_controls(frame, selector)
    if len(matches) != 1:
        raise RuntimeError(f"{error_code}:{len(matches)}")
    return matches[0]


def _close_material_search(frame: Frame) -> None:
    close = _visible_unique(
        frame,
        "#sectionArticleList .clsSectionTitleBarToolClose",
        "COSTING_MATERIAL_CLOSE_NOT_UNIQUE",
    )
    close.click()


def _material_rows(frame: Frame) -> list[dict[str, Any]]:
    grid = frame.locator("#gridArticleList_tblGridContent")
    if grid.count() != 1:
        return []
    return list(
        grid.evaluate(
            """element => [...element.querySelectorAll(':scope > tbody > tr')]
                .map(row => ({
                    row_id: String(
                        row.getAttribute('rowid') || row.id || ''
                    ).trim(),
                    article_code: String(
                        row.querySelector('#lblArticleCode')?.textContent || ''
                    ).trim(),
                    article_name: String(
                        row.querySelector('#lblArticleName')?.textContent || ''
                    ).trim()
                }))"""
        )
        or ()
    )


def _search_material(
    frame: Frame,
    *,
    article_code: str = "",
    article_name: str = "",
) -> list[dict[str, Any]]:
    code = str(article_code or "").strip()
    name = str(article_name or "").strip()
    if not code and not name:
        return []
    code_input = frame.locator("#txtSearchArticleCode")
    name_input = frame.locator("#txtSearchArticleName")
    if code_input.count() != 1 or name_input.count() != 1:
        raise RuntimeError("COSTING_MATERIAL_SEARCH_INPUT_NOT_UNIQUE")
    code_input.fill("")
    name_input.fill("")
    search = code_input if code else name_input
    wanted = code or name
    search.fill(wanted)
    search.press("Enter")

    deadline = time.monotonic() + 8
    previous: list[dict[str, Any]] | None = None
    stable_reads = 0
    latest: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        checkpoint()
        latest = _material_rows(frame)
        searchable = [
            row["article_code"] if code else row["article_name"]
            for row in latest
        ]
        filtered = not latest or all(
            value.casefold() == wanted.casefold() for value in searchable
        )
        if filtered and latest == previous:
            stable_reads += 1
        else:
            stable_reads = 0
        if filtered and stable_reads >= 1:
            break
        previous = latest
        _sleep(0.15)
    return [
        row
        for row in latest
        if (
            row["article_code"].casefold() == code.casefold()
            if code
            else row["article_name"].casefold() == name.casefold()
        )
    ]


def _resolved_search(
    addition: Mapping[str, Any],
    resolutions: Mapping[str, str],
) -> tuple[str, str]:
    item_key = str(addition.get("import_item_key") or "").strip()
    resolution = str(resolutions.get(item_key) or "").strip()
    return (
        resolution or str(addition.get("article_code") or "").strip(),
        "" if resolution else str(addition.get("article_name") or "").strip(),
    )


def _preflight_article_additions(
    context: Any,
    frame: Frame,
    additions: Sequence[Mapping[str, Any]],
    resolutions: Mapping[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for addition in additions:
        grouped.setdefault(str(addition.get("section_key") or ""), []).append(
            addition
        )
    for section_key, section_items in grouped.items():
        _section_action(frame, section_key, "imgAdd").click()
        _page, search_frame = _material_search_frame(context)
        try:
            for addition in section_items:
                code, name = _resolved_search(addition, resolutions)
                matches = _search_material(
                    search_frame,
                    article_code=code,
                    article_name=name,
                )
                if not matches:
                    missing.append(dict(addition))
                    continue
                if len(matches) > 1:
                    ambiguous.append(
                        {
                            **dict(addition),
                            "candidates": matches[:50],
                        }
                    )
                    continue
                found.append(
                    {
                        **dict(addition),
                        "resolved_code": matches[0]["article_code"],
                        "resolved_name": matches[0]["article_name"],
                    }
                )
        finally:
            _close_material_search(search_frame)
    if missing:
        _write_log(
            log,
            f"[COSTING] Bỏ qua {len(missing)} Article không tìm thấy.",
        )
    return {
        "found": found,
        "missing": missing,
        "ambiguous": ambiguous,
    }


def _select_material_match(
    frame: Frame,
    match: Mapping[str, Any],
) -> None:
    rows = frame.locator("#gridArticleList_tblGridContent > tbody > tr")
    candidates = []
    for index in range(rows.count()):
        row = rows.nth(index)
        row_id = str(
            row.get_attribute("rowid") or row.get_attribute("id") or ""
        ).strip()
        if row_id == str(match.get("row_id") or ""):
            candidates.append(row)
    if len(candidates) != 1:
        raise RuntimeError("COSTING_MATERIAL_RESULT_DETACHED")
    checkbox = candidates[0].locator("#chkSelector")
    if checkbox.count() != 1 or not checkbox.is_visible():
        raise RuntimeError("COSTING_MATERIAL_SELECTOR_NOT_UNIQUE")
    checkbox.check()


def _add_articles(
    context: Any,
    frame: Frame,
    preflight: Mapping[str, Any],
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    found = list(preflight.get("found") or ())
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for addition in found:
        grouped.setdefault(str(addition.get("section_key") or ""), []).append(
            addition
        )
    added = []
    for section_key, section_items in grouped.items():
        _section_action(frame, section_key, "imgAdd").click()
        _page, search_frame = _material_search_frame(context)
        for index, addition in enumerate(section_items):
            matches = _search_material(
                search_frame,
                article_code=str(addition.get("resolved_code") or ""),
            )
            if len(matches) != 1:
                _close_material_search(search_frame)
                raise RuntimeError("COSTING_MATERIAL_RESULT_CHANGED")
            _select_material_match(search_frame, matches[0])
            last = index == len(section_items) - 1
            selector = (
                "#sectionArticleList .clsSectionTitleBarToolAddnClose"
                if last
                else "#sectionArticleList .clsSectionTitleBarToolAddnContinue"
            )
            action = _visible_unique(
                search_frame,
                selector,
                "COSTING_MATERIAL_ACTION_NOT_UNIQUE",
            )
            action.click()
            added.append(dict(addition))
            _sleep(0.25)
    if added:
        _write_log(log, f"[COSTING] Đã thêm {len(added)} Article.")
    return added


def _delete_row_index(
    live: Mapping[str, Any],
    deletion: Mapping[str, Any],
) -> int:
    section_key = str(deletion.get("section_key") or "").casefold()
    item_key = str(
        deletion.get("live_item_key")
        or deletion.get("import_item_key")
        or ""
    ).casefold()
    indices = {
        int((field.get("_live") or {}).get("row_index") or 0)
        for field in live.get("fields") or ()
        if str(field.get("scope") or "").casefold() == "item"
        and str(field.get("section_key") or "").casefold() == section_key
        and str(field.get("item_key") or "").casefold() == item_key
    }
    if len(indices) != 1:
        raise RuntimeError("COSTING_DELETE_TARGET_NOT_UNIQUE")
    return indices.pop()


def _delete_articles(
    page: Page,
    frame: Frame,
    live: Mapping[str, Any],
    deletions: Sequence[Mapping[str, Any]],
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    if not deletions:
        return []
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_GRID_NOT_FOUND")
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for deletion in deletions:
        row_index = _delete_row_index(live, deletion)
        grouped.setdefault(
            str(deletion.get("section_key") or ""),
            [],
        ).append((row_index, deletion))
    ordered_groups = sorted(
        grouped.items(),
        key=lambda entry: max(row for row, _item in entry[1]),
        reverse=True,
    )
    deleted: list[dict[str, Any]] = []
    for section_key, targets in ordered_groups:
        rows = grid.locator(":scope > tbody > tr")
        for row_index, deletion in targets:
            if row_index < 0 or row_index >= rows.count():
                raise RuntimeError("COSTING_DELETE_TARGET_DETACHED")
            row = rows.nth(row_index)
            article_text = (
                row.locator("#lblArticle").first.inner_text()
                if row.locator("#lblArticle").count()
                else ""
            )
            code = str(deletion.get("article_code") or "").strip()
            name = str(deletion.get("article_name") or "").strip()
            if code and f"({code})".casefold() not in str(article_text).casefold():
                raise RuntimeError("COSTING_DELETE_TARGET_CHANGED")
            if not code and name and name.casefold() not in str(
                article_text
            ).casefold():
                raise RuntimeError("COSTING_DELETE_TARGET_CHANGED")
            checkbox = row.locator("#chkSelector")
            if checkbox.count() != 1 or not checkbox.is_visible():
                raise RuntimeError("COSTING_DELETE_SELECTOR_NOT_UNIQUE")
            checkbox.check()
            deleted.append(dict(deletion))

        delete = _section_action(frame, section_key, "imgDelete")
        native_dialog_seen = False

        def accept_delete(dialog: Any) -> None:
            nonlocal native_dialog_seen
            native_dialog_seen = True
            dialog.accept()

        page.on("dialog", accept_delete)
        try:
            delete.click()
            _sleep(0.35)
            popups = frame.locator("div#sectionCostSheetDeletionReason")
            visible_popups = [
                popups.nth(index)
                for index in range(popups.count())
                if popups.nth(index).is_visible()
            ]
            if len(visible_popups) != 1:
                raise RuntimeError("COSTING_DELETE_REASON_NOT_FOUND")
            popup = visible_popups[0]
            comments = popup.locator("#txtActionRemarks")
            if comments.count() != 1 or not comments.is_visible():
                raise RuntimeError("COSTING_DELETE_REASON_NOT_FOUND")
            comments.fill("Updated via Costing import")
            ok = popup.locator(".clsSectionTitleBarToolOk")
            visible_ok = [
                ok.nth(index)
                for index in range(ok.count())
                if ok.nth(index).is_visible()
            ]
            if len(visible_ok) != 1:
                raise RuntimeError("COSTING_DELETE_REASON_OK_NOT_FOUND")
            visible_ok[0].click()
            _sleep(0.35)
        finally:
            page.remove_listener("dialog", accept_delete)
        current_rows = grid.locator(":scope > tbody > tr")
        remaining_text = [
            (
                current_rows.nth(index).locator("#lblArticle").first.inner_text()
                if current_rows.nth(index).locator("#lblArticle").count()
                else ""
            )
            for index in range(current_rows.count())
        ]
        for _row_index, deletion in targets:
            code = str(deletion.get("article_code") or "").strip()
            if code and any(
                f"({code})".casefold() in text.casefold()
                for text in remaining_text
            ):
                raise RuntimeError("COSTING_DELETE_NOT_CONFIRMED")
        _write_log(
            log,
            f"[COSTING] Đã xóa {len(targets)} Article trong {section_key}"
            f"{' (đã xác nhận WFX)' if native_dialog_seen else ''}.",
        )
    return deleted


def _article_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("section_key") or "").casefold(),
        str(
            item.get("article_code")
            or item.get("article_name")
            or ""
        ).casefold(),
    )


def _split_article_row(
    frame: Frame,
    live_document: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    """Tạo đúng một continuation row bằng Splitter của Article hiện hữu."""
    wanted = _article_identity(request)
    candidates = [
        item
        for item in live_document.get("items") or ()
        if isinstance(item, Mapping) and _article_identity(item) == wanted
    ]
    if not candidates:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    source = max(
        candidates,
        key=lambda item: int(item.get("row_order") or 0),
    )
    source_item_key = str(source.get("item_key") or "").casefold()
    source_fields = [
        field
        for field in live_document.get("fields") or ()
        if (
            isinstance(field, Mapping)
            and str(field.get("section_key") or "").casefold() == wanted[0]
            and str(field.get("item_key") or "").casefold() == source_item_key
            and str((field.get("_live") or {}).get("region") or "") == "grid"
        )
    ]
    if not source_fields:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    row_index = int(
        (source_fields[0].get("_live") or {}).get("row_index") or 0
    )
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    if row_index < 0 or row_index >= rows.count():
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    row = rows.nth(row_index)
    splitters = row.locator(
        '#colSplitterForUsage [id="imgSplitterForUsage"]'
    )
    visible = [
        splitters.nth(index)
        for index in range(splitters.count())
        if splitters.nth(index).is_visible()
    ]
    if len(visible) != 1:
        raise RuntimeError("COSTING_SPLITTER_NOT_FOUND")
    before = rows.count()
    try:
        visible[0].click(timeout=3_000)
    except PlaywrightError:
        visible[0].evaluate("element => element.click()")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        checkpoint()
        current = _visible_costing_grid(frame)
        if current is not None and current.locator(":scope > tbody > tr").count() > before:
            return
        _sleep(0.1)
    raise RuntimeError("COSTING_SPLIT_NOT_CONFIRMED")


def _visible_controls(frame: Frame, selector: str) -> list[Any]:
    locator = frame.locator(selector)
    controls: list[Any] = []
    for index in range(locator.count()):
        checkpoint()
        candidate = locator.nth(index)
        try:
            if candidate.is_visible() and candidate.is_enabled():
                controls.append(candidate)
        except PlaywrightError:
            continue
    return controls


def _live_field_index(document: Mapping[str, Any]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    return {
        (
            str(field.get("scope") or "").casefold(),
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            str(field.get("field_key") or "").casefold(),
        ): field
        for field in document.get("fields") or ()
        if isinstance(field, Mapping)
    }


def _resolve_live_field(frame: Frame, field: Mapping[str, Any]) -> Any:
    live = field.get("_live") or {}
    dom_id = str(live.get("dom_id") or "")
    if dom_id in FORBIDDEN_CONTROL_IDS:
        raise RuntimeError("COSTING_FORBIDDEN_CONTROL")
    click_dom_id = str(live.get("click_dom_id") or dom_id)
    if click_dom_id.rstrip("~") in FORBIDDEN_CONTROL_IDS:
        raise RuntimeError("COSTING_FORBIDDEN_CONTROL")
    region = str(live.get("region") or "")
    if region == "grid":
        grid = _visible_costing_grid(frame)
        if grid is None:
            raise RuntimeError("COSTING_FIELD_DETACHED")
        rows = grid.locator(":scope > tbody > tr")
        row_index = int(live.get("row_index") or 0)
        if row_index < 0 or row_index >= rows.count():
            raise RuntimeError("COSTING_FIELD_DETACHED")
        row = rows.nth(row_index)
        candidates = row.locator(f'[id="{click_dom_id}"]')
        matches = []
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if (
                    candidate.get_attribute("id") == click_dom_id
                    and candidate.is_visible()
                ):
                    matches.append(candidate)
            except PlaywrightError:
                continue
        if len(matches) != 1:
            raise RuntimeError("COSTING_FIELD_DETACHED")
        return matches[0]
    matches = []
    candidates = frame.locator(f'[id="{click_dom_id}"]')
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            if (
                candidate.get_attribute("id") == click_dom_id
                and candidate.is_visible()
            ):
                matches.append(candidate)
        except PlaywrightError:
            continue
    if len(matches) != 1:
        raise RuntimeError("COSTING_FIELD_DETACHED")
    return matches[0]


def _base_costing_field_key(field: Mapping[str, Any]) -> str:
    return re.sub(
        r"__\d+$",
        "",
        str(field.get("field_key") or ""),
    ).casefold()


def _ensure_dependency_mapping_fields(document: dict[str, Any]) -> None:
    """Thêm field logic cho nội dung bên trong popup Dependency Table."""
    definitions = {
        "colcolordependency": (
            "colColorDependencyMapping",
            "Color Mapping",
            "Color",
        ),
        "colsizedependency": (
            "colSizeDependencyMapping",
            "Size Mapping",
            "Size",
        ),
    }
    fields = document.get("fields") or []
    existing = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            _base_costing_field_key(field),
        )
        for field in fields
    }
    additions = []
    for field in list(fields):
        definition = definitions.get(_base_costing_field_key(field))
        if definition is None or str(field.get("scope") or "") != "item":
            continue
        field_key, label, kind = definition
        identity = (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            field_key.casefold(),
        )
        if identity in existing:
            continue
        live = dict(field.get("_live") or {})
        live["dependency_kind"] = kind
        live["dependency_mode"] = str(field.get("value") or "")
        additions.append(
            {
                "scope": "item",
                "section_key": str(field.get("section_key") or ""),
                "item_key": str(field.get("item_key") or ""),
                "field_key": field_key,
                "label": label,
                "value": "",
                "data_type": "text",
                "editable": True,
                "required": False,
                "options": [],
                "row_order": int(field.get("row_order") or 0),
                "_live": live,
            }
        )
        existing.add(identity)
    fields.extend(additions)


def _scan_multiselect_field_options(
    frame: Frame,
    field: dict[str, Any],
) -> None:
    editor_ids = {
        "colmaterialcolorlist": "ddlMaterialColorList",
        "colmaterialsizelist": "ddlMaterialSizeList",
    }
    editor_id = editor_ids.get(_base_costing_field_key(field))
    if editor_id is None:
        return
    control = _resolve_live_field(frame, field)
    live = field.get("_live") or {}
    grid = _visible_costing_grid(frame)
    if grid is None:
        return
    rows = grid.locator(":scope > tbody > tr")
    row_index = int(live.get("row_index") or 0)
    if row_index < 0 or row_index >= rows.count():
        return
    row = rows.nth(row_index)
    editor = None
    try:
        control.click(timeout=2_000)
        editor = row.locator(f'#{editor_id}:visible')
        editor.wait_for(state="visible", timeout=2_000)
        editor.click(timeout=3_000)
        option_list = frame.locator(f'#{editor_id}ListItems:visible')
        option_list.wait_for(state="visible", timeout=4_000)
        options = option_list.locator("li.clsMultiSelectContent")
        labels: list[str] = []
        values: list[str] = []
        for index in range(options.count()):
            option = options.nth(index)
            anchor = option.locator("a")
            label = str(
                (anchor.get_attribute("title") if anchor.count() else "")
                or option.inner_text()
                or ""
            ).strip()
            checkbox = option.locator("input[type='checkbox']")
            value = str(
                checkbox.get_attribute("value") if checkbox.count() else ""
            ).strip()
            if label:
                labels.append(label)
                values.append(value or label)
        field["options"] = list(dict.fromkeys(labels))
        live["option_values"] = values
    finally:
        try:
            if editor is not None and editor.count() and editor.is_visible():
                editor.click(timeout=1_000)
                editor.press("Tab")
            else:
                frame.locator("body").press("Escape")
        except PlaywrightError:
            pass


def _scan_costing_item_options(
    frame: Frame,
    document: dict[str, Any],
) -> None:
    fields = [
        field
        for field in document.get("fields") or ()
        if _base_costing_field_key(field)
        in {"colmaterialcolorlist", "colmaterialsizelist"}
    ]
    if not fields:
        return
    requests = [
        {
            "row_index": int((field.get("_live") or {}).get("row_index") or 0),
            "kind": (
                "Color"
                if _base_costing_field_key(field) == "colmaterialcolorlist"
                else "Size"
            ),
        }
        for field in fields
    ]
    try:
        results = frame.evaluate(
            """requests => {
                const rows = GetObjGrid('CostSheetDetail')?.[0]?.data || [];
                return requests.map(request => {
                    const row = rows[request.row_index];
                    if (!row) return {...request, options: [], values: []};
                    const data = GetBindDDLData(
                        GUID,
                        request.kind,
                        gFromPage,
                        `ArticleID|${row.ArticleID}~Group|${row.GroupCounter}~`,
                        undefined,
                        undefined,
                        false
                    ) || [];
                    return {
                        ...request,
                        options: data.map(option => (
                            option[request.kind]
                            || `${option[request.kind + 'Name'] || ''} `
                                + `(${option[request.kind + 'Code'] || ''})`
                        ).trim()),
                        values: data.map(option => (
                            option[request.kind + 'Code']
                            || option[request.kind]
                            || ''
                        )),
                    };
                });
            }""",
            requests,
        )
    except (PlaywrightError, RuntimeError, TypeError, ValueError):
        results = []
    result_by_key = {
        (int(result.get("row_index") or 0), str(result.get("kind") or "")): result
        for result in results or ()
    }
    for field in fields:
        live = field.get("_live") or {}
        row_index = int(live.get("row_index") or 0)
        kind = (
            "Color"
            if _base_costing_field_key(field) == "colmaterialcolorlist"
            else "Size"
        )
        result = result_by_key.get((row_index, kind)) or {}
        options = [
            str(value).strip()
            for value in result.get("options") or ()
            if str(value).strip()
        ]
        values = [str(value).strip() for value in result.get("values") or ()]
        if options:
            field["options"] = list(dict.fromkeys(options))
            live["option_values"] = values


def _scan_dependency_table(
    frame: Frame,
    mapping_field: dict[str, Any],
    known_options: Sequence[str] = (),
) -> tuple[str, list[str]]:
    live = mapping_field.get("_live") or {}
    kind = str(live.get("dependency_kind") or "")
    if kind not in {"Color", "Size"}:
        return "", []
    grid = _visible_costing_grid(frame)
    if grid is None:
        return "", []
    rows = grid.locator(":scope > tbody > tr")
    row_index = int(live.get("row_index") or 0)
    if row_index < 0 or row_index >= rows.count():
        return "", []
    link = rows.nth(row_index).locator(f'[id="lnk{kind}Dependency"]:visible')
    if link.count() != 1:
        return "", []
    popup = frame.locator(f'div#section{kind}DepUsage.Targetblock:visible')
    try:
        link.click(timeout=3_000)
        popup.wait_for(state="visible", timeout=3_000)
        mapping_rows = popup.locator(
            f"#grid{kind}DepUsage_tblGridContent > tbody > tr"
        )
        lines: list[str] = []
        all_options: list[str] = list(known_options)
        editor_id = f"ddlStyle{kind}ListSDU"
        for index in range(mapping_rows.count()):
            mapping_row = mapping_rows.nth(index)
            source_cell = mapping_row.locator("#colMaterialArticleSDU")
            source_node = source_cell.locator("[title]")
            source = str(
                (source_node.first.get_attribute("title") if source_node.count() else "")
                or source_cell.inner_text()
                or ""
            ).strip()
            target_cell = mapping_row.locator("#colStyleSDU")
            editable = target_cell.locator(".lblEditable")
            if not source or editable.count() != 1:
                continue
            selected_text = str(
                editable.get_attribute("title")
                or editable.inner_text()
                or ""
            ).strip()
            selected = _split_dependency_display_values(selected_text)
            if not all_options:
                editable.click(timeout=2_000)
                editor = target_cell.locator(f'#{editor_id}:visible')
                editor.wait_for(state="visible", timeout=2_000)
                editor.click(timeout=2_000)
                option_list = frame.locator(f'#{editor_id}ListItems:visible')
                option_list.wait_for(state="visible", timeout=2_000)
                options = option_list.locator("li.clsMultiSelectContent")
                for option_index in range(options.count()):
                    option = options.nth(option_index)
                    anchor = option.locator("a")
                    label = str(
                        (
                            anchor.get_attribute("title")
                            if anchor.count()
                            else ""
                        )
                        or option.inner_text()
                        or ""
                    ).strip()
                    if label:
                        all_options.append(label)
                editor.press("Tab")
                try:
                    option_list.wait_for(state="hidden", timeout=1_000)
                except PlaywrightError:
                    frame.locator("body").press("Escape")
            lines.append(f"{source} => {' | '.join(selected)}")
        return "\n".join(lines), list(dict.fromkeys(all_options))
    finally:
        try:
            frame.locator("body").press("Escape")
            cancel = popup.locator(".clsSectionTitleBarToolCancel")
            if cancel.count() and cancel.is_visible():
                try:
                    cancel.click(timeout=1_000)
                except PlaywrightError:
                    cancel.evaluate("element => element.click()")
                popup.wait_for(state="hidden", timeout=2_000)
        except PlaywrightError:
            pass


def _scan_dependency_tables_from_page_data(
    frame: Frame,
    mapping_fields: Sequence[dict[str, Any]],
) -> tuple[dict[tuple[int, str], str], dict[str, list[str]]]:
    """Read dependency grids from WFX's already-loaded page data.

    ``bindDependencyUsageData`` is the same function used by the Color/Size
    dependency popup.  Calling it without displaying the popup builds the
    hidden grid immediately, avoiding one modal round-trip for every item.
    """
    requests = [
        {
            "row_index": int((field.get("_live") or {}).get("row_index") or 0),
            "kind": str((field.get("_live") or {}).get("dependency_kind") or ""),
        }
        for field in mapping_fields
    ]
    payload = frame.evaluate(
        """requests => {
            const output = {results: [], options: {Color: [], Size: []}};
            const styleKey = (
                typeof gArticleID === 'undefined'
                    ? ''
                    : `WFXCostSheet|ArticleID|${gArticleID}~`
            );
            for (const kind of ['Color', 'Size']) {
                const cache = (
                    typeof gobjDDLHashData === 'undefined'
                        ? null
                        : gobjDDLHashData?.[kind]?.[styleKey]
                ) || [];
                output.options[kind] = cache.map(row => (
                    row[kind]
                    || `${row[kind + 'Name'] || ''} (${row[kind + 'Code'] || ''})`
                ).trim()).filter(Boolean);
            }
            for (const request of requests) {
                try {
                    costSheetData.rowIndexForClickedRow = request.row_index;
                    bindDependencyUsageData(request.kind);
                    const grid = GetObjGrid(request.kind + 'DepUsage');
                    const rows = grid?.[0]?.data || [];
                    output.results.push({
                        row_index: request.row_index,
                        kind: request.kind,
                        rows: rows.map(row => ({
                            source: row['Material' + request.kind] || '',
                            target: row[request.kind + 'Name'] || '',
                        })),
                    });
                    if (typeof HideDiv === 'function') {
                        HideDiv('section' + request.kind + 'DepUsage', 1);
                    }
                } catch (error) {
                    output.results.push({
                        row_index: request.row_index,
                        kind: request.kind,
                        error: String(error),
                        rows: [],
                    });
                }
            }
            return output;
        }""",
        requests,
    )
    values: dict[tuple[int, str], str] = {}
    for result in payload.get("results") or ():
        row_index = int(result.get("row_index") or 0)
        kind = str(result.get("kind") or "")
        lines: list[str] = []
        for row in result.get("rows") or ():
            source = str(row.get("source") or "").strip()
            targets = _split_dependency_display_values(
                str(row.get("target") or "").strip()
            )
            if source:
                lines.append(f"{source} => {' | '.join(targets)}")
        if lines:
            values[(row_index, kind)] = "\n".join(lines)
    raw_options = payload.get("options") or {}
    options = {
        kind: list(
            dict.fromkeys(
                str(value).strip()
                for value in raw_options.get(kind) or ()
                if str(value).strip()
            )
        )
        for kind in ("Color", "Size")
    }
    return values, options


def _scan_costing_dependency_tables(
    frame: Frame,
    document: dict[str, Any],
) -> None:
    outer_modes = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            "Color" if _base_costing_field_key(field) == "colcolordependency" else "Size",
        ): str(field.get("value") or "")
        for field in document.get("fields") or ()
        if _base_costing_field_key(field) in {
            "colcolordependency",
            "colsizedependency",
        }
    }
    option_cache: dict[str, list[str]] = {"Color": [], "Size": []}
    mapping_fields = [
        field
        for field in document.get("fields") or ()
        if _base_costing_field_key(field)
        in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }
    ]
    table_fields: list[dict[str, Any]] = []
    for field in mapping_fields:
        base = _base_costing_field_key(field)
        if base not in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }:
            continue
        kind = "Color" if "color" in base else "Size"
        mode = outer_modes.get(
            (
                str(field.get("section_key") or "").casefold(),
                str(field.get("item_key") or "").casefold(),
                kind,
            ),
            "",
        )
        if mode.casefold() != "[table]":
            continue
        table_fields.append(field)

    direct_values: dict[tuple[int, str], str] = {}
    if table_fields:
        try:
            direct_values, option_cache = _scan_dependency_tables_from_page_data(
                frame,
                table_fields,
            )
        except (PlaywrightError, RuntimeError, TypeError, ValueError):
            direct_values = {}

    for field in table_fields:
        live = field.get("_live") or {}
        kind = str(live.get("dependency_kind") or "")
        row_index = int(live.get("row_index") or 0)
        direct_value = direct_values.get((row_index, kind), "")
        if direct_value:
            field["value"] = direct_value
            field["options"] = list(option_cache[kind])
            continue
        for attempt in range(1):
            try:
                value, options = _scan_dependency_table(
                    frame,
                    field,
                    option_cache[kind],
                )
                field["value"] = value
                field["options"] = options
                option_cache[kind] = options
                break
            except (PlaywrightError, RuntimeError):
                try:
                    frame.locator("body").press("Escape")
                except PlaywrightError:
                    pass
                if attempt == 0:
                    _sleep(0.2)
    for field in mapping_fields:
        kind = "Color" if "color" in _base_costing_field_key(field) else "Size"
        if not field.get("options"):
            field["options"] = list(option_cache[kind])


def _dependency_scan_incomplete(document: Mapping[str, Any]) -> bool:
    fields = list(document.get("fields") or ())
    values = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            _base_costing_field_key(field),
        ): str(field.get("value") or "").strip()
        for field in fields
    }
    for field in fields:
        base = _base_costing_field_key(field)
        if base not in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }:
            continue
        prefix = "color" if "color" in base else "size"
        identity = (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
        )
        mode = values.get((*identity, f"col{prefix}dependency"), "")
        material = values.get((*identity, f"colmaterial{prefix}list"), "")
        mapping = str(field.get("value") or "").strip()
        if mode.casefold() == "[table]" and material and not mapping:
            return True
    return False


def _option_value(field: Mapping[str, Any], value: Any) -> str:
    labels = [str(item) for item in field.get("options") or ()]
    values = [
        str(item)
        for item in (field.get("_live") or {}).get("option_values") or ()
    ]
    wanted = str(value or "").strip().casefold()
    matches = [
        values[index] if index < len(values) else labels[index]
        for index, label in enumerate(labels)
        if label.strip().casefold() == wanted
        or (index < len(values) and values[index].strip().casefold() == wanted)
    ]
    if len(matches) != 1:
        raise RuntimeError("COSTING_FIELD_OPTION_NOT_FOUND")
    return matches[0]


def _apply_inline_select_option(editor: Any, option_value: str) -> None:
    """Chọn option cho select thường hoặc backing select ẩn của Select2."""
    classes = str(editor.get_attribute("class") or "")
    if "select2-hidden-accessible" in classes.split():
        changed = editor.evaluate(
            """(element, value) => {
                element.value = String(value);
                if (element.value !== String(value)) return false;
                element.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }""",
            option_value,
        )
        if not changed:
            raise RuntimeError("COSTING_INLINE_OPTION_NOT_APPLIED")
        return
    editor.select_option(value=option_value)


def _edit_wfx_label(
    frame: Frame,
    control: Any,
    field: Mapping[str, Any],
    value: Any,
) -> None:
    try:
        control.click(timeout=2_000)
    except PlaywrightError:
        # WFX's frozen left columns can visually cover a valid cell after a
        # horizontal scroll.  Dispatch only on the already verified target;
        # _resolve_live_field has blocked every forbidden control beforehand.
        control.evaluate("element => element.click()")
    live = field.get("_live") or {}
    dom_id = str(live.get("dom_id") or "")
    suffix = re.sub(r"^(?:lbl|txt|cbo|ddl)", "", dom_id).rstrip("~").casefold()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        root: Any = frame
        if str(live.get("region") or "") == "grid":
            grid = _visible_costing_grid(frame)
            if grid is None:
                raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")
            rows = grid.locator(":scope > tbody > tr")
            row_index = int(live.get("row_index") or 0)
            if row_index < 0 or row_index >= rows.count():
                raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")
            root = rows.nth(row_index)
        editors = [
            editor
            for editor in _visible_controls(root, "input,select,textarea")
            if str(editor.get_attribute("type") or "").casefold()
            not in {"hidden", "checkbox", "radio", "file", "button", "submit"}
        ]
        preferred = [
            editor
            for editor in editors
            if suffix
            and suffix
            in " ".join(
                (
                    str(editor.get_attribute("id") or ""),
                    str(editor.get_attribute("name") or ""),
                )
            ).casefold()
        ]
        if len(preferred) == 1:
            editors = preferred
        if len(editors) == 1:
            editor = editors[0]
            tag = editor.evaluate("element => element.tagName.toLowerCase()")
            if tag == "select":
                options = editor.locator("option")
                matched = []
                wanted = str(value or "").strip().casefold()
                for index in range(options.count()):
                    option = options.nth(index)
                    label = (option.inner_text() or "").strip()
                    option_value = (option.get_attribute("value") or "").strip()
                    if wanted in {label.casefold(), option_value.casefold()}:
                        matched.append(option_value)
                if len(matched) != 1:
                    raise RuntimeError("COSTING_INLINE_OPTION_NOT_FOUND")
                # WFX dùng select 1×1 làm backing control cho Select2.
                # select_option có thể chờ actionability tới default timeout
                # dù option đã tồn tại.
                _apply_inline_select_option(editor, matched[0])
                editor.press("Tab")
            else:
                editor.fill(str(value if value is not None else ""))
                editor.press("Tab")
            return
        _sleep(0.1)
    raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")


def _dependency_kind(
    field: Mapping[str, Any],
    value: Any,
) -> str:
    field_key = re.sub(
        r"__\d+$",
        "",
        str(field.get("field_key") or ""),
    ).casefold()
    text = str(value or "").strip()
    if not text or text.startswith("["):
        return ""
    if field_key in {
        "colcolordependency",
        "colcolordependencymapping",
    }:
        return "Color"
    if field_key in {
        "colsizedependency",
        "colsizedependencymapping",
    }:
        return "Size"
    return ""


def _dependency_values(value: Any) -> list[str]:
    return list(
        dict.fromkeys(
            token.strip()
            for token in re.split(r"[|;\n]+", str(value or ""))
            if token.strip()
        )
    )


def _split_dependency_display_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    output: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character in {",", "|"} and depth == 0:
            token = text[start:index].strip()
            if token:
                output.append(token)
            start = index + 1
    token = text[start:].strip()
    if token:
        output.append(token)
    return output


def _dependency_match_tokens(value: Any) -> set[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    if not text:
        return set()
    tokens = {text, re.sub(r"[^a-z0-9]+", "", text)}
    code = re.search(r"\(([^()]*)\)\s*$", text)
    if code and code.group(1).strip():
        raw_code = code.group(1).strip()
        tokens.update({raw_code, re.sub(r"[^a-z0-9]+", "", raw_code)})
    return {token for token in tokens if token}


def _dependency_mapping_rules(
    value: Any,
) -> list[tuple[str | None, list[str]]]:
    text = str(value or "").strip()
    lines = [
        line.strip()
        for line in re.split(r"[;\n]+", text)
        if line.strip()
    ]
    rules: list[tuple[str | None, list[str]]] = []
    for line in lines:
        match = re.match(r"^(.*?)\s*(?:=>|->|→)\s*(.*)$", line)
        if not match:
            continue
        source = match.group(1).strip()
        targets = _dependency_values(match.group(2))
        if source:
            rules.append((source, targets))
    if rules:
        return rules
    # Tương thích workbook trước đây: một danh sách đích áp cho mọi dòng nguồn.
    targets = _dependency_values(text)
    return [(None, targets)] if targets else []


def _ensure_table_dependency_mode(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> str:
    dependency_kind = _dependency_kind(live_field, value)
    if not dependency_kind:
        raise RuntimeError("COSTING_DEPENDENCY_VALUE_INVALID")
    live_metadata = live_field.get("_live") or {}
    current_mode = str(
        live_metadata.get("dependency_mode") or live_field.get("value") or ""
    ).strip()
    if current_mode.casefold() == "[table]":
        return dependency_kind
    control = _resolve_live_field(frame, live_field)
    _edit_wfx_label(frame, control, live_field, "[Table]")
    _sleep(0.2)
    return dependency_kind


def _open_dependency_popup(
    frame: Frame,
    live_field: Mapping[str, Any],
    dependency_kind: str,
) -> Any:
    row_index = int((live_field.get("_live") or {}).get("row_index") or 0)
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_DEPENDENCY_ROW_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    if row_index < 0 or row_index >= rows.count():
        raise RuntimeError("COSTING_DEPENDENCY_ROW_NOT_FOUND")
    links = rows.nth(row_index).locator(
        f'[id="lnk{dependency_kind}Dependency"]:visible'
    )
    if links.count() != 1:
        raise RuntimeError("COSTING_DEPENDENCY_LINK_NOT_FOUND")
    try:
        links.first.click(timeout=3_000)
    except PlaywrightError:
        links.first.evaluate("element => element.click()")
    popup = frame.locator(
        f"div#section{dependency_kind}DepUsage.Targetblock:visible"
    )
    popup.wait_for(state="visible", timeout=3_000)
    return popup


def _dependency_source_label(mapping_row: Any) -> str:
    source_cell = mapping_row.locator("#colMaterialArticleSDU")
    source_node = source_cell.locator("[title]")
    return str(
        (
            source_node.first.get_attribute("title")
            if source_node.count()
            else ""
        )
        or source_cell.inner_text()
        or ""
    ).strip()


def _matching_dependency_rule(
    source_label: str,
    rules: Sequence[tuple[str | None, list[str]]],
) -> tuple[int, list[str]] | None:
    source_tokens = _dependency_match_tokens(source_label)
    matches = [
        (rule_index, targets)
        for rule_index, (source, targets) in enumerate(rules)
        if source is None or source_tokens & _dependency_match_tokens(source)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError("COSTING_DEPENDENCY_SOURCE_AMBIGUOUS")
    return matches[0]


_DEPENDENCY_OPTIONS_JS = """nodes => nodes.map((node, index) => {
    const anchor = node.querySelector('a');
    const checkbox = node.querySelector('input[type="checkbox"]');
    return {
        index,
        label: String(anchor?.getAttribute('title') || node.textContent || '').trim(),
        code: String(checkbox?.value || '').trim(),
        checked: Boolean(checkbox?.checked)
    };
})"""


def _dependency_option_indexes(
    option_snapshot: Sequence[Mapping[str, Any]],
    wanted_values: Sequence[str],
) -> set[int]:
    matched_indexes: dict[str, int] = {}
    for option in option_snapshot:
        label = str(option.get("label") or "").casefold()
        code = str(option.get("code") or "").casefold()
        for wanted_value in wanted_values:
            normalized_value = wanted_value.casefold()
            if normalized_value not in {label, code}:
                continue
            if normalized_value in matched_indexes:
                raise RuntimeError("COSTING_DEPENDENCY_OPTION_AMBIGUOUS")
            matched_indexes[normalized_value] = int(option["index"])
    missing_values = [
        value for value in wanted_values if value.casefold() not in matched_indexes
    ]
    if missing_values:
        raise RuntimeError(
            "COSTING_DEPENDENCY_OPTION_NOT_FOUND:"
            + ",".join(missing_values[:3])
        )
    return {matched_indexes[value.casefold()] for value in wanted_values}


def _set_dependency_row_options(
    frame: Frame,
    mapping_row: Any,
    dependency_kind: str,
    wanted_values: Sequence[str],
) -> None:
    target_cell = mapping_row.locator("#colStyleSDU")
    editable = target_cell.locator(".lblEditable")
    if editable.count() != 1:
        raise RuntimeError("COSTING_DEPENDENCY_TARGET_NOT_FOUND")
    editable.click(timeout=2_000)
    editor_id = f"ddlStyle{dependency_kind}ListSDU"
    editor = target_cell.locator(f"#{editor_id}:visible")
    editor.wait_for(state="visible", timeout=2_000)
    editor.click(timeout=2_000)
    option_list = frame.locator(f"#{editor_id}ListItems:visible")
    option_list.wait_for(state="visible", timeout=2_000)
    options = option_list.locator("li.clsMultiSelectContent")
    option_snapshot = options.evaluate_all(_DEPENDENCY_OPTIONS_JS)
    wanted_indexes = _dependency_option_indexes(
        option_snapshot,
        wanted_values,
    )
    for option in option_snapshot:
        option_index = int(option["index"])
        should_check = option_index in wanted_indexes
        if bool(option.get("checked")) == should_check:
            continue
        options.nth(option_index).locator("input[type='checkbox']").click(
            timeout=2_000
        )
    confirmed_snapshot = options.evaluate_all(_DEPENDENCY_OPTIONS_JS)
    confirmed_indexes = {
        int(option["index"])
        for option in confirmed_snapshot
        if option.get("checked")
    }
    if confirmed_indexes != wanted_indexes:
        raise RuntimeError("COSTING_DEPENDENCY_NOT_CONFIRMED")
    editor.press("Tab")


def _apply_dependency_rules(
    frame: Frame,
    popup: Any,
    dependency_kind: str,
    rules: Sequence[tuple[str | None, list[str]]],
) -> None:
    mapping_rows = popup.locator(
        f"#grid{dependency_kind}DepUsage_tblGridContent > tbody > tr"
    )
    if mapping_rows.count() < 1:
        raise RuntimeError("COSTING_DEPENDENCY_TABLE_EMPTY")
    matched_rule_indexes: set[int] = set()
    for row_index in range(mapping_rows.count()):
        mapping_row = mapping_rows.nth(row_index)
        matching_rule = _matching_dependency_rule(
            _dependency_source_label(mapping_row),
            rules,
        )
        if matching_rule is None:
            continue
        rule_index, wanted_values = matching_rule
        matched_rule_indexes.add(rule_index)
        _set_dependency_row_options(
            frame,
            mapping_row,
            dependency_kind,
            wanted_values,
        )
    missing_sources = [
        source
        for rule_index, (source, _targets) in enumerate(rules)
        if source is not None and rule_index not in matched_rule_indexes
    ]
    if missing_sources:
        raise RuntimeError(
            "COSTING_DEPENDENCY_SOURCE_NOT_FOUND:"
            + ",".join(missing_sources[:3])
        )


def _cancel_dependency_popup(popup: Any) -> None:
    try:
        cancel = popup.locator(".clsSectionTitleBarToolCancel")
        if cancel.count() and cancel.is_visible():
            cancel.click(timeout=1_000)
    except PlaywrightError:
        pass


def _set_dependency_mapping(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> None:
    """Chọn mapping thật trong popup Table thay vì chỉ ghi chữ ``[Table]``."""
    rules = _dependency_mapping_rules(value)
    if not rules:
        raise RuntimeError("COSTING_DEPENDENCY_VALUE_INVALID")
    dependency_kind = _ensure_table_dependency_mode(frame, live_field, value)
    popup = _open_dependency_popup(frame, live_field, dependency_kind)
    try:
        _apply_dependency_rules(frame, popup, dependency_kind, rules)
        popup.locator(".clsSectionTitleBarToolOk").click(timeout=3_000)
        popup.wait_for(state="hidden", timeout=3_000)
    except Exception:
        _cancel_dependency_popup(popup)
        raise


def _set_live_field(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> None:
    control = _resolve_live_field(frame, live_field)
    live = live_field.get("_live") or {}
    tag = str(live.get("tag") or "").casefold()
    input_type = str(live.get("input_type") or "").casefold()
    if tag == "select":
        control.select_option(value=_option_value(live_field, value))
    elif tag == "input" and input_type in {"checkbox", "radio"}:
        checked = str(value or "").strip().casefold() in {
            "1",
            "true",
            "yes",
            "y",
            "x",
            "có",
        }
        control.set_checked(checked)
    elif tag in {"input", "textarea"}:
        control.fill(str(value if value is not None else ""))
        control.press("Tab")
    else:
        _edit_wfx_label(frame, control, live_field, value)


def _field_value_matches(actual: Any, expected: Any, data_type: str) -> bool:
    if str(data_type or "").casefold() in {
        "number",
        "numeric",
        "decimal",
        "integer",
    }:
        try:
            return float(str(actual).strip() or 0) == float(
                str(expected).strip() or 0
            )
        except ValueError:
            pass
    return str(actual if actual is not None else "").strip() == str(
        expected if expected is not None else ""
    ).strip()


def _field_application_priority(field: Mapping[str, Any]) -> int:
    """Apply dependent Article fields in WFX's safe order."""
    semantic = " ".join(
        str(field.get(key) or "")
        for key in ("field_key", "label")
    ).casefold()
    if re.search(
        r"material.?size|material.?color|color.?dependency|size.?dependency",
        semantic,
    ):
        return 10
    if "supplier" in semantic:
        return 20
    if re.search(r"delivery.?term|currency", semantic):
        return 30
    if re.search(r"(?:^|[^a-z])rate(?:[^a-z]|$)|price", semantic):
        return 50
    return 40


def _save_costing(
    page: Page,
    frame: Frame,
    log: Callable[[str], None],
) -> None:
    save = frame.locator(
        'xpath=//*[@id="titlebarCostSheet"]/tbody/tr/td[3]/span/div[1]'
    )
    if save.count() != 1:
        raise RuntimeError("COSTING_SAVE_NOT_FOUND")
    _write_log(log, "[COSTING] Đang Save Cost Sheet...")
    dialog_messages: list[str] = []
    frame.evaluate(
        """() => {
            window.__codexCostingSaveMessages = [];
            window.__codexCostingOldDialog = window.showDialogMessage;
            window.__codexCostingOldSuccess = window.showSuccessMessage;
            if (typeof window.showDialogMessage === 'function') {
                window.showDialogMessage = function(type, title, message) {
                    window.__codexCostingSaveMessages.push({
                        kind: 'dialog',
                        title: String(title || ''),
                        message: String(message || '')
                    });
                    // Validation already returns false after showing this
                    // dialog.  Suppress WFX's blocking overlay while the
                    // automation returns the exact failure to the panel.
                    return false;
                };
            }
            if (typeof window.showSuccessMessage === 'function') {
                window.showSuccessMessage = function() {
                    window.__codexCostingSaveMessages.push({
                        kind: 'success',
                        title: '',
                        message: Array.from(arguments).join(' | ')
                    });
                    return window.__codexCostingOldSuccess.apply(this, arguments);
                };
            }
        }"""
    )

    def accept_save_dialog(dialog: Any) -> None:
        dialog_messages.append(str(dialog.message or "").strip())
        dialog.accept()

    page.on("dialog", accept_save_dialog)
    with cancellation_deferred():
        try:
            try:
                save.click(timeout=5_000)
            except PlaywrightError:
                save.evaluate("element => element.click()")
            _wait(page, 1_000)
        finally:
            page.remove_listener("dialog", accept_save_dialog)
    custom_messages = frame.evaluate(
        """() => {
            const messages = window.__codexCostingSaveMessages || [];
            if (window.__codexCostingOldDialog) {
                window.showDialogMessage = window.__codexCostingOldDialog;
            }
            if (window.__codexCostingOldSuccess) {
                window.showSuccessMessage = window.__codexCostingOldSuccess;
            }
            delete window.__codexCostingSaveMessages;
            delete window.__codexCostingOldDialog;
            delete window.__codexCostingOldSuccess;
            return messages;
        }"""
    )
    custom_failures = [
        " | ".join(
            token
            for token in (
                str(message.get("title") or "").strip(),
                str(message.get("message") or "").strip(),
            )
            if token
        )
        for message in custom_messages
        if (
            isinstance(message, Mapping)
            and message.get("kind") == "dialog"
            and not re.search(
                r"\bsav(?:e|ed)\b.*\bsuccess",
                " ".join(
                    (
                        str(message.get("title") or ""),
                        str(message.get("message") or ""),
                    )
                ),
                re.IGNORECASE,
            )
        )
    ]
    if custom_failures:
        raise RuntimeError(f"COSTING_SAVE_ALERT:{custom_failures[0][:160]}")
    failure_tokens = re.compile(
        r"\b(error|failed|invalid|required|missing|cannot|can't|not saved)\b",
        re.IGNORECASE,
    )
    failures = [
        message for message in dialog_messages if failure_tokens.search(message)
    ]
    if failures:
        raise RuntimeError(f"COSTING_SAVE_ALERT:{failures[0][:160]}")
    _write_log(
        log,
        "[COSTING] Đã Save; đang xác nhận trên màn hình hiện tại (không reload).",
    )


class CostingApplyAbort(RuntimeError):
    """Stop an apply workflow while preserving its structured panel result."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__(str(result.get("code") or "COSTING_APPLY_FAILED"))
        self.result = result


@dataclass
class _CostingApplySession:
    article_code: str
    browser: Any
    context: Any
    costing_page: Page
    frame: Frame
    scoped_pages: Sequence[Page] | None
    live: dict[str, Any]
    working_plan: dict[str, Any]
    source_document: Mapping[str, Any] | None
    log: Callable[[str], None]


@dataclass
class _CostingApplyProgress:
    preflight: dict[str, Any] = dataclass_field(default_factory=dict)
    added: list[dict[str, Any]] = dataclass_field(default_factory=list)
    deleted: list[dict[str, Any]] = dataclass_field(default_factory=list)
    split: list[dict[str, Any]] = dataclass_field(default_factory=list)
    applied: list[dict[str, Any]] = dataclass_field(default_factory=list)
    skipped: list[dict[str, Any]] = dataclass_field(default_factory=list)
    dependency_confirmed: set[tuple[str, str, str, str]] = dataclass_field(
        default_factory=set
    )


def _validate_costing_apply_request(
    article_code: str,
    plan: Mapping[str, Any],
    source_document: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if plan.get("new_required"):
        return _result(
            False,
            "COSTING_NOT_OPEN",
            "CostSheet phải ở trạng thái Open trước khi import.",
            article_code=article_code,
        )
    article_mutations = (
        plan.get("additions") or plan.get("splits") or plan.get("deletes")
    )
    if not article_mutations or source_document is not None:
        return None
    return _result(
        False,
        "COSTING_SOURCE_REQUIRED",
        "Plan thêm/split/xóa Article thiếu dữ liệu nguồn server-side.",
        additions=list(plan.get("additions") or ()),
        splits=list(plan.get("splits") or ()),
        deletes=list(plan.get("deletes") or ()),
    )


def _costing_plan_has_changes(plan: Mapping[str, Any]) -> bool:
    return any(
        plan.get(key)
        for key in ("additions", "splits", "deletes", "fields_to_set")
    )


def _costing_apply_scope(
    context: Any,
    article_code: str,
    active_tab_only: bool,
) -> Sequence[Page] | None:
    if not active_tab_only:
        return None
    active_page = _active_costing_page(context)
    detected_code = _article_code_from_page(active_page)
    if not detected_code:
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                "Không đọc được Style Code từ tab Costing đang chọn.",
            )
        )
    if detected_code.casefold() == article_code.casefold():
        return [active_page]
    raise CostingApplyAbort(
        _result(
            False,
            "COSTING_STYLE_MISMATCH",
            (
                "Tab Costing đang chọn không còn khớp file dry-run. "
                "Hãy quay lại đúng style rồi thử lại."
            ),
            file_style=article_code,
            live_style=detected_code,
        )
    )


def _open_costing_apply_session(
    browser: Any,
    article_code: str,
    plan: Mapping[str, Any],
    source_document: Mapping[str, Any] | None,
    active_tab_only: bool,
    log: Callable[[str], None],
) -> _CostingApplySession:
    context = browser.contexts[0]
    scoped_pages = _costing_apply_scope(
        context,
        article_code,
        active_tab_only,
    )
    costing_page, frame = _costing_frame(context, pages=scoped_pages)
    live = _inventory_costing_frame(
        frame,
        article_code,
        costing_status=str(plan.get("costing_status") or ""),
        title=_selected_costing_title(context, pages=scoped_pages),
    )
    if str(live.get("cost_sheet_status") or "").casefold() != "open":
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_NOT_OPEN",
                "CostSheet không còn ở trạng thái Open. Hãy mở/tạo Costing trước.",
                article_code=article_code,
            )
        )
    if str(plan.get("live_signature") or "") != live_signature(live):
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_PLAN_STALE",
                "Costing đã thay đổi sau dry-run. Hãy import và kiểm tra lại.",
            )
        )
    return _CostingApplySession(
        article_code=article_code,
        browser=browser,
        context=context,
        costing_page=costing_page,
        frame=frame,
        scoped_pages=scoped_pages,
        live=live,
        working_plan=dict(plan),
        source_document=source_document,
        log=log,
    )


def _refresh_apply_inventory(
    session: _CostingApplySession,
    *,
    wait_ms: int = 0,
    rebuild_plan: bool = True,
) -> None:
    if wait_ms:
        _wait(session.costing_page, wait_ms)
    session.live = _inventory_costing_frame(
        session.frame,
        session.article_code,
        costing_status="Open",
        title=_selected_costing_title(
            session.context,
            pages=session.scoped_pages,
        ),
    )
    if rebuild_plan and session.source_document is not None:
        session.working_plan = build_costing_plan(
            session.source_document,
            session.live,
        )


def _normalize_article_resolutions(
    article_resolutions: Mapping[str, str] | None,
) -> dict[str, str]:
    return {
        str(key): str(value).strip()
        for key, value in dict(article_resolutions or {}).items()
        if str(key).strip() and str(value).strip()
    }


def _prepare_costing_articles(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
    article_resolutions: Mapping[str, str] | None,
) -> None:
    _write_log(
        session.log,
        "[COSTING] Đang kiểm tra Article trước khi điền field.",
    )
    progress.preflight = _preflight_article_additions(
        session.context,
        session.frame,
        session.working_plan.get("additions") or (),
        _normalize_article_resolutions(article_resolutions),
        session.log,
    )
    if progress.preflight["ambiguous"]:
        raise CostingApplyAbort(
            _result(
                False,
                "COSTING_ARTICLE_AMBIGUOUS",
                "Có Article trùng kết quả. Chọn đúng Article Code rồi áp dụng lại.",
                ambiguous_articles=progress.preflight["ambiguous"],
                missing_articles=progress.preflight["missing"],
            )
        )
    progress.deleted = _delete_articles(
        session.costing_page,
        session.frame,
        session.live,
        session.working_plan.get("deletes") or (),
        session.log,
    )
    progress.added = _add_articles(
        session.context,
        session.frame,
        progress.preflight,
        session.log,
    )
    if progress.added or progress.deleted:
        _refresh_apply_inventory(session, wait_ms=500)


def _missing_article_codes(preflight: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("article_code") or item.get("article_name") or "").casefold()
        for item in preflight.get("missing") or ()
    }


def _apply_costing_splits(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> None:
    missing_codes = _missing_article_codes(progress.preflight)
    pending_splits = [
        request
        for request in session.working_plan.get("splits") or ()
        if str(
            request.get("article_code") or request.get("article_name") or ""
        ).casefold()
        not in missing_codes
    ]
    if pending_splits:
        _write_log(
            session.log,
            "[COSTING] Đang Splitter "
            f"{len(pending_splits)} dòng Article liền nhau.",
        )
    for request in pending_splits:
        checkpoint()
        _split_article_row(session.frame, session.live, request)
        progress.split.append(dict(request))
        _refresh_apply_inventory(
            session,
            wait_ms=250,
            rebuild_plan=False,
        )
    if progress.split and session.source_document is not None:
        session.working_plan = build_costing_plan(
            session.source_document,
            session.live,
        )


def _costing_change_key(
    change: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    return (
        str(change.get("scope") or "").casefold(),
        str(change.get("section_key") or "").casefold(),
        str(change.get("item_key") or "").casefold(),
        str(change.get("field_key") or "").casefold(),
    )


def _change_belongs_to_missing_article(
    change: Mapping[str, Any],
    missing_item_keys: set[str],
) -> bool:
    return (
        str(change.get("scope") or "").casefold() == "item"
        and str(change.get("item_key") or "").casefold() in missing_item_keys
    )


def _apply_single_costing_field(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
    live_fields: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    change: Mapping[str, Any],
    change_index: int,
    change_count: int,
) -> None:
    key = _costing_change_key(change)
    live_field = live_fields.get(key)
    if live_field is None or not live_field.get("editable"):
        progress.skipped.append({**change, "reason": "not_found_or_read_only"})
        return
    try:
        if _dependency_kind(live_field, change.get("value")):
            _set_dependency_mapping(
                session.frame,
                live_field,
                change.get("value"),
            )
            progress.dependency_confirmed.add(key)
        else:
            _set_live_field(session.frame, live_field, change.get("value"))
    except (PlaywrightError, RuntimeError) as error:
        field_key = str(change.get("field_key") or "")
        item_key = str(change.get("item_key") or "")
        reason = _first_line(error)[:160]
        _write_log(
            session.log,
            "[COSTING] Không thể điền field "
            f"{change_index}/{change_count} "
            f"{field_key} ({item_key}): {reason}",
        )
        raise CostingFieldApplyError(field_key, item_key, reason) from error
    progress.applied.append(dict(change))


def _apply_costing_fields(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> None:
    live_fields = _live_field_index(session.live)
    missing_item_keys = {
        str(item.get("import_item_key") or "").casefold()
        for item in progress.preflight.get("missing") or ()
    }
    ordered_changes = sorted(
        session.working_plan.get("fields_to_set") or (),
        key=_field_application_priority,
    )
    change_count = len(ordered_changes)
    if change_count:
        _write_log(
            session.log,
            f"[COSTING] Bắt đầu điền {change_count} field.",
        )
    for change_index, change in enumerate(ordered_changes, 1):
        checkpoint()
        if _change_belongs_to_missing_article(change, missing_item_keys):
            progress.skipped.append({**change, "reason": "article_not_found"})
            continue
        _apply_single_costing_field(
            session,
            progress,
            live_fields,
            change,
            change_index,
            change_count,
        )
        if change_index == 1 or change_index % 10 == 0:
            _write_log(
                session.log,
                f"[COSTING] Đã điền {change_index}/{change_count} field.",
            )


def _field_verification_mismatches(
    verified: Mapping[str, Any],
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    verified_fields = _live_field_index(verified)
    mismatches: list[dict[str, Any]] = []
    for change in progress.applied:
        key = _costing_change_key(change)
        if key in progress.dependency_confirmed:
            # Main inventory only renders [Table]; the popup was checked exactly.
            continue
        actual = verified_fields.get(key, {}).get("value")
        if _field_value_matches(
            actual,
            change.get("value"),
            str(change.get("data_type") or "text"),
        ):
            continue
        mismatches.append(
            {
                "field_key": change.get("field_key"),
                "expected": change.get("value"),
                "actual": actual,
            }
        )
    return mismatches


def _article_verification_mismatches(
    verified: Mapping[str, Any],
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    verified_codes = {
        str(item.get("article_code") or "").casefold()
        for item in verified.get("items") or ()
        if str(item.get("article_code") or "").strip()
    }
    for addition in progress.added:
        code = str(addition.get("resolved_code") or "").strip()
        if code and code.casefold() not in verified_codes:
            mismatches.append(
                {
                    "field_key": f"Article:{code}",
                    "expected": "present",
                    "actual": "missing_after_save",
                }
            )
    for deletion in progress.deleted:
        code = str(deletion.get("article_code") or "").strip()
        if code and code.casefold() in verified_codes:
            mismatches.append(
                {
                    "field_key": f"Article:{code}",
                    "expected": "deleted",
                    "actual": "still_present_after_save",
                }
            )
    return mismatches


def _split_verification_mismatches(
    verified: Mapping[str, Any],
    split_requests: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    identity_counts: dict[tuple[str, str], int] = {}
    for item in verified.get("items") or ():
        identity = _article_identity(item)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    mismatches: list[dict[str, Any]] = []
    for split_request in split_requests:
        expected_count = int(split_request.get("occurrence") or 2)
        actual_count = identity_counts.get(_article_identity(split_request), 0)
        if actual_count >= expected_count:
            continue
        article_identity = str(
            split_request.get("article_code")
            or split_request.get("article_name")
            or ""
        )
        mismatches.append(
            {
                "field_key": f"Splitter:{article_identity}",
                "expected": expected_count,
                "actual": actual_count,
            }
        )
    return mismatches


def _verify_costing_apply(
    session: _CostingApplySession,
    progress: _CostingApplyProgress,
) -> list[dict[str, Any]]:
    _wait(session.costing_page, 500)
    session.costing_page, session.frame = _costing_frame(
        session.context,
        timeout_seconds=10,
        pages=session.scoped_pages,
    )
    verified = _inventory_costing_frame(
        session.frame,
        session.article_code,
        costing_status="Open",
        title=_selected_costing_title(
            session.context,
            pages=session.scoped_pages,
        ),
    )
    return [
        *_field_verification_mismatches(verified, progress),
        *_article_verification_mismatches(verified, progress),
        *_split_verification_mismatches(verified, progress.split),
    ]


def _no_change_apply_result(article_code: str) -> dict[str, Any]:
    return _result(
        True,
        "COSTING_APPLIED",
        f"Costing style {article_code} đã khớp file; không cần Save.",
        article_code=article_code,
        applied_count=0,
        added_count=0,
        split_count=0,
        deleted_count=0,
        skipped_fields=[],
        verified=True,
        no_changes=True,
    )


def _run_costing_apply(
    session: _CostingApplySession,
    article_resolutions: Mapping[str, str] | None,
) -> dict[str, Any]:
    if not _costing_plan_has_changes(session.working_plan):
        return _no_change_apply_result(session.article_code)
    progress = _CostingApplyProgress()
    _prepare_costing_articles(session, progress, article_resolutions)
    _apply_costing_splits(session, progress)
    _apply_costing_fields(session, progress)
    _save_costing(session.costing_page, session.frame, session.log)
    mismatches = _verify_costing_apply(session, progress)
    if mismatches:
        return _result(
            False,
            "COSTING_VERIFY_FAILED",
            "WFX chưa xác nhận một số field sau Save.",
            applied_count=len(progress.applied),
            skipped_fields=progress.skipped,
            mismatches=mismatches,
        )
    return _result(
        True,
        "COSTING_APPLIED",
        f"Đã cập nhật và Save Costing cho style {session.article_code}.",
        article_code=session.article_code,
        applied_count=len(progress.applied),
        added_count=len(progress.added),
        split_count=len(progress.split),
        deleted_count=len(progress.deleted),
        missing_articles=progress.preflight["missing"],
        skipped_fields=progress.skipped,
        verified=True,
    )


def apply_costing_plan(
    article_code: str,
    plan: Mapping[str, Any],
    *,
    source_document: Mapping[str, Any] | None = None,
    article_resolutions: Mapping[str, str] | None = None,
    active_tab_only: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Áp dụng plan Open-only: Material Search, field, Delete và Save."""
    article_code = str(article_code or "").strip()
    validation_error = _validate_costing_apply_request(
        article_code,
        plan,
        source_document,
    )
    if validation_error is not None:
        return validation_error
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        session = _open_costing_apply_session(
            browser,
            article_code,
            plan,
            source_document,
            active_tab_only,
            log,
        )
        return _run_costing_apply(session, article_resolutions)
    except CostingApplyAbort as error:
        return error.result
    except CostingFieldApplyError as error:
        return _result(
            False,
            "COSTING_FIELD_APPLY_FAILED",
            (
                f"Không thể điền field {error.field_key or '(không rõ)'}"
                f"{f' của Article {error.item_key}' if error.item_key else ''}."
            ),
            article_code=article_code,
            failed_field=error.field_key,
            failed_item=error.item_key,
            failure_reason=error.reason,
        )
    except PlaywrightTimeoutError as error:
        code = str(error) if str(error).startswith("COSTING_") else "COSTING_APPLY_FAILED"
        return _result(False, code, "WFX chưa sẵn sàng để áp dụng Costing.")
    except CostingPlanError as error:
        return error.as_result()
    except Exception as error:
        raw = _first_line(error)
        code = raw.split(":", 1)[0] if raw.startswith("COSTING_") else "COSTING_APPLY_FAILED"
        _write_log(log, f"[COSTING] {type(error).__name__}: {raw}")
        return _result(
            False,
            code,
            "Không thể áp dụng Costing; chưa xác nhận Save thành công.",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _scan_open_costing_context(
    context: Any,
    article_code: str,
    *,
    pages: Sequence[Page] | None = None,
    style_status: Mapping[str, Any] | None = None,
    require_open: bool = True,
    scan_details: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét Costing trong phạm vi Page đã chỉ định."""
    _page, frame = _costing_frame(context, pages=pages)
    status = str(
        (style_status or {}).get("internal_costsheet_status") or ""
    ).strip()
    status = status or _status_from_tree(frame)
    if require_open and status.casefold() != "open":
        return _result(
            False,
            "COSTING_NOT_OPEN",
            (
                "CostSheet phải ở trạng thái Open mới có thể Export/Import. "
                "Hãy tự tạo hoặc mở Costing đầy đủ trước."
            ),
            article_code=article_code,
            costing_status=status or "Unknown",
        )
    season = str((style_status or {}).get("season") or "").strip()
    title = _selected_costing_title(context, pages=pages)
    document = _inventory_costing_frame(
        frame,
        article_code,
        costing_status=status,
        season=season,
        title=title,
        style_name=_style_name_from_page(_page),
        scan_details=scan_details,
    )
    if not (document["sections"] or document["fields"]):
        # Quick Find returns as soon as the Costing frame exists, while WFX
        # fills its grid in a later request. Never export a transient workbook.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (
            document["sections"] or document["fields"]
        ):
            _sleep(0.25)
            _page, frame = _costing_frame(
                context,
                timeout_seconds=2,
                pages=pages,
            )
            title = _selected_costing_title(context, pages=pages) or title
            document = _inventory_costing_frame(
                frame,
                article_code,
                costing_status=status,
                season=season,
                title=title,
                style_name=_style_name_from_page(_page),
                scan_details=scan_details,
            )
        if not (document["sections"] or document["fields"]):
            return _result(
                False,
                "COSTING_OPEN_NOT_LOADED",
                "Costing đang Open nhưng WFX chưa tải xong dữ liệu.",
                article_code=article_code,
            )
    _write_log(
        log,
        "[COSTING] Đã đọc "
        f"{len(document['sections'])} section, "
        f"{len(document['items'])} Article, "
        f"{len(document['fields'])} field.",
    )
    return _result(
        True,
        "COSTING_SCANNED",
        f"Đã đọc đầy đủ thông tin Costing cho style {article_code}.",
        article_code=article_code,
        costing=document,
        section_count=len(document["sections"]),
        item_count=len(document["items"]),
        field_count=len(document["fields"]),
    )


def _costing_scan_error(
    error: Exception,
    article_code: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    raw = _first_line(error)
    messages = {
        "COSTING_ACTIVE_TAB_NOT_FOUND": (
            "Tab đang chọn chưa ở màn Costing. Hãy mở Costing cần xuất rồi thử lại."
        ),
        "COSTING_ACTIVE_TAB_AMBIGUOUS": (
            "Có nhiều cửa sổ Costing đang hiển thị; hãy chỉ giữ màn cần xuất "
            "ở trạng thái đang chọn."
        ),
        "COSTING_CONTEXT_NOT_FOUND": (
            "Không tìm thấy màn Costing của style đang chọn."
        ),
    }
    if raw in messages:
        return _result(
            False,
            raw,
            messages[raw],
            article_code=article_code,
        )
    message = f"{type(error).__name__}: {raw}"
    _write_log(log, f"[COSTING] {message}")
    return _result(
        False,
        "COSTING_SCAN_FAILED",
        message,
        article_code=article_code,
    )


def scan_open_costing(
    article_code: str,
    *,
    style_status: Mapping[str, Any] | None = None,
    require_open: bool = True,
    scan_details: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc Costing đã tìm bằng app; không click New, Article, Delete hoặc Save."""
    article_code = str(article_code or "").strip()
    if not article_code:
        return _result(
            False,
            "CATALOG_RESULT_REQUIRED",
            "Hãy tìm và mở một Style Code trước.",
        )
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        return _scan_open_costing_context(
            browser.contexts[0],
            article_code,
            style_status=style_status,
            require_open=require_open,
            scan_details=scan_details,
            log=log,
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def scan_active_open_costing(
    *,
    require_open: bool = True,
    scan_details: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét đúng tab Costing đang hiển thị, không tìm Style hoặc đổi tab."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
    playwright: Playwright | None = None
    article_code = ""
    try:
        playwright = sync_playwright().start()
        browser, session_page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(session_page, log)
        if not _session_is_active(session_page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        context = browser.contexts[0]
        active_page = _active_costing_page(context)
        article_code = _article_code_from_page(active_page)
        if not article_code:
            return _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                (
                    "Đã thấy tab Costing nhưng chưa đọc được Style Code. "
                    "Hãy giữ phần thông tin Style trên tab rồi thử lại."
                ),
            )
        _write_log(
            log,
            f"[COSTING] Dùng tab Costing đang chọn của style {article_code}.",
        )
        return _scan_open_costing_context(
            context,
            article_code,
            pages=[active_page],
            require_open=require_open,
            scan_details=scan_details,
            log=log,
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def inspect_active_costing(
    *,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc nhanh Style Code/status của tab Costing hiện tại, không inventory."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
    playwright: Playwright | None = None
    article_code = ""
    try:
        playwright = sync_playwright().start()
        browser, session_page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(session_page, log)
        if not _session_is_active(session_page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        context = browser.contexts[0]
        active_page = _active_costing_page(context)
        article_code = _article_code_from_page(active_page)
        if not article_code:
            return _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                "Đã thấy tab Costing nhưng chưa đọc được Style Code.",
            )
        _page, frame = _costing_frame(
            context,
            timeout_seconds=3,
            pages=[active_page],
        )
        status = _status_from_tree(frame)
        _write_log(
            log,
            "[COSTING] Tab hiện tại: "
            f"{article_code}; status={status or 'Unknown'}.",
        )
        return _result(
            True,
            "COSTING_CONTEXT_INSPECTED",
            f"Đã nhận tab Costing {article_code}.",
            article_code=article_code,
            costing_status=status or "Unknown",
            style_status={
                "code": article_code,
                "season": "",
                "internal_costsheet_status": status or "Unknown",
            },
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def costing_forbidden_selectors() -> Sequence[str]:
    """Bề mặt testable để audit không có flow nào dùng selector bị cấm."""
    return tuple(sorted(FORBIDDEN_ACTION_SELECTORS))
