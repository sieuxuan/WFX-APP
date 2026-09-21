"use strict";
// Kết quả file Sample, huỷ hoá đơn nhà cung cấp, tải file.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function hideSampleFileResults() {
  const wrap = $(".sample-file-results");
  if (!wrap) return;
  wrap.hidden = true;
  $(".sample-file-results-title").textContent = "Kết quả";
  $(".sample-file-results-count").textContent = "";
  $(".sample-file-results-list").innerHTML = "";
}

function renderSampleFileResults(result) {
  const wrap = $(".sample-file-results");
  const list = $(".sample-file-results-list");
  if (!wrap || !list) return;
  if (result.code === "SAMPLE_MULTIPLE_RESULTS"
      && Array.isArray(result.samples) && result.samples.length) {
    $(".sample-file-results-title").textContent = "Chọn Sample";
    $(".sample-file-results-count").textContent =
      `${Number(result.result_count || result.samples.length)} kết quả`;
    list.innerHTML = result.samples.map((sample) => {
      const meta = [
        sample.sample_no ? `Sample ${escapeHtml(sample.sample_no)}` : "",
        sample.created_by ? `Tạo bởi ${escapeHtml(sample.created_by)}` : "",
        sample.buyer ? `Buyer ${escapeHtml(sample.buyer)}` : "",
      ].filter(Boolean).join(" · ");
      return `<button type="button" class="catalog-result-row" role="option"
        data-sample-choice-id="${escapeHtml(sample.choice_id || "")}">
        <span class="catalog-result-code">${escapeHtml(sample.style_code || "—")}</span>
        <span class="catalog-result-meta">${meta}</span>
      </button>`;
    }).join("");
    wrap.hidden = false;
    return;
  }
  if (result.code === "CATALOG_FILES_SCANNED"
      && Array.isArray(result.files)) {
    $(".sample-file-results-title").textContent = "File đính kèm";
    $(".sample-file-results-count").textContent = `${result.files.length} file`;
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
    $(".sample-file-results-title").textContent = "Kết quả";
    $(".sample-file-results-count").textContent = "";
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
