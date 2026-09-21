"""Selector, ngưỡng thời gian và snippet JS của EDI Buyer PO."""

from __future__ import annotations

EDI_MENU_SELECTOR = "a[href*='mnuEDIBuyerPO']"


REVISION_REPORT_MENU_XPATH = '//*[@id="0004_0110"]/a'


REVISION_REPORT_SELECTOR = (
    "[nodeid='258'] > span.groupNode, span.groupNode"
)


PACKAGE_VALUE = "1"


PACKAGE_LABEL = "StandardSalesOrder"


STATUS_TIMEOUT_SECONDS = 120


CONFIRM_PROCESS_TIMEOUT_SECONDS = 180


CONFIRM_FIRST_PASS_TIMEOUT_SECONDS = 8


CONFIRM_PAGE_SIZE_SELECTOR = "#gridEDIBuyerPO_divPageSize select"


CONFIRM_GRID_SELECTOR = "#gridEDIBuyerPO_tblGridContent"


CONFIRM_TAB_SELECTORS = {
    "new": "#tabNew",
    "revision": "#tabRevision",
}


_STATUS_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const key = value => norm(value).toLowerCase().replace(/[^a-z]/g, '');
  const wanted = {
    file_name: 'filename',
    imported: 'dataimported',
    validated: 'datavalidated',
    mapped: 'mappingresolved',
    transaction: 'transactiondetail'
  };
  const readGrid = (headerTable, contentTable) => {
    if (!headerTable || !contentTable) return [];
    const headers = [...headerTable.querySelectorAll('tr:first-child th, tr:first-child td')]
      .map(cell => key(cell.innerText || cell.textContent));
    const columns = {};
    for (const [name, token] of Object.entries(wanted)) {
      columns[name] = headers.findIndex(label => label.includes(token));
    }
    if (columns.imported < 0 || columns.validated < 0 ||
        columns.mapped < 0 || columns.transaction < 0) return [];
    for (const row of contentTable.querySelectorAll('tr')) {
      const cells = [...row.querySelectorAll(':scope > td, :scope > th')];
      const read = index => index >= 0
        ? norm(cells[index]?.innerText || cells[index]?.textContent)
        : '';
      const record = {
        file_name: read(columns.file_name),
        imported: read(columns.imported),
        validated: read(columns.validated),
        mapped: read(columns.mapped),
        transaction: read(columns.transaction),
        detail: norm(row.innerText || row.textContent).slice(0, 800)
      };
      if (record.imported || record.validated || record.mapped) return [record];
    }
    return [];
  };
  const direct = readGrid(
    document.querySelector('#gridEDIPackageImport_tblGridHeader'),
    document.querySelector('#gridEDIPackageImport_tblGridContent')
  );
  if (direct.length) return direct;
  for (const headerTable of document.querySelectorAll('table[id$="_tblGridHeader"]')) {
    const contentId = headerTable.id.replace(/_tblGridHeader$/, '_tblGridContent');
    const result = readGrid(headerTable, document.getElementById(contentId));
    if (result.length) return result;
  }
  return [];
}"""


_FAILED_RECORD_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const key = value => norm(value).toLowerCase().replace(/[^a-z0-9]/g, '');
  const headerTable = document.querySelector('#gridFailedRecord_tblGridHeader');
  const contentTable = document.querySelector('#gridFailedRecord_tblGridContent');
  if (!headerTable || !contentTable) return [];
  const headers = [...headerTable.querySelectorAll('tr:first-child th, tr:first-child td')]
    .map(cell => norm(cell.innerText || cell.textContent));
  const keyedHeaders = headers.map(key);
  const indexOf = token => keyedHeaders.findIndex(label => label.includes(token));
  const columns = {
    mapping_code: indexOf('mappingcode'),
    doc_no: indexOf('docno'),
    mapping_details: indexOf('mappingdetails'),
    inactive: indexOf('inactive')
  };
  return [...contentTable.querySelectorAll('tr')].slice(0, 50).map(row => {
    const cells = [...row.querySelectorAll(':scope > td, :scope > th')];
    const read = index => index >= 0
      ? norm(cells[index]?.innerText || cells[index]?.textContent)
      : '';
    const pairs = headers.map((header, index) => {
      const value = read(index);
      return header && value ? `${header}: ${value}` : '';
    }).filter(Boolean);
    return {
      mapping_code: read(columns.mapping_code),
      doc_no: read(columns.doc_no),
      mapping_details: read(columns.mapping_details),
      inactive: read(columns.inactive),
      detail: pairs.join(' | ').slice(0, 1200)
    };
  }).filter(record => record.detail);
}"""


