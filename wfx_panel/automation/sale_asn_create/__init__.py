"""Tạo Sale ASN từ workbook 22 cột: PO → Order Details → Style → Shipping.

Trước đây là một file 2739 dòng. Nay tách theo tầng: constants/errors/
values/progress → form → buyers/po → order_details →
style_details/shipping/price_check → flow. Package re-export
nguyên bề mặt cũ nên caller và test không đổi.

Luồng luôn dừng trước Save để user kiểm tra trên WFX.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import re  # noqa: F401
import unicodedata  # noqa: F401
from collections.abc import Callable, Sequence  # noqa: F401
from datetime import datetime  # noqa: F401
from decimal import Decimal, InvalidOperation  # noqa: F401
from typing import Any  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _domain_error_code,
    _ensure_select_value,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (  # noqa: F401
    _active_wfx_page,
    _click_module_menu_on_page,
)
from wfx_panel.automation.sale_asn_create.buyers import (  # noqa: F401
    _BUYER_OPTIONS_JS,
    _buyer_cell,
    _buyer_options,
    _normalise_buyer_options,
    _select_buyer,
    scan_sale_asn_buyers,
)
from wfx_panel.automation.sale_asn_create.constants import (  # noqa: F401
    _WFX_MONTH_NUMBERS,
    _WFX_MONTHS,
    ADD_ORDER_XPATH,
    CONSIGNEE_ADDRESS_SELECTOR,
    ORDER_FIELD_COLUMNS,
    ORDER_GRID_SELECTOR,
    ORDER_GRID_SYNC_TIMEOUT_SECONDS,
    PO_CONTINUE_SELECTOR,
    PO_OK_SELECTOR,
    PO_OK_XPATH,
    PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    PO_POPUP_SELECTOR,
    PO_RESULTS_TABLE_SELECTOR,
    PO_RESULTS_TABLE_XPATH,
    PO_SEARCH_SELECTOR,
    PORT_OF_LOADING_SELECTOR,
    PORT_OF_LOADING_SELECTORS,
    SALE_ASN_PO_SEARCH_FIELDS,
    SALE_ASN_PO_SEARCH_LABELS,
    SALE_ASN_STAGE_FRAME_SELECTORS,
    SHIP_TO_SELECTOR,
    SHIPMENT_DETAILS_GRID_SELECTOR,
    SHIPMENT_DETAILS_TAB_SELECTOR,
    SHIPMENT_MODE_SELECTOR,
    SHIPPING_FIELD_LABELS,
    SHIPPING_FIELDS,
    SHIPPING_MODE_VALUES,
    STYLE_INPUT_SELECTORS,
    SUMMARY_TOTAL_GRID_SELECTOR,
)
from wfx_panel.automation.sale_asn_create.errors import (  # noqa: F401
    _is_transient_frame_error,
    _po_selection_result,
    _POFrameChanged,
    _POSelectionRequired,
    _shipping_warning,
)
from wfx_panel.automation.sale_asn_create.flow import (  # noqa: F401
    run_sale_asn_create,
)
from wfx_panel.automation.sale_asn_create.form import (  # noqa: F401
    _SET_CONTROL_JS,
    _frame_with_selector,
    _open_new_form,
    _refresh_existing_new_form,
    _set_control,
)
from wfx_panel.automation.sale_asn_create.order_details import (  # noqa: F401
    _MARK_ORDER_GRID_CELL_JS,
    _READ_ORDER_DETAILS_JS,
    _edit_marked_table_cell,
    _ensure_order_grid_rows,
    _ensure_po_popup_for_next_row,
    _fill_order_details,
    _missing_order_rows,
    _order_row_identity,
    _order_row_is_present,
    _order_style_matches,
    _set_order_grid_cell,
    _wait_order_grid,
    scan_sale_asn_order_details,
)
from wfx_panel.automation.sale_asn_create.po import (  # noqa: F401
    _PO_RESULTS_JS,
    _SELECT_PO_ROW_JS,
    _add_selected_po_candidates,
    _auto_add_po,
    _auto_add_po_with_frame_retry,
    _click_dom_action,
    _click_search,
    _fill_popup_input,
    _recover_submitted_po_results,
    _search_po,
    _select_popup_destination,
    _unique_dispatched_qty_subset,
)
from wfx_panel.automation.sale_asn_create.price_check import (  # noqa: F401
    _READ_ASN_SUMMARY_TOTAL_JS,
    _READ_SHIPMENT_DETAILS_JS,
    _check_sale_asn_price_on_page,
    _price_check_rows,
    _shipment_order_po,
    _summary_price_check,
)
from wfx_panel.automation.sale_asn_create.progress import (  # noqa: F401
    SALE_ASN_STAGE_LABELS,
    SALE_ASN_STAGE_ORDER,
    _emit_stage_progress,
)
from wfx_panel.automation.sale_asn_create.shipping import (  # noqa: F401
    _fill_shipping,
)
from wfx_panel.automation.sale_asn_create.style_details import (  # noqa: F401
    _MARK_STYLE_GOODS_DESCRIPTION_CELL_JS,
    _MARK_STYLE_HTS_CELL_JS,
    _fill_style_details,
    _set_style_cells,
    _set_style_goods_description_cell,
    _set_style_hts_cell,
)
from wfx_panel.automation.sale_asn_create.values import (  # noqa: F401
    _best_dropdown_label,
    _best_factory_label,
    _date_for_wfx,
    _decimal_display,
    _decimal_or_none,
    _fold,
    _number_for_wfx,
    _parse_supported_date,
    _style_similarity,
    _table_value_matches,
    _try_date,
    _wfx_text_value_key,
)

__all__ = [
    "ADD_ORDER_XPATH",
    "CONSIGNEE_ADDRESS_SELECTOR",
    "ORDER_FIELD_COLUMNS",
    "ORDER_GRID_SELECTOR",
    "ORDER_GRID_SYNC_TIMEOUT_SECONDS",
    "PORT_OF_LOADING_SELECTOR",
    "PORT_OF_LOADING_SELECTORS",
    "PO_CONTINUE_SELECTOR",
    "PO_OK_SELECTOR",
    "PO_OK_XPATH",
    "PO_POPUP_RECOVERY_TIMEOUT_SECONDS",
    "PO_POPUP_SELECTOR",
    "PO_RESULTS_TABLE_SELECTOR",
    "PO_RESULTS_TABLE_XPATH",
    "PO_SEARCH_SELECTOR",
    "SALE_ASN_PO_SEARCH_FIELDS",
    "SALE_ASN_PO_SEARCH_LABELS",
    "SALE_ASN_STAGE_FRAME_SELECTORS",
    "SALE_ASN_STAGE_LABELS",
    "SALE_ASN_STAGE_ORDER",
    "SHIPMENT_DETAILS_GRID_SELECTOR",
    "SHIPMENT_DETAILS_TAB_SELECTOR",
    "SHIPMENT_MODE_SELECTOR",
    "SHIPPING_FIELDS",
    "SHIPPING_FIELD_LABELS",
    "SHIPPING_MODE_VALUES",
    "SHIP_TO_SELECTOR",
    "STYLE_INPUT_SELECTORS",
    "SUMMARY_TOTAL_GRID_SELECTOR",
    "run_sale_asn_create",
    "scan_sale_asn_buyers",
    "scan_sale_asn_order_details",
]
