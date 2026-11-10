"""Read the active Blanket GMPO grid and apply changes through WFX's editor."""

from __future__ import annotations

from urllib.parse import urlsplit

from wfx_panel.automation._common import (
    URL,
    PlaywrightError,
    _browser_boundary_result,
    _result,
    sync_playwright,
)
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.runtime import AutomationCancelled, checkpoint
from wfx_panel.workbooks.gmpo import quantity, row_key

_GRID = "#gridBlanketGMPOOrderGrid_tblGridContent"
_IDENTITY_JS = """row => [
    'OrderID', 'ColorCode', 'BoxCode', 'ArticleID', 'OCOrderID', 'GMPOOrderID',
    'PackingTypeCode', 'PackingOption', 'DivisionCode', 'RowType'
].map(field => String(row[field] ?? ''))"""
_SCOPE_JS = """() => {
    const saved = String(window.BlanketGMPOID ?? '');
    const seed = new URL(location.href).searchParams.get('SelectedOrderID') ?? '';
    return JSON.stringify([location.origin, Number(saved) > 0 ? ['saved', saved] : ['draft', seed]]);
}"""

_READ_JS = rf"""table => {{
    const model = window.GetObjGrid?.('BlanketGMPOOrderGrid')?.[0];
    const sizes = window.gSizeListJsonData?.OrderGridSizeList?.JsonData;
    if (!Array.isArray(model?.data) || !Array.isArray(sizes)) return null;
    const rows = [...table.querySelectorAll('tbody > tr.trContent')];
    if (rows.length !== model.data.length) return null;
    const identity = {_IDENTITY_JS};
    const scope = {_SCOPE_JS};
    const text = element => (element?.textContent ?? '').replace(/\s+/g, ' ').trim();
    const sizeById = new Map(sizes.map(size => [`col${{size.SizeCode}}`.toLowerCase(), size.SizeCode]));
    const headers = document.querySelector('#gridBlanketGMPOOrderGrid_trHeader');
    if (!headers) return null;
    const columns = [...headers.cells].map(cell => {{
        const id = cell.id.split('_td_')[1]?.toLowerCase();
        return {{id, label: cell.title || text(cell), size: sizeById.get(id) || ''}};
    }}).filter(column => column.id && column.label);
    if (!['colbuyerorderref', 'colstyle', 'colcolor'].every(id => columns.some(c => c.id === id))) return null;
    const sizeLabels = columns.filter(column => column.size).map(column => column.label);
    if (!sizeLabels.length || new Set(sizeLabels).size !== sizeLabels.length) return null;
    const data = rows.map((row, index) => {{
        const record = model.data[index];
        if (!record || row.getAttribute('rowid') !== String(record.OrderID)) return null;
        const cells = new Map([...row.cells].map(cell => [cell.id.toLowerCase(), cell]));
        const values = {{}};
        const qty = {{}};
        for (const column of columns) {{
            const cell = cells.get(column.id);
            const label = cell?.querySelector('span.clsGridLabelContent');
            values[column.id] = text(label ?? cell);
            const size = column.size;
            if (!size || !cell || String(record['My' + size] ?? '') === '') continue;
            const field = cell.querySelector('.divFocusEditable input[type=text]');
            const editing = field?.id === 'txt' + size && !field.disabled && !field.readOnly;
            qty[size] = {{
                value: String(record['My' + size]),
                max: String(record['My' + size + 'Max'] ?? ''),
                decimals: Number(record['My' + size + 'DecimalPlaces'] ?? 0),
                editable: record.IsEditable == 1 && Boolean(editing || label?.classList.contains('lblEditable')),
            }};
        }}
        return {{
            identity: identity(record), values, qty,
            total_qty: String(record.TotalQty),
            qty_factor: Number(record.PrePack) * Number(record.Carton),
        }};
    }});
    if (data.some(row => !row)) return null;
    return {{
        scope: scope(), kit: String(window.gIsPendingGMPOListForKitOrder) !== '0',
        dirty: [...table.querySelectorAll('.divFocusEditable input')].some(input => input.value !== input.defaultValue),
        columns, rows: data,
    }};
}}"""

