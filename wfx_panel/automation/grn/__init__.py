"""(GRN) Nhập kho nguyên phụ liệu từ RMPO, và tra cứu GRN đã tạo.

Trước đây là một file 880 dòng. Nay tách theo tầng: ``constants``/
``frames`` → ``controls`` → ``receipt``/``search``. Package re-export
nguyên bề mặt cũ nên caller và test không đổi.

Status Received phải trả GRN_ALREADY_RECEIVED trước mọi luồng nhập kho.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
from collections.abc import Callable, Sequence  # noqa: F401
from typing import Any  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _document_changed,
    _first_line,
    _first_visible,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.grn.constants import (  # noqa: F401
    _CONTROL_OPTIONS_JS,
    _GRN_CONTEXT,
    _GRN_DATE_CHECKBOX,
    _GRN_SEARCH_CONTEXT,
    _GRN_SEARCH_FILTERS,
    _SELECT_PO_ROW_JS,
    _SOURCING_CONTEXT,
    GRN_PENDING_XPATH,
    GRN_SEARCH_XPATH,
    SOURCING_ASN_NEW_XPATH,
)
from wfx_panel.automation.grn.controls import (  # noqa: F401
    _click_action,
    _read_control_options,
    _select_imported,
    _select_po_row,
    _set_exact,
    _wait_loading_finished,
)
from wfx_panel.automation.grn.frames import (  # noqa: F401
    _context_frames,
    _find_context_frame,
    _fold,
    _frame_has_context,
    _open_menu_form,
    _resolve_rmpo,
    _snapshot_context,
    _wait_new_context_frame,
)
from wfx_panel.automation.grn.receipt import (  # noqa: F401
    _prepare_grn_pending,
    _prepare_sourcing_asn,
    continue_grn_receipt,
    finalize_grn_receipt,
    prepare_grn_receipt,
)
from wfx_panel.automation.grn.search import (  # noqa: F401
    _click_grn_search,
    _set_grn_search_filter,
    _wait_grn_result_opened,
    search_grn_receipt,
)
from wfx_panel.automation.modules import (  # noqa: F401
    _active_wfx_page,
    search_rmpo_list,
)
from wfx_panel.automation.sale_asn_create import _set_control  # noqa: F401

__all__ = [
    "GRN_PENDING_XPATH",
    "GRN_SEARCH_XPATH",
    "SOURCING_ASN_NEW_XPATH",
    "continue_grn_receipt",
    "finalize_grn_receipt",
    "prepare_grn_receipt",
    "search_grn_receipt",
]
