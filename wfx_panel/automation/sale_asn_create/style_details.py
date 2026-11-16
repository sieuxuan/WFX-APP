"""Điền HS Code và Goods Description theo Style."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from wfx_panel.automation._common import Frame, _wait, _write_log
from wfx_panel.automation.sale_asn_create.errors import _filling_cell
from wfx_panel.automation.sale_asn_create.order_details import (
    _READ_TABLE_CELL_JS,
    _edit_marked_table_cell,
)
from wfx_panel.automation.sale_asn_create.progress import _emit_stage_progress

_MARK_STYLE_HTS_CELL_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, ' ').trim();
    const score = (wanted, actual) => {
        if (!wanted || !actual) return 0;
        if (wanted === actual) return 10000;
        if (actual.includes(wanted) || wanted.includes(actual)) {
            return 8000 + Math.min(wanted.length, actual.length);
        }
        const left = new Set(wanted.split(' ').filter(Boolean));
        const right = new Set(actual.split(' ').filter(Boolean));
        let shared = 0;
        left.forEach(token => { if (right.has(token)) shared += 1; });
        return shared * 100 - Math.abs(left.size - right.size);
    };
    const table = document.querySelector('#gridStyleDetails_tblGridContent');
    if (!table) return {ok: false, reason: 'style-grid-not-found'};
    const wanted = fold(spec.style);
    const candidates = [...table.querySelectorAll('tr.trContent')]
        .map(row => {
            const styleCell = row.querySelector('td#colStyle');
            const styleLabel = styleCell?.querySelector('#lblStyle');
            const styleText = clean(
                styleLabel?.getAttribute('title') || styleLabel?.textContent
                || styleCell?.textContent
            );
            return {row, styleText, score: score(wanted, fold(styleText))};
        })
        .filter(item => item.score > 0);
    const bestScore = Math.max(0, ...candidates.map(item => item.score));
    const best = candidates.filter(item => item.score === bestScore);
    // Một Style có thể tạo nhiều dòng WFX theo Style Description/Fit (ví dụ
    // SLIM FIT và CLASSIC FIT). Khi cả hai đều khớp exact/contains mạnh, cùng
    // HS Code và Goods Description từ file phải được áp dụng cho tất cả.
    // Khớp token yếu vẫn phải dừng để không ghi nhầm style gần giống.
    const strongDuplicate = bestScore >= 8000 && wanted.length >= 6;
    if (!best.length || (best.length > 1 && !strongDuplicate)) {
        return {
            ok: false,
            reason: 'style-row-ambiguous',
            count: best.length,
            styles: candidates.map(item => item.styleText),
        };
    }
    const targetIndex = Number.isInteger(Number(spec.target_index))
        ? Number(spec.target_index) : 0;
    if (targetIndex < 0 || targetIndex >= best.length) {
        return {ok: false, reason: 'style-row-index-changed', count: best.length};
    }
    const cell = best[targetIndex].row.querySelector('td#colHTSCode');
    if (!cell) return {ok: false, reason: 'hts-cell-not-found'};
    document.querySelectorAll('[data-wfx-sale-asn-target]').forEach(item =>
        item.removeAttribute('data-wfx-sale-asn-target'));
    cell.setAttribute('data-wfx-sale-asn-target', '1');
    return {
        ok: true,
        style: best[targetIndex].styleText,
        column_id: cell.id,
        target_count: best.length,
        target_index: targetIndex,
    };
}"""


# WFX dùng cùng cấu trúc bảng cho hai field Style Details. Giữ selector HTS
# riêng ở trên để các integration test cũ vẫn kiểm tra đúng cell hiện hữu;
# cột mô tả hàng hóa dùng chính selector WFX được cung cấp.
_MARK_STYLE_GOODS_DESCRIPTION_CELL_JS = _MARK_STYLE_HTS_CELL_JS.replace(
    "td#colHTSCode",
    "td#colGoodsDescription",
)


def _set_style_cells(
    frame: Frame,
    style: str,
    value: str,
    marker_script: str,
) -> int:
    target_count: int | None = None
    target_index = 0
    while target_count is None or target_index < target_count:
        marked = frame.evaluate(
            marker_script,
            {"style": style, "target_index": target_index},
        )
        if not marked.get("ok"):
            reason = marked.get("reason")
            if reason == "style-row-ambiguous" and marked.get("count") == 0:
                reason = "style-not-found"
            raise RuntimeError(f"SALE_ASN_TABLE_MAPPING_FAILED:{reason}")
        if target_count is None:
            target_count = max(1, int(marked.get("target_count") or 1))
        elif int(marked.get("target_count") or target_count) != target_count:
            raise RuntimeError(
                "SALE_ASN_TABLE_MAPPING_FAILED:style-row-count-changed"
            )
        _edit_marked_table_cell(frame, value)
        target_index += 1
    return target_count


