"""Báo lỗi tối giản qua webhook, không để lộ endpoint trong giao diện.

Webhook mặc định nhận góp ý và báo lỗi nằm ở ``DEFAULT_WEBHOOK_URL``. Khi cần
chạy thử có thể ghi đè bằng ``WFX_ERROR_WEBHOOK_URL`` trong environment hoặc
file .env của app. Payload có thể chứa User ID/Company/Division để hỗ trợ,
nhưng tuyệt đối không chứa password, cookie, URL WFX, query hay ảnh chụp màn hình.
"""

from __future__ import annotations

import json
import os
import platform
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wfx_panel.atomic_io import write_json_atomic

DEFAULT_WEBHOOK_URL = "https://n8n.itx.io.vn/webhook/wfx-app"
ENV_NAME = "WFX_ERROR_WEBHOOK_URL"
MAX_OUTBOX = 100
SCHEMA_VERSION = 1
_LOCK = threading.Lock()
_FLUSH_LOCK = threading.Lock()

METHOD_LABELS = {
    "login": "Đăng nhập WFX",
    "check_session": "Kiểm tra phiên WFX",
    "open_chrome": "Mở trình duyệt làm việc",
    "open_module": "Mở module",
    "prepare_catalog": "Chuẩn bị Catalog",
    "browse_catalog": "Mở Catalog List",
    "catalog_action": "Tìm trong Catalog",
    "find_code": "Tìm Article Code",
    "find_buyer_reference": "Tìm Buyer Reference",
    "open_catalog_destination": "Mở Costing/BOM",
    "download_catalog_file": "Tải file Catalog",
    "inspect_active_catalog_costing": "Nhận tab Costing hiện tại",
    "export_catalog_costing": "Tải Costing",
    "validate_catalog_costing_file": "Kiểm tra file Costing",
    "prepare_catalog_costing_import": "Kiểm tra file Costing",
    "apply_catalog_costing": "Áp dụng Costing",
    "clear_catalog_costing_dependencies": "Clear All Dependency",
    "open_sale_asn_new": "Mở Sale ASN mới",
    "open_sample_new": "Mở Sample Order mới",
    "search_oc": "Tìm trong OC List",
    "open_oc_revision_report": "Mở report Revise OC",
    "upload_oc": "Upload OC qua EDI Buyer PO",
    "review_oc_upload": "Review file Upload OC",
    "confirm_oc_upload": "Xác nhận Upload OC qua EDI Buyer PO",
    "run_gdn_dispatch": "Tạo (GDN) Dispatch",
    "cancel_oc_upload_review": "Hủy bước xem lại Upload OC",
    "search_sample": "Tìm trong Sample List",
    "check_sample_files": "Check File trong Sample List",
    "open_sample_file_choice": "Mở Style đã chọn trong Sample List",
    "search_sale_asn": "Tìm trong Sale ASN List",
    "prepare_sale_asn_documents": "Tải Documents Sale ASN",
    "save_sale_asn_documents": "Lưu Documents Sale ASN",
    "search_rmpo": "Tìm trong RMPO List",
    "search_indent": "Tìm trong Indent List",
    "search_advance_pr": "Tìm trong Advance PR List",
    "search_supplier_invoice": "Tìm trong Supplier Inv List",
    "search_expense_invoice": "Tìm trong Expense Inv List",
    "cancel_supplier_invoice": "Cancel Supplier Invoice",
    "cancel_supplier_invoice_choice": "Cancel Supplier Invoice đã chọn",
    "open_module_new": "Mở màn New của module",
    "open_supplier_category": "Mở Supplier List",
    "find_supplier": "Tìm Supplier",
    "find_supplier_in_category": "Tìm Supplier theo Category",
    "find_buyer": "Tìm Buyer",
    "toggle_company_foc": "Đổi FOC trong Company Setup",
    "switch_division": "Đổi Division",
    "review_catalog_style_import": "Kiểm tra file Tạo Style",
    "prepare_catalog_style_row": "Chuẩn bị Style",
    "scan_catalog_style_options": "Quét dropdown Style",
}

ERROR_CODE_INFO = {
    "DIVISION_CHANGE_NOT_CONFIRMED": (
        "WFX chưa xác nhận đổi Division",
        "Kiểm tra menu Division trên WFX rồi thử lại.",
    ),
    "MODULE_FAILED": (
        "Không thể thao tác module WFX",
        "Mở Log kỹ thuật để xem bước và lỗi gốc cuối cùng.",
    ),
    "MODULE_SEARCH_NOT_READY": (
        "Ô tìm kiếm của module chưa sẵn sàng",
        "App đã thử tự mở List; hãy chờ WFX ổn định rồi thử tìm lại.",
    ),
    "MODULE_SEARCH_NOT_CONFIRMED": (
        "WFX chưa xác nhận kết quả tìm kiếm",
        "Chờ bảng tải xong rồi thử lại.",
    ),
    "MODULE_SEARCH_FAILED": (
        "Không thể thao tác ô tìm kiếm",
        "Mở Log kỹ thuật để xem lỗi gốc rồi thử lại.",
    ),
    "FLOATING_FILTER_NOT_READY": (
        "Chưa bật được ô lọc trên bảng",
        "Chờ WFX tải xong bảng rồi thử lại.",
    ),
    "PANEL_ERROR": (
        "Ứng dụng gặp lỗi khi chạy tác vụ",
        "Mở Log kỹ thuật để xem mã lượt chạy.",
    ),
}

