"use strict";
// Cầu nối tới backend: gọi API, nhận kết quả, watchdog.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function handleResult(result) {
  if (!result) return;
  const cancelled = result.code === "ACTION_CANCELLED";
  setStatus(
    cancelled ? "warning" : (result.ok ? "success" : "error"),
    result.message || "",
  );
  if (result.code?.startsWith?.("GDN_")) {
    finishGdnProgress(result);
  }
  if (result.code === "SALE_ASN_BUYERS_SCANNED") {
    renderSaleAsnBuyers(result.buyers);
  }
  if (result.code === "REPORT_PARAMETERS_LOADED") {
    renderReportParameters(result);
  }
  if (["SALE_ASN_PO_SELECTION_REQUIRED", "SALE_ASN_FORM_COMPLETED"].includes(result.code) || result.resume_stage) {
    renderSaleAsnRunResult(result);
  }
  lastErrorCode = (!result.ok && result.code) ? result.code : "";
  $(".footer-help-button").hidden = !manualErrorCodes.has(lastErrorCode);
  if (result.user_id !== undefined) setAccount(result.user_id);
  if (result.chrome_alive !== undefined) {
    setBrowserStatus(Boolean(result.chrome_alive), result.browser_available, result.browser_name);
  }
  if (result.session_active !== undefined) {
    setSessionStatus(result.session_active, result.last_login_at);
  }
  if (result.current_division !== undefined) {
    setDivisionState(
      result.current_division,
      result.division_label,
      result.division_name
    );
  }
  if (result.has_credentials !== undefined) {
    hasCredentials = result.has_credentials === true;
  }
  if (result.style_status) setStyleStatus(result.style_status);
  if (result.costing_special_options) {
    setCostingSpecialOptionsState(result.costing_special_options);
  }
  if (result.source === "sample") {
    clearCatalogResult();
  } else if (["RESULT_OPENED", "CATALOG_FILES_SCANNED"].includes(result.code)
      && result.article_code && result.source !== "sample") {
    rememberCatalogResult(result);
  } else if ([
    "NO_RESULTS", "MULTIPLE_RESULTS", "CATALOG_RESULT_REQUIRED",
    "CATALOG_RESULT_CHANGED", "CATALOG_RESULT_EXPIRED",
  ].includes(result.code)) {
    clearCatalogResult();
  }
  if ([
    "MULTIPLE_RESULTS", "NO_RESULTS", "RESULT_OPENED",
    "CATALOG_FILES_SCANNED",
  ].includes(result.code)) {
    if (result.source === "sample") renderSampleFileResults(result);
    else renderCatalogResults(result);
  } else if (result.code === "SAMPLE_MULTIPLE_RESULTS") {
    renderSampleFileResults(result);
  } else if (result.code === "SAMPLE_RESULT_EXPIRED") {
    // Danh sách đang hiện trỏ vào grid đã đổi. Giữ lại là mời người dùng
    // bấm tiếp vào dòng đã chết và nhận đúng lỗi này thêm một lần nữa.
    hideSampleFileResults();
  } else if (result.code === "SUPPLIER_INVOICE_MULTIPLE_RESULTS") {
    renderSupplierInvoiceCancelResults(result);
  }
  if ([
    "RMPO_RESULTS_READY", "RMPO_NO_RESULTS", "RMPO_RESULT_EXPIRED",
  ].includes(result.code)) {
    renderRmpoResults(result);
  }
  if (String(result.code || "").startsWith("GRN_")) {
    renderGrnReceiptResult(result);
  }
  if (result.code === "COSTING_DRY_RUN_READY") {
    showCatalogSpace("costing", { focus: false });
    renderCostingPlan(result);
  } else if (result.code === "COSTING_ARTICLE_AMBIGUOUS") {
    showCatalogSpace("costing", { focus: false });
    renderCostingAmbiguities(result);
  } else if (result.code === "COSTING_APPLIED") {
    showCatalogSpace("costing", { focus: false });
    resetCostingPlan();
  }
  if (
    result.code === "CATALOG_DESTINATION_OPENED"
    && result.destination === "costsheet"
  ) {
    showCatalogSpace("costing", { focus: false });
  }
  if (["COSTING_EXPORTED", "COSTING_FILE_VALID"].includes(result.code)) {
    showCatalogSpace("costing", { focus: false });
  }
  if (result.default_folder !== undefined) {
    catalogDefaultFolder = result.default_folder;
    const folderLabel =
      catalogDefaultFolder?.path_label || "Mặc định (Master)";
    $(".catalog-folder-summary").dataset.tooltip =
      `Sửa vị trí mặc định: ${folderLabel}`;
  }
  if (result.admin_access !== undefined) {
    setAdminAccess(
      result.admin_access,
      result.admin_module_ids,
      result.admin_mode
    );
  }
  if (result.jobs) renderJobs(result.jobs);
  if (result.run_id) refreshJobs();
  if (["MISSING_CREDENTIALS", "PASSWORD_REQUIRED", "USER_ID_REQUIRED",
       "LOGIN_FAILED", "LOGIN_TIMEOUT", "NOT_LOGGED_IN",
       "SESSION_USER_MISMATCH"].includes(result.code)) {
    // Kiểm tra nền không được kéo người dùng ra khỏi việc đang làm để mở
    // một sheet bị khóa. Badge WFX ở footer và dòng trạng thái đã đủ; chỉ
    // thao tác do chính người dùng bấm mới ép nhập lại tài khoản.
    if (result.method !== "maintain_session") {
      showCredentialPrompt(result.code, result.message);
    }
  } else if (["LOGGED_IN", "LOGGED_IN_AFTER_DELAY", "SESSION_REUSED",
              "SESSION_ACTIVE", "SESSION_RESTORED"].includes(result.code)) {
    clearCredentialPrompt();
  }
}
window.wfxHandleBackendResult = (result) => {
  handleResult(result);
  // Result sink là đường hồi phục độc lập với Promise của pywebview. Trên
  // một số phiên WebView2 chạy lâu, backend đã xong và log đã có kết quả
  // nhưng Promise bridge không resolve; nếu không nhả busy tại đây, toàn bộ
  // workflow tiếp theo vẫn bị disabled tới watchdog.
  settleBusyUi();
};

