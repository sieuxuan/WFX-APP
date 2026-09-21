"""Kích thước cửa sổ, khoảng cách và nhịp poll của lớp vỏ desktop.

Tách khỏi ``panel_app`` để các controller trong ``wfx_panel/app`` dùng chung
mà không tạo vòng import ngược về orchestrator.
"""

from __future__ import annotations

from wfx_panel import prefs

TASKBAR_ACTIVATION_POLL_SECONDS = 0.25

PANEL_BLUR_GRACE_SECONDS = 0.35

BUBBLE_CONTEXT_POLL_SECONDS = 0.04

BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS = 0.75

WFX_MANUAL_URL = (
    "https://wfx.pro-sports.com.vn/wfx-digital-dictionary/system-manual"
)

BUBBLE_MENU_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "bubble_menu.html"

MANUAL_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "manual.html"

MANUAL_WINDOW_TITLE = "WFX Smart · Hướng dẫn sử dụng"

MANUAL_WINDOW_WIDTH = 1000

MANUAL_WINDOW_HEIGHT = 720

MANUAL_WINDOW_MIN = (720, 520)

WINDOW_WIDTH = 440

WINDOW_HEIGHT = 620

WINDOW_MARGIN = 24

# Khôi phục đúng kích thước launcher cũ; bubble chỉ tách thành cửa sổ riêng.
BUBBLE_SIZE = 48

BUBBLE_PANEL_GAP = 10

BUBBLE_MENU_WIDTH = 184

BUBBLE_MENU_HEIGHT = 82

BUBBLE_MENU_GAP = 8

STATUS_POLL_SECONDS = 5

SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS = 60

SESSION_MAINTENANCE_SECONDS = 4 * 60

UPDATE_INITIAL_DELAY_SECONDS = 1

UPDATE_POLL_SECONDS = 4 * 60 * 60

ARTICLE_LIBRARY_INITIAL_DELAY_SECONDS = 3

ARTICLE_LIBRARY_POLL_SECONDS = 60 * 60

ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"

MODULE_NOTIFICATION_METHODS = frozenset(
    {
        "open_module",
        "prepare_catalog",
        "browse_catalog",
        "catalog_action",
        "find_code",
        "find_buyer_reference",
        "open_catalog_destination",
        "download_catalog_file",
        "export_catalog_costing",
        "prepare_catalog_costing_import",
        "apply_catalog_costing",
        "open_sale_asn_new",
        "scan_sale_asn_buyers",
        "scan_sale_asn_order_details",
        "start_sale_asn_create",
        "continue_sale_asn_create",
        "skip_sale_asn_create_step",
        "open_sample_new",
        "search_oc",
        "open_oc_revision_report",
        "upload_oc",
        "confirm_oc_upload",
        "confirm_oc_pending",
        "reject_all_oc_pending",
        "run_gdn_dispatch",
        "open_gdn_status",
        "search_sample",
        "check_sample_files",
        "open_sample_file_choice",
        "search_sale_asn",
        "prepare_sale_asn_documents",
        "save_sale_asn_documents",
        "open_supplier_category",
        "find_supplier",
        "find_supplier_in_category",
        "find_buyer",
        "toggle_company_foc",
    }
)

NOTIFICATION_ACTION_LABELS = {
    "open_module": "Mở module",
    "prepare_catalog": "Catalog",
    "browse_catalog": "Catalog",
    "catalog_action": "Catalog",
    "find_code": "Tìm Article Code",
    "find_buyer_reference": "Tìm Buyer Reference",
    "open_catalog_destination": "Catalog",
    "download_catalog_file": "Tải file",
    "export_catalog_costing": "Tải Costing",
    "prepare_catalog_costing_import": "Kiểm tra file Costing",
    "apply_catalog_costing": "Áp dụng Costing",
    "open_sale_asn_new": "Sale ASN",
    "scan_sale_asn_buyers": "Quét Buyer Sale ASN",
    "scan_sale_asn_order_details": "Xuất PO đang mở",
    "start_sale_asn_create": "Tạo Sale ASN",
    "continue_sale_asn_create": "Tiếp tục Sale ASN",
    "skip_sale_asn_create_step": "Bỏ qua bước Sale ASN",
    "open_sample_new": "Sample",
    "search_oc": "Tìm OC",
    "open_oc_revision_report": "Mở report Revise OC",
    "upload_oc": "Upload OC",
    "confirm_oc_upload": "Upload OC",
    "confirm_oc_pending": "Confirm nhanh OC",
    "reject_all_oc_pending": "Reject All OC",
    "run_gdn_dispatch": "(GDN) Dispatch",
    "open_gdn_status": "Kiểm tra GDN",
    "test_notification": "Thông báo thử",
    "search_sample": "Tìm Sample",
    "check_sample_files": "Check File Sample",
    "open_sample_file_choice": "File Sample",
    "search_sale_asn": "Tìm Sale ASN",
    "prepare_sale_asn_documents": "Tải Documents Sale ASN",
    "save_sale_asn_documents": "Lưu Documents Sale ASN",
    "open_supplier_category": "Supplier",
    "find_supplier": "Tìm Supplier",
    "find_supplier_in_category": "Tìm Supplier",
    "find_buyer": "Tìm Buyer",
    "toggle_company_foc": "Company Setup · FOC",
}
