"""Buyer List và Supplier List: mở, đổi Category và tìm công ty.

Trước đây là một file 980 dòng. Nay tách theo tầng: ``frames`` →
``supplier_open``/``company_query`` → ``supplier_search``/``buyer``. Package
re-export nguyên bề mặt cũ nên caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
from collections.abc import Mapping  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from dataclasses import field as dataclass_field  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    _COMPANY_ROWS_JS,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _document_changed,
    _first_line,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.directory.buyer import (  # noqa: F401
    _BuyerEditTarget,
    _BuyerSearchResultRequest,
    _first_buyer_edit_target,
    _open_and_confirm_buyer_edit,
    _open_first_matching_buyer,
    find_and_open_buyer,
)
from wfx_panel.automation.directory.company_query import (  # noqa: F401
    _company_result_state_key,
    _fill_company_query,
    _filter_company_rows,
    _wait_company_results,
)
from wfx_panel.automation.directory.frames import (  # noqa: F401
    _actionable_master,
    _buyer_search_frame,
    _company_frame_marker,
    _company_marker_matches,
    _company_search_frame,
    _select_supplier_category,
    _supplier_category_frame,
    _supplier_company_ready,
    _wait_supplier_left,
)
from wfx_panel.automation.directory.supplier_open import (  # noqa: F401
    _open_supplier_category_on_page,
    _open_supplier_master,
    _wait_supplier_company_ready,
    open_supplier_category,
)
from wfx_panel.automation.directory.supplier_search import (  # noqa: F401
    _restore_first_supplier_result,
    _scan_supplier_categories,
    _supplier_search_result,
    _SupplierSearchRequest,
    _SupplierSearchState,
    find_supplier_across_categories,
    find_supplier_in_category,
)
from wfx_panel.automation.modules import (  # noqa: F401
    MODULE_CONTEXT_PROBE_SECONDS,
    _active_wfx_page,
    _click_module_menu_on_page,
    _click_navigation_control,
)

__all__ = [
    "find_and_open_buyer",
    "find_supplier_across_categories",
    "find_supplier_in_category",
    "open_supplier_category",
]
