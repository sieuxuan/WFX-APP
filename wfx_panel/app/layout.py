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

BUBBLE_MENU_WIDTH = 120

BUBBLE_MENU_HEIGHT = 46

BUBBLE_MENU_GAP = 8

STATUS_POLL_SECONDS = 5

SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS = 60

SESSION_MAINTENANCE_SECONDS = 4 * 60

UPDATE_INITIAL_DELAY_SECONDS = 1

UPDATE_POLL_SECONDS = 4 * 60 * 60

ARTICLE_LIBRARY_INITIAL_DELAY_SECONDS = 3

ARTICLE_LIBRARY_POLL_SECONDS = 60 * 60

ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"

# Mọi flow qua ``_run()`` đều phải báo khi xong để người dùng quay lại kiểm
# tra; chỉ các lượt nền/không do người dùng chờ mới im lặng. Dùng danh sách
# loại trừ thay cho danh sách cho phép để flow mới thêm sau không bị sót toast.
SILENT_RESULT_METHODS = frozenset(
    {
        # Kiểm tra/duy trì phiên nền: heartbeat thành công im lặng tuyệt đối.
        "maintain_session",
        "check_session",
        # Tự mở Catalog khi vào module: không qua result sink.
        "auto_prepare_catalog",
        # Bấm ngay trên panel, badge Division đã đổi tại chỗ.
        "switch_division",
        # Bước dạo đầu của Export Costing; toast do lượt Export phát.
        "inspect_active_catalog_costing",
        # Chỉ xóa review cục bộ, không chạy automation.
        "cancel_oc_upload_review",
    }
)

NOTIFICATION_ACTION_LABELS = {
    "fill_expense_import": "Nhập Expense Invoice",
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
    "login": "Đăng nhập WFX",
    "open_chrome": "Mở trình duyệt",
    "open_module_new": "Mở màn New",
    "scan_catalog_folders": "Quét thư mục Catalog",
    "validate_catalog_costing_file": "Kiểm tra file Costing",
    "clear_catalog_costing_dependencies": "Clear All Dependency",
    "review_catalog_style_import": "Kiểm tra file Tạo Style",
    "scan_catalog_style_options": "Quét danh sách Tạo Style",
    "prepare_catalog_style_row": "Chuẩn bị Style",
    "publish_reference_data": "Publish Article và Style",
    "probe_catalog_data_source": "Dò nguồn dữ liệu Catalog",
    "extract_catalog_articles": "Lấy Article từ WFX",
    "review_oc_upload": "Review Upload OC",
    "save_oc_upload_file": "Lưu file Upload OC",
    "search_rmpo": "Tìm RMPO",
    "run_rmpo_action": "Thao tác RMPO",
    "prepare_grn_receipt": "Nhập kho GRN",
    "continue_grn_receipt": "Tiếp tục làm GRN",
    "finalize_grn_receipt": "Mở New GRN",
    "search_grn": "Tìm GRN",
    "search_indent": "Tìm Indent",
    "search_advance_pr": "Tìm Advance PR",
    "search_supplier_invoice": "Tìm Supplier Invoice",
    "search_expense_invoice": "Tìm Expense Invoice",
    "cancel_supplier_invoice": "Cancel Supplier Invoice",
    "cancel_supplier_invoice_choice": "Cancel Supplier Invoice",
    "load_report_parameters": "Tải tham số báo cáo",
    "export_report_excel": "Xuất Excel báo cáo",
    "load_color_report_options": "Tải tham số Color Combination",
    "run_color_report_batch": "Tải hàng loạt Color Combination",
}
