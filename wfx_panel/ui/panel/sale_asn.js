"use strict";
// Tạo Sale ASN: Buyer, file, review, tiến độ 5 bước.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

async function downloadSaleAsnDocuments() {
  const prepared = await call(
    "prepare_sale_asn_documents",
    moduleFilterKinds.sale_asn,
    $(".sale-asn-query").value.trim(),
  );
  if (!prepared?.ok || !prepared.export_token) return prepared;
  const selected = await callQuiet(
    "choose_sale_asn_export_file",
    prepared.invoice_no || "Invoice",
  );
  if (!selected?.ok) {
    await callQuiet("cancel_sale_asn_documents", prepared.export_token);
    if (selected?.code !== "SALE_ASN_FILE_DIALOG_CANCELLED") {
      handleResult(selected);
    }
    return selected;
  }
  const saved = await call(
    "save_sale_asn_documents",
    prepared.export_token,
    selected.file_path,
  );
  return saved;
}

function showSaleAsnView(view, { focus = true } = {}) {
  const selected = view === "lookup" ? "lookup" : "create";
  $$('[data-sale-asn-view]').forEach((button) => {
    const active = button.dataset.saleAsnView === selected;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $$('[data-sale-asn-pane]').forEach((pane) => {
    pane.hidden = pane.dataset.saleAsnPane !== selected;
  });
  if (focus) {
    const target = selected === "create" ? ".sale-asn-buyer" : ".sale-asn-query";
    setTimeout(() => $(target)?.focus(), 0);
  }
}

function openSaleAsnAdvanced({ scrollTo = "" } = {}) {
  const advanced = $(".sale-asn-advanced");
  if (!advanced) return;
  advanced.open = true;
  if (!scrollTo) return;
  setTimeout(() => {
    $(scrollTo)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, 0);
}

function renderSaleAsnBuyers(items) {
  saleAsnBuyers = Array.isArray(items)
    ? items.filter((item) => String(item?.label || "").trim())
    : [];
  hideSaleAsnBuyerSuggestions();
  syncSaleAsnCreate();
}

function saleAsnExactBuyer() {
  const entered = String($(".sale-asn-buyer")?.value || "").trim();
  if (!entered) return "";
  return saleAsnBuyers.find(
    (item) => String(item.label || "").trim().toLocaleLowerCase("vi")
      === entered.toLocaleLowerCase("vi"),
  )?.label || "";
}

function hideSaleAsnBuyerSuggestions() {
  const host = $(".sale-asn-buyer-suggestions");
  if (!host) return;
  host.innerHTML = "";
  host.hidden = true;
  $(".sale-asn-buyer")?.setAttribute("aria-expanded", "false");
  $(".sale-asn-buyer-dropdown")?.setAttribute("aria-expanded", "false");
}

function renderSaleAsnBuyerSuggestions({ showAll = false } = {}) {
  const host = $(".sale-asn-buyer-suggestions");
  const input = $(".sale-asn-buyer");
  if (!host || !input) return;
  const entered = String(input.value || "").trim();
  if (!showAll && (entered.length < 2 || saleAsnExactBuyer())) {
    hideSaleAsnBuyerSuggestions();
    return;
  }
  const folded = entered.toLocaleLowerCase("vi");
  const matches = showAll
    ? saleAsnBuyers
    : saleAsnBuyers
      .filter((item) => String(item.label || "").toLocaleLowerCase("vi").includes(folded))
      .slice(0, 20);
  if (!matches.length) {
    hideSaleAsnBuyerSuggestions();
    return;
  }
  host.innerHTML = matches.map((item) => `
    <button type="button" class="sale-asn-buyer-suggestion" role="option"
      aria-selected="false" data-buyer-value="${escapeHtml(item.label)}"
    >${escapeHtml(item.label)}</button>`).join("");
  host.hidden = false;
  input.setAttribute("aria-expanded", "true");
  $(".sale-asn-buyer-dropdown")?.setAttribute("aria-expanded", "true");
}

function selectedSaleAsnStages() {
  return $$('[data-sale-asn-stage]:checked').map((input) => input.dataset.saleAsnStage);
}

function applySaleAsnStages(stages) {
  // prefs không bao giờ trả về danh sách rỗng; nếu thiếu thì giữ mặc định đủ bước.
  if (!Array.isArray(stages) || !stages.length) return;
  $$('[data-sale-asn-stage]').forEach((input) => {
    input.checked = stages.includes(input.dataset.saleAsnStage);
  });
  resetSaleAsnProgress();
  syncSaleAsnCreate();
}

function selectedSaleAsnPoSearchFields() {
  return $$('[data-sale-asn-po-search-field]:checked')
    .map((input) => input.dataset.saleAsnPoSearchField);
}

function applySaleAsnPoSearchFields(fields) {
  const requested = Array.isArray(fields)
    ? fields.filter((field) => SALE_ASN_PO_SEARCH_FIELDS.includes(field))
    : [];
  const selected = requested.length ? requested : SALE_ASN_PO_SEARCH_FIELDS;
  $$('[data-sale-asn-po-search-field]').forEach((input) => {
    input.checked = selected.includes(input.dataset.saleAsnPoSearchField);
  });
}

function syncSaleAsnCreate() {
  const buyer = saleAsnExactBuyer();
  const stages = selectedSaleAsnStages();
  const needsBuyer = stages.includes("po");
  const importButton = $('[data-module-action="sale-asn-import"]');
  if (importButton) {
    importButton.disabled = busy || !stages.length || (needsBuyer && !buyer);
  }
  const buyerInput = $(".sale-asn-buyer");
  if (buyerInput) buyerInput.setAttribute("aria-required", String(needsBuyer));
  const box = $(".sale-asn-buyer-box");
  if (box) {
    const entered = String(buyerInput?.value || "").trim();
    box.dataset.match = buyer ? "exact" : (entered ? "none" : "");
  }
  // Quét Buyer mở hẳn form New trên Chrome nên không tự chạy; thay vào đó làm
  // nút ↻ nổi bật khi kho Buyer còn rỗng.
  const scanButton = $('[data-module-action="sale-asn-scan-buyers"]');
  if (scanButton) {
    scanButton.dataset.needsScan = String(needsBuyer && !saleAsnBuyers.length);
  }
  const status = $(".sale-asn-inline-status");
  if (!status || saleAsnReviewToken) return;
  if (!stages.length) {
    status.textContent = "Chọn ít nhất một bước trong Tùy chọn nâng cao.";
  } else if (!needsBuyer) {
    status.textContent = "Sẽ dùng Sale ASN đang mở và bỏ qua bước Thêm PO.";
  } else if (!saleAsnBuyers.length) {
    status.textContent = "Bấm ↻ để quét Buyer lần đầu từ WFX.";
  } else if (!buyer) {
    status.textContent = "Gõ và chọn đúng một Buyer trong danh sách.";
  } else {
    status.textContent = "Buyer đã sẵn sàng. Chọn file Excel để kiểm tra.";
  }
}

// Màn Tạo mới chỉ hiện đúng phần của giai đoạn hiện tại. Ở "idle" là hàng
// Buyer/chọn file/Tùy chọn nâng cao; từ "review" trở đi chúng thu về một dòng
// ngữ cảnh để thẻ review/tiến độ/kết quả không phải xếp chồng lên nhau.
function setSaleAsnStageView(view) {
  const pane = $(".sale-asn-create");
  if (!pane) return;
  pane.dataset.stageView = view;
  const context = $(".sale-asn-context");
  if (!context) return;
  context.hidden = view === "idle";
  if (view === "idle") return;
  const buyer = String($(".sale-asn-buyer")?.value || "").trim();
  $(".sale-asn-context-buyer").textContent = buyer || "Sale ASN đang mở";
  $(".sale-asn-context-file").textContent = saleAsnSelectedFile?.file_name || "";
}

// Dòng trạng thái chỉ phục vụ lúc chuẩn bị (chọn Buyer/file) nên nằm trong
// khối setup và tự ẩn từ giai đoạn review. Thông điệp khi lượt chạy dừng lại
// không có chỗ nào khác nên đặt ngay trong thẻ review, cạnh nút Bắt đầu.
function setSaleAsnReviewNote(message) {
  const note = $(".sale-asn-review-note");
  if (!note) return;
  note.textContent = message || "";
  note.hidden = !message;
}

function saleAsnStageRow(stage) {
  return $(`[data-sale-asn-progress-stage="${stage}"]`);
}

function setSaleAsnStageState(stage, state, detail = "") {
  const row = saleAsnStageRow(stage);
  if (!row) return;
  row.dataset.state = state;
  const note = row.querySelector(".sale-asn-progress-row small");
  if (note) note.textContent = detail;
}

function resetSaleAsnProgress({ show = false } = {}) {
  const selected = selectedSaleAsnStages();
  SALE_ASN_STAGES.forEach((stage) => {
    const skipped = stage !== "price_check" && !selected.includes(stage);
    setSaleAsnStageState(stage, skipped ? "skipped" : "pending", skipped ? "không chạy" : "");
  });
  const count = $(".sale-asn-progress-count");
  if (count) count.textContent = `0/${SALE_ASN_STAGES.length}`;
  const done = $(".sale-asn-done");
  if (done) done.hidden = true;
  hideSaleAsnStageAction();
  const card = $(".sale-asn-progress-card");
  if (card) card.hidden = !show;
}

function hideSaleAsnStageAction() {
  const action = $(".sale-asn-stage-action");
  if (!action) return;
  action.hidden = true;
  $(".sale-asn-skip-step").hidden = true;
  $(".sale-asn-stage-message").textContent = "";
  renderSaleAsnCandidates([]);
  $(".sale-asn-progress-card")?.appendChild(action);
}

function selectedSaleAsnCandidateIds() {
  return $$(".sale-asn-candidate-select:checked")
    .map((input) => String(input.value || "").trim())
    .filter(Boolean);
}

function syncSaleAsnCandidateAction() {
  const button = $('[data-module-action="sale-asn-continue"]');
  const choices = $$(".sale-asn-candidate-select");
  if (button && choices.length) {
    button.disabled = busy || !choices.some((choice) => choice.checked);
  }
}

// Backend đã trả sẵn các dòng WFX tìm được. Checkbox ở đây là lựa chọn thật;
// backend xác nhận ID rồi tự tick đúng dòng trên popup WFX.
function renderSaleAsnCandidates(candidates) {
  const box = $(".sale-asn-candidates");
  const list = $(".sale-asn-candidate-list");
  if (!box || !list) return;
  const items = Array.isArray(candidates) ? candidates.slice(0, 20) : [];
  list.innerHTML = items
    .map((item) => {
      const cell = (value) => String(value ?? "").trim();
      const po = escapeHtml(cell(item?.po_no) || "—");
      const style = escapeHtml(cell(item?.style_no));
      const qty = escapeHtml(cell(item?.dispatched_qty));
      const candidateId = escapeHtml(cell(item?.candidate_id));
      return `<li><label><input class="sale-asn-candidate-select" type="checkbox" value="${candidateId}" />`
        + `<b>${po}</b>`
        + (style ? `<span>${style}</span>` : "")
        + (qty ? `<em>${qty}</em>` : "")
        + "</label></li>";
    })
    .join("");
  box.hidden = !items.length;
  syncSaleAsnCandidateAction();
}

// Thẻ hành động là duy nhất trong DOM và được chuyển vào đúng dòng bước đang
// vướng, để trạng thái chờ/lỗi không rời khỏi ngữ cảnh bước.
function showSaleAsnStageAction(stage, { message, manual, canSkip, stageLabel, candidates = [] }) {
  const row = saleAsnStageRow(stage);
  const action = $(".sale-asn-stage-action");
  if (!row || !action) return;
  row.appendChild(action);
  action.hidden = false;
  $(".sale-asn-stage-message").textContent = message || "";
  renderSaleAsnCandidates(candidates);
  const skipButton = $(".sale-asn-skip-step");
  skipButton.hidden = !canSkip;
  skipButton.textContent = `Bỏ qua ${stageLabel || "bước này"}`;
  const continueButton = $('[data-module-action="sale-asn-continue"]');
  continueButton.textContent = manual ? "Thêm dòng đã chọn" : "Thử lại bước này";
  continueButton.disabled = Boolean(manual);
  $(".sale-asn-progress-card").hidden = false;
}

function resetSaleAsnReview(message = "") {
  saleAsnSelectedFile = null;
  saleAsnReviewToken = "";
  saleAsnDoneInvoice = "";
  saleAsnPriceCheck = null;
  $(".sale-asn-review").hidden = true;
  $(".sale-asn-done").hidden = true;
  $(".sale-asn-price-result").hidden = true;
  setSaleAsnStageView("idle");
  clearSaleAsnFileError();
  resetSaleAsnProgress();
  if (message) $(".sale-asn-inline-status").textContent = message;
  syncSaleAsnCreate();
}

function renderSaleAsnReview(result) {
  saleAsnReviewToken = String(result.review_token || "");
  saleAsnDoneInvoice = String(result.invoice_no || "");
  saleAsnPriceCheck = null;
  $(".sale-asn-review-invoice").textContent = result.invoice_no || "";
  $(".sale-asn-review-po").textContent = String(result.po_count || 0);
  $(".sale-asn-review-style").textContent = String(result.style_count || 0);
  const destination = String(result.destination || "").trim();
  const destinationStat = $(".sale-asn-review-destination");
  destinationStat.textContent = destination;
  destinationStat.hidden = !destination;
  $(".sale-asn-review").hidden = false;
  $(".sale-asn-done").hidden = true;
  clearSaleAsnFileError();
  resetSaleAsnProgress();
  setSaleAsnStageView("review");
  setSaleAsnReviewNote("");
  $('[data-module-action="sale-asn-start"]').textContent =
    Array.isArray(result.selected_stages) && !result.selected_stages.includes("po")
      ? "Chạy các bước đã chọn"
      : "Bắt đầu tạo Sale ASN";
}

function clearSaleAsnFileError() {
  const card = $(".sale-asn-file-error");
  if (!card) return;
  card.hidden = true;
  card.replaceChildren();
}

function renderSaleAsnFileError(result) {
  const card = $(".sale-asn-file-error");
  if (!card) return;
  const errors = Array.isArray(result?.errors)
    ? result.errors.filter(Boolean).slice(0, 12)
    : [];
  const remaining = Math.max(
    0,
    (Array.isArray(result?.errors) ? result.errors.length : 0) - errors.length,
  );
  card.innerHTML = `
    <strong>Không kiểm tra được file Sale ASN</strong>
    <p>${escapeHtml(result?.message || "File chưa hợp lệ. Hãy kiểm tra các mục bên dưới.")}</p>
    ${errors.length ? `<ul>${errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}${remaining ? `<li>Còn ${remaining} lỗi khác.</li>` : ""}</ul>` : ""}
    ${result?.code ? `<code>${escapeHtml(result.code)}</code>` : ""}`;
  card.hidden = false;
}

async function scanSaleAsnBuyers() {
  const result = await call("scan_sale_asn_buyers");
  if (result?.ok) {
    renderSaleAsnBuyers(result.buyers);
    $(".sale-asn-inline-status").textContent = result.message || "Đã cập nhật Buyer.";
  }
  return result;
}

async function chooseSaleAsnInput() {
  const stages = selectedSaleAsnStages();
  if (!stages.length) {
    openSaleAsnAdvanced({ scrollTo: ".sale-asn-stage-options" });
    syncSaleAsnCreate();
    return null;
  }
  const buyer = saleAsnExactBuyer();
  if (stages.includes("po") && !buyer) {
    syncSaleAsnCreate();
    $(".sale-asn-buyer")?.focus();
    return null;
  }
  const selected = await callQuiet("choose_sale_asn_import_file");
  if (!selected?.ok) {
    if (selected?.code !== "SALE_ASN_FILE_DIALOG_CANCELLED") handleResult(selected);
    return selected;
  }
  saleAsnSelectedFile = selected;
  clearSaleAsnFileError();
  $(".sale-asn-inline-status").textContent = `Đang kiểm tra ${selected.file_name}…`;
  const result = await call(
    "prepare_sale_asn_create",
    selected.file_path,
    buyer,
    stages,
  );
  if (result?.ok) {
    renderSaleAsnReview(result);
  } else if (result) {
    $(".sale-asn-inline-status").textContent = "File chưa hợp lệ. Xem chi tiết bên dưới.";
    renderSaleAsnFileError(result);
  }
  return result;
}

async function exportSaleAsnContinueTemplate() {
  const prepared = await call("scan_sale_asn_order_details");
  if (!prepared?.ok) {
    $(".sale-asn-inline-status").textContent = prepared?.message || "Không đọc được PO đang mở.";
    return prepared;
  }
  const saved = await call(
    "save_sale_asn_continue_template",
    prepared.rows || [],
  );
  if (saved) {
    $(".sale-asn-inline-status").textContent = saved.message || "Đã xuất form từ PO đang mở.";
  }
  return saved;
}

// Progress chỉ để hiển thị. renderSaleAsnRunResult chạy sau và là nguồn sự thật,
// nên payload đến trễ không thể để lại trạng thái sai.
function updateSaleAsnProgress(progress) {
  const card = $(".sale-asn-progress-card");
  if (!card || !progress || !saleAsnRunActive) return;
  const stage = String(progress.stage || "");
  const index = SALE_ASN_STAGES.indexOf(stage);
  if (index < 0) return;
  card.hidden = false;
  $(".sale-asn-review").hidden = true;
  $(".sale-asn-done").hidden = true;
  setSaleAsnStageView("running");
  const state = String(progress.state || "active");
  SALE_ASN_STAGES.slice(0, index).forEach((earlier) => {
    const row = saleAsnStageRow(earlier);
    if (row && !["done", "skipped"].includes(row.dataset.state)) {
      setSaleAsnStageState(earlier, "done", "");
    }
  });
  if (state === "skipped") {
    setSaleAsnStageState(stage, "skipped", "đã bỏ qua");
  } else {
    // Backend kết thúc message bằng "n/m" khi bước đó chạy theo từng dòng.
    const counter = /(\d+\/\d+)\s*$/.exec(String(progress.message || ""));
    setSaleAsnStageState(stage, "active", counter ? counter[1] : "");
  }
  const count = $(".sale-asn-progress-count");
  if (count) {
    count.textContent = `${Math.max(1, Number(progress.step || 1))}/${SALE_ASN_STAGES.length}`;
  }
  if (busy && progress.message) {
    setStatus("neutral", progress.message);
  }
}

// Stop, ACTION_IN_PROGRESS, review hết hiệu lực hay watchdog đều dừng lượt
// chạy mà không có checkpoint để tiếp tục. Thẻ review là nơi duy nhất chứa
// nút Bắt đầu, nên phải trả nó lại; nếu không user kẹt với thẻ tiến độ trống.
function haltSaleAsnRun(result) {
  hideSaleAsnStageAction();
  SALE_ASN_STAGES.forEach((stage) => {
    if (saleAsnStageRow(stage)?.dataset.state === "active") {
      setSaleAsnStageState(stage, "warn", "đã dừng");
    }
  });
  if (saleAsnReviewToken) {
    $(".sale-asn-review").hidden = false;
    setSaleAsnStageView("review");
  }
  setSaleAsnReviewNote(
    result?.message || "Đã dừng. Bấm Bắt đầu để chạy lại.",
  );
}

function renderSaleAsnRunResult(result) {
  const stageOf = (value) => (SALE_ASN_STAGES.includes(value) ? value : "");
  if (!result) {
    haltSaleAsnRun(null);
    return;
  }
  if (result.code === "SALE_ASN_PO_SELECTION_REQUIRED") {
    saleAsnReviewToken = String(result.review_token || saleAsnReviewToken);
    showSaleAsnView("create", { focus: false });
    $(".sale-asn-review").hidden = true;
    setSaleAsnStageView("running");
    setSaleAsnStageState("po", "warn", "chờ bạn chọn");
    showSaleAsnStageAction("po", {
      message: result.message || "",
      manual: true,
      canSkip: false,
      stageLabel: "Thêm PO",
      candidates: result.candidates,
    });
    return;
  }
  if (result.resumable) {
    saleAsnReviewToken = String(result.review_token || saleAsnReviewToken);
    const stage = stageOf(result.resume_stage) || "po";
    showSaleAsnView("create", { focus: false });
    $(".sale-asn-review").hidden = true;
    setSaleAsnStageView("running");
    setSaleAsnStageState(stage, "warn", "chưa hoàn tất");
    showSaleAsnStageAction(stage, {
      message: result.message
        || "Có lỗi trên WFX. Bạn có thể thử lại mà không tạo lại ASN.",
      manual: false,
      canSkip: Boolean(result.can_skip),
      stageLabel: result.stage_label || "bước này",
    });
    return;
  }
  if (result.code === "SALE_ASN_FORM_COMPLETED") {
    saleAsnReviewToken = "";
    $(".sale-asn-review").hidden = true;
    hideSaleAsnStageAction();
    SALE_ASN_STAGES.forEach((stage) => {
      const row = saleAsnStageRow(stage);
      if (row && row.dataset.state !== "skipped") {
        setSaleAsnStageState(stage, "done", "");
      }
    });
    const count = $(".sale-asn-progress-count");
    if (count) count.textContent = `${SALE_ASN_STAGES.length}/${SALE_ASN_STAGES.length}`;
    renderSaleAsnDone(result);
    return;
  }
  haltSaleAsnRun(result);
}

function renderSaleAsnDone(result) {
  const done = $(".sale-asn-done");
  if (!done) return;
  setSaleAsnStageView("done");
  $(".sale-asn-done-invoice").textContent = saleAsnDoneInvoice;
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const warnBlock = $(".sale-asn-done-warn");
  if (warnBlock) {
    $(".sale-asn-done-warnings").innerHTML = warnings
      .map((item) => `<li>${escapeHtml(String(item))}</li>`).join("");
    $(".sale-asn-done-warn-count").textContent =
      `${warnings.length} cảnh báo Shipping Info`;
    warnBlock.hidden = !warnings.length;
  }
  $(".sale-asn-done-message").textContent = warnings.length
    ? "Bổ sung các mục cảnh báo rồi tự bấm Save trên WFX."
    : "Kiểm tra lại toàn bộ chứng từ rồi tự bấm Save trên WFX.";
  const priceResult = $(".sale-asn-price-result");
  if (priceResult) {
    priceResult.hidden = true;
    priceResult.replaceChildren();
  }
  saleAsnPriceCheck = result.price_check || null;
  const priceExport = $('[data-module-action="sale-asn-export-price-check"]');
  if (priceExport) priceExport.disabled = !saleAsnPriceCheck;
  if (saleAsnPriceCheck) renderSaleAsnPriceCheck(saleAsnPriceCheck);
  done.hidden = false;
  // Thẻ kết quả nằm dưới progress và có thể ngoài viewport của vùng module.
  // Chờ layout nhận chiều cao mới rồi đưa kết quả vào tầm nhìn, để user thấy
  // ngay cảnh báo và nút Xuất Invoice + PKL sau khi flow hoàn tất.
  setTimeout(() => {
    if (!done.hidden) {
      done.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, 0);
}

// Panel chỉ rộng 440px nên kết quả check phải đọc được trong một tầm mắt:
// chip tổng kết trước, dòng lệch hiện sẵn, dòng khớp gấp lại.
const SALE_ASN_SUMMARY_LABELS = {
  total_quantity: "Total Quantity",
  value_in_doc_currency: "Value In Doc Currency",
  net_value_in_doc_currency: "Net Value In Doc Currency",
};

function saleAsnPriceRow(item) {
  const tone = item.status === "ok" ? "ok" : "bad";
  const head = `<div class="sale-asn-price-row-head"><b>${escapeHtml(item.po_no || "—")}</b>`
    + `<span title="${escapeHtml(item.style_no || "")}">${escapeHtml(item.style_no || "")}</span></div>`;
  // Chỉ so được Qty/Price khi cả hai phía đều có số; các trạng thái còn lại
  // (thiếu dữ liệu, không thấy PO, nhiều giá) chỉ có thông điệp để hiển thị.
  const comparable = ["ok", "mismatch"].includes(item.status);
  if (!comparable) {
    return `<li data-tone="${tone}">${head}`
      + `<div class="sale-asn-price-row-note">${escapeHtml(item.message || "")}</div></li>`;
  }
  const systemPrice = (item.system_prices || [])[0] || "—";
  const cell = (label, ok, fileValue, systemValue) => {
    const text = ok
      ? `${label} ${fileValue || "—"}`
      : `${label} ${fileValue || "—"} → ${systemValue || "—"}`;
    return `<span data-ok="${ok}">${escapeHtml(text)}</span>`;
  };
  return `<li data-tone="${tone}">${head}<div class="sale-asn-price-row-diff">`
    + cell("Qty", item.qty_ok !== false, item.file_qty, item.system_qty)
    + cell("Price", item.price_ok !== false, item.file_price, systemPrice)
    + "</div></li>";
}

function renderSaleAsnPriceCheck(result) {
  const host = $(".sale-asn-price-result");
  if (!host || !result) return;
  const comparisons = Array.isArray(result.comparisons) ? result.comparisons : [];
  const matched = comparisons.filter((item) => item.status === "ok");
  const attention = comparisons.filter((item) => item.status !== "ok");
  const summaryChecks = result.summary?.checks || {};
  const summaryOk = Object.keys(SALE_ASN_SUMMARY_LABELS)
    .every((key) => summaryChecks[key]?.ok);
  const summaryFailed = Object.keys(SALE_ASN_SUMMARY_LABELS)
    .filter((key) => summaryChecks[key] && !summaryChecks[key].ok);

  const chips = [
    `<span class="sale-asn-price-chip" data-tone="${matched.length ? "ok" : "muted"}">${matched.length} khớp</span>`,
    attention.length
      ? `<span class="sale-asn-price-chip" data-tone="bad">${attention.length} lệch</span>`
      : "",
    `<span class="sale-asn-price-chip" data-tone="${summaryOk ? "ok" : "bad"}">Summary ${summaryOk ? "✓" : "✕"}</span>`,
  ].join("");

  const summaryRows = summaryFailed.map((key) => {
    const check = summaryChecks[key];
    return `<li data-tone="bad"><div class="sale-asn-price-row-head"><b>Summary</b>`
      + `<span>${escapeHtml(SALE_ASN_SUMMARY_LABELS[key])}</span></div>`
      + `<div class="sale-asn-price-row-diff"><span data-ok="false">`
      + `${escapeHtml(`${check.expected || "—"} → ${check.actual || "—"}`)}</span></div></li>`;
  }).join("");

  const problems = attention.map(saleAsnPriceRow).join("") + summaryRows;
  host.innerHTML = `<div class="sale-asn-price-chips">${chips}</div>`
    + (problems
      ? `<p class="sale-asn-price-legend">File → WFX</p>`
        + `<ul class="sale-asn-price-rows">${problems}</ul>`
      : "")
    + (matched.length
      ? `<details class="sale-asn-price-more"><summary>${matched.length} dòng khớp</summary>`
        + `<ul class="sale-asn-price-rows">${matched.map(saleAsnPriceRow).join("")}</ul></details>`
      : "");
  host.hidden = false;
}

function handoffSaleAsnDocuments() {
  showSaleAsnView("lookup", { focus: false });
  setModuleFilterKind("sale_asn", "invoice_no");
  const query = $(".sale-asn-query");
  if (query) {
    query.value = saleAsnDoneInvoice;
    syncAllInputValidation();
  }
  setTimeout(() => $('[data-module-action="sale-asn-search"]')?.focus(), 0);
  return null;
}

async function exportSaleAsnPriceCheck() {
  if (!saleAsnPriceCheck) return null;
  const selected = await callQuiet(
    "choose_sale_asn_price_check_export_file",
    saleAsnDoneInvoice || "Invoice",
  );
  if (!selected?.ok) {
    if (selected?.code !== "SALE_ASN_FILE_DIALOG_CANCELLED") handleResult(selected);
    return selected;
  }
  return call("export_sale_asn_price_check", saleAsnPriceCheck, selected.file_path);
}

async function startSaleAsnCreate() {
  if (!saleAsnReviewToken) return null;
  resetSaleAsnProgress({ show: true });
  $(".sale-asn-review").hidden = true;
  saleAsnRunActive = true;
  const result = await call("start_sale_asn_create", saleAsnReviewToken);
  saleAsnRunActive = false;
  renderSaleAsnRunResult(result);
  return result;
}

async function continueSaleAsnCreate() {
  if (!saleAsnReviewToken) return null;
  const selectedCandidates = selectedSaleAsnCandidateIds();
  if ($$(".sale-asn-candidate-select").length && !selectedCandidates.length) return null;
  hideSaleAsnStageAction();
  saleAsnRunActive = true;
  const result = await call(
    "continue_sale_asn_create",
    saleAsnReviewToken,
    selectedCandidates,
  );
  saleAsnRunActive = false;
  renderSaleAsnRunResult(result);
  return result;
}

async function skipSaleAsnCreateStep() {
  if (!saleAsnReviewToken) return null;
  hideSaleAsnStageAction();
  saleAsnRunActive = true;
  const result = await call("skip_sale_asn_create_step", saleAsnReviewToken);
  saleAsnRunActive = false;
  renderSaleAsnRunResult(result);
  return result;
}

async function cancelSaleAsnReview() {
  const token = saleAsnReviewToken;
  saleAsnRunActive = false;
  resetSaleAsnReview("Đã hủy file đang chuẩn bị.");
  return token ? callQuiet("cancel_sale_asn_create", token) : null;
}
