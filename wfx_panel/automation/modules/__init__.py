"""Mở màn hình WFX và tìm kiếm trên List của từng module.

Trước đây là một file 3448 dòng. Nay tách theo tầng: constants/text →
context/inputs → menu/grid → search → các module nghiệp vụ
(sample, rmpo, supplier_invoice, creation, company).
Package re-export nguyên bề mặt cũ nên caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import re  # noqa: F401
from collections.abc import Mapping  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from urllib.parse import urlsplit  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    _MODULE_GRID_STATE_JS,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _document_changed,
    _ensure_select_value,
    _first_line,
    _first_visible,
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _mark_document,
    _result,
    _scroll_horizontal_grid,
    _wait,
    _wait_frame_with_selectors,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (  # noqa: F401
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.catalog import (  # noqa: F401
    _catalog_tree_frame_now,
    _click_catalog_master,
    _open_catalog_menu_on_page,
    _show_catalog_floating_filter,
)
from wfx_panel.automation.modules.company import (  # noqa: F401
    _COMPANY_FOC_CHECKBOX_SELECTOR,
    _COMPANY_MISC_SELECTOR,
    _COMPANY_SAVE_SELECTOR,
    _company_save_response_handler,
    _toggle_company_foc_setting,
    _unsaved_company_foc_result,
    _wait_company_foc_saved,
    toggle_company_foc,
)
from wfx_panel.automation.modules.constants import (  # noqa: F401
    _MODULE_LOADING_SELECTOR,
    MODULE_CONTEXT_PROBE_SECONDS,
    MODULE_DIRECT_ROUTE_TIMEOUT_MS,
    MODULE_FILTER_VISIBLE_STABLE_SECONDS,
    MODULE_GRID_POLL_MS,
    MODULE_NEW_CONFIRM_SECONDS,
)
from wfx_panel.automation.modules.context import (  # noqa: F401
    _FRAME_MARKER_JS,
    _frame_context_marker,
    _frame_has_every_search_field,
    _frame_matches_module_context,
    _frame_serves_search_spec,
    _frame_with_visible_context,
    _wait_module_search_settled,
)
from wfx_panel.automation.modules.creation import (  # noqa: F401
    _wait_module_new_page,
    open_module_new,
    open_sale_asn_new,
    open_sample_new,
)
from wfx_panel.automation.modules.grid import (  # noqa: F401
    _click_floating_filter_if_due,
    _floating_filter_input_ready,
    _FloatingFilterState,
    _grid_root_is_new,
    _mark_grid_roots,
    _module_grid_settled,
    _show_module_floating_filter,
    open_module_with_floating_filter,
)
from wfx_panel.automation.modules.inputs import (  # noqa: F401
    _apply_module_search,
    _click_navigation_control,
    _module_search_is_loading,
    _search_input_across_horizontal_grid,
    _search_input_in_frame,
    _search_input_in_frames,
    _visible_locator_in_frames,
    _visible_search_input,
    _wait_module_search_stable,
)
from wfx_panel.automation.modules.menu import (  # noqa: F401
    _MENU_ROUTE_CACHE,
    _active_wfx_page,
    _click_module_menu_on_page,
    _context_pages,
    _mark_page_documents,
    _menu_target_markers,
    _MenuOpenResult,
    _open_menu_href_in_target_frame,
    _open_module_menu,
    _same_origin,
    _wait_for_module_navigation,
    open_module,
    reset_menu_route_cache,
)
from wfx_panel.automation.modules.rmpo import (  # noqa: F401
    _CLICK_RMPO_CELL_JS,
    _RMPO_ROWS_JS,
    _click_rmpo_cell,
    _find_rmpo_frame,
    _read_rmpo_rows,
    _rmpo_grid,
    _snapshot_browser_documents,
    _wait_rmpo_revision_button,
    _wait_rmpo_rows,
    open_rmpo_result_action,
    search_rmpo_list,
)
from wfx_panel.automation.modules.sample import (  # noqa: F401
    _CLICK_SAMPLE_STYLE_JS,
    _SAMPLE_RESULT_ROWS_JS,
    _apply_sample_filters,
    _click_sample_style_result,
    _sample_file_result,
    _sample_filter_values,
    _sample_result_grid,
    find_sample_file_results_with_filters,
    open_sample_file_result,
    search_sample_list_with_filters,
)
from wfx_panel.automation.modules.search import (  # noqa: F401
    _clear_list_search_fields,
    _clear_multi_search_fields,
    _fill_multi_search_fields,
    _open_list_search_context,
    _open_multi_field_search_context,
    _resolve_multi_search_fields,
    _search_module_fields,
    _search_module_list,
    _submit_multi_search,
    search_advance_pr_list,
    search_expense_invoice_list,
    search_indent_list,
    search_oc_list,
    search_sale_asn_list,
    search_supplier_invoice_list,
)
from wfx_panel.automation.modules.supplier_invoice import (  # noqa: F401
    _CLICK_SUPPLIER_INVOICE_ROW_JS,
    _SUPPLIER_INVOICE_ROWS_JS,
    _SUPPLIER_INVOICE_SCAN_JS,
    _find_supplier_invoice_frame,
    _select_supplier_invoice_row,
    _submit_supplier_invoice_cancel,
    _supplier_invoice_action_for_status,
    _supplier_invoice_grid,
    _supplier_invoice_rows,
    cancel_supplier_invoice_choice,
    prepare_supplier_invoice_cancel,
)
from wfx_panel.automation.modules.text import (  # noqa: F401
    _normalise_search_text,
)
from wfx_panel.automation.runtime import cancellation_deferred  # noqa: F401
from wfx_panel.automation.search_specs import (  # noqa: F401
    ADVANCE_PR_SEARCH_SPEC,
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
    OC_SEARCH_SPEC,
    RMPO_SEARCH_SPEC,
    SALE_ASN_SEARCH_SPEC,
    SAMPLE_SEARCH_SPEC,
    SUPPLIER_INVOICE_SEARCH_SPEC,
    ModuleSearchSpec,
)

__all__ = [
    "MODULE_CONTEXT_PROBE_SECONDS",
    "MODULE_DIRECT_ROUTE_TIMEOUT_MS",
    "MODULE_FILTER_VISIBLE_STABLE_SECONDS",
    "MODULE_GRID_POLL_MS",
    "MODULE_NEW_CONFIRM_SECONDS",
    "cancel_supplier_invoice_choice",
    "find_sample_file_results_with_filters",
    "open_module",
    "open_module_new",
    "open_module_with_floating_filter",
    "open_rmpo_result_action",
    "open_sale_asn_new",
    "open_sample_file_result",
    "open_sample_new",
    "prepare_supplier_invoice_cancel",
    "reset_menu_route_cache",
    "search_advance_pr_list",
    "search_expense_invoice_list",
    "search_indent_list",
    "search_oc_list",
    "search_rmpo_list",
    "search_sale_asn_list",
    "search_sample_list_with_filters",
    "search_supplier_invoice_list",
    "toggle_company_foc",
]
