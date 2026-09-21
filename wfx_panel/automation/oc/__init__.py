"""Automation Upload OC qua EDI Buyer PO và mở report Revise OC.

Trước đây là một file 1651 dòng. Nay tách theo tầng: ``constants``/``dom`` →
``package``/``transaction``/``confirm`` → ``flows``. Package re-export nguyên
bề mặt cũ nên caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import re  # noqa: F401
from pathlib import Path  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import _active_wfx_page  # noqa: F401
from wfx_panel.automation.oc.confirm import (  # noqa: F401
    _active_confirm_mode,
    _click_confirm_toolbar,
    _click_reject_toolbar,
    _confirm_all_pending,
    _confirm_frame,
    _focus_confirm_grid,
    _open_confirm_grid,
    _prepare_revision_style,
    _read_confirm_styles,
    _reject_all_pending,
    _select_confirm_style,
    _set_confirm_page_size,
    _wait_confirm_grid_ready,
    _wait_style_processed,
)
from wfx_panel.automation.oc.constants import (  # noqa: F401
    _ACTIVE_CONFIRM_TAB_JS,
    _CONFIRM_GROUPS_JS,
    _FAILED_RECORD_JS,
    _MARK_CONFIRM_STYLE_JS,
    _PREPARE_REVISION_STYLE_JS,
    _STATUS_JS,
    CONFIRM_FIRST_PASS_TIMEOUT_SECONDS,
    CONFIRM_GRID_SELECTOR,
    CONFIRM_PAGE_SIZE_SELECTOR,
    CONFIRM_PROCESS_TIMEOUT_SECONDS,
    CONFIRM_TAB_SELECTORS,
    EDI_MENU_SELECTOR,
    PACKAGE_LABEL,
    PACKAGE_VALUE,
    REVISION_REPORT_MENU_XPATH,
    REVISION_REPORT_SELECTOR,
    STATUS_TIMEOUT_SECONDS,
)
from wfx_panel.automation.oc.dom import (  # noqa: F401
    _attached_in_frames,
    _select_exact_option,
    _toolbar_link,
    _visible_in_frames,
)
from wfx_panel.automation.oc.flows import (  # noqa: F401
    confirm_oc_pending,
    open_oc_revision_report,
    reject_all_oc_pending,
    upload_oc_edi,
)
from wfx_panel.automation.oc.package import (  # noqa: F401
    _STATUS_LINK_SELECTORS,
    _STATUS_STAGE_LABELS,
    _failed_status,
    _format_resolution_error,
    _open_edi_form,
    _open_status_error_details,
    _process_package,
    _status_kind,
    _status_rows,
    _wait_statuses,
)
from wfx_panel.automation.oc.transaction import (  # noqa: F401
    _NO_RECORD_SELECTED_RE,
    _TRANSACTION_SUCCESS_RE,
    SUCCESS_BANNER_SELECTOR,
    _click_pending_transaction,
    _create_transaction,
    _CreateTransactionDialogs,
    _select_first_transaction,
    _success_banner_text,
    _transaction_checkboxes,
    _wait_transaction_confirmed,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint  # noqa: F401

__all__ = [
    "CONFIRM_FIRST_PASS_TIMEOUT_SECONDS",
    "CONFIRM_GRID_SELECTOR",
    "CONFIRM_PAGE_SIZE_SELECTOR",
    "CONFIRM_PROCESS_TIMEOUT_SECONDS",
    "CONFIRM_TAB_SELECTORS",
    "EDI_MENU_SELECTOR",
    "PACKAGE_LABEL",
    "PACKAGE_VALUE",
    "REVISION_REPORT_MENU_XPATH",
    "REVISION_REPORT_SELECTOR",
    "STATUS_TIMEOUT_SECONDS",
    "SUCCESS_BANNER_SELECTOR",
    "confirm_oc_pending",
    "open_oc_revision_report",
    "reject_all_oc_pending",
    "upload_oc_edi",
]
