"""Selector, regex, snippet JS và exception dùng chung cho Costing.

Không import module Costing nào khác nên luôn nạp được đầu tiên."""

from __future__ import annotations

import re
from typing import Any

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


# Đọc bảng Dependency phải mở popup, nên một lượt hỏng vì popup chưa kịp hiện
# là chuyện bình thường. Đây là thao tác chỉ đọc nên thử lại an toàn.
DEPENDENCY_TABLE_ATTEMPTS = 2


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


_SPECIAL_COST_SECTION_EDITORS = {
    "cmcosts": {
        "header_class": "CMCostHeaderRowType",
        "row_class": "CMCostDataRowType",
        "label": "#CostSheetCMCosts_lblSupplierCompany",
        "editor": "#CostSheetCMCosts_ddlSupplierCompany",
    },
    "productioncosts": {
        "header_class": "ProdProcessHeaderRowType",
        "row_class": "ProdProcessDataRowType",
        "label": "#CostSheetProdProcessDetails_lblProcessName",
        "editor": "#CostSheetProdProcessDetails_ddlProcessName",
    },
    "indirectcosts": {
        "header_class": "ICHeaderRowType",
        "row_class": "ICDataRowType",
        "label": "#lblTitle",
        "editor": "#ddlTitle",
    },
}


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
        const articleElement = row.querySelector('#lblArticle');
        // WFX keeps a hidden ``lblArticle`` containing ">>" on subtotal and
        // total rows.  Only a visible label represents an Article usage row;
        // inheriting from hidden labels turns the final subtotal into a fake
        // split row for the preceding Article.
        if (!shown(articleElement)) return {code: '', name: ''};
        const articleText = clean(articleElement.textContent);
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
        const articleElement = row.querySelector('#lblArticle');
        const articleText = shown(articleElement)
            ? clean(articleElement.textContent)
            : '';
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


_VISIBLE_JS = """elements => elements
    .map((element, index) => ({element, index}))
    .filter(({element}) => {
        if (!element.isConnected) return false;
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return false;
        }
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    })
    .map(({index}) => index)"""


# Tương đương `is_visible()` + `is_enabled()` của Playwright: bounding box khác
# rỗng, không bị ẩn, và `:disabled` bắt cả control nằm trong fieldset disabled.
_USABLE_CONTROL_JS = """elements => elements
    .map((element, index) => ({element, index}))
    .filter(({element}) => {
        if (!element.isConnected) return false;
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return false;
        }
        const rect = element.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        return !element.matches(':disabled');
    })
    .map(({index}) => index)"""


# WFX lặp cùng một id trên nhiều dòng, nên selector `[id="..."]` vẫn phải được
# soát lại bằng chính `getAttribute('id')` trước khi coi là đúng control.
_VISIBLE_WITH_ID_JS = """(elements, wantedId) => elements
    .map((element, index) => ({element, index}))
    .filter(({element}) => {
        if (element.getAttribute('id') !== wantedId) return false;
        if (!element.isConnected) return false;
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return false;
        }
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    })
    .map(({index}) => index)"""


_MATERIAL_VARIANT_FIELDS = {
    "colmaterialcolorlist": {
        "kind": "Color",
        "editor_id": "ddlMaterialColorList",
        "add_id": "imgMaterialColorAdd",
        "list_url": "wfx_articlecolorlist",
        "fallback_card": "",
    },
    "colmaterialsizelist": {
        "kind": "Size",
        "editor_id": "ddlMaterialSizeList",
        "add_id": "imgMaterialSizeAdd",
        "list_url": "wfx_articlesizelist",
        "fallback_card": "Sample",
    },
}


_MATERIAL_VARIANT_CARD_XPATH = (
    "/html/body/form/table[3]/tbody/tr[2]/td/table/tbody/"
    "tr[1]/td[1]/table/tbody/tr[1]"
)


_MATERIAL_VARIANT_SEARCH_XPATH = (
    "/html/body/form/table[3]/tbody/tr[2]/td/table/tbody/"
    "tr[1]/td[1]/table/tbody/tr[2]"
)


_MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH = (
    "/html/body/form/table[3]/tbody/tr[2]/td/table/tbody/tr[4]/td[1]/a"
)


_MATERIAL_VARIANT_SAVE_XPATH = (
    "/html/body/form/table[1]/tbody/tr/td[3]/table/tbody/tr/td[2]/a"
)


_MATERIAL_VARIANT_CLOSE_XPATH = (
    "/html/body/form/table[1]/tbody/tr/td[3]/table/tbody/tr/td[3]/a"
)


# Một lượt gọi thay cho `is_visible`+`is_enabled`+`type`+`id`+`name`+`tagName`
# của từng control: một dòng Costing có vài chục input/select.
_INLINE_EDITOR_JS = """(elements, suffix) => {
    const blocked = new Set(
        ['hidden', 'checkbox', 'radio', 'file', 'button', 'submit']
    );
    const usable = [];
    elements.forEach((element, index) => {
        if (!element.isConnected) return;
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') return;
        const rect = element.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;
        if (element.matches(':disabled')) return;
        const type = String(element.getAttribute('type') || '').toLowerCase();
        if (blocked.has(type)) return;
        const identity = [
            element.getAttribute('id') || '',
            element.getAttribute('name') || ''
        ].join(' ').toLowerCase();
        usable.push({
            index,
            tag: element.tagName.toLowerCase(),
            matches_suffix: Boolean(suffix) && identity.includes(suffix)
        });
    });
    return usable;
}"""


# Giống hệt cách `_select_special_cost_article` đã dùng: khớp exact theo nhãn
# hoặc value ngay trong trình duyệt. Dropdown Article của WFX có thể vài trăm
# option, mỗi option trước đây tốn 2 lượt gọi.
_MATCHING_OPTION_VALUES_JS = """(options, wanted) => options
    .filter(option => [option.textContent, option.value]
        .some(value => String(value || '').trim().toLowerCase() === wanted))
    .map(option => String(option.value || '').trim())"""


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


class CostingApplyAbort(RuntimeError):
    """Stop an apply workflow while preserving its structured panel result."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__(str(result.get("code") or "COSTING_APPLY_FAILED"))
        self.result = result