def _set_style_hts_cell(frame: Frame, style: str, value: str) -> int:
    return _set_style_cells(frame, style, value, _MARK_STYLE_HTS_CELL_JS)


def _set_style_goods_description_cell(
    frame: Frame,
    style: str,
    value: str,
) -> int:
    """Điền Goods Description vào đúng dòng Style Details trên WFX."""
    return _set_style_cells(
        frame,
        style,
        value,
        _MARK_STYLE_GOODS_DESCRIPTION_CELL_JS,
    )


_MARK_DESCRIPTION_FOR_CLEAR_JS = """row => {
    const cell = row.querySelector('td#colGoodsDescription');
    const styleCell = row.querySelector('td#colStyle');
    const styleLabel = styleCell?.querySelector('#lblStyle');
    const style = (styleLabel?.getAttribute('title') || styleCell?.textContent || '').trim();
    if (!cell) return {style_no: style, missing: true};
    const value = (READ_CELL)(cell).trim();
    if (value) {
        document.querySelector('[data-wfx-sale-asn-target]')?.removeAttribute('data-wfx-sale-asn-target');
        cell.setAttribute('data-wfx-sale-asn-target', '1');
    }
    return {style_no: style, value};
}""".replace("READ_CELL", _READ_TABLE_CELL_JS)


def _clear_style_goods_descriptions(frame: Frame, log: Callable[[str], None]) -> None:
    rows = frame.locator("#gridStyleDetails_tblGridContent tr.trContent")
    with _filling_cell({}, "Goods Description"):
        rows.first.wait_for(state="visible", timeout=8_000)
    count = rows.count()
    for index in range(count):
        row_label = f"Goods Description (dòng WFX {index + 1})"
        with _filling_cell({}, row_label):
            marked = rows.nth(index).evaluate(_MARK_DESCRIPTION_FOR_CLEAR_JS, timeout=3_000)
        with _filling_cell(marked, row_label):
            if marked.get("missing"):
                raise RuntimeError("SALE_ASN_TABLE_MAPPING_FAILED:cell-not-found")
            if marked.get("value"):
                actual = _edit_marked_table_cell(frame, "")
                if actual:
                    raise RuntimeError(f"SALE_ASN_FIELD_VALUE_NOT_CONFIRMED:{actual}")
    _write_log(log, f"[SALE ASN] Đã xóa Goods Description trên toàn bộ {count} dòng Style Details.")


def _fill_style_details(
    frame: Frame,
    rows: Sequence[dict],
    log: Callable[[str], None],
    progress: Callable[..., None] | None = None,
) -> None:
    tab = frame.locator("#tabStyleDetails").first
    tab.wait_for(state="visible", timeout=8_000)
    tab.click(timeout=5_000)
    _wait(frame, 500)
    _clear_style_goods_descriptions(frame, log)

    grouped: dict[str, dict[str, tuple[str, dict]]] = {}
    for row in rows:
        style = str(row.get("style_no") or "")
        detail = grouped.setdefault(style, {})
        hs_code = str(row.get("hs_code") or "").strip()
        if hs_code:
            old_hs_code, _ = detail.setdefault("hs_code", (hs_code, row))
            if old_hs_code != hs_code:
                with _filling_cell(row, f"HS Code {hs_code}"):
                    raise RuntimeError(f"SALE_ASN_STYLE_HS_CODE_CONFLICT:{old_hs_code} và {hs_code}")
        description = str(row.get("goods_description") or "").strip()
        if description:
            old_description, _ = detail.setdefault("goods_description", (description, row))
            if old_description != description:
                with _filling_cell(row, "Goods Description"):
                    raise RuntimeError("SALE_ASN_STYLE_GOODS_DESCRIPTION_CONFLICT")
    for index, (style, values) in enumerate(grouped.items(), 1):
        _emit_stage_progress(
            progress,
            "style_details",
            f"Style Details {index}/{len(grouped)}",
        )
        if "hs_code" in values:
            code, source_row = values["hs_code"]
            with _filling_cell(source_row, f"HS Code {code}"):
                hts_count = _set_style_hts_cell(frame, style, code)
            hts_scope = (
                f"{hts_count} dòng "
                if isinstance(hts_count, int) and hts_count > 1
                else ""
            )
            _write_log(
                log,
                f"[SALE ASN] Đã điền HS Code cho {hts_scope}Style {style}.",
            )
        if "goods_description" not in values:
            continue
        description, source_row = values["goods_description"]
        with _filling_cell(source_row, "Goods Description"):
            description_count = _set_style_goods_description_cell(frame, style, description)
        description_scope = (
            f"{description_count} dòng "
            if isinstance(description_count, int) and description_count > 1
            else ""
        )
        _write_log(
            log,
            f"[SALE ASN] Đã điền Goods Description cho {description_scope}Style {style}.",
        )
