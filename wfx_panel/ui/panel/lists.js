"use strict";
let expenseReviewToken = "";
let expenseSelectionRevision = 0;

function downloadExpenseTemplate() {
  return call("download_expense_template");
}

function syncExpenseImportActions() {
  const button = $('[data-module-action="expense-invoice-fill"]');
  if (button) button.disabled = busy || !expenseReviewToken;
}

function clearExpenseImportView() {
  expenseReviewToken = "";
  const view = $(".expense-import-review");
  if (view) view.hidden = true;
  syncExpenseImportActions();
}

async function chooseExpenseImport() {
  const revision = ++expenseSelectionRevision;
  const selected = await callQuiet("choose_expense_import_file");
  if (revision !== expenseSelectionRevision) return null;
  if (!selected?.ok) {
    if (selected && selected.code !== "EXPENSE_FILE_DIALOG_CANCELLED") handleResult(selected);
    return selected;
  }
  if (expenseReviewToken) await callQuiet("clear_expense_import", expenseReviewToken);
  clearExpenseImportView();
  const result = await call("review_expense_import", selected.file_path);
  if (revision !== expenseSelectionRevision) {
    if (result?.review_token) await callQuiet("clear_expense_import", result.review_token);
    return null;
  }
  if (result?.ok) {
    expenseReviewToken = result.review_token;
    $(".expense-import-file").textContent = result.file_name;
    $(".expense-import-summary").textContent =
      `${result.supplier} · ${result.invoice_no} · ${result.row_count} dòng · ${result.total} ${result.currency}`;
    $(".expense-import-review").hidden = false;
    syncExpenseImportActions();
  }
  return result;
}

async function clearExpenseImport() {
  expenseSelectionRevision += 1;
  const token = expenseReviewToken;
  clearExpenseImportView();
  return token ? callQuiet("clear_expense_import", token) : null;
}

async function fillExpenseImport() {
  if (!expenseReviewToken) return null;
  const token = expenseReviewToken;
  // Mỗi review chỉ chạy một lần; sau lỗi cần chọn lại file để kiểm tra lại.
  clearExpenseImportView();
  return call("fill_expense_import", token);
}

// Kết quả file Sample, huỷ hoá đơn nhà cung cấp, tải file.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

// Danh sách Sample gần nhất. Token của nó vẫn còn hiệu lực ở backend sau khi
// mở một Sample (grid WFX vẫn mở nguyên), nên người dùng quay lại chọn Sample
// kế tiếp mà không phải tìm lại. Mọi lối ẩn danh sách đều bỏ bản giữ này.
let sampleChoiceResult = null;
const sampleCheckedChoices = new Set();

function setSampleFileResultsExtras(note, showBack) {
  const noteNode = $(".sample-file-results-note");
  if (noteNode) {
    noteNode.textContent = note || "";
    noteNode.hidden = !note;
  }
  const back = $(".sample-file-results-back");
  if (back) back.hidden = !showBack;
}

function hideSampleFileResults() {
  sampleChoiceResult = null;
  sampleCheckedChoices.clear();
  const wrap = $(".sample-file-results");
  if (!wrap) return;
  wrap.hidden = true;
  $(".sample-file-results-title").textContent = "Kết quả";
  $(".sample-file-results-count").textContent = "";
  $(".sample-file-results-list").innerHTML = "";
  setSampleFileResultsExtras("", false);
}

function showSampleChoiceList() {
  if (sampleChoiceResult) renderSampleFileResults(sampleChoiceResult);
}

