"use strict";
// Mở màn module, bộ lọc tìm kiếm dùng chung.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

const SHARED_WORKSPACE_VALIDATION_GROUPS = { indent: "indent" };

function clearSharedWorkspaceInputs(kind) {
  const group = SHARED_WORKSPACE_VALIDATION_GROUPS[kind];
  if (!group) return;
  (INPUT_VALIDATION_GROUPS[group] || []).forEach((selector) => {
    const input = $(selector);
    if (input) input.value = "";
  });
  syncInputValidation(group);
}

function openModulePage(moduleId) {
  const module = allModules().find((item) => item.id === moduleId);
  if (!module) return;
  if ($(".module-page").hidden) {
    moduleReturnFocus = document.activeElement;
  }
  const previousModule = selectedModule;
  selectedModule = module;
  $("#module-page-title").textContent = module.name;
  $(".module-modal-subtitle").textContent =
    module.description || "Mở màn hình WFX.";
  $$('[data-module-view]').forEach((view) => {
    view.hidden = view.dataset.moduleView !== module.kind;
  });
  const page = $(".module-page");
  $(".panel-body").hidden = true;
  page.hidden = false;
  page.setAttribute("aria-hidden", "false");
  replayMotion(page, "view-enter");
  const focusTarget = {
    catalog: ".catalog-query",
    oc: ".oc-query",
    gdn_dispatch: ".gdn-invoice-query",
    grn_receipt: ".grn-rmpo-query",
    sample: ".sample-no-query",
    advance_pr: ".advance-pr-buyer-query",
    supplier_invoice: ".supplier-invoice-supplier-query",
    expense_invoice: ".expense-invoice-supplier-query",
    sale_asn: ".sale-asn-buyer",
    rmpo: ".rmpo-supplier-query",
    indent: ".indent-supplier-query",
    list_new: '[data-module-action="list-new-list"]',
    supplier: ".supplier-category",
    buyer: '[data-module-action="buyer-list"]',
    company_setup: '[data-module-action="company-list"]',
    reports: '[data-module-action="report-shipment-summary"]',
  }[module.kind] || ".module-back-button";
  if (module.kind === "list_new") {
    $(".list-new-module-label").textContent = `Mở New từ ${module.name}`;
  }
  setTimeout(() => $(focusTarget)?.focus(), 0);
  if (module.kind === "catalog") {
    catalogFolderEditorOpen = false;
    showCatalogSpace("search", { focus: false });
    syncCatalogKind();
    hideCatalogResults();
    syncCatalogStepButtons();
  } else if (module.kind === "sale_asn") {
    showSaleAsnView("create", { focus: false });
    resetSaleAsnProgress();
    // resetSaleAsnProgress ẩn thẻ kết quả nhưng không xóa review đang chờ, nên
    // giai đoạn phải bám theo token; nếu không, mở lại module sau một lượt xong
    // sẽ kẹt ở "done" và mất hẳn hàng Buyer/chọn file.
    setSaleAsnStageView(saleAsnReviewToken ? "review" : "idle");
    // Bung sẵn khối nâng cao nếu còn bước đang bỏ tích, để user không bất ngờ
    // vì app chạy thiếu bước.
    if (selectedSaleAsnStages().length < SALE_ASN_USER_STAGES.length) {
      openSaleAsnAdvanced();
    }
    syncSaleAsnCreate();
  } else if (module.kind === "rmpo") {
    hideRmpoResults();
  } else if (module.kind === "grn_receipt") {
    resetGrnReceipt();
  } else if (module.kind === "reports") {
    showReportList();
  } else if (module.kind === "sample") {
    // Danh sách file của lượt trước trỏ vào Sample cũ; giữ lại sẽ mời người
    // dùng tải nhầm file.
    hideSampleFileResults();
  } else if (module.kind === "supplier_invoice") {
    // Cancel là thao tác phá hủy: không để lại danh sách chọn của lượt trước.
    hideSupplierInvoiceCancelResults();
  }
  if (
    previousModule
    && previousModule.id !== module.id
    && previousModule.kind === module.kind
  ) {
    clearSharedWorkspaceInputs(module.kind);
  }
}

async function stopCurrentAction() {
  const button = $(".stop-action-button");
  if (!busy || !button || button.disabled) return;
  button.disabled = true;
  button.classList.add("is-stopping");
  setStatus("warning", "Đang dừng tại checkpoint an toàn…");
  const result = await callQuiet("cancel_current_action");
  if (!result?.ok) {
    button.disabled = false;
    button.classList.remove("is-stopping");
    setStatus("warning", result?.message || "Chưa thể dừng tác vụ.");
  }
}

function closeModulePage() {
  const page = $(".module-page");
  if (page.hidden) return;
  page.hidden = true;
  page.setAttribute("aria-hidden", "true");
  const panelBody = $(".panel-body");
  panelBody.hidden = false;
  replayMotion(panelBody, "view-enter");
  moduleReturnFocus?.focus?.();
  moduleReturnFocus = null;
}

async function openModuleDirect(moduleId) {
  return call("open_module", moduleId);
}

async function runSelectedModuleAction(method, ...args) {
  const result = await call(method, ...args);
  return result;
}

const moduleFilterPlaceholders = {
  oc: {
    oc_no: "Nhập OC No.",
    style: "Nhập Style",
  },
  sale_asn: {
    invoice_no: "Nhập Invoice No.",
    buyer_order_ref: "Nhập Buyer Order Ref/OC No.",
  },
  grn: {
    invoice: "Nhập số Invoice",
    rmpo: "Nhập RMPO / Order No.",
  },
};

function setModuleFilterKind(group, kind) {
  if (!moduleFilterPlaceholders[group]?.[kind]) return;
  moduleFilterKinds[group] = kind;
  $$(`.module-filter-button[data-filter-group="${group}"]`).forEach(
    (button) => button.setAttribute(
      "aria-pressed",
      String(button.dataset.filterKind === kind),
    ),
  );
  const input = $(`.${group.replace("_", "-")}-query`);
  if (input) {
    input.placeholder = moduleFilterPlaceholders[group][kind];
    input.focus();
  }
}

function sampleFilterValues() {
  return [
    $(".sample-no-query").value.trim(),
    $(".sample-style-query").value.trim(),
    $(".sample-created-by-query").value.trim(),
    $(".sample-buyer-query").value.trim(),
  ];
}

function supplierInvoiceFilterValues() {
  return [
    $(".supplier-invoice-supplier-query").value.trim(),
    $(".supplier-invoice-no-query").value.trim(),
    $(".supplier-invoice-po-query").value.trim(),
    $(".supplier-invoice-asn-grn-query").value.trim(),
  ];
}

function advancePrFilterValues() {
  return [
    $(".advance-pr-buyer-query").value.trim(),
    $(".advance-pr-supplier-query").value.trim(),
    $(".advance-pr-invoice-query").value.trim(),
    $(".advance-pr-order-query").value.trim(),
  ];
}

function expenseInvoiceFilterValues() {
  return [
    $(".expense-invoice-supplier-query").value.trim(),
    $(".expense-invoice-no-query").value.trim(),
    $(".expense-invoice-created-by-query").value.trim(),
    $(".expense-invoice-status-query").value.trim(),
  ];
}
