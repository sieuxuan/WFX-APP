"""Điền điều kiện tìm kiếm cho List một ô và List nhiều ô."""

from __future__ import annotations

from collections.abc import Mapping

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _first_line,
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _result,
    _scroll_horizontal_grid,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.modules.constants import (
    MODULE_CONTEXT_PROBE_SECONDS,
    MODULE_GRID_POLL_MS,
)
from wfx_panel.automation.modules.context import (
    _frame_with_visible_context,
    _grid_reports_no_rows,
    _wait_module_search_settled,
)
from wfx_panel.automation.modules.grid import (
    _mark_grid_roots,
    _show_module_floating_filter,
)
from wfx_panel.automation.modules.inputs import (
    SearchValueNotConfirmed,
    _apply_module_search,
    _search_input_in_frame,
    _search_input_in_frames,
)
from wfx_panel.automation.modules.menu import (
    _active_wfx_page,
    _click_module_menu_on_page,
)
from wfx_panel.automation.search_specs import (
    ADVANCE_PR_SEARCH_SPEC,
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
    OC_SEARCH_SPEC,
    SALE_ASN_SEARCH_SPEC,
    SUPPLIER_INVOICE_SEARCH_SPEC,
    ModuleSearchSpec,
)


def _search_failure(
    search_spec: ModuleSearchSpec,
    stage: str,
    labels: str,
    exc: BaseException,
    log: Callable[[str], None],
    **data: Any,
) -> dict[str, Any]:
    """Câu lỗi cho người dùng theo bước hỏng; lỗi gốc chỉ nằm trong log.

    Footer hiện nguyên `message`, nên selector hay "Timeout 30000ms exceeded"
    không được lọt vào đó. Log kỹ thuật vẫn giữ lỗi gốc cho Báo lỗi một chạm.
    """
    module = search_spec.module_name
    if stage == "context":
        code = "MODULE_SEARCH_NOT_READY"
        message = (
            f"App đã tự mở {module} nhưng màn List chưa sẵn sàng để tìm. "
            "Chờ WFX tải xong rồi bấm Tìm lại."
        )
    elif stage == "field" and search_spec.requires_floating_filter:
        code = "MODULE_SEARCH_NOT_READY"
        message = (
            f"Không thấy ô lọc {labels} trên {module}. Nếu bạn đã ẩn cột "
            f"{labels} trên WFX, hãy hiện lại cột đó rồi tìm lại."
        )
    elif stage == "field":
        code = "MODULE_SEARCH_NOT_READY"
        message = (
            f"Không thấy ô {labels} trên {module}. "
            "Chờ WFX tải xong rồi bấm Tìm lại."
        )
    elif stage == "value":
        code = "MODULE_SEARCH_NOT_CONFIRMED"
        message = (
            f"WFX không nhận giá trị {labels} vừa nhập vào {module}. "
            "Bấm Tìm lại."
        )
    else:
        code = "MODULE_SEARCH_NOT_CONFIRMED"
        message = (
            f"Đã nhập {labels} nhưng {module} vẫn đang tải. "
            "Xem kết quả trên WFX hoặc bấm Tìm lại."
        )
    _write_log(
        log,
        f"[MODULE SEARCH] {module} dừng ở bước {stage}: "
        f"{type(exc).__name__}: {_first_line(exc)}",
    )
    _write_log(log, message)
    return _result(False, code, message, module=module, **data)


def _open_multi_field_search_context(
    page: Page,
    search_spec: ModuleSearchSpec,
    xpath: str,
    log: Callable[[str], None],
) -> Frame:
    context_selector = ", ".join(search_spec.context_field.selectors)
    try:
        return _frame_with_visible_context(
            page,
            context_selector,
            module_name=search_spec.module_name,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
            search_spec=search_spec,
        )
    except PlaywrightTimeoutError:
        _write_log(
            log,
            f"[MODULE SEARCH] {search_spec.module_name} chưa mở "
            "hoặc màn đang mở là module khác dùng chung selector; "
            "đang tự mở List...",
        )
        _click_module_menu_on_page(page, search_spec.module_name, xpath, log)
        return _frame_with_visible_context(
            page,
            context_selector,
            module_name=search_spec.module_name,
            timeout_s=30,
            search_spec=search_spec,
        )


