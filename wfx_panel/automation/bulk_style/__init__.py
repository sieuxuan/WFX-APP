"""Tạo Style hàng loạt cho Apparel từ workbook Excel.

Trước đây là một file 897 dòng. Nay tách theo tầng: ``constants`` →
``frames`` → ``editor`` → ``flows``. Package re-export nguyên bề mặt cũ
nên caller và test không đổi.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
from typing import Any  # noqa: F401
from urllib.parse import urljoin  # noqa: F401

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
from wfx_panel.automation.bulk_style.constants import (  # noqa: F401
    _CLICK_COPY_RESULT_JS,
    _COPY_RESULTS_JS,
    _HYDRATE_STYLE_OPTIONS_JS,
    _READ_STYLE_OPTIONS_JS,
    _SET_STYLE_FIELD_JS,
    COPY_ARTICLE_CODE_NAME_XPATH,
    COPY_AS_VARIANT_XPATH,
    COPY_COSTSHEET_XPATH,
    COPY_SEARCH_XPATH,
    FIXED_STYLE_FIELDS,
    NEW_STYLE_XPATH,
    SAVE_STYLE_XPATH,
    STYLE_FIELDS,
)
from wfx_panel.automation.bulk_style.editor import (  # noqa: F401
    _field_options_with_wait,
    _fill_style_editor,
    _read_style_options,
    _save_style,
    _set_field,
)
from wfx_panel.automation.bulk_style.flows import (  # noqa: F401
    _prepare_copy,
    prepare_catalog_style_row,
    scan_catalog_style_options,
)
from wfx_panel.automation.bulk_style.frames import (  # noqa: F401
    _article_left_frame,
    _close_pages_opened_since,
    _copy_result_frame,
    _frame_with_visible_locator,
    _new_style_link,
    _open_style_choice,
    _style_editor_frame,
)
from wfx_panel.automation.catalog import open_catalog_folder  # noqa: F401
from wfx_panel.automation.modules import _active_wfx_page  # noqa: F401
from wfx_panel.automation.runtime import cancellation_deferred  # noqa: F401

__all__ = [
    "COPY_ARTICLE_CODE_NAME_XPATH",
    "COPY_AS_VARIANT_XPATH",
    "COPY_COSTSHEET_XPATH",
    "COPY_SEARCH_XPATH",
    "FIXED_STYLE_FIELDS",
    "NEW_STYLE_XPATH",
    "SAVE_STYLE_XPATH",
    "STYLE_FIELDS",
    "prepare_catalog_style_row",
    "scan_catalog_style_options",
]
