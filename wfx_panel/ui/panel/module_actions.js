"use strict";
// Bảng tra hành vi: moduleActions cho từng nút, BACKEND_PROGRESS_HANDLERS cho
// progress từ backend. File này PHẢI nạp sau mọi file định nghĩa handler và
// trước bootstrap.js: khai báo top-level đọc giá trị ngay lúc chạy, không hoạt động
// theo kiểu hoisting xuyên file như khi tất cả còn nằm trong một IIFE.

// Backend bắn progress cho nhiều flow; rẽ theo method để mỗi thẻ tiến độ chỉ
// nhận đúng payload của nó. Method lạ bị bỏ qua, không ném lỗi.
const BACKEND_PROGRESS_HANDLERS = {
  run_gdn_dispatch: updateGdnProgress,
  start_sale_asn_create: updateSaleAsnProgress,
  continue_sale_asn_create: updateSaleAsnProgress,
  skip_sale_asn_create_step: updateSaleAsnProgress,
  run_color_report_batch: updateColorReportProgress,
};

const moduleActions = {
  "oc-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "oc-template": async () => {
    const result = await call("download_oc_template");
    if (result) renderOcUploadResult(result, result.file_name || "");
    return result;
  },
  "oc-upload-new": () => uploadOcFile("new"),
  "oc-confirm-new": () => confirmOcPending("new"),
  "oc-review-cancel": cancelOcUploadReview,
  "oc-review-download": downloadOcUploadFile,
  "oc-review-confirm": confirmOcUploadReview,
  "oc-revise-report": async () => {
    const result = await call("open_oc_revision_report");
    if (result) renderOcUploadResult(result);
    return result;
  },
  "oc-upload-revise": () => uploadOcFile("revise"),
  "oc-confirm-revision": () => confirmOcPending("revision"),
  "oc-reject-all": rejectAllOcPending,
  "oc-search": () => runSelectedModuleAction(
    "search_oc",
    moduleFilterKinds.oc,
    $(".oc-query").value.trim(),
  ),
  "gdn-dispatch-submit": submitGdnDispatch,
  "gdn-status": () => runSelectedModuleAction("open_gdn_status"),
  "sample-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "sample-new": () => runSelectedModuleAction("open_sample_new"),
  "sample-search": () => {
    hideSampleFileResults();
    return runSelectedModuleAction(
      "search_sample",
      ...sampleFilterValues(),
    );
  },
  "sample-check-file": () => {
    hideSampleFileResults();
    return runSelectedModuleAction(
      "check_sample_files",
      ...sampleFilterValues(),
    );
  },
  "sale-asn-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "sale-asn-new": () => runSelectedModuleAction("open_sale_asn_new"),
  "sale-asn-scan-buyers": scanSaleAsnBuyers,
  "sale-asn-template": () => call("download_sale_asn_template"),
  "sale-asn-continue-export": exportSaleAsnContinueTemplate,
  "sale-asn-import": chooseSaleAsnInput,
  "sale-asn-review-cancel": cancelSaleAsnReview,
  "sale-asn-start": startSaleAsnCreate,
  "sale-asn-continue": continueSaleAsnCreate,
  "sale-asn-skip-step": skipSaleAsnCreateStep,
  "sale-asn-handoff-documents": handoffSaleAsnDocuments,
  "sale-asn-export-price-check": exportSaleAsnPriceCheck,
  "sale-asn-search": () => runSelectedModuleAction(
    "search_sale_asn",
    moduleFilterKinds.sale_asn,
    $(".sale-asn-query").value.trim(),
  ),
  "sale-asn-documents": () => downloadSaleAsnDocuments(),
  "rmpo-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "rmpo-search": () => {
    hideRmpoResults();
    return runSelectedModuleAction(
      "search_rmpo",
      $(".rmpo-supplier-query").value.trim(),
      $(".rmpo-order-query").value.trim(),
    );
  },
  "rmpo-check-po": () => runRmpoAction("check_po"),
  "rmpo-edit-po": () => runRmpoAction("edit_po"),
  "rmpo-receive": () => runRmpoAction("receive"),
  "rmpo-check-received": () => runRmpoAction("check_received"),
  "grn-foreign": () => startGrnReceipt("foreign"),
  "grn-domestic": () => startGrnReceipt("domestic"),
  "grn-rmpo-list": () => openModulePage("0005_0050_0020"),
  "grn-continue": continueGrnReceipt,
  "grn-next": finalizeGrnReceipt,
  "grn-search": () => runSelectedModuleAction(
    "search_grn",
    moduleFilterKinds.grn,
    $(".grn-search-query").value.trim(),
  ),
  "indent-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "indent-search": () => selectedModule && runSelectedModuleAction(
    "search_indent",
    selectedModule.id,
    $(".indent-supplier-query").value.trim(),
    $(".indent-article-query").value.trim(),
    $(".indent-no-query").value.trim(),
    $(".indent-style-query").value.trim(),
  ),
  "advance-pr-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "advance-pr-new": () => selectedModule && runSelectedModuleAction("open_module_new", selectedModule.id),
  "advance-pr-search": () => runSelectedModuleAction(
    "search_advance_pr",
    ...advancePrFilterValues(),
  ),
  "supplier-invoice-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "supplier-invoice-search": () => runSelectedModuleAction(
    "search_supplier_invoice",
    ...supplierInvoiceFilterValues(),
  ),
  "supplier-invoice-cancel": () => {
    hideSupplierInvoiceCancelResults();
    return runSelectedModuleAction(
      "cancel_supplier_invoice",
      $(".supplier-invoice-cancel-query").value.trim(),
    );
  },
  "expense-invoice-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "expense-invoice-new": () => selectedModule && runSelectedModuleAction("open_module_new", selectedModule.id),
  "expense-invoice-search": () => runSelectedModuleAction(
    "search_expense_invoice",
    ...expenseInvoiceFilterValues(),
  ),
  "report-shipment-summary": loadShipmentSummaryReport,
  "report-color-combination": () => loadColorReportOptions(""),
  "report-last-month": setReportLastMonth,
  "report-save-parameters": saveSelectedReportParameters,
  "report-export-excel": exportSelectedReport,
  "color-report-select-all": () => setColorReportSelection(true),
  "color-report-clear-all": () => setColorReportSelection(false),
  "color-report-choose-dir": chooseColorReportDir,
  "color-report-run": () => runColorReportBatch(),
  "list-new-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "list-new-new": () => selectedModule && runSelectedModuleAction("open_module_new", selectedModule.id),
  // Supplier: mỗi nút là một flow độc lập và tự mở List khi cần, nên giữ
  // panel mở để người dùng còn đổi Category hoặc tìm tiếp.
  "supplier-list": () => selectedModule && call("open_module", selectedModule.id),
  "supplier-open": () => call("open_supplier_category", $(".supplier-category").value),
  "supplier-find": () => runSelectedModuleAction(
    "find_supplier",
    $(".supplier-query").value.trim(),
  ),
  // Quét cả 6 Category tốn tới 6 lượt đổi Category + lọc. Khi user đã biết
  // Supplier nằm ở Category nào thì đi thẳng, không bắt chờ hết vòng quét.
  "supplier-find-category": () => runSelectedModuleAction(
    "find_supplier_in_category",
    $(".supplier-category").value,
    $(".supplier-query").value.trim(),
  ),
  "buyer-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "buyer-find": () => runSelectedModuleAction("find_buyer", $(".buyer-query").value.trim()),
  "company-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
  "company-toggle-foc": async () => {
    const result = await runSelectedModuleAction("toggle_company_foc");
    if (result?.foc_mode) {
      $(".company-foc-state").hidden = false;
      $(".company-foc-state strong").textContent = result.foc_mode;
    }
    return result;
  },
};
