"use strict";
// Trạng thái dùng chung, tiện ích DOM, tooltip và bảng nhãn.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

let MODULE_GROUPS = [
  { name: "Operation", accent: "cyan", modules: [
    { name: "Catalog", id: "0003_6200", icon: "CA", kind: "catalog", description: "Quản lý Style, làm và tra cứu Costing, BOM." },
    { name: "OC List", id: "0004_0050_0020", icon: "OC", kind: "oc", description: "Quản lý, tạo mới và điều chỉnh đơn đặt hàng OC." },
    { name: "Sample Order", id: "0004_0056_4070", icon: "SL", kind: "sample", description: "Quản lý và tạo mới đơn hàng mẫu." },
    { name: "Sale ASN", id: "0004_0070_0020", icon: "AS", kind: "sale_asn", description: "Tạo và tra cứu thông báo giao hàng Sale ASN." },
    { name: "(GDN) Dispatch", id: "gdn_dispatch", icon: "GD", kind: "gdn_dispatch", description: "Tạo phiếu xuất kho GDN từ Invoice GRN." },
    { name: "(GRN) Nhập kho", id: "grn_receipt", icon: "GR", kind: "grn_receipt", description: "Nhập kho nguyên phụ liệu từ RMPO và tra cứu GRN." },
    { name: "RMPO List", id: "0005_0050_0020", icon: "RM", kind: "rmpo", description: "Quản lý đơn mua nguyên phụ liệu và theo dõi nhập kho." },
    { name: "Indent List", id: "0005_0080_0020", icon: "IN", kind: "indent", description: "Quản lý yêu cầu cấp nguyên phụ liệu." },
    { name: "User Indent", id: "user_indent_list", icon: "UI", kind: "indent", description: "Tra cứu yêu cầu cấp nguyên phụ liệu của người dùng." },
    { name: "QA List", id: "0063_0030_0020", icon: "QA", kind: "list_new", description: "Quản lý và tạo yêu cầu kiểm tra chất lượng." },
  ]},
  { name: "Finance", accent: "violet", modules: [
    { name: "Advance PR", id: "0065_0880_0010_0020", icon: "PR", kind: "advance_pr", description: "Quản lý và tạo đề nghị thanh toán tạm ứng." },
    { name: "Supplier Inv", id: "0065_0880_0020_0020", icon: "SI", kind: "supplier_invoice", description: "Quản lý, tra cứu và hủy hóa đơn nhà cung cấp." },
    { name: "Expense Inv", id: "0065_0880_0030_0020", icon: "EI", kind: "expense_invoice", description: "Quản lý và tạo hóa đơn chi phí." },
  ]},
  { name: "Reports", accent: "cyan", modules: [
    { name: "Reports", id: "reports", icon: "RP", kind: "reports", description: "Tải báo cáo WFX với tham số đã chọn." },
  ]},
  { name: "Admin", accent: "amber", modules: [
    { name: "Org Structure", id: "0090_0001", icon: "OR", kind: "generic", description: "Quản lý cơ cấu tổ chức." },
    { name: "System Coding", id: "0090_0250", icon: "SC", kind: "generic", description: "Quản lý mã dùng trong hệ thống." },
    { name: "Company Setup", id: "0090_0007", icon: "CO", kind: "company_setup", description: "Quản lý thiết lập công ty và nơi áp dụng FOC." },
    { name: "Buyer List", id: "0004_0010_1720", icon: "BU", kind: "buyer", description: "Quản lý và tra cứu khách hàng." },
    { name: "Supplier List", id: "0005_0010_1290", icon: "SU", kind: "supplier", description: "Quản lý và tra cứu nhà cung cấp." },
  ]},
];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const settingsOverlay = () => $(".settings-main-overlay");
const feedbackOverlay = () => $(".feedback-overlay");
const api = () => (window.pywebview && window.pywebview.api) || null;
const escapeHtml = (value) => String(value == null ? "" : value)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const TOOLTIP_SHOW_DELAY_MS = 420;
const TOOLTIP_FOCUS_DELAY_MS = 80;
let tooltipTimer = 0;
let tooltipTarget = null;

