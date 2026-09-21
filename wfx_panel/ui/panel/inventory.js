"use strict";
// RMPO và (GRN) Nhập kho.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function normaliseRmpoStatus(value) {
  return String(value || "").trim().toLocaleLowerCase("vi")
    .replace(/\s+/g, " ");
}

function rmpoStatusTone(value) {
  const status = normaliseRmpoStatus(value);
  if (status === "received") return "received";
  if (status === "part received") return "part-received";
  return "other";
}

function hideRmpoResults() {
  rmpoRows = [];
  selectedRmpoChoice = null;
  const wrap = $(".rmpo-results");
  if (!wrap) return;
  wrap.hidden = true;
  $(".rmpo-results-count").textContent = "";
  $(".rmpo-results-body").replaceChildren();
  $(".rmpo-results-empty").hidden = true;
  $(".rmpo-table").hidden = false;
  $(".rmpo-selection").hidden = true;
}

function selectRmpoChoice(choiceId) {
  const selected = rmpoRows.find(
    (item) => String(item.choice_id || "") === String(choiceId || ""),
  );
  if (!selected) return;
  selectedRmpoChoice = selected;
  $$(".rmpo-results-body tr").forEach((row) => {
    row.setAttribute(
      "aria-selected",
      String(row.dataset.rmpoChoiceId === selected.choice_id),
    );
  });
  $(".rmpo-selection-order").textContent = selected.order_no || "—";
  $(".rmpo-selection-meta").textContent = [
    selected.status || "Chưa có Status",
    selected.supplier || "Chưa có Supplier",
    selected.qty ? `Qty ${selected.qty}` : "",
  ].filter(Boolean).join(" · ");
  const status = normaliseRmpoStatus(selected.status);
  $('[data-module-action="rmpo-receive"]').hidden = status === "received";
  $('[data-module-action="rmpo-check-received"]').hidden =
    !["received", "part received"].includes(status);
  $(".rmpo-selection").hidden = false;
}

function renderRmpoResults(result) {
  const wrap = $(".rmpo-results");
  const body = $(".rmpo-results-body");
  if (!wrap || !body) return;
  if (result.code === "RMPO_RESULT_EXPIRED") {
    hideRmpoResults();
    return;
  }
  if (result.code === "RMPO_NO_RESULTS") {
    rmpoRows = [];
    selectedRmpoChoice = null;
    body.replaceChildren();
    $(".rmpo-results-count").textContent = "0 kết quả";
    $(".rmpo-table").hidden = true;
    $(".rmpo-results-empty").hidden = false;
    $(".rmpo-selection").hidden = true;
    wrap.hidden = false;
    return;
  }
  if (result.code !== "RMPO_RESULTS_READY" || !Array.isArray(result.rmpos)) {
    return;
  }
  rmpoRows = result.rmpos.filter((item) => item?.choice_id);
  selectedRmpoChoice = null;
  $(".rmpo-results-count").textContent =
    `${Number(result.result_count || rmpoRows.length)} kết quả`;
  body.innerHTML = rmpoRows.map((item) => `
    <tr tabindex="0" aria-selected="false"
      data-rmpo-choice-id="${escapeHtml(item.choice_id)}">
      <td data-rmpo-status="${rmpoStatusTone(item.status)}"
        title="${escapeHtml(item.status || "")}">${escapeHtml(item.status || "—")}</td>
      <td title="${escapeHtml(item.supplier || "")}">${escapeHtml(item.supplier || "—")}</td>
      <td title="${escapeHtml(item.order_no || "")}">${escapeHtml(item.order_no || "—")}</td>
      <td title="${escapeHtml(item.last_created || "")}">${escapeHtml(item.last_created || "—")}</td>
      <td title="${escapeHtml(item.qty || "")}">${escapeHtml(item.qty || "—")}</td>
    </tr>`).join("");
  body.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", () => selectRmpoChoice(row.dataset.rmpoChoiceId));
    row.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectRmpoChoice(row.dataset.rmpoChoiceId);
    });
  });
  $(".rmpo-table").hidden = false;
  $(".rmpo-results-empty").hidden = true;
  $(".rmpo-selection").hidden = true;
  wrap.hidden = false;
}

function resetGrnReceipt() {
  grnReceiptToken = "";
  grnLinkedChoiceId = "";
  grnLinkedSupplier = "";
  const input = $(".grn-rmpo-query");
  if (input) input.value = "";
  const context = $(".grn-linked-context");
  if (context) context.hidden = true;
  const supplier = $(".grn-linked-supplier");
  if (supplier) supplier.textContent = "";
  const checkpoint = $(".grn-sourcing-checkpoint");
  if (checkpoint) checkpoint.hidden = true;
  const siteStep = $(".grn-site-step");
  if (siteStep) siteStep.hidden = true;
  const site = $(".grn-site-select");
  if (site) site.replaceChildren(new Option("Chọn Site", ""));
  const done = $(".grn-done");
  if (done) done.hidden = true;
  syncInputValidation("grn-create");
  syncGrnStepActions();
}