def _resolve_multi_search_fields(
    frame: Frame,
    search_spec: ModuleSearchSpec,
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for field_name, field_spec in search_spec.fields.items():
        candidates = frame.locator(", ".join(field_spec.selectors))
        if (
            not candidates.count()
            or not candidates.first.is_visible()
            or not candidates.first.is_enabled()
        ):
            raise PlaywrightTimeoutError(
                f"Không tìm thấy ô {field_spec.label} trong đúng màn "
                f"{search_spec.module_name}."
            )
        resolved[field_name] = candidates.first
    return resolved


def _clear_multi_search_fields(fields: Mapping[str, Any]) -> None:
    for search_field in fields.values():
        # Ô đã trống thì không chạm: mỗi `change` trên form lọc ASP.NET có thể
        # bắn thêm một lượt lọc phía server trước khi điều kiện thật được gõ.
        try:
            if not search_field.input_value(timeout=1_000):
                continue
        except PlaywrightError:
            pass
        tag_name = str(
            search_field.evaluate("element => element.tagName") or ""
        ).upper()
        if tag_name == "SELECT":
            try:
                search_field.select_option(value="")
            except PlaywrightError:
                search_field.select_option(index=0)
        else:
            search_field.fill("")
        try:
            search_field.dispatch_event("change")
        except PlaywrightError:
            pass


def _fill_multi_search_fields(
    fields: Mapping[str, Any],
    cleaned_values: Mapping[str, str],
    active_fields: list[str],
    search_spec: ModuleSearchSpec,
    log: Callable[[str], None],
) -> tuple[list[str], Any | None]:
    active_labels: list[str] = []
    last_field: Any | None = None
    for field_name in active_fields:
        field_spec = search_spec.fields[field_name]
        search_field = fields[field_name]
        value = cleaned_values[field_name]
        tag_name = str(
            search_field.evaluate("element => element.tagName") or ""
        ).upper()
        if tag_name == "SELECT":
            try:
                search_field.select_option(value=value)
            except PlaywrightError:
                search_field.select_option(label=value)
            selected_text = str(
                search_field.evaluate(
                    "element => element.selectedOptions?.[0]?.textContent || ''"
                )
                or ""
            ).strip()
            value_confirmed = (
                search_field.input_value(timeout=1_000) == value
                or selected_text.casefold() == value.casefold()
            )
        else:
            search_field.type(value, delay=25)
            value_confirmed = (
                search_field.input_value(timeout=1_000) == value
            )
        if not value_confirmed:
            raise SearchValueNotConfirmed(
                f"WFX không xác nhận giá trị search {field_spec.label}."
            )
        active_labels.append(field_spec.label)
        last_field = search_field
        _write_log(log, f"[MODULE SEARCH] Đã nhập {field_spec.label}.")
    return active_labels, last_field


def _submit_multi_search(last_field: Any | None) -> None:
    if last_field is None:
        return
    try:
        last_field.press("Enter", timeout=2_000)
    except PlaywrightError:
        pass
    try:
        last_field.dispatch_event("change")
    except PlaywrightError:
        pass


def _search_module_fields(
    search_spec: ModuleSearchSpec,
    xpath: str,
    values: dict[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Xóa và điền một nhóm filter trong cùng frame để hỗ trợ lọc kết hợp."""
    cleaned = {
        key: str(values.get(key) or "").strip()
        for key in search_spec.fields
    }
    active = [key for key, value in cleaned.items() if value]
    if not active:
        labels = ", ".join(
            field_spec.label for field_spec in search_spec.fields.values()
        )
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập ít nhất một điều kiện: {labels}.",
        )

    playwright: Playwright | None = None
    stage = "browser"
    active_text = ", ".join(search_spec.fields[key].label for key in active)
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        stage = "context"
        frame = _open_multi_field_search_context(
            page,
            search_spec,
            xpath,
            log,
        )
        stage = "field"
        fields = _resolve_multi_search_fields(frame, search_spec)
        stage = "value"
        _clear_multi_search_fields(fields)
        active_labels, last_field = _fill_multi_search_fields(
            fields,
            cleaned,
            active,
            search_spec,
            log,
        )
        stage = "settle"
        _submit_multi_search(last_field)
        _wait_module_search_settled(page, active_labels)
        if _grid_reports_no_rows(page, frame):
            return _result(
                False,
                "MODULE_SEARCH_NO_RESULTS",
                f"Không có dòng nào trong {search_spec.module_name} khớp "
                f"{active_text}.",
                module=search_spec.module_name,
                filter_kinds=active,
            )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã lọc {search_spec.module_name} theo "
            f"{', '.join(active_labels)}.",
            module=search_spec.module_name,
            filter_kinds=active,
        )
    except RuntimeError as exc:
        boundary = _browser_boundary_result(exc, module=search_spec.module_name)
        if boundary is not None:
            return boundary
        message = (
            f"Không thể tìm trong {search_spec.module_name}: "
            f"RuntimeError: {_first_line(exc)}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
        )
    except PlaywrightTimeoutError as exc:
        labels = active_text
        if isinstance(exc, SearchValueNotConfirmed):
            stage = "value"
        elif stage == "field":
            # Lỗi resolve nêu đúng ô thiếu ("Không tìm thấy ô Style trong đúng
            # màn Indent List."), nên báo đúng ô đó thay vì cả nhóm điều kiện.
            labels = next(
                (
                    field_spec.label
                    for field_spec in search_spec.fields.values()
                    if f"ô {field_spec.label} " in str(exc)
                ),
                active_text,
            )
        elif stage not in {"value", "settle"}:
            stage = "context"
        return _search_failure(search_spec, stage, labels, exc, log)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = f"Không thể tìm trong {search_spec.module_name}: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _open_list_search_context(
    page: Page,
    search_spec: ModuleSearchSpec,
    xpath: str,
    log: Callable[[str], None],
) -> Frame:
    try:
        frame, _context_field = _search_input_in_frames(
            page,
            search_spec.context_field.selectors,
            search_spec.context_field.aliases,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
            scan_horizontal=search_spec.requires_floating_filter,
            module_name=search_spec.module_name,
        )
        return frame
    except PlaywrightTimeoutError:
        _write_log(
            log,
            f"[MODULE SEARCH] {search_spec.module_name} chưa sẵn sàng; "
            "đang tự mở List...",
        )
        previous_grids = (
            _mark_grid_roots(page)
            if search_spec.requires_floating_filter
            else None
        )
        _click_module_menu_on_page(page, search_spec.module_name, xpath, log)
        if search_spec.requires_floating_filter:
            _show_module_floating_filter(
                page,
                log,
                previous_grids,
                module_name=search_spec.module_name,
            )
        frame, _context_field = _search_input_in_frames(
            page,
            search_spec.context_field.selectors,
            search_spec.context_field.aliases,
            timeout_s=30,
            scan_horizontal=search_spec.requires_floating_filter,
            module_name=search_spec.module_name,
        )
        return frame


def _clear_list_search_fields(
    frame: Frame,
    selectors: tuple[str, ...],
    *,
    scan_horizontal: bool = False,
    keep_visible: tuple[str, ...] = (),
) -> int:
    """Xóa filter cũ để các lần Search không âm thầm kết hợp điều kiện.

    Trả số ô đã xóa. `keep_visible` là selector của ô sắp điền: nếu lượt quét
    ngang đi qua cột đó thì dừng grid ở đúng vị trí ấy, để bước tìm ô kế tiếp
    thấy ngay mà không phải quét lại cả bảng lần hai.
    """
    def clear_visible() -> int:
        cleared = 0
        # Một locator union trả node unique theo DOM order, tránh query lại
        # cùng input khi nhiều selector fallback cùng match nó.
        candidates = frame.locator(", ".join(selectors))
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if not candidate.is_visible() or not candidate.is_enabled():
                    continue
                if not candidate.input_value(timeout=500):
                    continue
                candidate.fill("")
                cleared += 1
                try:
                    candidate.dispatch_event("change")
                except PlaywrightError:
                    pass
            except PlaywrightError:
                continue
        return cleared

    def target_visible() -> bool:
        if not keep_visible:
            return False
        try:
            candidates = frame.locator(", ".join(keep_visible))
            return any(
                candidates.nth(index).is_visible()
                for index in range(candidates.count())
            )
        except PlaywrightError:
            return False

    cleared = clear_visible()
    if not scan_horizontal:
        return cleared
    roots = frame.locator(".ag-root-wrapper")
    for index in range(roots.count()):
        root = roots.nth(index)
        try:
            if not root.is_visible():
                continue
            state = _horizontal_grid_state(root)
            original = max(0, int(float(state.get("current") or 0)))
            target_position = original if target_visible() else None
            for position in _horizontal_grid_positions(state):
                # Vị trí hiện tại vừa được clear_visible() ở trên.
                if position == original:
                    continue
                _scroll_horizontal_grid(root, position)
                _wait(frame, MODULE_GRID_POLL_MS)
                cleared += clear_visible()
                if target_position is None and target_visible():
                    target_position = position
            _scroll_horizontal_grid(
                root,
                original if target_position is None else target_position,
            )
        except PlaywrightError:
            continue
    return cleared


def _search_module_list(
    search_spec: ModuleSearchSpec,
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    selected_field = search_spec.fields.get(filter_kind)
    if selected_field is None:
        return _result(
            False,
            "INVALID_FILTER",
            f"Kiểu tìm {search_spec.module_name} không hợp lệ.",
        )
    query = str(query or "").strip()
    if not query:
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập {selected_field.label} cần tìm.",
        )
    playwright: Playwright | None = None
    stage = "browser"
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        stage = "context"
        frame = _open_list_search_context(page, search_spec, xpath, log)
        stage = "field"
        cleared = _clear_list_search_fields(
            frame,
            search_spec.field_selectors,
            scan_horizontal=search_spec.requires_floating_filter,
            keep_visible=selected_field.selectors,
        )
        # Chỉ chờ grid vẽ lại khi thật sự vừa xóa filter cũ.
        if cleared:
            _wait(page, 250)
        field = _search_input_in_frame(
            page,
            frame,
            selected_field.selectors,
            selected_field.aliases,
            timeout_s=8,
            scan_horizontal=search_spec.requires_floating_filter,
        )
        stage = "settle"
        _apply_module_search(
            page,
            field,
            query,
            selected_field.label,
            log,
        )
        if _grid_reports_no_rows(page, frame):
            return _result(
                False,
                "MODULE_SEARCH_NO_RESULTS",
                f"Không có dòng nào trong {search_spec.module_name} khớp "
                f"{selected_field.label}: {query}.",
                module=search_spec.module_name,
                filter_kind=selected_field.label,
            )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã tìm {search_spec.module_name} theo "
            f"{selected_field.label}: {query}.",
            module=search_spec.module_name,
            filter_kind=selected_field.label,
        )
    except RuntimeError as exc:
        boundary = _browser_boundary_result(exc, module=search_spec.module_name)
        if boundary is not None:
            return boundary
        message = (
            f"Không thể tìm theo {selected_field.label} trong "
            f"{search_spec.module_name}: RuntimeError: {_first_line(exc)}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
        )
    except PlaywrightTimeoutError as exc:
        if isinstance(exc, SearchValueNotConfirmed):
            stage = "value"
        elif stage not in {"field", "settle"}:
            stage = "context"
        return _search_failure(
            search_spec,
            stage,
            selected_field.label,
            exc,
            log,
            filter_kind=selected_field.label,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = (
            f"Không thể tìm theo {selected_field.label} trong "
            f"{search_spec.module_name}: {detail}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def search_oc_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_list(
        OC_SEARCH_SPEC,
        xpath,
        filter_kind,
        query,
        log,
    )


def search_sale_asn_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_list(
        SALE_ASN_SEARCH_SPEC,
        xpath,
        filter_kind,
        query,
        log,
    )


def search_indent_list(
    xpath: str,
    module_name: str,
    supplier: str,
    article: str,
    indent_no: str,
    style: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    search_spec = INDENT_SEARCH_SPECS.get(module_name)
    if search_spec is None:
        return _result(
            False,
            "INVALID_FILTER",
            "Module Indent không hợp lệ.",
        )
    return _search_module_fields(
        search_spec,
        xpath,
        {
            "supplier": supplier,
            "article": article,
            "indent_no": indent_no,
            "style": style,
        },
        log,
    )


def search_advance_pr_list(
    xpath: str,
    buyer: str,
    supplier: str,
    invoice_no: str,
    order_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        ADVANCE_PR_SEARCH_SPEC,
        xpath,
        {
            "buyer": buyer,
            "supplier": supplier,
            "invoice_no": invoice_no,
            "order_no": order_no,
        },
        log,
    )


def search_supplier_invoice_list(
    xpath: str,
    supplier: str,
    invoice_no: str,
    po_no: str,
    asn_grn_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        SUPPLIER_INVOICE_SEARCH_SPEC,
        xpath,
        {
            "supplier": supplier,
            "invoice_no": invoice_no,
            "po_no": po_no,
            "asn_grn_no": asn_grn_no,
        },
        log,
    )


def search_expense_invoice_list(
    xpath: str,
    supplier: str,
    invoice_no: str,
    created_by: str,
    status: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        EXPENSE_INVOICE_SEARCH_SPEC,
        xpath,
        {
            "supplier": supplier,
            "invoice_no": invoice_no,
            "created_by": created_by,
            "status": status,
        },
        log,
    )
