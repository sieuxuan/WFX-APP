"""(GDN) Dispatch: từ Invoice GRN tới transaction trên EDI Production Order.

Trước đây là một file 993 dòng. Nay tách theo tầng: ``constants`` → ``status``
→ ``report``/``edi`` → ``flows``. Package re-export nguyên bề mặt cũ nên caller
và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import re  # noqa: F401
import tempfile  # noqa: F401
from datetime import datetime  # noqa: F401
from pathlib import Path  # noqa: F401

from openpyxl import load_workbook  # noqa: F401

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
from wfx_panel.automation.dispatch.constants import (  # noqa: F401
    _EDI_ROWS_JS,
    EDI_CREATE_SELECTOR,
    EDI_GRID_SELECTOR,
    EDI_MENU_XPATH,
    EDI_UPLOAD_SELECTOR,
    GDN_PROGRESS_TOTAL,
    PACKAGE_LABEL,
    PACKAGE_TIMEOUT_SECONDS,
    PACKAGE_TYPE_SELECTOR,
    PACKAGE_TYPE_VALUE,
    PACKAGE_VALUE,
    REPORT_DOC_NO_SELECTOR,
    REPORT_EXCEL_SELECTOR,
    REPORT_EXPORT_IMAGE_SELECTOR,
    REPORT_EXPORT_LINK_SELECTOR,
    REPORT_EXPORT_MENU_SELECTOR,
    REPORT_TIMEOUT_SECONDS,
    REPORT_URL,
    REPORT_VIEW_SELECTOR,
    TRANSACTION_TIMEOUT_SECONDS,
    _emit_progress,
)
from wfx_panel.automation.dispatch.edi import (  # noqa: F401
    _create_transaction_link,
    _edi_frame,
    _edi_rows,
    _open_edi,
    _open_import_popup,
    _process_package,
    _select_transaction,
    _visible_message,
    _wait_transaction_result,
)
from wfx_panel.automation.dispatch.flows import (  # noqa: F401
    open_gdn_status,
    run_gdn_dispatch,
)
from wfx_panel.automation.dispatch.report import (  # noqa: F401
    _download_report,
    _prepare_dispatch_workbook,
    _wait_report_ready,
    reload_dispatch_workbook,
)
from wfx_panel.automation.dispatch.status import (  # noqa: F401
    DispatchFlowError,
    _normalise_status,
    _processed_sort_key,
    _status_complete,
    _status_failed,
    choose_latest_pending_row,
)
from wfx_panel.automation.modules import _active_wfx_page  # noqa: F401
from wfx_panel.automation.oc import (  # noqa: F401
    _attached_in_frames,
    _select_exact_option,
    _toolbar_link,
)
from wfx_panel.automation.runtime import (  # noqa: F401
    cancellation_deferred,
    checkpoint,
    save_native_download,
    snapshot_downloads,
)

__all__ = [
    "DispatchFlowError",
    "EDI_CREATE_SELECTOR",
    "EDI_GRID_SELECTOR",
    "EDI_MENU_XPATH",
    "EDI_UPLOAD_SELECTOR",
    "GDN_PROGRESS_TOTAL",
    "PACKAGE_LABEL",
    "PACKAGE_TIMEOUT_SECONDS",
    "PACKAGE_TYPE_SELECTOR",
    "PACKAGE_TYPE_VALUE",
    "PACKAGE_VALUE",
    "REPORT_DOC_NO_SELECTOR",
    "REPORT_EXCEL_SELECTOR",
    "REPORT_EXPORT_IMAGE_SELECTOR",
    "REPORT_EXPORT_LINK_SELECTOR",
    "REPORT_EXPORT_MENU_SELECTOR",
    "REPORT_TIMEOUT_SECONDS",
    "REPORT_URL",
    "REPORT_VIEW_SELECTOR",
    "TRANSACTION_TIMEOUT_SECONDS",
    "choose_latest_pending_row",
    "open_gdn_status",
    "reload_dispatch_workbook",
    "run_gdn_dispatch",
]