_EDIT_JS = f"""(table, edit) => {{
    const identity = {_IDENTITY_JS};
    const scope = {_SCOPE_JS};
    if (scope() !== edit.scope || String(window.gIsPendingGMPOListForKitOrder) !== '0') return false;
    const model = window.GetObjGrid?.('BlanketGMPOOrderGrid')?.[0];
    const record = model?.data?.[edit.index];
    const row = table.querySelectorAll('tbody > tr.trContent')[edit.index];
    if (!record || !row || row.getAttribute('rowid') !== edit.identity[0] ||
        identity(record).some((value, index) => value !== edit.identity[index]) ||
        record.IsEditable != 1 || Number(record['My' + edit.size]) !== Number(edit.before)) return false;
    if ([...table.querySelectorAll('.divFocusEditable input')].some(input => input.value !== input.defaultValue)) return false;
    const cell = [...row.cells].find(cell => cell.id === 'Col' + edit.size);
    if (!cell) return false;
    cell.querySelector('.lblEditable')?.click();
    const field = cell.querySelector('.divFocusEditable input[type=text]');
    if (!field || field.id !== 'txt' + edit.size || field.disabled || field.readOnly ||
        Number(field.value) !== Number(edit.before) ||
        !field.getAttribute('onchange')?.includes('txtOrderGridSize_onChange(this)')) return false;
    const value = Number(edit.value);
    const max = field.getAttribute('maxval');
    const min = field.getAttribute('minval');
    if ((max && value > Number(max)) || (min && value < Number(min))) return false;
    const expectedTotal = Number(record.TotalQty) +
        (value - Number(edit.before)) * Number(record.PrePack) * Number(record.Carton);
    let failed = false;
    const recordError = () => {{ failed = true; }};
    window.addEventListener('error', recordError);
    try {{
        field.value = edit.value;
        const accepted = field.dispatchEvent(new Event('change', {{bubbles: true, cancelable: true}}));
        return accepted && !failed && field.getAttribute('Invalid') !== '1' &&
            Number(model.data[edit.index]['My' + edit.size]) === value &&
            Math.abs(Number(model.data[edit.index].TotalQty) - expectedTotal) < 0.000051;
    }} finally {{
        window.removeEventListener('error', recordError);
    }}
}}"""


class GMPOError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _active_grid(context):
    candidates = []
    for page in context.pages:
        for frame in page.frames:
            url = urlsplit(frame.url)
            if (url.scheme, url.netloc, url.path.casefold()) != (
                "https",
                urlsplit(URL).netloc,
                "/wfxbase4.0/wfxblanketgmpo.aspx",
            ):
                continue
            grid = frame.locator(_GRID)
            if grid.count() == 1 and grid.is_visible():
                state = page.evaluate(
                    "() => [document.hasFocus(), document.visibilityState === 'visible']"
                )
                candidates.append((grid, state))
    for index in (0, 1):
        active = [grid for grid, state in candidates if state[index]]
        if len(active) == 1:
            return active[0]
    if len(candidates) == 1:
        return candidates[0][0]
    raise GMPOError(
        "GMPO_TAB_REQUIRED",
        "Hãy mở bảng Order Details của Blanket GMPO. Nếu có nhiều tab GMPO, chỉ để tab cần xử lý.",
    )


def _snapshot(grid) -> dict:
    snapshot = grid.evaluate(_READ_JS, timeout=3_000)
    if not snapshot or not snapshot["rows"]:
        raise GMPOError(
            "GMPO_GRID_NOT_READY", "Bảng GMPO chưa có dữ liệu Order Details để xử lý."
        )
    if snapshot["dirty"]:
        raise GMPOError(
            "GMPO_GRID_NOT_READY", "Hãy xác nhận ô đang sửa trên WFX rồi thử lại."
        )
    rows = snapshot["rows"]
    if len({row_key(row["identity"]) for row in rows}) != len(rows):
        raise GMPOError(
            "GMPO_GRID_NOT_READY",
            "Bảng GMPO có dòng trùng thông tin nhận diện. Chưa thể đối chiếu an toàn.",
        )
    return snapshot


