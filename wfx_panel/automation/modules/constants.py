"""Ngưỡng thời gian và selector loading dùng chung cho mọi module WFX."""

from __future__ import annotations

MODULE_GRID_POLL_MS = 150


MODULE_FILTER_VISIBLE_STABLE_SECONDS = 0.5


_MODULE_LOADING_SELECTOR = (
    ".ag-overlay-loading-wrapper, .ag-loading, .blockUI, .blockOverlay, "
    ".ui-widget-overlay, .loading, .loader, [aria-busy='true'], "
    "[id*='loading' i], [id*='progress' i], "
    "[class*='loading' i], [class*='progress' i]"
)


MODULE_CONTEXT_PROBE_SECONDS = 0.75


MODULE_DIRECT_ROUTE_TIMEOUT_MS = 12_000


MODULE_NEW_CONFIRM_SECONDS = 12.0