function syncGrnStepActions() {
  const continueButton = $('[data-module-action="grn-continue"]');
  const checkpoint = $(".grn-sourcing-checkpoint");
  if (continueButton) {
    continueButton.disabled = busy || !grnReceiptToken || checkpoint?.hidden !== false;
  }
  const next = $('[data-module-action="grn-next"]');
  const siteStep = $(".grn-site-step");
  const site = String($(".grn-site-select")?.value || "").trim();
  if (next) next.disabled = busy || !grnReceiptToken || !site || siteStep?.hidden !== false;
}

function handoffRmpoToGrn() {
  if (!selectedRmpoChoice?.choice_id) {
    setStatus("warning", "Hãy chọn một RMPO trong danh sách trước.");
    return null;
  }
  const choice = { ...selectedRmpoChoice };
  openModulePage("grn_receipt");
  grnLinkedChoiceId = choice.choice_id;
  grnLinkedSupplier = String(choice.supplier || "").trim();
  $(".grn-rmpo-query").value = choice.order_no || "";
  $(".grn-linked-supplier").textContent = grnLinkedSupplier
    ? `Supplier: ${grnLinkedSupplier}`
    : "App sẽ đọc Supplier từ RMPO List";
  $(".grn-linked-context").hidden = false;
  syncInputValidation("grn-create");
  setStatus("success", "Đã chuyển RMPO sang module (GRN) Nhập kho.");
  return { ok: true, code: "GRN_RMPO_LINKED" };
}

function renderGrnReceiptResult(result) {
  if (!result) return;
  if (["GRN_SESSION_EXPIRED", "GRN_RMPO_SELECTION_EXPIRED"].includes(result.code)) {
    grnReceiptToken = "";
    grnLinkedChoiceId = "";
    $(".grn-sourcing-checkpoint").hidden = true;
    $(".grn-site-step").hidden = true;
    return;
  }
  if (result.code === "GRN_SOURCING_ASN_READY") {
    grnReceiptToken = String(result.receipt_token || "");
    grnLinkedSupplier = String(result.supplier || grnLinkedSupplier || "");
    $(".grn-sourcing-checkpoint").hidden = false;
    $(".grn-site-step").hidden = true;
    $(".grn-done").hidden = true;
    $(".grn-sourcing-rmpo").textContent = result.rmpo_no || "RMPO đã chọn";
    syncGrnStepActions();
    return;
  }
  if (result.code === "GRN_SITE_SELECTION_REQUIRED") {
    grnReceiptToken = String(result.receipt_token || grnReceiptToken || "");
    const sites = Array.isArray(result.sites) ? result.sites : [];
    const select = $(".grn-site-select");
    select.replaceChildren(
      new Option("Chọn Site", ""),
      ...sites.map((site) => new Option(String(site), String(site))),
    );
    $(".grn-sourcing-checkpoint").hidden = true;
    $(".grn-site-step").hidden = false;
    $(".grn-done").hidden = true;
    syncGrnStepActions();
    select.focus();
    return;
  }
  if (result.code === "GRN_NEW_READY") {
    grnReceiptToken = "";
    $(".grn-site-step").hidden = true;
    $(".grn-done").hidden = false;
    syncGrnStepActions();
  }
}

async function startGrnReceipt(mode) {
  const rmpo = $(".grn-rmpo-query").value.trim();
  if (!rmpo) {
    setStatus("warning", "Hãy nhập RMPO No.");
    return null;
  }
  return runSelectedModuleAction(
    "prepare_grn_receipt",
    rmpo,
    mode,
    grnLinkedChoiceId,
  );
}

async function continueGrnReceipt() {
  if (!grnReceiptToken) {
    setStatus("warning", "Phiên nhập kho đã hết hiệu lực. Hãy bắt đầu lại.");
    return null;
  }
  if (!window.confirm(
    "Bạn xác nhận đã nhập đủ thông tin, số lượng và Confirm Sourcing ASN trên WFX?"
  )) return null;
  return runSelectedModuleAction(
    "continue_grn_receipt",
    grnReceiptToken,
    true,
  );
}

async function finalizeGrnReceipt() {
  const site = $(".grn-site-select").value.trim();
  if (!grnReceiptToken || !site) {
    setStatus("warning", "Hãy chọn Site trước khi tiếp tục.");
    return null;
  }
  return runSelectedModuleAction("finalize_grn_receipt", grnReceiptToken, site);
}

async function runRmpoAction(action) {
  if (!selectedRmpoChoice?.choice_id) {
    setStatus("warning", "Hãy chọn một RMPO trong danh sách trước.");
    return null;
  }
  if (action === "receive") {
    return handoffRmpoToGrn();
  }
  return runSelectedModuleAction(
    "run_rmpo_action",
    selectedRmpoChoice.choice_id,
    action,
  );
}
