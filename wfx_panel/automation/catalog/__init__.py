"""State machine Catalog: menu → Category → Master → grid → filter → Article.

Trước đây là một file 2745 dòng. Nay tách theo tầng: navigation →
grid/folders/filters → article → files/downloads →
flows. Package re-export nguyên bề mặt cũ nên caller và test không đổi.

Không được coi "đã click", "đã tìm thấy frame" hay "đã thấy input" là thành
công nếu trạng thái thật trên UI chưa được xác nhận.
"""

from __future__ import annotations

# Bề mặt cũ của file gốc: các tên này từng ở module level nên caller và
# test vẫn đọc/gắn qua tên package. Giữ nguyên để tách file không đổi
# hợp đồng import.
import html  # noqa: F401
import re  # noqa: F401
import tempfile  # noqa: F401
from collections.abc import Mapping  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from pathlib import Path  # noqa: F401
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit  # noqa: F401

from wfx_panel.automation._common import (  # noqa: F401
    CATALOG_XPATH,
    COMPANY_ID,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _first_line,
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _result,
    _scroll_horizontal_grid,
    _sleep,
    _style_status_suffix,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (  # noqa: F401
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    _start_persistent_chrome,
    invalidate_browser,
)
from wfx_panel.automation.catalog.article import (  # noqa: F401
    _article_navigation_states,
    _article_page_for_code,
    _article_page_has_code,
    _open_article_destination,
    _refresh_article_context,
    open_catalog_destination,
)
from wfx_panel.automation.catalog.downloads import (  # noqa: F401
    _CONTENT_RANGE_RE,
    _DOWNLOAD_CHUNK_SIZE,
    _available_download_path,
    _download_attachment_in_chunks,
    _safe_attachment_name,
    download_catalog_file,
)
from wfx_panel.automation.catalog.files import (  # noqa: F401
    _ATTACHMENT_ROWS_JS,
    _ATTACHMENT_TABLE_SELECTOR,
    ARTICLE_FILE_TAB_INDEXES,
    _article_documents_changed,
    _article_file_tab,
    _article_tab_selected,
    _attachment_url,
    _ensure_article_techpack,
    _mark_article_documents,
    _scan_article_file_tabs,
    _visible_attachment_tables,
    scan_catalog_files,
)
from wfx_panel.automation.catalog.filters import (  # noqa: F401
    _CATALOG_FILTER_INPUT_SELECTORS,
    _CATALOG_FILTER_SPECS,
    _catalog_grid_result_ready,
    _catalog_grid_state_key,
    _catalog_result_from_rows,
    _catalog_styles_from_rows,
    _CatalogFilterSpec,
    _CatalogGridPoll,
    _click_catalog_style,
    _filter_grid_and_maybe_open,
    _refill_catalog_filter,
    _resolve_catalog_filter,
    _visible_catalog_filter,
    _wait_catalog_grid_rows,
)
from wfx_panel.automation.catalog.flows import (  # noqa: F401
    _find_in_open_catalog,
    filter_and_open_catalog_code,
    find_and_open_catalog_destination,
    find_in_open_catalog,
    open_catalog_folder,
    open_catalog_master,
    prepare_catalog_master,
    quick_find_catalog,
    scan_catalog_folders,
    set_catalog_category,
)
from wfx_panel.automation.catalog.folders import (  # noqa: F401
    _catalog_folder_for_node,
    _catalog_folder_nodes,
    _wait_catalog_folder_selected,
)
from wfx_panel.automation.catalog.grid import (  # noqa: F401
    _catalog_filter_row_active,
    _catalog_grid_frame,
    _catalog_grid_is_interactive,
    _reuse_prepared_catalog_master,
    _show_catalog_floating_filter,
    _wait_catalog_grid_data_ready,
)
from wfx_panel.automation.catalog.navigation import (  # noqa: F401
    _catalog_direct_url,
    _catalog_left_frame,
    _catalog_tree_frame_now,
    _click_catalog_master,
    _is_catalog_tree_frame,
    _navigate_catalog_body_direct,
    _open_catalog_menu_on_page,
    _open_catalog_tree_on_page,
    _select_catalog_category_on_page,
)
from wfx_panel.automation.runtime import (  # noqa: F401
    _user_downloads_dir,
    recycle_playwright,
)
from wfx_panel.automation.session import _session_is_active, login  # noqa: F401

__all__ = [
    "ARTICLE_FILE_TAB_INDEXES",
    "download_catalog_file",
    "filter_and_open_catalog_code",
    "find_and_open_catalog_destination",
    "find_in_open_catalog",
    "open_catalog_destination",
    "open_catalog_folder",
    "open_catalog_master",
    "prepare_catalog_master",
    "quick_find_catalog",
    "scan_catalog_files",
    "scan_catalog_folders",
    "set_catalog_category",
]