def _plan_edits(snapshot: dict, scope: str, changes: list[dict]) -> list[dict]:
    if snapshot["scope"] != scope:
        raise GMPOError(
            "GMPO_IMPORT_CONFLICT",
            "File Excel thuộc Blanket GMPO khác. Hãy mở đúng đơn đã xuất.",
        )
    if snapshot["kit"]:
        raise GMPOError(
            "GMPO_IMPORT_CONFLICT", "GMPO dạng Packing Kit chỉ hỗ trợ xuất Excel."
        )
    rows = {
        row_key(row["identity"]): (index, row)
        for index, row in enumerate(snapshot["rows"])
    }
    plan = []
    for change in changes:
        label, size, value = change["label"], change["size"], change["value"]
        if change["key"] not in rows:
            raise GMPOError(
                "GMPO_IMPORT_CONFLICT",
                f"Không tìm thấy PO hoặc dòng màu của {label} trong tab GMPO.",
            )
        index, row = rows[change["key"]]
        cell = row["qty"].get(size)
        if not cell or not cell["editable"] or change["before"] is None:
            raise GMPOError(
                "GMPO_IMPORT_CONFLICT", f"WFX không cho chỉnh ô tại {label}."
            )
        current = quantity(cell["value"])
        if current == value:
            continue
        if current != change["before"]:
            raise GMPOError(
                "GMPO_IMPORT_CONFLICT",
                f"Số lượng trên WFX đã đổi tại {label}. Hãy xuất lại file.",
            )
        if cell["max"] and value > quantity(cell["max"]):
            raise GMPOError(
                "GMPO_IMPORT_CONFLICT",
                f"Số lượng tại {label} vượt mức WFX cho phép ({cell['max']}).",
            )
        if -value.normalize().as_tuple().exponent > cell["decimals"]:
            raise GMPOError(
                "GMPO_IMPORT_CONFLICT",
                f"Số lượng tại {label} có quá nhiều chữ số thập phân.",
            )
        plan.append(
            {
                "index": index,
                "identity": row["identity"],
                "size": size,
                "scope": scope,
                "before": format(current, "f"),
                "value": format(value.normalize(), "f"),
                "label": label,
            }
        )
    return plan


def run_gmpo(log, *, scope: str = "", changes: list[dict] | None = None) -> dict:
    playwright = None
    applied = 0
    current = ""
    try:
        playwright = sync_playwright().start()
        browser, _page = _active_wfx_page(playwright, log, bring_to_front=False)
        grid = _active_grid(browser.contexts[0])
        snapshot = _snapshot(grid)
        if changes is None:
            return _result(True, "GMPO_READ", "Đã đọc bảng GMPO.", snapshot=snapshot)
        plan = _plan_edits(snapshot, scope, changes)
        for edit in plan:
            checkpoint()
            current = edit["label"]
            if not grid.evaluate(_EDIT_JS, edit, timeout=3_000):
                raise GMPOError(
                    "GMPO_APPLY_FAILED", f"WFX chưa xác nhận số lượng tại {current}."
                )
            applied += 1
        message = (
            f"Đã điền {applied} ô Order Qty. Kiểm tra kết quả rồi bấm Save trên WFX."
            if applied
            else "Không có ô Order Qty cần cập nhật."
        )
        return _result(True, "GMPO_IMPORT_READY", message, updated_cells=applied)
    except AutomationCancelled:
        if not applied:
            raise
        return _result(
            False,
            "ACTION_CANCELLED",
            f"Đã dừng sau khi điền {applied} ô. Kiểm tra trên WFX trước khi Save.",
            updated_cells=applied,
        )
    except GMPOError as error:
        message = str(error)
        if error.code == "GMPO_APPLY_FAILED":
            message += f" Đã xác nhận {applied} ô. Kiểm tra bảng WFX trước khi Save."
        return _result(False, error.code, message, updated_cells=applied)
    except (PlaywrightError, RuntimeError, ValueError) as error:
        boundary = _browser_boundary_result(error)
        if boundary and not current:
            return boundary
        log(f"[GMPO] {type(error).__name__}: {error}")
        if current:
            message = f"Đã xác nhận {applied} ô trước khi mất phản hồi tại {current}. Kiểm tra WFX trước khi Save."
        else:
            message = "Chưa đọc được bảng GMPO. Hãy kiểm tra tab WFX rồi thử lại."
        return _result(
            False,
            "GMPO_APPLY_FAILED" if current else "GMPO_GRID_NOT_READY",
            message,
            updated_cells=applied,
        )
    finally:
        if playwright is not None:
            playwright.stop()
