"""Luồng nhập kho: Sourcing ASN → checkpoint người dùng → GRN Pending.

Giữa hai bước là checkpoint BẮT BUỘC: user tự nhập số lượng và Confirm
Sourcing ASN trên WFX. App không tự Confirm và chỉ mở GRN sau khi user xác
nhận Tiếp tục làm GRN."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.grn.constants import (
    _GRN_CONTEXT,
    _SOURCING_CONTEXT,
    GRN_PENDING_XPATH,
    SOURCING_ASN_NEW_XPATH,
)
from wfx_panel.automation.grn.controls import (
    _click_action,
    _read_control_options,
    _select_imported,
    _select_po_row,
    _set_exact,
    _wait_loading_finished,
)
from wfx_panel.automation.grn.frames import (
    _find_context_frame,
    _open_menu_form,
    _resolve_rmpo,
    _snapshot_context,
    _wait_new_context_frame,
)
from wfx_panel.automation.modules import _active_wfx_page


def _prepare_sourcing_asn(
    context: Any,
    page: Page,
    rmpo_no: str,
    supplier: str,
    log: Callable[[str], None],
) -> None:
    frame = _open_menu_form(
        context,
        page,
        SOURCING_ASN_NEW_XPATH,
        _SOURCING_CONTEXT,
        "Sourcing ASN New",
        log,
    )
    _set_exact(
        frame,
        "#CellID12 > div:nth-child(2), #CellID12",
        "RMPO",
        "Order Type = RMPO",
        log,
    )
    _set_exact(
        frame,
        (
            "#CellIDSupplier > div:nth-child(2) > span, "
            "#CellIDSupplier > div:nth-child(2), #CellIDSupplier"
        ),
        supplier,
        "Supplier",
        log,
    )
    page_ids, snapshots = _snapshot_context(context, "grn-sourcing-add")
    _click_action(
        frame,
        'xpath=//*[@id="sectionSupplierASNShipmentDetail"]/tbody/tr/td[2]/span/div[1]',
        "Add",
    )
    popup = _wait_new_context_frame(
        context,
        page_ids,
        snapshots,
        ("#sectionRMPOList",),
        timeout_s=40,
    )
    _select_po_row(popup, "#sectionRMPOList", rmpo_no)
    _click_action(
        popup,
        'xpath=//*[@id="sectionRMPOList"]/tbody/tr/td[2]/span/div[1]/a',
        "Add & Close",
    )
    _write_log(log, "[GRN] Đã Add RMPO vào Sourcing ASN.")


_SITE_SELECTOR = (
    "#CellID11 > div:nth-child(2) > span, #CellID11 > div:nth-child(2), #CellID11"
)
_SEARCH_SELECTOR = 'xpath=//*[@id="CellID13"]/div'


def _search_grn_pending(context: Any, frame: Frame) -> Frame:
    _click_action(frame, _SEARCH_SELECTOR, "Search")
    _wait_loading_finished(frame)
    # Search là postback: resolve lại document trước khi đọc Site/bảng PO.
    return _find_context_frame(context, _GRN_CONTEXT, timeout_s=20)


def _open_new_grn(
    context: Any,
    frame: Frame,
    rmpo_no: str,
    site: str,
    log: Callable[[str], None],
) -> None:
    """Chọn Site, Search lại theo Site rồi chọn đúng PO No. và click New.

    Search lại là bắt buộc: bảng PO của lượt Search trước chưa lọc theo Site,
    và đổi Site không tự làm WFX tải lại kết quả."""
    _set_exact(frame, _SITE_SELECTOR, site, "Site", log)
    frame = _search_grn_pending(context, frame)
    _write_log(log, "[GRN] Đã Search lại GRN Pending theo Site.")
    _select_po_row(frame, "#sectionOrderShipment", rmpo_no, timeout_s=20)
    _click_action(
        frame,
        'xpath=//*[@id="titlebarGRNPending"]/tbody/tr/td[2]/span/div[1]',
        "New",
    )
    _wait(frame, 300)
    _write_log(log, "[GRN] Đã chọn đúng PO No. và click New.")


def _prepare_grn_pending(
    context: Any,
    page: Page,
    supplier: str,
    mode: str,
    log: Callable[[str], None],
    *,
    rmpo_no: str = "",
    site: str = "",
) -> list[str]:
    """Mở GRN Pending, điền Receipt Type/From/Imported và Search.

    Có ``site`` (user đã chọn trong app) thì đi tiếp tới New và trả ``[]``;
    chưa có thì đọc danh sách Site để user chọn."""
    frame = _open_menu_form(
        context,
        page,
        GRN_PENDING_XPATH,
        _GRN_CONTEXT,
        "GRN Pending",
        log,
    )
    receipt_type = (
        "ASN from Supplier - Against ASN"
        if mode == "foreign"
        else "ASN from Supplier - Against PO"
    )
    _set_exact(
        frame,
        "#CellID1 > div:nth-child(2) > span, #CellID1 > div:nth-child(2), #CellID1",
        receipt_type,
        "Receipt Type",
        log,
    )
    # Receipt Type có thể làm WFX bind lại control From; resolve lại document.
    frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=20)
    _set_exact(
        frame,
        "#CellID12 > div:nth-child(2) > span, #CellID12 > div:nth-child(2), #CellID12",
        supplier,
        "From",
        log,
    )
    if mode == "foreign":
        _select_imported(frame, log)
    frame = _search_grn_pending(context, frame)
    if site and rmpo_no:
        _open_new_grn(context, frame, rmpo_no, site, log)
        return []
    sites = _read_control_options(frame, _SITE_SELECTOR)
    if not sites:
        raise PlaywrightTimeoutError("Không đọc được danh sách Site trên GRN.")
    _write_log(log, f"[GRN] Đã đọc {len(sites)} Site.")
    return sites


def _site_ready_result(
    message: str,
    sites: list[str],
    **data: Any,
) -> dict[str, Any]:
    if not sites:
        return _result(
            True,
            "GRN_NEW_READY",
            "Đã chọn RMPO và mở New GRN. Hãy tiếp tục kiểm tra trên WFX.",
            **data,
        )
    return _result(True, "GRN_SITE_SELECTION_REQUIRED", message, sites=sites, **data)


def prepare_grn_receipt(
    rmpo_xpath: str,
    rmpo_no: str,
    supplier: str,
    mode: str,
    log: Callable[[str], None] = print,
    *,
    site: str = "",
) -> dict[str, Any]:
    """Chuẩn bị Sourcing ASN, hoặc với hàng trong nước đi thẳng tới GRN.

    Trong nước đã có ``site`` thì mở luôn New GRN; chưa có thì dừng ở bước chọn
    Site. Nước ngoài luôn dừng ở checkpoint Sourcing ASN."""
    rmpo_no = " ".join(str(rmpo_no or "").split())
    supplier = " ".join(str(supplier or "").split())
    site = " ".join(str(site or "").split())
    mode = str(mode or "").strip().casefold()
    if not rmpo_no:
        return _result(False, "GRN_RMPO_REQUIRED", "Vui lòng nhập RMPO No.")
    if mode not in {"foreign", "domestic"}:
        return _result(False, "GRN_MODE_INVALID", "Loại nhập kho không hợp lệ.")
    if not supplier:
        rmpo_no, supplier, error = _resolve_rmpo(rmpo_xpath, rmpo_no, log)
        if error is not None:
            return error
    assert rmpo_no is not None and supplier is not None

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        if mode == "foreign":
            _prepare_sourcing_asn(context, page, rmpo_no, supplier, log)
            return _result(
                True,
                "GRN_SOURCING_ASN_READY",
                (
                    "Đã thêm RMPO vào Sourcing ASN. Hãy tự nhập đủ thông tin, "
                    "số lượng và Confirm trên WFX."
                ),
                rmpo_no=rmpo_no,
                supplier=supplier,
                mode=mode,
            )
        sites = _prepare_grn_pending(
            context, page, supplier, mode, log, rmpo_no=rmpo_no, site=site
        )
        return _site_ready_result(
            "Đã chuẩn bị GRN. Hãy chọn Site trong ứng dụng.",
            sites,
            rmpo_no=rmpo_no,
            supplier=supplier,
            mode=mode,
            site=site,
        )
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        message = f"Chưa chuẩn bị được nhập kho: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_PREPARE_FAILED", message, module="(GRN) Nhập kho")
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="(GRN) Nhập kho")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_PREPARE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()


def continue_grn_receipt(
    supplier: str,
    log: Callable[[str], None] = print,
    *,
    rmpo_no: str = "",
    site: str = "",
) -> dict[str, Any]:
    """Sau khi user Confirm Sourcing ASN, mở GRN Against ASN.

    Đã có ``site`` + ``rmpo_no`` thì mở luôn New GRN; chưa thì trả Site."""
    supplier = " ".join(str(supplier or "").split())
    rmpo_no = " ".join(str(rmpo_no or "").split())
    site = " ".join(str(site or "").split())
    if not supplier:
        return _result(False, "GRN_SESSION_EXPIRED", "Phiên nhập kho đã hết hiệu lực.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        sites = _prepare_grn_pending(
            browser.contexts[0],
            page,
            supplier,
            "foreign",
            log,
            rmpo_no=rmpo_no,
            site=site,
        )
        return _site_ready_result(
            "Đã chuẩn bị GRN từ Sourcing ASN. Hãy chọn Site trong ứng dụng.",
            sites,
            supplier=supplier,
            mode="foreign",
            rmpo_no=rmpo_no,
            site=site,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="(GRN) Nhập kho")
        if boundary is not None:
            return boundary
        message = f"Chưa tiếp tục được GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_CONTINUE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()


def finalize_grn_receipt(
    rmpo_no: str,
    site: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chọn Site, Search lại, chọn đúng PO No. và click New trên GRN Pending."""
    rmpo_no = " ".join(str(rmpo_no or "").split())
    site = " ".join(str(site or "").split())
    if not rmpo_no or not site:
        return _result(False, "GRN_SITE_REQUIRED", "Vui lòng chọn Site.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, _page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=12)
        _open_new_grn(context, frame, rmpo_no, site, log)
        return _result(
            True,
            "GRN_NEW_READY",
            "Đã chọn RMPO và mở New GRN. Hãy tiếp tục kiểm tra trên WFX.",
            rmpo_no=rmpo_no,
            site=site,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="(GRN) Nhập kho")
        if boundary is not None:
            return boundary
        message = f"Chưa mở được New GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_FINALIZE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()
