"""XPath, snippet JS và danh sách field của form New Style."""

from __future__ import annotations

NEW_STYLE_XPATH = "/html/body/form/table/tbody/tr[3]/td/input"


# WFX đặt ô tìm "ArticleCode/Name" ở dòng 8. Style copy luôn nhận Article Name
# từ Article List, nên không dùng Buyer Reference (dòng 10) nữa.
COPY_ARTICLE_CODE_NAME_XPATH = "/html/body/form/table/tbody/tr[8]/td/input"


COPY_SEARCH_XPATH = "/html/body/form/table/tbody/tr[12]/td/input"


COPY_COSTSHEET_XPATH = (
    '//*[@id="wfx_ArticleEdit"]/form/table[3]/tbody/tr/td[1]/table/'
    "tbody/tr[2]/td[4]/input"
)


COPY_AS_VARIANT_XPATH = (
    '//*[@id="wfx_ArticleEdit"]/form/table[3]/tbody/tr/td[2]/table/'
    "tbody/tr/td[2]/input"
)


SAVE_STYLE_XPATH = '//*[@id="titlebarArticle"]/tbody/tr/td[2]/span/div[1]/a'


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


_READ_STYLE_OPTIONS_JS = """spec => {
    const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const folded = value => clean(value).toLocaleLowerCase('en');
    let control = null;
    for (const id of spec.ids || []) {
        const candidate = document.getElementById(id);
        if (candidate && !candidate.disabled) {
            control = candidate;
            break;
        }
    }
    if (!control) return [];
    if (control.tagName === 'SELECT') {
        return [...control.options].map(option => ({
            value: clean(option.value),
            label: clean(option.textContent),
            disabled: Boolean(option.disabled),
        })).filter(option => option.label && option.value
            && !option.disabled
            && !/^(select|choose|--)/i.test(option.label));
    }
    if (['radio', 'checkbox'].includes(folded(control.type))) {
        const group = control.name
            ? [...document.querySelectorAll(`input[name="${CSS.escape(control.name)}"]`)]
            : [control];
        return group.filter(item => !item.disabled).map(item => ({
            value: clean(item.value),
            label: clean(item.title || item.parentElement?.textContent || item.value),
        })).filter(option => option.label);
    }
    return [];
}"""


_HYDRATE_STYLE_OPTIONS_JS = """spec => {
    for (const id of spec.ids || []) {
        const control = document.getElementById(id);
        if (!control || control.disabled || control.tagName !== 'SELECT') continue;
        control.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true,
            cancelable: true,
            view: window,
        }));
        return true;
    }
    return false;
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