function hideTooltip() {
  window.clearTimeout(tooltipTimer);
  tooltipTimer = 0;
  const tooltip = $("#app-tooltip");
  if (tooltip) tooltip.hidden = true;
  if (tooltipTarget) {
    const previous = tooltipTarget.dataset.tooltipPreviousDescribedby;
    if (previous) tooltipTarget.setAttribute("aria-describedby", previous);
    else tooltipTarget.removeAttribute("aria-describedby");
    delete tooltipTarget.dataset.tooltipPreviousDescribedby;
  }
  tooltipTarget = null;
}

function positionTooltip(target, tooltip) {
  const targetRect = target.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const edge = 8;
  const gap = 8;
  const roomAbove = targetRect.top - edge;
  const placement = roomAbove >= tooltipRect.height + gap ? "top" : "bottom";
  const preferredTop = placement === "top"
    ? targetRect.top - tooltipRect.height - gap
    : targetRect.bottom + gap;
  const maxLeft = Math.max(edge, window.innerWidth - tooltipRect.width - edge);
  const left = Math.min(
    maxLeft,
    Math.max(edge, targetRect.left + (targetRect.width - tooltipRect.width) / 2),
  );
  const maxTop = Math.max(edge, window.innerHeight - tooltipRect.height - edge);
  tooltip.dataset.placement = placement;
  tooltip.style.left = `${Math.round(left)}px`;
  tooltip.style.top = `${Math.round(Math.min(maxTop, Math.max(edge, preferredTop)))}px`;
}

function showTooltip(target) {
  const label = String(target?.dataset.tooltip || "").trim();
  const tooltip = $("#app-tooltip");
  if (!label || !tooltip || !target.isConnected) return;
  hideTooltip();
  tooltipTarget = target;
  tooltip.textContent = label;
  tooltip.hidden = false;
  tooltipTarget.dataset.tooltipPreviousDescribedby =
    tooltipTarget.getAttribute("aria-describedby") || "";
  tooltipTarget.setAttribute("aria-describedby", tooltip.id);
  positionTooltip(target, tooltip);
}

function scheduleTooltip(target, delay) {
  if (!target || target === tooltipTarget) return;
  hideTooltip();
  tooltipTimer = window.setTimeout(() => showTooltip(target), delay);
}

function tooltipTrigger(event) {
  return event.target instanceof Element
    ? event.target.closest("[data-tooltip]")
    : null;
}

