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
from wfx_panel.automation.sale_asn_create.buyers import _select_buyer
from wfx_panel.automation.sale_asn_create.constants import (
    ADD_ORDER_XPATH,
    PO_POPUP_SELECTOR,
    SALE_ASN_PO_SEARCH_FIELDS,
    SALE_ASN_STAGE_FRAME_SELECTORS,
)
from wfx_panel.automation.sale_asn_create.errors import (
    _po_selection_result,
    _POSelectionRequired,
)
from wfx_panel.automation.sale_asn_create.form import (
    _frame_with_selector,
    _open_new_form,
    _refresh_existing_new_form,
)
from wfx_panel.automation.sale_asn_create.order_details import (
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
) -> dict[str, Any]:
    playwright = None
    current_stage = str(stage or "po")
    add_po_selected = current_stage == "po"
    shipping_warnings: list[str] = []
    price_check: dict[str, Any] | None = None
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
        if current_stage == "po":
            _emit_stage_progress(
                progress,
                "po",
                "Đang mở Add Order Details",
            )
            if start_index <= 0 and not selected_po_candidates:
                main_frame = _refresh_existing_new_form(page, log)
                if main_frame is None:
                    main_frame = _open_new_form(page, xpath, log)
                _select_buyer(main_frame, buyer)
                add = main_frame.locator(f"xpath={ADD_ORDER_XPATH}").first
                _click_dom_action(add)
                _write_log(log, "[SALE ASN] Đã chọn Buyer và mở Add Order Details.")
            first_pending = max(0, int(start_index))
            if selected_po_candidates:
                selected_row = dict(selected_po_row or {})
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
                first_pending = min(len(rows), first_pending + 1)
                if first_pending < len(rows):
                    popup_frame = _ensure_po_popup_for_next_row(
                        context,
                        rows[:first_pending],
                        log,
                    )
            # Vòng lặp nằm hẳn trong guard: ngoài guard thì popup chưa được mở
            # nên không có tên nào để tham chiếu nhầm.
            if first_pending < len(rows):
                if not selected_po_candidates:
                    _popup_page, popup_frame = _frame_with_selector(
                        context,
                        PO_POPUP_SELECTOR,
                        timeout_s=15,
                    )
                for index in range(first_pending, len(rows)):
                    row = dict(rows[index])
                    _emit_stage_progress(
                        progress,
                        "po",
                        f"Thêm PO {index + 1}/{len(rows)}",
                    )
                    final_pending = index == len(rows) - 1
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
                    if not final_pending:
                        popup_frame = _ensure_po_popup_for_next_row(
                            context,
                            rows[: index + 1],
                            log,
                        )
            current_stage = "order_details"

        start_stage_index = SALE_ASN_STAGE_ORDER.index(current_stage)
        # Frame chỉ được resolve khi tới bước thật sự chạy. Nếu resolve trước
        # vòng lặp thì một bước đang bị bỏ qua vì tab của nó không hiện vẫn bắt
        # user chờ hết timeout của đúng tab đó — nút Bỏ qua thành vô dụng.
        main_frame = None
        for step in SALE_ASN_STAGE_ORDER[start_stage_index:]:
            current_stage = step
            # Đây là bước bắt buộc cuối luồng, không thuộc các checkbox "Các
            # bước app sẽ làm". Chạy trên form vừa điền để user thấy kết quả
            # trước Save, thay vì phải bấm thêm một nút Check giá.
            if step == "price_check":
                _emit_stage_progress(
                    progress,
                    step,
                    "Đang đối chiếu Shipment Details và Summary Total",
                )
                price_check = _check_sale_asn_price_on_page(page, rows, log)
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
                _main_page, main_frame = _frame_with_selector(
                    context,
                    SALE_ASN_STAGE_FRAME_SELECTORS[step],
                    timeout_s=15,
                )
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
                        rows,
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
                _fill_order_details(main_frame, rows, log, progress)
            elif step == "style_details":
                _fill_style_details(main_frame, rows, log, progress)
            elif step == "shipping_info":
                shipping_warnings.extend(
                    _fill_shipping(main_frame, dict(rows[0]), log) or ()
                )
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
    except RuntimeError as error:
        code = _domain_error_code(error, "SALE_ASN_CREATE_FAILED")
        message = f"Không hoàn tất Sale ASN: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage not in {"po", "price_check"},
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        message = f"Sale ASN chưa sẵn sàng: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            "SALE_ASN_CREATE_FAILED",
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage not in {"po", "price_check"},
        )
    except Exception as error:
        message = f"{type(error).__name__}: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            "SALE_ASN_CREATE_FAILED",
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage not in {"po", "price_check"},
        )
    finally:
        if playwright is not None:
            playwright.stop()