function renderSampleFileResults(result) {
  const wrap = $(".sample-file-results");
  const list = $(".sample-file-results-list");
  if (!wrap || !list) return;
  if (result.code === "SAMPLE_MULTIPLE_RESULTS"
      && Array.isArray(result.samples) && result.samples.length) {
    if (result !== sampleChoiceResult) sampleCheckedChoices.clear();
    sampleChoiceResult = result;
    const listed = result.samples.length;
    const total = Math.max(
      Number(result.total_rows || 0),
      Number(result.result_count || 0),
      listed,
    );
    $(".sample-file-results-title").textContent = "Chọn Sample";
    $(".sample-file-results-count").textContent =
      total > listed ? `${listed}/${total} kết quả` : `${listed} kết quả`;
    setSampleFileResultsExtras(
      result.truncated
        ? `Chỉ hiện ${listed} dòng đầu; thêm điều kiện để thu hẹp.`
        : "",
      false,
    );
    list.innerHTML = result.samples.map((sample) => {
      const meta = [
        sample.sample_no ? `Sample ${escapeHtml(sample.sample_no)}` : "",
        sample.created_by ? `Tạo bởi ${escapeHtml(sample.created_by)}` : "",
        sample.buyer ? `Buyer ${escapeHtml(sample.buyer)}` : "",
      ].filter(Boolean).join(" · ");
      const checked = sampleCheckedChoices.has(sample.choice_id);
      return `<button type="button" class="catalog-result-row${
        checked ? " is-checked" : ""
      }" role="option"
        data-sample-choice-id="${escapeHtml(sample.choice_id || "")}"
        ${checked ? 'data-tooltip="Đã xem file"' : ""}>
        <span class="catalog-result-code">${escapeHtml(sample.style_code || "—")}</span>
        <span class="catalog-result-meta">${meta}</span>
      </button>`;
    }).join("");
    wrap.hidden = false;
    return;
  }
  if (result.code === "CATALOG_FILES_SCANNED"
      && Array.isArray(result.files)) {
    if (result.choice_id) sampleCheckedChoices.add(result.choice_id);
    const style = String(result.article_code || "").trim();
    $(".sample-file-results-title").textContent =
      style ? `File đính kèm · ${style}` : "File đính kèm";
    $(".sample-file-results-count").textContent = `${result.files.length} file`;
    // Mục click không xác nhận được thì "không có file" chỉ đúng một phần.
    const unread = (Array.isArray(result.sections) ? result.sections : [])
      .filter((section) => section && section.available === false)
      .map((section) => String(section.name || "").trim())
      .filter(Boolean);
    setSampleFileResultsExtras(
      unread.length ? `Chưa đọc được: ${unread.join(", ")}.` : "",
      Boolean(sampleChoiceResult),
    );
    let previousSection = "";
    list.innerHTML = result.files.length
      ? result.files.map((file) => {
        const section = String(file.section || "File");
        const heading = section !== previousSection
          ? `<div class="catalog-file-group-label" role="presentation">${
            escapeHtml(section)
          }</div>`
          : "";
        previousSection = section;
        const meta = [
          file.uploaded_on ? `Ngày: ${escapeHtml(file.uploaded_on)}` : "",
          file.uploaded_by ? `Bởi: ${escapeHtml(file.uploaded_by)}` : "",
        ].filter(Boolean).join(" · ");
        return `${heading}<button type="button"
          class="catalog-result-row catalog-file-row" role="option"
          data-file-id="${escapeHtml(file.file_id || "")}">
          <span class="catalog-file-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>
          </span>
          <span class="catalog-file-copy">
            <strong data-tooltip="${escapeHtml(file.file_name || "")}">${escapeHtml(file.file_name || "")}</strong>
            ${meta ? `<small>${meta}</small>` : ""}
            ${file.comments ? `<small>Ghi chú: ${escapeHtml(file.comments)}</small>` : ""}
          </span>
        </button>`;
      }).join("")
      : '<div class="catalog-results-empty">Không có file đính kèm trong 4 mục đã kiểm tra.</div>';
    wrap.hidden = false;
    return;
  }
  if (result.code === "NO_RESULTS") {
    sampleChoiceResult = null;
    $(".sample-file-results-title").textContent = "Kết quả";
    $(".sample-file-results-count").textContent = "";
    setSampleFileResultsExtras("", false);
    list.innerHTML = '<div class="catalog-results-empty">Không tìm thấy Sample phù hợp.</div>';
    wrap.hidden = false;
    return;
  }
  hideSampleFileResults();
}

async function openSampleFileChoice(row) {
  const choiceId = String(row?.dataset.sampleChoiceId || "");
  if (!choiceId) return;
  await withButtonLoading(
    row,
    () => call("open_sample_file_choice", choiceId),
  );
}

function hideSupplierInvoiceCancelResults() {
  const wrap = $(".supplier-invoice-cancel-results");
  if (!wrap) return;
  wrap.hidden = true;
  $(".supplier-invoice-cancel-results-title").textContent = "Chọn Supplier Invoice";
  $(".supplier-invoice-cancel-results-count").textContent = "";
  $(".supplier-invoice-cancel-results-list").innerHTML = "";
}

function renderSupplierInvoiceCancelResults(result) {
  const wrap = $(".supplier-invoice-cancel-results");
  const list = $(".supplier-invoice-cancel-results-list");
  if (!wrap || !list || result.code !== "SUPPLIER_INVOICE_MULTIPLE_RESULTS") return;
  const invoices = Array.isArray(result.invoices) ? result.invoices : [];
  if (!invoices.length) {
    hideSupplierInvoiceCancelResults();
    return;
  }
  // Danh sách gần đúng phải trông khác danh sách trùng khớp: người dùng đang
  // ở một bước bấm là Delete/Cancel thật trên WFX.
  $(".supplier-invoice-cancel-results-title").textContent = result.exact_match
    ? "Chọn Supplier Invoice để Cancel"
    : "Không có Invoice No. trùng khớp — chọn thủ công";
  $(".supplier-invoice-cancel-results-count").textContent =
    `${Number(result.result_count || invoices.length)} kết quả`;
  list.innerHTML = invoices.map((invoice) => {
    const meta = [
      invoice.supplier ? `Supplier ${escapeHtml(invoice.supplier)}` : "",
      invoice.po_no ? `PO ${escapeHtml(invoice.po_no)}` : "",
      invoice.asn_grn_no ? `ASN/GRN ${escapeHtml(invoice.asn_grn_no)}` : "",
      invoice.status ? `Status ${escapeHtml(invoice.status)}` : "",
    ].filter(Boolean).join(" · ");
    return `<button type="button" class="catalog-result-row" role="option"
      data-supplier-invoice-cancel-choice="${escapeHtml(invoice.choice_id || "")}">
      <span class="catalog-result-code">${escapeHtml(invoice.invoice_no || "—")}</span>
      <span class="catalog-result-meta">${meta}</span>
    </button>`;
  }).join("");
  wrap.hidden = false;
}

async function cancelSupplierInvoiceChoice(row) {
  const choiceId = String(row?.dataset.supplierInvoiceCancelChoice || "");
  if (!choiceId) return;
  const result = await withButtonLoading(
    row,
    () => call("cancel_supplier_invoice_choice", choiceId),
  );
  if (result?.ok) hideSupplierInvoiceCancelResults();
}

async function downloadCatalogFile(row) {
  const fileId = String(row?.dataset.fileId || "");
  if (!fileId) return;
  await withButtonLoading(
    row,
    () => call("download_catalog_file", fileId),
  );
}
