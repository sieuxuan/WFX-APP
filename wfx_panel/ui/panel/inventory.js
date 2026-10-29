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
  if (status.startsWith("waiting")) return "waiting";
  return "other";
}

// Cùng luật với backend (rmpo_receipt_refusal): Received đã nhập hết, Waiting
// chưa được duyệt; Part Received vẫn nhập tiếp phần còn lại.
function rmpoCanReceive(value) {
  return !["received", "waiting"].includes(rmpoStatusTone(value));
}

const RMPO_STATUS_NOTES = {
  received: "Đã nhập kho hết, không nhập thêm được. Bấm Check Received để xem phần đã nhận.",
  waiting: "RMPO đang chờ duyệt (Waiting) nên chưa nhập kho được.",
  "part-received": "Đã nhận một phần, có thể nhập tiếp phần còn lại.",
};

function hideRmpoResults() {
  rmpoRows = [];
  selectedRmpoChoice = null;
  const wrap = $(".rmpo-results");
  if (!wrap) return;
  wrap.hidden = true;
  $(".rmpo-results-count").textContent = "";
  $(".rmpo-results-body").replaceChildren();
  $(".rmpo-results-empty").hidden = true;
  $(".rmpo-table-wrap").hidden = false;
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
  const tone = rmpoStatusTone(selected.status);
  const receivable = rmpoCanReceive(selected.status);
  const order = $(".rmpo-selection-order");
  order.textContent = selected.order_no || "—";
  order.dataset.tooltip = selected.order_no || "";
  const badge = $(".rmpo-status-badge");
  badge.textContent = selected.status || "Chưa có Status";
  badge.dataset.rmpoStatus = tone;
  const supplier = $(".rmpo-selection-supplier");
  supplier.textContent = selected.supplier || "—";
  supplier.dataset.tooltip = selected.supplier || "";
  $(".rmpo-selection-qty").textContent = selected.qty || "—";
  $(".rmpo-selection-created").textContent = selected.last_created || "—";
  const note = $(".rmpo-selection-note");
  note.textContent = RMPO_STATUS_NOTES[tone] || "";
  note.hidden = !note.textContent;
  const card = $(".rmpo-selection");
  card.dataset.rmpoReceivable = String(receivable);
  $('[data-module-action="rmpo-receive"]').hidden = !receivable;
  $('[data-module-action="rmpo-check-received"]').hidden =
    !["received", "part-received"].includes(tone);
  card.hidden = false;
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
    $(".rmpo-table-wrap").hidden = false;
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
  $(".rmpo-results-empty").hidden = true;
  $(".rmpo-selection").hidden = true;
  wrap.hidden = false;
  // Một dòng duy nhất: chọn luôn và chỉ hiện thẻ thao tác (thẻ đã gồm đủ
  // Status/Supplier/Qty), không bắt user click lại đúng dòng đó.
  const single = rmpoRows.length === 1;
  $(".rmpo-table-wrap").hidden = single;
  $(".rmpo-table").hidden = single;
  if (single) selectRmpoChoice(rmpoRows[0].choice_id);
}

// Site nhận kho nhớ theo User ID + Division ở backend. Option trống nghĩa là
// để app tự đọc dropdown Site của GRN Pending rồi dừng cho user chọn.
function renderGrnSites(sites, { fromWfx = false } = {}) {
  const select = $(".grn-site-select");
  if (!select) return;
  const list = (Array.isArray(sites) ? sites : [])
    .map((site) => String(site || "").trim())
    .filter(Boolean);
  const previous = select.value;
  let placeholder = "Tự đọc từ WFX";
  if (fromWfx) placeholder = "Chọn Site";
  else if (list.length) placeholder = "Đọc lại Site từ WFX";
  select.replaceChildren(
    new Option(placeholder, ""),
    ...list.map((site) => new Option(site, site)),
  );
  if (list.includes(previous)) select.value = previous;
  else if (list.length === 1) select.value = list[0];
  const hint = $(".grn-site-hint");
  if (hint) {
    hint.textContent = list.length
      ? "Đã chọn Site thì app đi thẳng tới New GRN, không dừng hỏi Site."
      : "Lần đầu để trống: app đọc danh sách Site từ WFX và nhớ cho lần sau.";
  }
  syncGrnStepActions();
}

async function loadGrnSites() {
  const result = await callQuiet("grn_sites");
  if (result?.ok) renderGrnSites(result.sites);
}

function selectedGrnSite() {
  return String($(".grn-site-select")?.value || "").trim();
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
  const done = $(".grn-done");
  if (done) done.hidden = true;
  syncInputValidation("grn-create");
  syncGrnStepActions();
  loadGrnSites();
}

function syncGrnStepActions() {
  const continueButton = $('[data-module-action="grn-continue"]');
  const checkpoint = $(".grn-sourcing-checkpoint");
  if (continueButton) {
    continueButton.disabled = busy || !grnReceiptToken || checkpoint?.hidden !== false;
  }
  const next = $('[data-module-action="grn-next"]');
  const siteStep = $(".grn-site-step");
  if (next) {
    next.disabled = busy || !grnReceiptToken || !selectedGrnSite()
      || siteStep?.hidden !== false;
  }
}

function handoffRmpoToGrn() {
  if (!selectedRmpoChoice?.choice_id) {
    setStatus("warning", "Hãy chọn một RMPO trong danh sách trước.");
    return null;
  }
  if (!rmpoCanReceive(selectedRmpoChoice.status)) {
    setStatus("warning", `RMPO ${selectedRmpoChoice.order_no || ""} đang ${selectedRmpoChoice.status || "không ở trạng thái nhập kho được"}, chưa nhập kho được.`);
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
  if (result.code === "GRN_SITE_INVALID") {
    loadGrnSites();
    return;
  }
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
    $(".grn-sourcing-checkpoint").hidden = true;
    $(".grn-site-step").hidden = false;
    $(".grn-done").hidden = true;
    renderGrnSites(result.sites, { fromWfx: true });
    $(".grn-site-select").focus();
    return;
  }
  if (result.code === "GRN_NEW_READY") {
    grnReceiptToken = "";
    $(".grn-sourcing-checkpoint").hidden = true;
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
    selectedGrnSite(),
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
    selectedGrnSite(),
  );
}

async function finalizeGrnReceipt() {
  const site = selectedGrnSite();
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
