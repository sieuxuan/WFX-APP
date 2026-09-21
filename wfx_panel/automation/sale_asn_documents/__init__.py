"""Tải Buyer Invoice và Packing List của một Sale ASN từ màn Documents.

Trước đây là một file 942 dòng. Nay tách theo tầng: ``constants`` →
``grid``/``report`` → ``flow``. Package re-export nguyên bề mặt cũ nên caller
và test không đổi.

Sau khi bấm Docs, luôn tự đóng mọi popup do chính lượt này tạo — kể cả khi
download hoặc ghép gặp lỗi — nhưng giữ nguyên các Page đã có từ trước.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import base64  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401
from urllib.parse import urljoin  # noqa: F401

from openpyxl import load_workbook  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (  # noqa: F401
    MODULE_GRID_POLL_MS,
    _active_wfx_page,
    _apply_module_search,
    _clear_list_search_fields,
    _open_list_search_context,
    _search_input_in_frame,
)
from wfx_panel.automation.runtime import cancellation_deferred  # noqa: F401
from wfx_panel.automation.sale_asn_documents.constants import (  # noqa: F401
    _CLICK_SALE_ASN_DOCS_JS,
    _REPORT_FETCH_CHUNK_JS,
    _REPORT_FETCH_CLEANUP_JS,
    _REPORT_FETCH_START_JS,
    _REPORT_FETCH_STATE_JS,
    _SALE_ASN_ROWS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
    BUYER_INVOICE_SELECTOR,
    DOCUMENTS_FRAME_TIMEOUT_SECONDS,
    PACKING_LIST_SELECTOR,
    REPORT_DOWNLOAD_CHUNK_BYTES,
    REPORT_DOWNLOAD_MAX_ATTEMPTS,
    REPORT_DOWNLOAD_POLL_MS,
    REPORT_DOWNLOAD_PROGRESS_INTERVAL_SECONDS,
    REPORT_DOWNLOAD_RETRY_DELAY_MS,
    REPORT_DOWNLOAD_START_TIMEOUT_SECONDS,
    REPORT_EXPORT_SELECTOR,
    REPORT_READY_TIMEOUT_SECONDS,
)
from wfx_panel.automation.sale_asn_documents.flow import (  # noqa: F401
    prepare_sale_asn_documents,
)
from wfx_panel.automation.sale_asn_documents.grid import (  # noqa: F401
    _click_sale_asn_docs,
    _merge_sale_asn_row_payloads,
    _sale_asn_horizontal_positions,
    _sale_asn_result_grid,
    _scan_sale_asn_rows,
    _select_sale_asn_row,
)
from wfx_panel.automation.sale_asn_documents.report import (  # noqa: F401
    _close_sale_asn_document_popups,
    _documents_frame,
    _download_report_excel,
    _find_frame_with,
    _mark_report_frames,
    _report_export_url,
    _report_frame_is_new,
    _report_workbook_kind,
    _restore_documents_screen,
    _validate_report_kind,
    _wait_report_ready,
)
from wfx_panel.automation.search_specs import SALE_ASN_SEARCH_SPEC  # noqa: F401
from wfx_panel.workbooks.asn import (  # noqa: F401
    ASNWorkbookError,
    merge_sale_asn_reports,
    sale_asn_sheet_names,
)

__all__ = [
    "BUYER_INVOICE_SELECTOR",
    "DOCUMENTS_FRAME_TIMEOUT_SECONDS",
    "PACKING_LIST_SELECTOR",
    "REPORT_DOWNLOAD_CHUNK_BYTES",
    "REPORT_DOWNLOAD_MAX_ATTEMPTS",
    "REPORT_DOWNLOAD_POLL_MS",
    "REPORT_DOWNLOAD_PROGRESS_INTERVAL_SECONDS",
    "REPORT_DOWNLOAD_RETRY_DELAY_MS",
    "REPORT_DOWNLOAD_START_TIMEOUT_SECONDS",
    "REPORT_EXPORT_SELECTOR",
    "REPORT_READY_TIMEOUT_SECONDS",
    "prepare_sale_asn_documents",
]