ERROR_CODE_INFO.update(
    {
        "SUPPLIER_INVOICE_ACTION_NOT_READY": (
            "Nút Delete/Cancel chưa sẵn sàng",
            "Mở lại Supplier Inv List, tìm đúng invoice rồi thử lại.",
        ),
        "SUPPLIER_INVOICE_CANCEL_FAILED": (
            "Không thể Cancel Supplier Invoice",
            "Mở Log kỹ thuật, kiểm tra đúng invoice và quyền thao tác trên WFX.",
        ),
        "SUPPLIER_INVOICE_NOT_FOUND": (
            "Không tìm thấy Supplier Invoice",
            "Kiểm tra lại Invoice No. trước khi Cancel.",
        ),
        "SUPPLIER_INVOICE_NOT_READY": (
            "Supplier Inv List chưa sẵn sàng",
            "Chờ WFX tải xong rồi tìm lại Invoice No. cần Cancel.",
        ),
        "SUPPLIER_INVOICE_RESULT_EXPIRED": (
            "Kết quả Supplier Invoice đã thay đổi",
            "Tìm lại Invoice No. rồi chọn đúng một dòng để tiếp tục.",
        ),
        "SUPPLIER_INVOICE_STATUS_NOT_CANCELLABLE": (
            "Status Supplier Invoice không thể xử lý",
            "Chỉ tiếp tục khi Status là Save hoặc Confirm.",
        ),
        "BUYER_EDIT_NOT_CONFIRMED": (
            "WFX chưa xác nhận màn Edit Buyer",
            "Mở Buyer List, tìm lại Buyer rồi thử mở Edit.",
        ),
        "BUYER_EDIT_NOT_FOUND": (
            "Không tìm thấy nút Edit của Buyer",
            "Kiểm tra quyền chỉnh sửa Buyer và cấu trúc dòng kết quả.",
        ),
        "BUYER_SEARCH_FAILED": (
            "Không thể tìm Buyer",
            "Mở Log kỹ thuật và kiểm tra Buyer List đang hiển thị.",
        ),
        "BUYER_SEARCH_NOT_READY": (
            "Buyer List chưa sẵn sàng",
            "Chờ danh sách tải xong rồi thử tìm lại.",
        ),
        "CATALOG_DESTINATION_FAILED": (
            "Không thể mở Costing/BOM",
            "Mở lại style từ Catalog rồi thử lại.",
        ),
        "CATALOG_FILES_SCAN_FAILED": (
            "Không thể đọc file đính kèm Catalog",
            "Mở lại Article và kiểm tra tab file đính kèm.",
        ),
        "CATALOG_FILE_DOWNLOAD_FAILED": (
            "Không thể tải file Catalog",
            "Kiểm tra phiên WFX và quyền tải file rồi thử lại.",
        ),
        "CATALOG_FILE_SAVE_FAILED": (
            "Không thể lưu file Catalog",
            "Kiểm tra quyền ghi thư mục tải xuống và dung lượng ổ đĩa.",
        ),
        "CATALOG_FILE_TABS_NOT_FOUND": (
            "Không tìm thấy tab file của Article",
            "Mở lại Article rồi kiểm tra tab Images/Documents.",
        ),
        "CATALOG_FILE_URL_INVALID": (
            "WFX trả về liên kết file không hợp lệ",
            "Mở Log kỹ thuật và kiểm tra cấu hình file trên WFX.",
        ),
        "CATALOG_FOLDER_OPEN_FAILED": (
            "Không thể mở thư mục Catalog",
            "Quét lại cây folder rồi thử mở lại.",
        ),
        "CATALOG_FOLDER_OPEN_TIMEOUT": (
            "WFX phản hồi chậm khi mở thư mục Catalog",
            "Chờ Catalog tải xong rồi thử lại.",
        ),
        "CATALOG_FOLDER_SCAN_FAILED": (
            "Không thể quét cây thư mục Catalog",
            "Kiểm tra quyền Catalog của tài khoản rồi thử lại.",
        ),
        "CATALOG_FOLDER_SCAN_TIMEOUT": (
            "WFX phản hồi chậm khi tải cây Catalog",
            "Chờ cây Catalog hiển thị rồi quét lại.",
        ),
        "STYLE_COPY_CHOICE_INVALID": (
            "Lựa chọn Style nguồn không còn hợp lệ",
            "Tìm lại và chọn đúng một Style nguồn trong bảng điều khiển.",
        ),
        "STYLE_COPY_NOT_FOUND": (
            "Không tìm thấy Style nguồn",
            "Kiểm tra Article Code hoặc Buyer Reference trong cột Style copy.",
        ),
        "STYLE_COPY_RESULT_DETACHED": (
            "Kết quả Style nguồn đã thay đổi",
            "Tìm lại Style nguồn rồi chọn lại đúng dòng.",
        ),
        "STYLE_FIELD_NOT_AVAILABLE": (
            "Không điền được một trường Style",
            "Giữ form Article đang mở, xem Log kỹ thuật.",
        ),
        "STYLE_FILE_EMPTY": (
            "File Tạo Style chưa có dữ liệu",
            "Điền ít nhất một dòng trong sheet Tạo Style rồi chọn lại file.",
        ),
        "STYLE_FILE_HEADERS_INVALID": (
            "Header file Tạo Style không đúng",
            "Tải form mới và giữ nguyên tên, thứ tự các cột.",
        ),
        "STYLE_FILE_INVALID": (
            "File Tạo Style không hợp lệ",
            "Lưu lại bằng định dạng XLSX rồi chọn lại.",
        ),
        "STYLE_FILE_TOO_LARGE": (
            "File Tạo Style quá lớn",
            "Giảm số dòng hoặc dữ liệu thừa để file nhỏ hơn 15 MB.",
        ),
        "STYLE_FILE_TYPE_UNSUPPORTED": (
            "Định dạng file Tạo Style không được hỗ trợ",
            "Chỉ chọn file XLSX được tạo từ form của WFX Smart.",
        ),
        "STYLE_FILE_UNSAFE": (
            "File Tạo Style có nội dung không an toàn",
            "Xóa macro hoặc tải form XLSX mới rồi nhập lại dữ liệu.",
        ),
        "STYLE_FILE_VALIDATION_FAILED": (
            "Dữ liệu Tạo Style chưa hợp lệ",
            "Sửa các dòng được báo trong bảng điều khiển rồi chọn lại file.",
        ),
        "STYLE_FORM_NOT_READY": (
            "Form Article chưa sẵn sàng",
            "Chờ WFX tải xong Group và màn New/Copy rồi thử lại.",
        ),
        "STYLE_GROUP_REQUIRED": (
            "Chưa chọn Group Apparel",
            "Quét lại Group và chọn đúng một Group trước khi Import.",
        ),
        "STYLE_GROUP_STALE": (
            "Group Apparel đã thay đổi",
            "Quét lại danh sách Group, chọn lại rồi Import file lần nữa.",
        ),
        "STYLE_IMPORT_EXPIRED": (
            "Danh sách Tạo Style đã hết hạn",
            "Chọn lại file để tạo danh sách chuẩn bị mới.",
        ),
        "STYLE_PREPARE_FAILED": (
            "Không chuẩn bị được form Style",
            "Giữ màn hình WFX, xem Log kỹ thuật rồi thử lại dòng hiện tại.",
        ),
        "STYLE_PREPARE_UNSUPPORTED": (
            "Phiên bản chưa hỗ trợ Tạo Style",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "STYLE_REQUIRED_FIELD_MISSING": (
            "Style New còn thiếu trường bắt buộc",
            "Điền đủ các cột của dòng New rồi chọn lại file.",
        ),
        "STYLE_ROW_INVALID": (
            "Không tìm thấy dòng Tạo Style",
            "Chọn lại file để làm mới danh sách dòng.",
        ),
        "STYLE_OPTIONS_SCAN_FAILED": (
            "Chưa quét được dropdown Style",
            "Giữ Chrome đăng nhập, chọn Group có quyền tạo Style rồi thử lại.",
        ),
        "STYLE_OPTIONS_SCAN_UNSUPPORTED": (
            "Chưa hỗ trợ quét dropdown Style",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "STYLE_TEMPLATE_SHEET_MISSING": (
            "Thiếu sheet Tạo Style",
            "Tải form mới và nhập dữ liệu vào đúng sheet Tạo Style.",
        ),
        "COSTING_CONTEXT_NOT_FOUND": (
            "Không tìm thấy màn Costing",
            "Mở lại đúng style trong Catalog rồi thử lại.",
        ),
        "COSTING_ACTIVE_TAB_NOT_FOUND": (
            "Tab đang chọn chưa ở màn Costing",
            "Mở Style > Costing cần xuất và giữ đúng tab đó đang hiển thị.",
        ),
        "COSTING_ACTIVE_TAB_AMBIGUOUS": (
            "Có nhiều cửa sổ Costing cùng hiển thị",
            "Chỉ giữ cửa sổ cần xuất ở trạng thái đang chọn rồi thử lại.",
        ),
        "COSTING_STYLE_NOT_DETECTED": (
            "Chưa đọc được Style Code từ tab Costing",
            "Giữ phần thông tin Style trên tab Costing rồi thử export lại.",
        ),
        "COSTING_OPEN_NOT_LOADED": (
            "Costing Open chưa tải xong dữ liệu",
            "Chờ lưới Costing hiển thị đầy đủ rồi thử export/import lại.",
        ),
        "COSTING_SCAN_FAILED": (
            "Không thể đọc cấu trúc Costing",
            "Mở Log kỹ thuật và kiểm tra Costing của style vẫn đang hiển thị.",
        ),
        "COSTING_APPLY_FAILED": (
            "Không thể áp dụng Costing",
            "Xem trước lại file và kiểm tra field WFX trước khi Save.",
        ),
        "COSTING_FIELD_APPLY_FAILED": (
            "WFX không nhận một field Costing",
            "Xem field/Article được báo trong Log kỹ thuật rồi kiểm tra lại file.",
        ),
        "COSTING_NEW_DIALOG_NOT_FOUND": (
            "Không tìm thấy cửa sổ New Costing",
            "Mở lại Costing của style chưa có Cost Sheet rồi thử lại.",
        ),
        "COSTING_NEW_FAILED": (
            "Không thể tạo Costing mới",
            "Kiểm tra quyền tạo Internal Cost Sheet và template FOB.",
        ),
        "COSTING_SAVE_NOT_FOUND": (
            "Không tìm thấy nút Save Costing",
            "Mở lại Cost Sheet đang trạng thái Open rồi thử lại.",
        ),
        "COSTING_SAVE_ALERT": (
            "WFX từ chối Save Costing",
            "Điền field bắt buộc WFX báo thiếu rồi xem trước lại.",
        ),
        "COSTING_VERIFY_FAILED": (
            "WFX chưa xác nhận dữ liệu Costing sau Save",
            "Xem field báo sai trong Log rồi xem trước lại.",
        ),
        "CATALOG_NOT_OPEN": (
            "Catalog Master chưa sẵn sàng",
            "Bấm Mở Catalog và chờ bảng Master hiện ra.",
        ),
        "CATALOG_SEARCH_FAILED": (
            "Không thể tìm trong Catalog",
            "Mở lại Catalog Master rồi thử tìm lại.",
        ),
        "CATEGORY_FAILED": (
            "Không thể chọn Category",
            "Mở lại module và kiểm tra quyền Category của tài khoản.",
        ),
        "CHROME_OPEN_FAILED": (
            "Không thể mở trình duyệt làm việc",
            "Kiểm tra cài đặt Chrome/Edge và quyền chạy ứng dụng.",
        ),
        "CODE_FILTER_FAILED": (
            "Không dùng được ô lọc Code",
            "Mở lại Catalog Master rồi thử lại.",
        ),
        "CODE_FILTER_TIMEOUT": (
            "Ô lọc Code phản hồi quá chậm",
            "Chờ bảng Catalog tải xong rồi thử lại.",
        ),
        "COMPANY_FOC_FAILED": (
            "Không thể đổi cấu hình FOC",
            "Mở lại Company Setup và kiểm tra quyền chỉnh sửa.",
        ),
        "COMPANY_LIST_OPEN_FAILED": (
            "Không thể tự mở Company Setup",
            "Kiểm tra quyền Company Setup và trạng thái menu WFX rồi thử lại.",
        ),
        "COMPANY_FOC_NOT_READY": (
            "Màn cấu hình FOC chưa sẵn sàng",
            "Chờ Miscellaneous Settings tải xong rồi thử lại.",
        ),
        "COMPANY_FOC_SAVE_NOT_CONFIRMED": (
            "WFX chưa xác nhận lưu cấu hình FOC",
            "Kiểm tra trạng thái checkbox và bấm Save lại trên WFX.",
        ),
        "DIVISION_CHANGE_FAILED": (
            "Không thể đổi Division",
            "Kiểm tra menu Division và phiên đăng nhập rồi thử lại.",
        ),
        "DIVISION_DETECT_FAILED": (
            "Không thể nhận diện Division hiện tại",
            "Kiểm tra màn Home WFX và đăng nhập lại nếu cần.",
        ),
        "FILTER_RESULTS_NOT_READY": (
            "Kết quả lọc chưa ổn định",
            "Chờ bảng tải xong rồi tìm lại.",
        ),
        "FILTER_VALUE_NOT_CONFIRMED": (
            "WFX chưa nhận giá trị ô lọc",
            "Mở lại ô lọc rồi nhập lại.",
        ),
        "LOGIN_FAILED": (
            "Đăng nhập WFX thất bại",
            "Kiểm tra tài khoản, Company và trạng thái trang đăng nhập.",
        ),
        "COSTING_CLEAR_FAILED": (
            "Không thể Clear toàn bộ Dependency",
            "Giữ đúng CostSheet Open đang chọn, kiểm tra Log rồi thử lại.",
        ),
        "COSTING_CLEAR_DEPENDENCY_TARGET_CHANGED": (
            "Section Costing đã đổi khi đang Clear",
            "Chờ Costing tải ổn định rồi bấm Clear All Dependency lại.",
        ),
        "COSTING_CLEAR_UNSUPPORTED": (
            "Bản này chưa hỗ trợ Clear All Dependency",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "OC_EDI_FAILED": (
            "Không hoàn tất được Upload OC",
            "Kiểm tra màn EDI Buyer PO trước khi Create Transaction.",
        ),
        "OC_EDI_NOT_READY": (
            "EDI Buyer PO chưa sẵn sàng",
            "Chờ WFX tải xong, kiểm tra quyền EDI Buyer PO rồi thử upload lại.",
        ),
        "OC_REVISION_REPORT_FAILED": (
            "Không thể mở report Revise OC",
            "Mở Log kỹ thuật và kiểm tra quyền Reporting & Analytic của tài khoản.",
        ),
        "OC_REVISION_REPORT_NOT_READY": (
            "Report Upload OC from OC_Sale chưa sẵn sàng",
            "Chờ cây báo cáo tải xong rồi bấm Mở report lại.",
        ),
        "OC_UPLOAD_FILE_MISSING": (
            "File Upload OC tạm không còn tồn tại",
            "Chọn lại file OC. Nếu vẫn lỗi, xem Log kỹ thuật.",
        ),
        "LOGIN_TIMEOUT": (
            "WFX phản hồi quá chậm khi đăng nhập",
            "Kiểm tra mạng và thử đăng nhập lại.",
        ),
        "MASTER_FAILED": (
            "Không thể mở Master",
            "Mở lại Category rồi thử Master lần nữa.",
        ),
        "MASTER_NOT_FOUND": (
            "Không tìm thấy mục Master",
            "Kiểm tra quyền truy cập và cây menu của Category.",
        ),
        "MODULE_ACCESS_CHECK_FAILED": (
            "Không thể kiểm tra quyền module",
            "Đăng nhập lại và tải lại danh sách quyền.",
        ),
        "MODULE_NOT_FOUND": (
            "Không tìm thấy module trên menu WFX",
            "Kiểm tra quyền tài khoản và menu module.",
        ),
        "MODULE_OPEN_NOT_CONFIRMED": (
            "WFX chưa xác nhận mở module",
            "Kiểm tra trang có đang tải hoặc có hộp thoại chờ xác nhận rồi thử lại.",
        ),
        "QUICK_SEARCH_FAILED": (
            "Quick Search gặp lỗi",
            "Mở module thủ công và thử lại từng bước.",
        ),
        "QUICK_SEARCH_TIMEOUT": (
            "Quick Search phản hồi quá chậm",
            "Chờ WFX tải xong rồi thử lại.",
        ),
        "RESULT_DETACHED": (
            "Dòng kết quả đã thay đổi trước khi mở",
            "Tìm lại để lấy dòng kết quả mới.",
        ),
        "SALE_ASN_NEW_FAILED": (
            "Không thể tạo màn Sale ASN mới",
            "Mở lại Sale ASN và kiểm tra quyền tạo mới.",
        ),
        "SALE_ASN_NEW_NOT_READY": (
            "Màn Sale ASN mới chưa sẵn sàng",
            "Chờ form tải xong rồi thử lại.",
        ),
        "SALE_ASN_DOCUMENTS_UNSUPPORTED": (
            "Chưa hỗ trợ tải Documents Sale ASN",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "SALE_ASN_INVOICE_NOT_FOUND": (
            "Không tìm thấy Invoice No. trên Sale ASN List",
            "Kiểm tra Invoice No., xóa bộ lọc cũ trên WFX rồi thử lại.",
        ),
        "SALE_ASN_SELECTION_REQUIRED": (
            "Chưa xác định được dòng Sale ASN cần tải",
            "Nhập Invoice No. chính xác hoặc chọn đúng một dòng trên WFX.",
        ),
        "SALE_ASN_MULTIPLE_RESULTS": (
            "Có nhiều dòng Sale ASN phù hợp",
            "Chọn đúng một dòng trên WFX rồi bấm tải lại.",
        ),
        "SALE_ASN_DOCS_NOT_AVAILABLE": (
            "Không thấy nút Docs, hoặc chưa đủ quyền",
            "Kiểm tra đúng dòng Sale ASN và quyền Documents trên WFX.",
        ),
        "SALE_ASN_REPORT_NOT_READY": (
            "Report Sale ASN chưa sẵn sàng",
            "Chờ Documents/Report Viewer load xong rồi thử lại.",
        ),
        "SALE_ASN_REPORT_DOWNLOAD_FAILED": (
            "Không tải được report Sale ASN",
            "Kiểm tra Packing List, Buyer Invoice và quyền export Excel.",
        ),
        "SALE_ASN_REPORT_MERGE_FAILED": (
            "Không ghép được hai report Sale ASN",
            "Mở Log kỹ thuật để xem file report.",
        ),
        "SALE_ASN_DOCUMENTS_SAVE_FAILED": (
            "Không lưu được file Documents Sale ASN",
            "Chọn thư mục có quyền ghi, đóng file cũ nếu đang mở và thử lại.",
        ),
        "SALE_ASN_BUYER_SCAN_FAILED": (
            "Không quét được Buyer Sale ASN",
            "Mở lại Sale ASN New, chờ danh sách Buyer tải xong rồi quét lại.",
        ),
        "SALE_ASN_BUYER_REQUIRED": (
            "Chưa chọn Buyer Sale ASN",
            "Gõ và chọn đúng một Buyer trong danh sách trước khi chọn file.",
        ),
        "SALE_ASN_BUYER_NOT_FOUND": (
            "Buyer không còn trong danh sách WFX",
            "Quét lại Buyer rồi chọn đúng giá trị trước khi chạy.",
        ),
        "SALE_ASN_BUYER_NOT_CONFIRMED": (
            "WFX chưa xác nhận Buyer Sale ASN",
            "Kiểm tra danh sách Buyer trên form New rồi thử lại.",
        ),
        "SALE_ASN_CREATE_FAILED": (
            "Không thể hoàn tất Sale ASN từ Excel",
            "Giữ màn hình WFX, mở Log kỹ thuật và kiểm tra bước cuối cùng.",
        ),
        "SALE_ASN_CREATE_REVIEW_EXPIRED": (
            "Phiên kiểm tra Sale ASN đã hết hiệu lực",
            "Chọn lại file Excel để tạo một review mới.",
        ),
        "SALE_ASN_CREATE_STAGE_INVALID": (
            "Checkpoint tạo Sale ASN không hợp lệ",
            "Chọn lại file Excel để bắt đầu một phiên tạo Sale ASN mới.",
        ),
        "SALE_ASN_CREATE_STAGE_NOT_SKIPPABLE": (
            "Không thể bỏ qua bước Sale ASN hiện tại",
            "Hoàn tất bước thêm PO hoặc thử lại bước hiện tại trên WFX.",
        ),
        "SALE_ASN_CREATE_STEPS_REQUIRED": (
            "Chưa chọn bước Sale ASN cần thực hiện",
            "Tích ít nhất một bước trong Tùy chọn nâng cao.",
        ),
        "SALE_ASN_FIELD_NOT_EDITABLE": (
            "Một ô Sale ASN không thể chỉnh sửa",
            "Kiểm tra quyền sửa chứng từ và trạng thái form Sale ASN trên WFX.",
        ),
        "SALE_ASN_FILE_EMPTY": (
            "File Sale ASN chưa có dữ liệu",
            "Điền ít nhất một dòng PO trong form rồi chọn lại file.",
        ),
        "SALE_ASN_FILE_FORMULA_ERROR": (
            "File Sale ASN có công thức",
            "Dán dữ liệu thành giá trị trong vùng nhập rồi chọn lại file.",
        ),
        "SALE_ASN_FILE_HEADERS_INVALID": (
            "Header file Sale ASN không đúng",
            "Tải form mới và giữ nguyên đủ các tên cột chuẩn.",
        ),
        "SALE_ASN_FILE_INVALID": (
            "File Sale ASN không hợp lệ",
            "Lưu lại file bằng định dạng XLSX rồi chọn lại.",
        ),
        "SALE_ASN_FILE_NOT_FOUND": (
            "Không tìm thấy file Sale ASN",
            "Lưu và đóng file Excel rồi chọn lại từ vị trí hiện tại.",
        ),
        "SALE_ASN_FILE_TOO_LARGE": (
            "File Sale ASN quá lớn",
            "Xóa dữ liệu thừa để file nhỏ hơn 20 MB.",
        ),
        "SALE_ASN_FILE_TOO_MANY_ROWS": (
            "File Sale ASN có quá nhiều dòng",
            "Chia file thành các Invoice nhỏ hơn, tối đa 2.000 dòng mỗi file.",
        ),
        "SALE_ASN_FILE_TYPE_UNSUPPORTED": (
            "Định dạng file Sale ASN không được hỗ trợ",
            "Chỉ chọn file XLSX được tạo từ form Sale ASN.",
        ),
        "SALE_ASN_FILE_UNSAFE": (
            "File Sale ASN chứa macro",
            "Xóa macro hoặc tải form XLSX mới rồi nhập lại dữ liệu.",
        ),
        "SALE_ASN_FILE_VALIDATION_FAILED": (
            "Dữ liệu Sale ASN chưa hợp lệ",
            "Sửa các ô và dòng được ứng dụng báo rồi chọn lại file.",
        ),
        "SALE_ASN_PO_SEARCH_NOT_READY": (
            "Ô tìm PO Sale ASN chưa sẵn sàng",
            "Chờ cửa sổ Add Order Details tải xong rồi chạy lại.",
        ),
        "SALE_ASN_PO_POPUP_NOT_CLOSED": (
            "Cửa sổ chọn PO chưa đóng",
            "Bấm OK trong Add Order Details rồi chạy lại từ form New.",
        ),
        "SALE_ASN_PO_SELECTION_NOT_CONFIRMED": (
            "WFX chưa xác nhận dòng PO đã chọn",
            "Chọn đúng dòng PO trên WFX rồi bấm Add & Continue.",
        ),
        "SALE_ASN_ORDER_GRID_NOT_READY": (
            "Bảng Order Details chưa nhận đủ PO",
            "Chờ WFX tải đủ các dòng PO rồi chạy lại.",
        ),
        "SALE_ASN_ORDER_GRID_EMPTY": (
            "Order Details đang mở chưa có PO",
            "Mở đúng Sale ASN đã thêm PO, vào Order Details rồi xuất form lại.",
        ),
        "SALE_ASN_ORDER_SCAN_FAILED": (
            "Không đọc được Order Details đang mở",
            "Mở đúng tab Order Details của Sale ASN cần xử lý rồi thử xuất lại.",
        ),
        "SALE_ASN_ORDER_FILE_HEADERS_INVALID": (
            "Header form Order Details không đúng",
            "Xuất form mới từ WFX và giữ nguyên đủ tám tên cột.",
        ),
        "SALE_ASN_ORDER_FILE_EMPTY": (
            "Form Order Details chưa có dữ liệu",
            "Giữ PO No. và điền ít nhất một ô cần cập nhật rồi chọn lại file.",
        ),
        "SALE_ASN_ORDER_FILE_VALIDATION_FAILED": (
            "Dữ liệu Order Details chưa hợp lệ",
            "Sửa các dòng được ứng dụng báo rồi chọn lại file.",
        ),
        "SALE_ASN_ORDER_ROWS_NOT_FOUND": (
            "PO trong file không có trên Sale ASN đang mở",
            "Mở đúng chứng từ có đủ PO trong file rồi bấm Thử lại Order Details.",
        ),
        "SALE_ASN_ORDER_REVIEW_EXPIRED": (
            "Phiên kiểm tra Order Details đã hết hiệu lực",
            "Chọn lại file Order Details để tạo một phiên kiểm tra mới.",
        ),
        "SALE_ASN_ORDER_FILL_FAILED": (
            "Không điền xong Order Details",
            "Giữ đúng Sale ASN đang mở, kiểm tra tab Order Details rồi thử lại.",
        ),
        "SALE_ASN_ORDER_TEMPLATE_EXPORT_FAILED": (
            "Không tạo được form Order Details",
            "Chọn thư mục có quyền ghi, đóng file cũ nếu đang mở và thử lại.",
        ),
        "SALE_ASN_FIELD_VALUE_NOT_CONFIRMED": (
            "WFX chưa giữ giá trị vừa nhập",
            "Kiểm tra ô Order Details hoặc HS Code được báo trong Log kỹ thuật.",
        ),
        "SALE_ASN_SHIPPING_FIELD_FAILED": (
            "Không điền được Shipping Info",
            "Kiểm tra Destination, FTY và danh sách lựa chọn trên WFX.",
        ),
        "SALE_ASN_STYLE_HS_CODE_CONFLICT": (
            "Một Style có nhiều HS Code trong file",
            "Dùng cùng một HS Code cho các dòng của cùng Style.",
        ),
        "SALE_ASN_TABLE_MAPPING_FAILED": (
            "Không ghép được dòng file với bảng Sale ASN",
            "Kiểm tra PO No. và Style No., sau đó mở Log kỹ thuật.",
        ),
        "SALE_ASN_TEMPLATE_EXPORT_FAILED": (
            "Không tạo được form Sale ASN",
            "Chọn thư mục có quyền ghi và thử tải form lại.",
        ),
        "SALE_ASN_PRICE_CHECK_FAILED": (
            "Không check được giá Sale ASN",
            "Mở đúng Sale ASN, chờ Shipment Details và Summary Total tải xong rồi thử lại.",
        ),
        "SALE_ASN_PRICE_EXPORT_FAILED": (
            "Không xuất được kết quả Check giá Sale ASN",
            "Chọn thư mục có quyền ghi rồi bấm Xuất kết quả check lại.",
        ),
        "SALE_ASN_PRICE_FILE_EMPTY": (
            "File Sale ASN không còn dữ liệu để Check giá",
            "Chọn lại file Sale ASN trước khi chạy Check giá.",
        ),
        "SALE_ASN_SHIPMENT_DETAILS_EMPTY": (
            "Shipment Details chưa có dữ liệu",
            "Mở đúng Sale ASN có Shipment Details rồi thử Check giá lại.",
        ),
        "SALE_ASN_SUMMARY_TOTAL_EMPTY": (
            "Summary Total chưa có dữ liệu",
            "Chờ Summary Total tải xong rồi thử Check giá lại.",
        ),
        "SAMPLE_NEW_FAILED": (
            "Không thể tạo màn Sample Order mới",
            "Mở lại Sample List và kiểm tra quyền tạo mới.",
        ),
        "SAMPLE_NEW_NOT_READY": (
            "Màn Sample Order mới chưa sẵn sàng",
            "Chờ form tải xong rồi thử lại.",
        ),
        "SAMPLE_FILES_UNSUPPORTED": (
            "Bản này chưa hỗ trợ kiểm tra file Sample",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "SAMPLE_FILE_SEARCH_FAILED": (
            "Không thể đọc kết quả Sample để kiểm tra file",
            "Mở lại Sample List, chờ bảng tải xong rồi thử lại.",
        ),
        "SAMPLE_FILE_OPEN_FAILED": (
            "Không thể mở Style từ kết quả Sample",
            "Tìm lại Sample và kiểm tra Style Code trên WFX.",
        ),
        "SESSION_CHECK_FAILED": (
            "Không thể kiểm tra phiên WFX",
            "Kiểm tra trình duyệt làm việc và đăng nhập lại.",
        ),
        "SUPPLIER_MASTER_NOT_READY": (
            "Supplier Master chưa sẵn sàng",
            "Chờ Supplier List và Category tải xong rồi thử lại.",
        ),
        "SUPPLIER_OPEN_FAILED": (
            "Không thể mở Supplier List",
            "Kiểm tra quyền Supplier và menu WFX.",
        ),
        "SUPPLIER_SEARCH_FAILED": (
            "Không thể tìm Supplier",
            "Mở Log kỹ thuật và kiểm tra Category đang thao tác.",
        ),
        "SUPPLIER_SEARCH_NOT_READY": (
            "Ô tìm Supplier chưa sẵn sàng",
            "Chờ Supplier Master tải xong rồi thử lại.",
        ),
        "SUPPLIER_SEARCH_PARTIAL": (
            "Chưa kiểm tra được toàn bộ Category Supplier",
            "Thử lại để kiểm tra các Category bị lỗi hoặc mở từng Category riêng.",
        ),
    }
)

_URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(
        password|passwd|pwd|cookie|session[_\s-]?id|login[_\s-]?id|
        query|article[_\s-]?code|buyer[_\s-]?reference|style[_\s-]?code
    )\b
    \s*[:=]\s*
    ("[^"]*"|'[^']*'|[^\s,;]+)
    """
)
_EXACT_CODE_PATTERN = re.compile(
    r"(?i)\bcode\s+(?:chính\s+xác|cần\s+tìm)\s*:\s*[^\s,;]+"
)


ERROR_CODE_INFO.update(
    {
        "GDN_DISPATCH_FAILED": (
            "Không thể hoàn tất (GDN) Dispatch",
            "Mở Log kỹ thuật, kiểm tra report và EDI Production Order rồi thử lại.",
        ),
        "GDN_DISPATCH_UNSUPPORTED": (
            "Phiên bản chưa hỗ trợ (GDN) Dispatch",
            "Cập nhật WFX Smart lên bản mới nhất rồi thử lại.",
        ),
        "GDN_GRN_WAIT_CONFIRMATION_REQUIRED": (
            "Chưa xác nhận thời gian chờ sau GRN",
            "Chờ đủ 15 phút, đánh dấu xác nhận rồi Submit lại.",
        ),
        "GDN_INVOICE_INVALID": (
            "Invoice GRN không hợp lệ",
            "Kiểm tra lại nội dung Invoice GRN rồi Submit lại.",
        ),
        "GDN_INVOICE_REQUIRED": (
            "Chưa nhập Invoice GRN",
            "Nhập đúng Invoice GRN trước khi Submit.",
        ),
        "GDN_EDI_NOT_READY": (
            "EDI Production Order chưa sẵn sàng",
            "Chờ WFX tải xong và kiểm tra quyền EDI Production Order.",
        ),
        "GDN_PACKAGE_PROCESS_FAILED": (
            "WFX từ chối Process Package GDN",
            "Xem lỗi trên WFX. Invoice có thể đã import trước đó.",
        ),
        "GDN_PENDING_NOT_FOUND": (
            "Không tìm thấy package GDN Pending mới",
            "Kiểm tra Processed ON và Transaction Detail trên EDI Production Order.",
        ),
        "GDN_REPORT_DOWNLOAD_FAILED": (
            "Không tải được report Buyer Dispatch",
            "Kiểm tra phiên WFX, quyền report và thử lại sau khi WFX ổn định.",
        ),
        "GDN_REPORT_EMPTY": (
            "Report Buyer Dispatch không có dữ liệu",
            "Kiểm tra Invoice GRN và bảo đảm đã chờ đủ thời gian đồng bộ.",
        ),
        "GDN_REPORT_NOT_READY": (
            "Report Buyer Dispatch chưa sẵn sàng",
            "Chờ report load xong rồi Submit lại.",
        ),
        "GDN_TRANSACTION_FAILED": (
            "WFX báo lỗi khi tạo GDN Dispatch",
            "Xem lỗi WFX và Log kỹ thuật trước khi xử lý lại invoice.",
        ),
        "GDN_TRANSACTION_UNCONFIRMED": (
            "Chưa xác nhận được kết quả GDN Dispatch",
            "Đừng chạy lại. Kiểm tra transaction mới nhất trên WFX.",
        ),
        "GDN_WORKBOOK_RELOAD_FAILED": (
            "Không reload được file XLSX GDN",
            "Kiểm tra file report tải về và dung lượng thư mục tạm.",
        ),
    }
)


def redact_telemetry_text(value: object) -> str:
    """Loại URL, secret và query nghiệp vụ khỏi mô tả gửi ra ngoài."""
    text = str(value or "").strip()
    text = _URL_PATTERN.sub("[URL đã ẩn]", text)
    text = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=[đã ẩn]",
        text,
    )
    return _EXACT_CODE_PATTERN.sub("Code [đã ẩn]", text)


_METHOD_MODULES = {
    "search_oc": "OC List",
    "open_oc_revision_report": "OC List",
    "upload_oc": "OC List",
    "review_oc_upload": "OC List",
    "confirm_oc_upload": "OC List",
    "cancel_oc_upload_review": "OC List",
    "search_sample": "Sample List",
    "check_sample_files": "Sample List",
    "open_sample_file_choice": "Sample List",
    "search_sale_asn": "Sale ASN",
    "prepare_sale_asn_documents": "Sale ASN",
    "save_sale_asn_documents": "Sale ASN",
    "search_rmpo": "RMPO List",
    "search_advance_pr": "Advance PR List",
    "search_supplier_invoice": "Supplier Inv List",
    "search_expense_invoice": "Expense Inv List",
    "cancel_supplier_invoice": "Supplier Inv List",
    "cancel_supplier_invoice_choice": "Supplier Inv List",
    "find_supplier": "Supplier List",
    "find_supplier_in_category": "Supplier List",
    "find_buyer": "Buyer List",
    "toggle_company_foc": "Company Setup",
    "run_gdn_dispatch": "(GDN) Dispatch",
}
_MODULE_NAMES_BY_ID = {
    "0003_6200": "Catalog",
    "0004_0050_0020": "OC List",
    "0004_0056_4070": "Sample List",
    "0004_0070_0020": "Sale ASN",
    "gdn_dispatch": "(GDN) Dispatch",
    "0005_0050_0020": "RMPO List",
    "0005_0080_0020": "Indent List",
    "user_indent_list": "User Indent",
    "0063_0030_0020": "QA List",
    "0065_0880_0010_0020": "Advance PR List",
    "0065_0880_0020_0020": "Supplier Inv List",
    "0065_0880_0030_0020": "Expense Inv List",
    "0090_0001": "Org Structure",
    "0090_0250": "System Coding",
    "0090_0007": "Company Setup",
    "0004_0010_1720": "Buyer List",
    "0005_0010_1290": "Supplier List",
}
_FILTER_LABELS = {
    "search_oc": {
        "oc_no": "OC No.",
        "style": "Style",
    },
    "search_sample": {
        "sample_no": "Sample Order No.",
        "style": "Style",
        "created_by": "Created By",
        "buyer": "Buyer",
        "multiple": "nhiều điều kiện Sample",
    },
    "check_sample_files": {
        "sample_no": "Sample Order No.",
        "style": "Style",
        "created_by": "Created By",
        "buyer": "Buyer",
        "multiple": "nhiều điều kiện Sample",
    },
    "search_sale_asn": {
        "invoice_no": "Invoice No.",
        "buyer_order_ref": "Buyer Order Ref/OC No.",
        "style": "Buyer Order Ref/OC No.",
    },
    "prepare_sale_asn_documents": {
        "invoice_no": "Invoice No.",
        "buyer_order_ref": "Buyer Order Ref/OC No.",
        "style": "Buyer Order Ref/OC No.",
    },
    "search_supplier_invoice": {
        "multiple": "Supplier / Invoice No. / PO No. / ASN-GRN No.",
    },
    "search_advance_pr": {
        "multiple": "Buyer Name / Supplier / Invoice Number / Order No.",
    },
    "search_expense_invoice": {
        "multiple": "Supplier / Invoice No. / Created By / Status",
    },
    "cancel_supplier_invoice": {
        "invoice_no": "Invoice No.",
    },
}
_METHOD_DEFAULT_FILTERS = {
    "search_rmpo": "Supplier / RMPO No.",
    "search_indent": "Supplier / Article / Indent No. / Style",
    "search_advance_pr": "Buyer Name / Supplier / Invoice Number / Order No.",
    "search_supplier_invoice": "Supplier / Invoice No. / PO No. / ASN-GRN No.",
    "search_expense_invoice": "Supplier / Invoice No. / Created By / Status",
    "cancel_supplier_invoice": "Invoice No.",
}
_DIVISION_LABELS = {
    "woven": "WOVEN",
    "knit": "KNIT",
    "pssg": "PSSG",
}


def _error_operation_context(
    method: str,
    result: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, str, str]:
    module_id = str(request.get("module_id") or "").strip()
    module = (
        str(result.get("module") or "").strip()
        or _MODULE_NAMES_BY_ID.get(module_id, "")
        or _METHOD_MODULES.get(method, "")
    )
    raw_filter = str(
        result.get("filter_kind")
        or request.get("filter_kind")
        or ""
    ).strip()
    filter_kind = (
        _FILTER_LABELS.get(method, {}).get(raw_filter, raw_filter)
        or _METHOD_DEFAULT_FILTERS.get(method, "")
    )
    division_key = str(request.get("division_key") or "").strip().casefold()
    division_label = _DIVISION_LABELS.get(division_key, "")
    return module, filter_kind, division_label


def _fallback_error_detail(
    method: str,
    code: str,
    method_label: str,
    module: str,
    filter_kind: str,
    division_label: str,
) -> str:
    if code in {"MODULE_SEARCH_NOT_READY", "MODULE_LIST_NOT_OPEN"}:
        target = f"ô {filter_kind}" if filter_kind else "ô tìm kiếm"
        location = f" trong {module}" if module else ""
        if code == "MODULE_SEARCH_NOT_READY":
            return (
                f"Không tìm thấy {target}{location} sau khi app tự mở List."
            )
        return f"Không tìm thấy {target}{location}; màn List chưa sẵn sàng."
    if code == "MODULE_SEARCH_NOT_CONFIRMED":
        target = f" theo {filter_kind}" if filter_kind else ""
        location = f" trong {module}" if module else ""
        return f"WFX chưa xác nhận kết quả tìm kiếm{target}{location}."
    if method in {"open_module", "open_module_new"}:
        target = module or "module được chọn"
        return (
            f"Không thể mở {target}; menu hoặc frame WFX chưa sẵn sàng "
            f"(mã {code})."
        )
    if method == "switch_division":
        target = f" sang Division {division_label}" if division_label else ""
        return f"WFX chưa hoàn tất chuyển Division{target} (mã {code})."
    return f"{method_label} trả về mã {code} nhưng không kèm lỗi gốc."


def automation_error_context(
    method: str,
    result: dict[str, Any],
    request: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Tạo mô tả webhook rõ nghĩa, chỉ lấy dữ liệu đã whitelist."""
    method = str(method or "")
    safe_request = request if isinstance(request, dict) else {}
    code = str(result.get("code") or "UNKNOWN")
    method_label = METHOD_LABELS.get(method, method or "Tác vụ WFX")
    default_title = f"{method_label} chưa hoàn tất"
    title, suggestion = ERROR_CODE_INFO.get(
        code,
        (
            default_title,
            "Mở Log kỹ thuật và dùng Run ID để đối chiếu bước bị lỗi.",
        ),
    )
    module, filter_kind, division_label = _error_operation_context(
        method,
        result,
        safe_request,
    )
    if code == "MODULE_FAILED" and module:
        title = f"Không thể thao tác module {module}"
    detail = redact_telemetry_text(result.get("message"))
    if not detail:
        detail = _fallback_error_detail(
            method,
            code,
            method_label,
            module,
            filter_kind,
            division_label,
        )
    return {
        "method_label": method_label,
        "error_title": title,
        "error_detail": detail[:2_000],
        "suggestion": suggestion,
        "message": f"{title}: {detail}"[:4_000],
        "module": module,
        "filter_kind": filter_kind,
    }


def _outbox_path(base_dir: Path) -> Path:
    return Path(base_dir) / "telemetry-outbox.json"


def _read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip()
        try:
            parsed = json.loads(value)
            return str(parsed).strip()
        except (json.JSONDecodeError, TypeError):
            return value.strip("\"' ")
    return ""


def webhook_url(base_dir: Path) -> str:
    """Resolve endpoint mà không bao giờ trả nó qua PanelAPI/UI."""
    return (
        os.getenv(ENV_NAME, "").strip()
        or _read_env_value(Path(base_dir) / ".env", ENV_NAME)
        or DEFAULT_WEBHOOK_URL.strip()
    )


def is_configured(base_dir: Path) -> bool:
    return webhook_url(base_dir).startswith(("https://", "http://"))


def outbox_count(base_dir: Path) -> int:
    return len(_load_outbox(base_dir))


def _load_outbox(base_dir: Path) -> list[dict[str, Any]]:
    path = _outbox_path(base_dir)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_outbox(base_dir: Path, rows: list[dict[str, Any]]) -> None:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = _outbox_path(base_dir)
    if not rows:
        try:
            path.unlink()
        except OSError:
            pass
        return
    write_json_atomic(path, rows[-MAX_OUTBOX:], indent=2)


def _json_safe(value: Any) -> Any:
    """Chỉ giữ giá trị JSON hóa được.

    Payload góp ý nhúng cả ``get_status()`` và diagnostics; một object lạ lọt
    vào sẽ làm ``json.dumps`` raise TypeError — mà TypeError không nằm trong
    danh sách except của flush(), nên nó bay thẳng ra bridge.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def enqueue(base_dir: Path, event: dict[str, Any]) -> int:
    envelope = {
        "schema": SCHEMA_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **_json_safe(event),
    }
    with _LOCK:
        rows = _load_outbox(base_dir)
        rows.append(envelope)
        rows = rows[-MAX_OUTBOX:]
        _write_outbox(base_dir, rows)
        return len(rows)


def _discord_payload(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "event")
    title = "WFX Smart · Báo lỗi" if event_type == "automation_error" else "WFX Smart · Góp ý"
    fields = []
    for key in ("kind", "code", "method", "run_id", "elapsed_ms", "app_version"):
        value = event.get(key)
        if value in (None, ""):
            continue
        fields.append(
            {
                "name": key.replace("_", " ").title(),
                "value": str(value)[:1000],
                "inline": key not in {"run_id"},
            }
        )
    account = event.get("account")
    if isinstance(account, dict):
        for key in (
            "user_id",
            "company_id",
            "division_label",
            "division_name",
        ):
            value = account.get(key)
            if value in (None, ""):
                continue
            fields.append(
                {
                    "name": key.replace("_", " ").title(),
                    "value": str(value)[:1000],
                    "inline": key != "division_name",
                }
            )
    description = str(event.get("message") or "Báo lỗi tự động (không kèm dữ liệu nghiệp vụ).")
    return {
        "username": "WFX Smart Reporter",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "description": description[:4000],
                "fields": fields[:20],
            }
        ],
    }


def _post(url: str, event: dict[str, Any], timeout: float = 5.0) -> None:
    payload = (
        _discord_payload(event)
        if "discord.com/api/webhooks/" in url
        or "discordapp.com/api/webhooks/" in url
        else event
    )
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "WFX-Smart-Reporter/1",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= int(response.status) < 300:
            raise HTTPError(url, response.status, "Webhook rejected", {}, None)


def flush(
    base_dir: Path,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Gửi outbox qua endpoint đã chốt tại lúc lên lịch, nếu được truyền vào."""
    url = (
        webhook_url(base_dir)
        if endpoint is None
        else str(endpoint or "").strip()
    )
    if not url.startswith(("https://", "http://")):
        return {
            "ok": True,
            "code": "WEBHOOK_NOT_CONFIGURED",
            "sent": 0,
            "queued": len(_load_outbox(base_dir)),
        }
    # _FLUSH_LOCK tuần tự hóa phần GỬI, _LOCK chỉ bảo vệ đọc/ghi file.
    # Vì sao tách: mỗi lỗi automation spawn một thread flush, nên hai flush có
    # thể chồng nhau. Nếu chúng cùng snapshot outbox thì cùng POST một event —
    # webhook nhận trùng. Còn nếu giữ _LOCK suốt lúc gửi (bản cũ) thì 100 event
    # × timeout 5 s chặn cả enqueue, và submit_feedback đứng im trên UI thread.
    if not _FLUSH_LOCK.acquire(blocking=False):
        return {
            "ok": True,
            "code": "WEBHOOK_BUSY",
            "sent": 0,
            "queued": len(_load_outbox(base_dir)),
        }
    try:
        with _LOCK:
            rows = _load_outbox(base_dir)
        sent = 0
        failed = False
        for event in rows:
            try:
                _post(url, event)
            except (OSError, HTTPError, URLError, ValueError, TypeError):
                failed = True
                break
            sent += 1
        if sent:
            with _LOCK:
                # Chỉ bỏ đúng số event ĐÃ gửi ở đầu hàng đợi, không ghi đè cả
                # file bằng snapshot cũ: event mới xếp vào trong lúc đang gửi
                # phải còn nguyên. Cũng không xóa outbox trước khi gửi — bị kill
                # giữa lúc POST thì gửi lại vài event vẫn tốt hơn là mất chúng.
                _write_outbox(base_dir, _load_outbox(base_dir)[sent:])
        queued = len(_load_outbox(base_dir))
    finally:
        _FLUSH_LOCK.release()
    # Trạng thái phải phản ánh việc GỬI có lỗi hay không, không phải độ sâu hàng
    # đợi: một event vừa được enqueue giữa lúc flush làm queued > 0 nhưng webhook
    # vẫn hoàn toàn bình thường.
    return {
        "ok": not failed,
        "code": "WEBHOOK_UNAVAILABLE" if failed else "REPORTS_FLUSHED",
        "sent": sent,
        "queued": queued,
    }


def submit(base_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    queued = enqueue(base_dir, event)
    outcome = flush(base_dir)
    if outcome["sent"] > 0 and outcome["queued"] == 0:
        return {
            "ok": True,
            "code": "REPORT_SENT",
            "delivery": "sent",
            "queued": 0,
        }
    return {
        "ok": True,
        "code": "REPORT_QUEUED",
        "delivery": "queued",
        "queued": outcome.get("queued", queued),
    }


def system_summary() -> dict[str, str]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
    }