_CONFIRM_GROUPS_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return [];
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  return starts.map((start, groupIndex) => {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const groupRows = rows.slice(start.index, end);
    const styleCell = groupRows[0].querySelector(
      '#colStyle, #lblStyle, [id*="Style" i]'
    );
    return {
      key: signature(groupRows),
      label: norm(styleCell?.getAttribute('title') || styleCell?.textContent ||
        groupRows[0].textContent).slice(0, 180),
      row_count: groupRows.length,
    };
  });
}"""


_PREPARE_REVISION_STYLE_JS = r"""targetKey => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return {ok: false, reason: 'grid-not-found'};
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  let groupRows = null;
  for (let groupIndex = 0; groupIndex < starts.length; groupIndex += 1) {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const candidate = rows.slice(starts[groupIndex].index, end);
    if (signature(candidate) === targetKey) {
      groupRows = candidate;
      break;
    }
  }
  if (!groupRows) return {ok: false, reason: 'style-changed'};
  const rowPlans = groupRows.map((row, rowIndex) => {
    const cell = row.querySelector('#colWFXSalesOrder');
    const select = cell?.querySelector('select');
    if (!select) return {row, cell, select: null, choices: [], rowIndex};
    cell.click();
    select.focus();
    select.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
    const choices = [...select.options]
      .filter(option => !option.disabled)
      .map(option => ({value: norm(option.value), label: norm(option.textContent)}))
      .filter(option => option.value &&
        !/^(select|choose|--|\[select\])$/i.test(option.label));
    const unique = [...new Map(
      choices.map(option => [option.value.toLocaleLowerCase('en'), option])
    ).values()];
    return {row, cell, select, choices: unique, rowIndex};
  });
  const ambiguous = rowPlans.find(plan => plan.choices.length > 1);
  if (ambiguous) {
    return {
      ok: false,
      reason: 'multiple-sales-orders',
      row_number: ambiguous.rowIndex + 1,
      options: ambiguous.choices.map(option => option.label || option.value),
    };
  }
  let selectedCount = 0;
  let emptyCount = 0;
  rowPlans.forEach(plan => {
    if (plan.choices.length === 0) {
      emptyCount += 1;
      return;
    }
    plan.cell?.click();
    plan.select.focus();
    plan.select.value = plan.choices[0].value;
    plan.select.dispatchEvent(new Event('input', {bubbles: true}));
    plan.select.dispatchEvent(new Event('change', {bubbles: true}));
    selectedCount += 1;
  });
  return {
    ok: true,
    selected_count: selectedCount,
    empty_count: emptyCount,
    row_count: groupRows.length,
  };
}"""


_MARK_CONFIRM_STYLE_JS = r"""targetKey => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return {ok: false, reason: 'grid-not-found'};
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  document.querySelectorAll('[data-wfx-oc-confirm-row]').forEach(row =>
    row.removeAttribute('data-wfx-oc-confirm-row'));
  for (let groupIndex = 0; groupIndex < starts.length; groupIndex += 1) {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const groupRows = rows.slice(starts[groupIndex].index, end);
    if (signature(groupRows) !== targetKey) continue;
    groupRows.forEach(row => row.setAttribute('data-wfx-oc-confirm-row', '1'));
    return {ok: true, row_count: groupRows.length};
  }
  return {ok: false, reason: 'style-changed'};
}"""


_ACTIVE_CONFIRM_TAB_JS = r"""() => {
  const score = element => {
    if (!element) return 0;
    let value = 0;
    let current = element;
    for (let depth = 0; current && depth < 4; depth += 1) {
      const classes = String(current.className || '').toLocaleLowerCase('en')
        .split(/[^a-z0-9]+/).filter(Boolean);
      if (classes.some(token => [
        'active', 'selected', 'tabactive', 'tabselected', 'current',
        'clstabtdselected'
      ].includes(token))) value += 10 - depth;
      if (current.getAttribute('aria-selected') === 'true') value += 20 - depth;
      if (current.getAttribute('aria-current') === 'page') value += 20 - depth;
      if (['active', 'selected'].includes(
        String(current.dataset?.state || '').toLocaleLowerCase('en')
      )) value += 20 - depth;
      current = current.parentElement;
    }
    return value;
  };
  const tabs = [
    {mode: 'new', element: document.querySelector('#tabNew')},
    {mode: 'revision', element: document.querySelector('#tabRevision')},
  ].filter(tab => tab.element);
  if (tabs.length !== 2) return '';
  const ranked = tabs.map(tab => ({...tab, score: score(tab.element)}))
    .sort((left, right) => right.score - left.score);
  if (ranked[0].score > 0 && ranked[0].score > ranked[1].score) {
    return ranked[0].mode;
  }
  const focused = tabs.find(tab => tab.element === document.activeElement ||
    tab.element.contains(document.activeElement));
  return focused?.mode || '';
}"""