function bindTooltips() {
  document.addEventListener("pointerover", (event) => {
    if (event.pointerType === "touch") return;
    const target = tooltipTrigger(event);
    if (!target || target.contains(event.relatedTarget)) return;
    scheduleTooltip(target, TOOLTIP_SHOW_DELAY_MS);
  });
  document.addEventListener("pointerout", (event) => {
    const target = tooltipTrigger(event);
    if (target && !target.contains(event.relatedTarget)) hideTooltip();
  });
  document.addEventListener("focusin", (event) => {
    const target = tooltipTrigger(event);
    if (target) scheduleTooltip(target, TOOLTIP_FOCUS_DELAY_MS);
  });
  document.addEventListener("focusout", (event) => {
    if (tooltipTrigger(event)) hideTooltip();
  });
  document.addEventListener("pointerdown", hideTooltip, true);
  document.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideTooltip();
  }, true);
}
const MODULE_ICON_PATHS = {
  CA: '<path d="M4 7h6l2 2h8v10H4V7Z"/><path d="m9 14 2 2 4-5"/>',
  OC: '<path d="M6 3h9l3 3v15H6V3Z"/><path d="M14 3v4h4"/><path d="m9 14 2 2 4-5"/>',
  SL: '<path d="M9 3h6M10 3v6l-4 7a3 3 0 0 0 2.6 4.5h6.8A3 3 0 0 0 18 16l-4-7V3"/><path d="M7.5 15h9"/>',
  AS: '<path d="M3 6h11v11H3V6Z"/><path d="M14 10h4l3 3v4h-7v-7Z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
  GD: '<path d="M4 5h11v13H4V5Z"/><path d="M8 9h4M8 13h4"/><path d="M15 10h3l2 3v5h-5v-8Z"/><circle cx="8" cy="19" r="2"/><circle cx="17" cy="19" r="2"/>',
  GR: '<path d="M4 5h16v14H4V5Z"/><path d="M8 9h8M8 13h5"/><path d="M12 2v7m0 0-3-3m3 3 3-3"/>',
  RM: '<path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/><path d="m9 14 2 2 4-4"/>',
  IN: '<path d="M4 5h16v14H4V5Z"/><path d="M4 14h4l2 3h4l2-3h4"/><path d="M12 3v8m0 0-3-3m3 3 3-3"/>',
  UI: '<path d="M5 4h14v16H5V4Z"/><circle cx="9" cy="10" r="2"/><path d="M6.5 16a2.5 2.5 0 0 1 5 0M14 9h3M14 13h3"/>',
  QA: '<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/>',
  PR: '<path d="M4 7h16v11H4V7Z"/><path d="M7 7V5h8v2M15 12h5"/><path d="m17 10 3 2-3 2"/>',
  SI: '<path d="M6 3h12v18l-2-1.5L14 21l-2-1.5L10 21l-2-1.5L6 21V3Z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
  EI: '<circle cx="12" cy="12" r="9"/><path d="M9 9.5c0-1 1-1.8 3-1.8s3 .8 3 1.8-1 1.7-3 1.7-3 .8-3 1.8 1 1.8 3 1.8 3-.8 3-1.8M12 5.5v13"/>',
  OR: '<rect x="9" y="3" width="6" height="4" rx="1"/><rect x="3" y="17" width="6" height="4" rx="1"/><rect x="15" y="17" width="6" height="4" rx="1"/><path d="M12 7v5M6 17v-5h12v5"/>',
  SC: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  CO: '<path d="M4 21V5l8-3 8 3v16M8 7h2m4 0h2M8 11h2m4 0h2M8 15h2m4 0h2M10 21v-3h4v3"/>',
  RP: '<path d="M5 3h14v18H5V3Z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  BU: '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5"/>',
  SU: '<path d="M3 21V10l6 3v-3l6 3V6l6 3v12H3Z"/><path d="M7 17h2m3 0h2m3 0h2"/>',
};
function moduleIconSvg(icon) {
  const paths = MODULE_ICON_PATHS[String(icon || "").toUpperCase()]
    || '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8 12h8M12 8v8"/>';
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
}
// Ngưỡng cứu UI nếu bridge call không phản hồi. Dài hơn tổng deadline hợp lệ
// của các automation (login + grid settle + filter + mở đích ~ trên phút).
const CALL_WATCHDOG_MS = 180000;
const LONG_CALL_WATCHDOG_MS = 360000;
const REPORT_CALL_WATCHDOG_MS = 420000;
const COLOR_REPORT_BATCH_WATCHDOG_MS = 7200000;
let busy = false;
let pointerInsidePanel = false;
let favoriteModuleIds = new Set();
let hotkeyLabel = "Ctrl + Shift + X";
let selectedModule = null;
let selectedReportId = "";
const reportParameterCache = new Map();
let colorReportRunActive = false;
let colorReportOptionsRevision = 0;
const colorReportState = {
  levels: { division: [], buyer: [], season: [] },
  styleRefs: [],
  selected: new Set(),
  outputDir: "",
};
let jobs = [];
let adminAccess = false;
let adminMode = false;
let adminModuleIds = new Set();
let referenceSyncState = {};
let sessionActive = null;
let currentDivision = null;
let manualErrorCodes = new Set();
let lastErrorCode = "";
let hasCredentials = false;
let accountEditing = false;
let accountUserId = "";
let lastLoginTime = "";
let feedbackSubmitting = false;
let bootstrapReceived = false;
let toastEnabled = true;
let lastCatalogResult = null;
let currentCostingStatus = "";
let catalogKind = "code";
let catalogSpace = "search";
let catalogPendingDestination = null;
let costingPlanToken = "";
let costingPlanDeleteCount = 0;
let costingArticleResolutions = {};
let pendingOcReview = null;
let saleAsnBuyers = [];
let saleAsnSelectedFile = null;
let saleAsnReviewToken = "";
let saleAsnDoneInvoice = "";
let saleAsnPriceCheck = null;
let rmpoRows = [];
let selectedRmpoChoice = null;
let grnReceiptToken = "";
let grnLinkedChoiceId = "";
let grnLinkedSupplier = "";
// Progress tới qua evaluate_js từ worker, còn kết quả flow về bằng đường khác;
// hai luồng không đảm bảo thứ tự. Chỉ nhận progress khi đang có lời gọi chạy,
// nếu không một payload đến trễ sẽ xóa thẻ kết quả và kéo lùi bộ đếm.
let saleAsnRunActive = false;
const SALE_ASN_USER_STAGES = ["po", "order_details", "style_details", "shipping_info"];
const SALE_ASN_STAGES = [...SALE_ASN_USER_STAGES, "price_check"];
const SALE_ASN_PO_SEARCH_FIELDS = ["po", "style", "destination"];
let ocSelectionRevision = 0;
let checkedCostingFile = null;
let catalogThemeChoice = "light";
let catalogDefaultFolder = null;
const catalogFoldersByCategory = new Map();
const catalogExpandedFoldersByCategory = new Map();
const CATALOG_DEFAULT_CATEGORY = "Apparel";
let catalogSelectedNodeId = "";
let catalogFolderScanning = false;
let catalogFolderSaving = false;
let catalogFolderScanGeneration = 0;
let catalogFolderEditorOpen = false;
let catalogStyleReview = null;
let catalogStyleRowIndex = 0;
let catalogStyleAwaitingSave = false;
let catalogStyleGroupId = "";
let catalogStyleAutoSave = false;
let articleSuggestionTimer = 0;
let articleSuggestionGeneration = 0;
const moduleFilterKinds = {
  oc: "oc_no",
  sale_asn: "invoice_no",
  grn: "invoice",
};
const MODULE_RUN_METHODS = new Set([
  "open_chrome", "login", "retry_job", "open_module",
  "prepare_catalog", "scan_catalog_folders", "find_code", "find_buyer_reference",
  "open_catalog_destination", "browse_catalog", "catalog_action",
  "open_sale_asn_new", "scan_sale_asn_buyers", "start_sale_asn_create",
  "scan_sale_asn_order_details",
  "continue_sale_asn_create", "skip_sale_asn_create_step",
  "open_sample_new", "search_oc", "search_sample",
  "check_sample_files", "open_sample_file_choice",
  "search_sale_asn", "prepare_sale_asn_documents",
  "save_sale_asn_documents", "search_rmpo", "run_rmpo_action",
  "prepare_grn_receipt", "continue_grn_receipt", "finalize_grn_receipt",
  "search_grn", "search_indent",
  "search_advance_pr", "search_supplier_invoice", "search_expense_invoice",
  "cancel_supplier_invoice", "cancel_supplier_invoice_choice", "open_module_new",
  "load_report_parameters", "export_report_excel",
  "load_color_report_options", "run_color_report_batch",
  "open_supplier_category", "find_supplier",
  "find_supplier_in_category", "find_buyer",
  "toggle_company_foc",
  "open_oc_revision_report", "upload_oc", "confirm_oc_upload",
  "choose_oc_upload_export_file", "save_oc_upload_file",
  "confirm_oc_pending",
  "reject_all_oc_pending",
  "run_gdn_dispatch",
  "clear_catalog_costing_dependencies",
  "review_catalog_style_import", "prepare_catalog_style_row",
  "download_style_template",
]);
const BUSY_MESSAGES = {
  open_chrome: "Đang mở và đăng nhập WFX…",
  retry_job: "Đang chạy lại tác vụ…",
  open_module: "Đang mở module trên WFX…",
  prepare_catalog: "Đang chuẩn bị Catalog…",
  scan_catalog_folders: "Đang quét thư mục Catalog…",
  browse_catalog: "Đang mở vị trí Catalog…",
  catalog_action: "Đang tìm và mở dữ liệu Catalog…",
  find_code: "Đang tìm Article Code…",
  find_buyer_reference: "Đang tìm Buyer Reference…",
  open_catalog_destination: "Đang mở dữ liệu style…",
  download_catalog_file: "Đang tải file đính kèm…",
  export_catalog_costing: "Đang đọc và tải Costing…",
  inspect_active_catalog_costing: "Đang nhận tab Costing hiện tại…",
  validate_catalog_costing_file: "Đang kiểm tra cấu trúc file…",
  prepare_catalog_costing_import: "Đang kiểm tra file và lập dry-run…",
  apply_catalog_costing: "Đang áp dụng Costing và Save…",
  clear_catalog_costing_dependencies: "Đang Clear toàn bộ Dependency và Save…",
  review_catalog_style_import: "Đang kiểm tra file Tạo Style…",
  prepare_catalog_style_row: "Đang chuẩn bị Style theo chế độ Save đã chọn…",
  download_style_template: "Đang tạo form Tạo Style…",
  open_sale_asn_new: "Đang mở Sale ASN mới…",
  scan_sale_asn_buyers: "Đang quét Buyer từ WFX…",
  scan_sale_asn_order_details: "Đang đọc PO trên Sale ASN đang mở…",
  start_sale_asn_create: "Đang thêm PO và điền Sale ASN…",
  continue_sale_asn_create: "Đang tiếp tục các PO còn lại…",
  skip_sale_asn_create_step: "Đang bỏ qua bước và tiếp tục…",
  download_sale_asn_template: "Đang tạo form Sale ASN…",
  open_sample_new: "Đang mở Sample Order mới…",
  search_oc: "Đang tìm OC…",
  open_oc_revision_report: "Đang mở report Revise OC…",
  upload_oc: "Đang kiểm tra file và upload OC qua EDI…",
  review_oc_upload: "Đang kiểm tra file và tổng hợp review…",
  confirm_oc_upload: "Đang upload OC đã xác nhận qua EDI…",
  save_oc_upload_file: "Đang lưu file EDI để có thể Upload lại…",
  confirm_oc_pending: "Đang Confirm từng Style và chờ WFX xử lý…",
  reject_all_oc_pending: "Đang Reject lần lượt từng PO…",
  run_gdn_dispatch: "Đang tạo (GDN) Dispatch trên WFX…",
  download_oc_template: "Đang tạo form Upload OC…",
  search_sample: "Đang tìm Sample…",
  check_sample_files: "Đang tìm Sample và kiểm tra file…",
  open_sample_file_choice: "Đang mở Style và kiểm tra file…",
  search_sale_asn: "Đang tìm Sale ASN…",
  prepare_sale_asn_documents: "Đang tải và ghép Documents Sale ASN…",
  save_sale_asn_documents: "Đang lưu file Excel Sale ASN…",
  search_rmpo: "Đang lọc RMPO List…",
  run_rmpo_action: "Đang mở RMPO đã chọn…",
  prepare_grn_receipt: "Đang chuẩn bị quy trình nhập kho…",
  continue_grn_receipt: "Đang tiếp tục tạo GRN…",
  finalize_grn_receipt: "Đang chọn RMPO và mở New GRN…",
  search_grn: "Đang tìm GRN…",
  search_indent: "Đang lọc Indent List…",
  search_advance_pr: "Đang lọc Advance PR List…",
  search_supplier_invoice: "Đang lọc Supplier Inv List…",
  search_expense_invoice: "Đang lọc Expense Inv List…",
  cancel_supplier_invoice: "Đang tìm Supplier Invoice để Cancel…",
  cancel_supplier_invoice_choice: "Đang Cancel Supplier Invoice đã chọn…",
  open_module_new: "Đang mở màn New…",
  open_supplier_category: "Đang mở Supplier…",
  find_supplier: "Đang tìm Supplier…",
  find_supplier_in_category: "Đang tìm Supplier trong Category…",
  find_buyer: "Đang tìm Buyer…",
  toggle_company_foc: "Đang đổi và lưu cấu hình FOC…",
  switch_division: "Đang đổi Division…",
  load_report_parameters: "Đang tải tham số báo cáo…",
  export_report_excel: "Đang chạy report và export Excel…",
  load_color_report_options: "Đang tải tham số Color Combination…",
  run_color_report_batch: "Đang tải báo cáo theo từng style…",
  sync_reference_data: "Đang đồng bộ Article và Style từ server…",
  publish_reference_data: "Đang publish Article và Style lên server…",
  login: "Đang đăng nhập WFX…",
};
// Nhãn tiếng Việt cho lịch sử tác vụ; tránh phơi tên hàm kỹ thuật ra người dùng.
const JOB_METHOD_LABELS = {
  login: "Đăng nhập WFX",
  check_session: "Kiểm tra phiên",
  open_chrome: "Mở trình duyệt",
  open_module: "Mở module",
  prepare_catalog: "Chuẩn bị Catalog",
  browse_catalog: "Mở vị trí Catalog",
  scan_catalog_folders: "Quét thư mục Catalog",
  catalog_action: "Tìm Catalog",
  find_code: "Tìm Article Code",
  find_buyer_reference: "Tìm Buyer Reference",
  open_catalog_destination: "Mở Costing / BOM",
  download_catalog_file: "Tải file đính kèm",
  export_catalog_costing: "Tải Costing",
  inspect_active_catalog_costing: "Nhận tab Costing",
  validate_catalog_costing_file: "Kiểm tra file Costing",
  prepare_catalog_costing_import: "Dry-run Costing",
  apply_catalog_costing: "Áp dụng Costing",
  clear_catalog_costing_dependencies: "Clear All Dependency",
  review_catalog_style_import: "Kiểm tra file Tạo Style",
  prepare_catalog_style_row: "Chuẩn bị Style",
  clear_catalog_style_import: "Hủy Tạo Style",
  sync_reference_data: "Đồng bộ Article và Style",
  publish_reference_data: "Publish Article và Style",
  open_sale_asn_new: "Sale ASN mới",
  scan_sale_asn_buyers: "Quét Buyer Sale ASN",
  scan_sale_asn_order_details: "Xuất PO đang mở",
  start_sale_asn_create: "Tạo Sale ASN",
  continue_sale_asn_create: "Tiếp tục Sale ASN",
  skip_sale_asn_create_step: "Bỏ qua bước Sale ASN",
  open_sample_new: "Sample Order mới",
  search_oc: "Tìm OC",
  open_oc_revision_report: "Mở report Revise OC",
  upload_oc: "Upload OC",
  review_oc_upload: "Review Upload OC",
  confirm_oc_upload: "Xác nhận Upload OC",
  confirm_oc_pending: "Confirm nhanh OC",
  reject_all_oc_pending: "Reject All OC",
  run_gdn_dispatch: "Tạo (GDN) Dispatch",
  cancel_oc_upload_review: "Hủy Upload OC",
  search_sample: "Tìm Sample",
  check_sample_files: "Check File Sample",
  open_sample_file_choice: "Mở file Sample",
  search_sale_asn: "Tìm Sale ASN",
  prepare_sale_asn_documents: "Tải Documents Sale ASN",
  save_sale_asn_documents: "Lưu Documents Sale ASN",
  search_rmpo: "Tìm RMPO",
  run_rmpo_action: "Thao tác RMPO",
  prepare_grn_receipt: "Chuẩn bị nhập kho GRN",
  continue_grn_receipt: "Tiếp tục làm GRN",
  finalize_grn_receipt: "Mở New GRN",
  search_grn: "Tìm GRN",
  search_indent: "Tìm Indent",
  search_advance_pr: "Tìm Advance PR",
  search_supplier_invoice: "Tìm Supplier Invoice",
  search_expense_invoice: "Tìm Expense Invoice",
  cancel_supplier_invoice: "Cancel Supplier Invoice",
  cancel_supplier_invoice_choice: "Cancel Supplier Invoice đã chọn",
  open_module_new: "Mở màn New",
  open_supplier_category: "Mở Supplier",
  find_supplier: "Tìm Supplier",
  find_supplier_in_category: "Tìm Supplier theo Category",
  find_buyer: "Tìm Buyer",
  toggle_company_foc: "Đổi FOC Company Setup",
  switch_division: "Đổi Division",
  load_report_parameters: "Tải tham số báo cáo",
  export_report_excel: "Xuất Excel báo cáo",
  load_color_report_options: "Tải tham số Color Combination",
  run_color_report_batch: "Tải hàng loạt Color Combination",
};
const jobMethodLabel = (method) =>
  JOB_METHOD_LABELS[String(method || "")] || String(method || "Tác vụ");