async function call(method, ...args) {
  const bridge = api();
  if (!bridge || typeof bridge[method] !== "function") {
    setStatus("error", "Bridge chưa sẵn sàng");
    return null;
  }
  const busyMessage = BUSY_MESSAGES[method] || "Đang xử lý trên WFX…";
  setBusy(true, busyMessage);
  setStatus("neutral", busyMessage);
  // Watchdog: nếu một bridge call treo (Chrome/WFX không phản hồi, promise
  // không resolve), giải phóng UI thay vì để mọi nút disable vĩnh viễn ("đơ").
  // Backend vẫn giữ run lock; kết quả thật (nếu có) sẽ về sau qua result sink.
  let watchdog;
  const watchdogMs = method === "run_color_report_batch"
    ? COLOR_REPORT_BATCH_WATCHDOG_MS
    : (method === "export_report_excel"
    ? REPORT_CALL_WATCHDOG_MS
    : (method === "run_gdn_dispatch"
      ? LONG_CALL_WATCHDOG_MS
      : CALL_WATCHDOG_MS));
  const timeout = new Promise((resolve) => {
    watchdog = window.setTimeout(
      () => resolve({ __timeout: true }), watchdogMs
    );
  });
  try {
    // Bắt đầu backend ngay; đưa Chrome lên trước chỉ là hiệu ứng song song,
    // không được nằm trên critical path của automation.
    const pending = bridge[method](...args);
    if (MODULE_RUN_METHODS.has(method)) {
      Promise.resolve(api()?.focus_automation_browser?.()).catch(() => {});
    }
    // Nếu watchdog thắng trước, promise gốc reject muộn sẽ không còn ai bắt →
    // gắn no-op catch để tránh "unhandled rejection". Race vẫn bắt lỗi bình thường.
    pending.catch(() => {});
    const result = await Promise.race([pending, timeout]);
    if (result && result.__timeout) {
      setStatus(
        "error",
        "Tác vụ chạy quá lâu và có thể vẫn đang xử lý trên WFX. "
          + "Vui lòng chờ hoặc thử lại sau giây lát.",
      );
      return null;
    }
    handleResult(result);
    return result;
  } catch (error) {
    setStatus("error", String(error));
    return null;
  } finally {
    window.clearTimeout(watchdog);
    settleBusyUi();
  }
}

async function callQuiet(method, ...args) {
  const bridge = api();
  if (!bridge || typeof bridge[method] !== "function") {
    setStatus("error", "Bridge chưa sẵn sàng");
    return null;
  }
  try { return await bridge[method](...args); }
  catch (error) { setStatus("error", String(error)); return null; }
}

async function refreshJobs() {
  const result = await callQuiet("get_job_history", 30);
  if (result && result.jobs) renderJobs(result.jobs);
}

// Hai module dùng chung một workspace (Indent List và User Indent) nên điều
// kiện lọc của module trước phải được xóa khi người dùng đổi sang module kia.
