"""Điểm vào run_sale_asn_create — chạy năm bước theo lựa chọn của user."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from wfx_panel.automation._common import (
    PlaywrightError,
    PlaywrightTimeoutError,
    _domain_error_code,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.runtime import AutomationCancelled
from wfx_panel.automation.sale_asn_create.buyers import _select_buyer
from wfx_panel.automation.sale_asn_create.constants import (
    ADD_ORDER_XPATH,
    ORDER_GRID_SELECTOR,
    PO_POPUP_SELECTOR,
    SALE_ASN_PO_SEARCH_FIELDS,
    SALE_ASN_STAGE_FRAME_SELECTORS,
)
from wfx_panel.automation.sale_asn_create.errors import (
    _CellFillError,
    _failure_reason,
    _po_selection_result,
    _POAddUnconfirmed,
    _POSelectionRequired,
    _row_label,
)
from wfx_panel.automation.sale_asn_create.form import (
    _frame_with_selector,
    _open_new_form,
    _refresh_existing_new_form,
)
from wfx_panel.automation.sale_asn_create.line_mapping import (
    _line_group,
    _remember_line_selection,
    _separate_line_groups,
    _used_line_selections,
)
from wfx_panel.automation.sale_asn_create.order_details import (
    _READ_ORDER_DETAILS_JS,
    _combined_order_rows,
    _ensure_order_grid_rows,
    _ensure_po_popup_for_next_row,
    _fill_order_details,
    _missing_order_rows,
    _wait_order_grid,
)
from wfx_panel.automation.sale_asn_create.po import (
    _add_selected_po_candidates,
    _auto_add_po_with_frame_retry,
    _click_dom_action,
    _po_search_row,
)
from wfx_panel.automation.sale_asn_create.price_check import (
    _check_sale_asn_price_on_page,
)
from wfx_panel.automation.sale_asn_create.progress import (
    SALE_ASN_STAGE_LABELS,
    SALE_ASN_STAGE_ORDER,
    _emit_stage_progress,
)
from wfx_panel.automation.sale_asn_create.shipping import _fill_shipping
from wfx_panel.automation.sale_asn_create.style_details import _fill_style_details
from wfx_panel.automation.sale_asn_create.values import _decimal_or_none


def _find_draft(context: Any, draft: dict) -> Any:
    try:
        _, frame = _frame_with_selector(
            context, f'html[data-wfx-sale-asn-review="{draft["token"]}"]', timeout_s=3,
        )
    except PlaywrightTimeoutError as error:
        raise RuntimeError("SALE_ASN_DRAFT_UNAVAILABLE") from error
    return frame


def _mark_draft(frame: Any, draft: dict) -> None:
    frame.evaluate("token => document.documentElement.dataset.wfxSaleAsnReview = token", draft["token"])
    draft["bound"] = True


def _pause_after_stage(stage: str, skipped: set[str]) -> dict[str, Any]:
    index = SALE_ASN_STAGE_ORDER.index(stage)
    next_stage = next(item for item in SALE_ASN_STAGE_ORDER[index + 1:] if item not in skipped)
    return _result(
        True, "SALE_ASN_STAGE_READY",
        f"Đã xong {SALE_ASN_STAGE_LABELS[stage]}. Bạn có thể kiểm tra trên WFX trước khi chạy {SALE_ASN_STAGE_LABELS[next_stage]}.",
        resume_stage=next_stage,
        stage_label=SALE_ASN_STAGE_LABELS[next_stage],
        can_skip=next_stage not in {"po", "price_check"},
    )


def _confirm_pending_add(frame: Any, pending: _POAddUnconfirmed, separate: bool) -> bool:
    live_rows = frame.evaluate(_READ_ORDER_DETAILS_JS, {
        "table": ORDER_GRID_SELECTOR, "line_details": True,
    })
    wanted = {
        str(candidate.get("selection_value") or "").rpartition("_")[2]
        for candidate in pending.candidates
    }
    present_ids = {str(item["row_id"]) for item in live_rows}
    if wanted and "" not in wanted and wanted.issubset(present_ids):
        return True
    if separate or len(pending.candidates) != 1:
        return False
    # Trong trường hợp WFX dùng định danh khác ở kết quả tìm kiếm và Order
    # Details, chỉ dùng mã PO/Style cho một dòng không lặp.
    return not _missing_order_rows([pending.row], {_line_group(item) for item in live_rows})


def run_sale_asn_create(
    xpath: str,
    buyer: str,
    rows: Sequence[dict],
    start_index: int = 0,
    log: Callable[[str], None] = print,
    *,
    stage: str = "po",
    skip_stages: Sequence[str] = (),
    search_fields: Sequence[str] = SALE_ASN_PO_SEARCH_FIELDS,
    progress: Callable[..., None] | None = None,
    selected_po_row: dict | None = None,
    selected_po_candidates: Sequence[dict] = (),
    selected_po_final: bool = False,
    line_bindings: dict | None = None,
    draft: dict | None = None,
    step_by_step: bool = False,
) -> dict[str, Any]:
    playwright = None
    current_stage = str(stage or "po")
    add_po_selected = current_stage == "po"
    shipping_warnings = list((draft or {}).get("shipping_warnings", ()))
    price_check: dict[str, Any] | None = None
    bindings = line_bindings if line_bindings is not None else {}
    separate_groups = _separate_line_groups(rows)
    line_options = {"line_bindings": bindings} if separate_groups else {}
    po_index = max(0, int(start_index))
    location = "Kết nối WFX"
    active_row: dict = {}
    try:
        if add_po_selected and not buyer.strip():
            return _result(False, "SALE_ASN_BUYER_REQUIRED", "Hãy chọn Buyer trước khi chạy.")
        if not rows:
            return _result(False, "SALE_ASN_FILE_EMPTY", "File Sale ASN chưa có dữ liệu.")
        if current_stage not in SALE_ASN_STAGE_LABELS:
            return _result(
                False,
                "SALE_ASN_CREATE_STAGE_INVALID",
                "Checkpoint tạo Sale ASN không hợp lệ; hãy chọn file lại.",
            )
        skipped = {item for item in skip_stages if item in SALE_ASN_STAGE_LABELS}
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        context = page.context
        main_frame = None
        if draft is not None and draft.get("bound"):
            location = "Form Sale ASN đang làm"
            main_frame = _find_draft(context, draft)
            page = main_frame.page
        if current_stage == "po":
            location = "Add Order Details"
            _emit_stage_progress(
                progress,
                "po",
                "Đang mở Add Order Details",
            )
            existing_form = main_frame is not None
            if not existing_form and po_index == 0 and not selected_po_candidates:
                bindings.clear()
                main_frame = _refresh_existing_new_form(page, log)
                if main_frame is None:
                    main_frame = _open_new_form(page, xpath, log)
                location = f"Buyer {buyer}"
                _select_buyer(main_frame, buyer)
                if draft is not None:
                    _mark_draft(main_frame, draft)
                location = "Add Order Details"
                add = main_frame.locator(f"xpath={ADD_ORDER_XPATH}").first
                _click_dom_action(add)
                _write_log(log, "[SALE ASN] Đã chọn Buyer và mở Add Order Details.")
            if draft is not None and (uncertain := draft.get("unconfirmed_po")):
                active_row = uncertain.row
                location = _row_label(active_row)
                separate = _line_group(active_row) in separate_groups
                if not _confirm_pending_add(main_frame, uncertain, separate):
                    raise uncertain
                if separate:
                    _remember_line_selection(bindings, active_row, uncertain.candidates)
                draft.pop("unconfirmed_po", None)
                po_index = min(len(rows), po_index + 1)

            first_pending = po_index
            if selected_po_candidates:
                selected_row = dict(selected_po_row or {})
                location = _row_label(selected_row)
                _emit_stage_progress(
                    progress,
                    "po",
                    f"Thêm PO {selected_row.get('po_no', '')} · {first_pending + 1}/{len(rows)}",
                )
                _popup_page, selected_frame = _frame_with_selector(
                    context,
                    PO_POPUP_SELECTOR,
                    timeout_s=15,
                )
                _add_selected_po_candidates(
                    selected_frame,
                    selected_row,
                    selected_po_candidates,
                    log,
                    final=selected_po_final,
                )
                if _line_group(selected_row) in separate_groups:
                    _remember_line_selection(bindings, selected_row, selected_po_candidates)
                first_pending = min(len(rows), first_pending + 1)
                po_index = first_pending
                if first_pending < len(rows):
                    location = f"Mở Add Order Details cho {_row_label(rows[first_pending])}"
                    popup_frame = _ensure_po_popup_for_next_row(
                        context,
                        rows[:first_pending],
                        log,
                    )
            # Vòng lặp nằm hẳn trong guard: ngoài guard thì popup chưa được mở
            # nên không có tên nào để tham chiếu nhầm.
            if first_pending < len(rows):
                if not selected_po_candidates:
                    if existing_form:
                        location = _row_label(rows[first_pending])
                        popup_frame = _ensure_po_popup_for_next_row(
                            context, rows[:first_pending], log, main_frame=main_frame,
                        )
                    else:
                        _popup_page, popup_frame = _frame_with_selector(
                            context, PO_POPUP_SELECTOR, timeout_s=15,
                        )
                for index in range(first_pending, len(rows)):
                    row = _po_search_row(rows[index], rows)
                    po_index = index
                    location = _row_label(row)
                    final_pending = index == len(rows) - 1
                    if _line_group(row) in separate_groups:
                        source_row = int(row["source_row"])
                        if bindings.get(source_row, {}).get("combined_into"):
                            po_index = index + 1
                            continue
                        row["_separate_line"] = True
                        row["_used_line_selections"] = _used_line_selections(bindings, source_row)
                        if not final_pending:
                            next_row = rows[index + 1]
                            if (
                                next_row.get("source_row") == source_row + 1
                                and _line_group(next_row) == _line_group(row)
                                and source_row + 1 not in bindings
                                and (qty := _decimal_or_none(next_row.get("qty"))) is not None
                                and qty > 0
                            ):
                                row["_next_line_qty"] = qty
                                row["_next_line_is_last"] = index == len(rows) - 2
                    _emit_stage_progress(
                        progress,
                        "po",
                        f"Thêm PO {row.get('po_no', '')} · {index + 1}/{len(rows)}",
                    )
                    added, candidates, reason, popup_frame = (
                        _auto_add_po_with_frame_retry(
                            context,
                            popup_frame,
                            row,
                            log,
                            final=final_pending,
                            search_fields=search_fields,
                        )
                    )
                    if not added:
                        return _po_selection_result(
                            row,
                            candidates,
                            reason,
                            final=final_pending,
                            pending_index=index,
                            next_index=index + 1,
                            completed=index,
                            total=len(rows),
                        )
                    po_index = index + 1
                    if _line_group(row) in separate_groups:
                        _remember_line_selection(bindings, row, candidates)
                        final_pending = final_pending or (
                            row.get("_next_line_is_last")
                            and bindings.get(source_row + 1, {}).get("combined_into") == source_row
                        )
                    if not final_pending:
                        location = f"Mở Add Order Details cho {_row_label(rows[po_index])}"
                        popup_frame = _ensure_po_popup_for_next_row(
                            context,
                            rows[: index + 1],
                            log,
                        )
            if step_by_step:
                location = "Xác nhận PO trong Order Details"
                order_frame = main_frame
                if order_frame is None:
                    _main_page, order_frame = _frame_with_selector(
                        context, SALE_ASN_STAGE_FRAME_SELECTORS["order_details"], timeout_s=15,
                    )
                _ensure_order_grid_rows(context, order_frame, _combined_order_rows(rows, bindings), log, search_fields)
                return _pause_after_stage("po", skipped)
            current_stage = "order_details"
            if draft is None:
                main_frame = None

        start_stage_index = SALE_ASN_STAGE_ORDER.index(current_stage)
        # Frame chỉ được resolve khi tới bước thật sự chạy. Nếu resolve trước
        # vòng lặp thì một bước đang bị bỏ qua vì tab của nó không hiện vẫn bắt
        # user chờ hết timeout của đúng tab đó — nút Bỏ qua thành vô dụng.
        for step in SALE_ASN_STAGE_ORDER[start_stage_index:]:
            current_stage = step
            location = ""
            # Đây là bước bắt buộc cuối luồng, không thuộc các checkbox "Các
            # bước app sẽ làm". Chạy trên form vừa điền để user thấy kết quả
            # trước Save, thay vì phải bấm thêm một nút Check giá.
            if step == "price_check":
                if draft is not None and not draft.get("bound"):
                    page, main_frame = _frame_with_selector(context, "#tabShipmentDetails", timeout_s=15)
                    _mark_draft(main_frame, draft)
                _emit_stage_progress(
                    progress,
                    step,
                    "Đang đối chiếu Shipment Details và Summary Total",
                )
                price_check = _check_sale_asn_price_on_page(page, rows, log, **line_options)
                _emit_stage_progress(
                    progress,
                    step,
                    price_check["message"],
                    state="completed",
                )
                continue
            if step in skipped:
                _write_log(
                    log,
                    f"[SALE ASN] Đã bỏ qua bước {SALE_ASN_STAGE_LABELS[step]} theo yêu cầu.",
                )
                _emit_stage_progress(
                    progress,
                    step,
                    f"Đã bỏ qua {SALE_ASN_STAGE_LABELS[step]}",
                    state="skipped",
                )
                continue
            if main_frame is None:
                page, main_frame = _frame_with_selector(
                    context,
                    SALE_ASN_STAGE_FRAME_SELECTORS[step],
                    timeout_s=15,
                )
            if draft is not None and not draft.get("bound"):
                _mark_draft(main_frame, draft)
            _emit_stage_progress(
                progress,
                step,
                f"Đang điền {SALE_ASN_STAGE_LABELS[step]}",
            )
            if step == "order_details":
                if add_po_selected:
                    main_frame = _ensure_order_grid_rows(
                        context,
                        main_frame,
                        _combined_order_rows(rows, bindings),
                        log,
                        search_fields,
                    )
                else:
                    present = _wait_order_grid(
                        main_frame,
                        rows,
                        timeout_s=3,
                        allow_incomplete=True,
                    )
                    missing = _missing_order_rows(rows, present)
                    if missing:
                        missing_pos = [
                            str(row.get("po_no") or "") for row in missing
                        ]
                        raise RuntimeError(
                            "SALE_ASN_ORDER_ROWS_NOT_FOUND:"
                            + ", ".join(missing_pos[:10])
                        )
                _fill_order_details(main_frame, rows, log, progress, **line_options)
            elif step == "style_details":
                _fill_style_details(main_frame, rows, log, progress)
            elif step == "shipping_info":
                shipping_warnings = _fill_shipping(main_frame, dict(rows[0]), log) or []
                if draft is not None:
                    draft["shipping_warnings"] = shipping_warnings
            if step_by_step:
                paused = _pause_after_stage(step, skipped)
                paused["warnings"] = shipping_warnings
                return paused
        warning_message = ""
        if shipping_warnings:
            warning_message = (
                f" Shipping Info đã bỏ qua {len(shipping_warnings)} trường: "
                f"{' · '.join(shipping_warnings)}."
            )
        return _result(
            True,
            "SALE_ASN_FORM_COMPLETED",
            (
                f"Đã hoàn tất Sale ASN và Check giá / Qty.{warning_message} "
                "Hãy kiểm tra lại trên WFX rồi tự bấm Save."
            ),
            completed=len(rows),
            total=len(rows),
            invoice_no=rows[0].get("invoice_no"),
            save_required=True,
            warnings=shipping_warnings,
            warning_count=len(shipping_warnings),
            add_po_selected=add_po_selected,
            price_check=price_check,
        )
    except _POSelectionRequired as pending:
        # Lượt Tiếp tục quay lại bước Thêm PO với start_index = hết danh sách:
        # vòng lặp PO bị bỏ qua, còn _ensure_order_grid_rows tự dò lại đúng các
        # PO còn thiếu nên không thêm trùng dòng đã vào grid.
        return _po_selection_result(
            pending.row,
            pending.candidates,
            pending.reason,
            final=pending.final,
            pending_index=len(rows),
            next_index=len(rows),
            completed=len(rows),
            total=len(rows),
        )
    except (Exception, AutomationCancelled) as error:
        if isinstance(error, _POAddUnconfirmed):
            current_stage = "po"
            location = _row_label(error.row)
            if draft is not None:
                draft["unconfirmed_po"] = error
        if isinstance(error, _CellFillError):
            location = error.location
            error = error.error
        label = SALE_ASN_STAGE_LABELS[current_stage]
        raw = _first_line(error)
        code = _domain_error_code(error, "SALE_ASN_CREATE_FAILED")
        if code == "SALE_ASN_CREATE_FAILED":
            if isinstance(error, PlaywrightTimeoutError):
                reason = "Quá thời gian chờ WFX phản hồi."
            elif isinstance(error, PlaywrightError):
                reason = "Không thao tác được trên trang WFX. Kiểm tra form đang mở rồi thử lại."
            else:
                reason = f"{type(error).__name__}: {raw}"
        else:
            reason = _failure_reason(code, raw.partition(":")[2].strip())
        if raw and raw not in reason:
            _write_log(log, f"[SALE ASN] {type(error).__name__}: {raw}")
        message = " · ".join(filter(None, (label, location))) + f": {reason}"
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            resumable=True,
            resume_stage=current_stage,
            resume_index=po_index,
            stage_label=label,
            can_skip=current_stage not in {"po", "price_check"} and code != "SALE_ASN_DRAFT_UNAVAILABLE",
        )
    finally:
        if playwright is not None:
            playwright.stop()
