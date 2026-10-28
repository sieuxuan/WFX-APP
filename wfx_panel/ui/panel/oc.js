"use strict";
// Upload OC New/Revise, Confirm và Reject All.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

// Lỗi file OC có thể dài tới vài trăm dòng; danh sách cuộn được nhưng vẫn
// phải nói rõ còn bao nhiêu mục bị cắt để user không tưởng đã sửa hết.
const OC_RESULT_DETAIL_LIMIT = 40;

function ocResultTitle(result, pending) {
  if (pending) return "Đang kiểm tra";
  if (result.code === "ACTION_CANCELLED") return "Đã dừng";
  return result.ok ? "Hoàn tất" : "Cần kiểm tra";
}

function ocResultState(result, pending) {
  if (pending) return "pending";
  if (result.code === "ACTION_CANCELLED") return "warning";
  return String(Boolean(result.ok));
}

// Số liệu tiến độ của Confirm/Reject/Upload: user cần biết flow đã đi tới
// đâu trước khi dừng, vì cả ba đều không tự chạy lại.
function ocResultFacts(result) {
  const facts = [];
  if (result.buyer) {
    const rows = Number(result.row_count || 0);
    facts.push(`Buyer: ${result.buyer}${rows ? ` · ${rows.toLocaleString("en-US")} dòng` : ""}`);
  }
  if (result.error_stage) facts.push(`Bước lỗi: ${result.error_stage}`);
  if (result.destination_tab) facts.push(`Transaction nằm ở tab ${result.destination_tab}`);
  if (Number.isFinite(result.confirmed_styles)) {
    facts.push(`Đã Confirm: ${result.confirmed_styles} Style`);
  }
  if (Number(result.selected_sales_orders) > 0) {
    facts.push(`Đã chọn WFX Sales Order: ${result.selected_sales_orders}`);
  }
  if (Number.isFinite(result.rejected_rows)) {
    facts.push(`Đã Reject: ${result.rejected_rows} PO`);
  }
  if (result.stopped_style) facts.push(`Dừng tại Style: ${result.stopped_style}`);
  else if (result.stopped_row) facts.push(`Dừng tại: ${result.stopped_row}`);
  return facts;
}

function ocDetailList(items, className) {
  if (!items.length) return "";
  const shown = items.slice(0, OC_RESULT_DETAIL_LIMIT);
  const hidden = items.length - shown.length;
  return `<ul class="${className}">${shown.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}${
    hidden > 0 ? `<li class="oc-result-more">… và ${hidden} mục khác</li>` : ""
  }</ul>`;
}

// Sau khi Create Transaction thành công, bước kế tiếp luôn là Confirm đúng tab
// vừa nhận transaction. Nút này chỉ là lối tắt có nhãn riêng, không tự chạy.
function syncOcNextAction(result) {
  const button = $(".oc-upload-next-button");
  if (!button) return;
  const tab = result?.ok && result.code === "OC_TRANSACTION_CREATED"
    ? result.destination_tab
    : "";
  button.hidden = !tab;
  button.dataset.mode = tab === "Revision" ? "revision" : "new";
  button.textContent = `Confirm ngay tab ${tab || "New"}`;
}

function renderOcUploadResult(result, fileName = "", { pending = false } = {}) {
  const panel = $(".oc-upload-result");
  const body = $(".oc-upload-result-body");
  if (!panel || !body || !result) return;
  const errors = Array.isArray(result.errors) ? result.errors.map(String) : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings.map(String) : [];
  const options = Array.isArray(result.sales_order_options)
    ? result.sales_order_options.map(String)
    : [];
  const facts = ocResultFacts(result);
  panel.dataset.valid = ocResultState(result, pending);
  body.innerHTML = `
    <strong>${escapeHtml(ocResultTitle(result, pending))}</strong>
    <span>${escapeHtml(result.message || "")}</span>
    ${fileName ? `<small class="oc-result-file">${escapeHtml(fileName)}</small>` : ""}
    ${facts.map((fact) => `<small>${escapeHtml(fact)}</small>`).join("")}
    ${errors.length ? `<small class="oc-result-section">${errors.length} lỗi cần sửa</small>` : ""}
    ${ocDetailList(errors, "oc-result-errors")}
    ${options.length ? `<small class="oc-result-section">WFX Sales Order cần chọn thủ công</small>` : ""}
    ${ocDetailList(options, "oc-result-options")}
    ${warnings.length ? `<small class="oc-result-section">${warnings.length} lưu ý</small>` : ""}
    ${ocDetailList(warnings, "oc-result-warnings")}
  `;
  syncOcNextAction(pending ? null : result);
  panel.hidden = false;
  if (!pending && (errors.length || !result.ok)) {
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function hideOcUploadReview() {
  const review = $(".oc-upload-review");
  if (review) review.hidden = true;
}

function syncOcUploadReviewActions() {
  const hasReview = Boolean(pendingOcReview?.token);
  const downloaded = Boolean(hasReview && pendingOcReview.downloaded);
  const downloadButton = $('[data-module-action="oc-review-download"]');
  const confirmButton = $('[data-module-action="oc-review-confirm"]');
  if (downloadButton) {
    downloadButton.disabled = !hasReview;
    downloadButton.dataset.done = String(downloaded);
    downloadButton.textContent = downloaded ? "✓ Đã tải file EDI" : "1 · Tải file EDI";
  }
  if (confirmButton) confirmButton.disabled = !downloaded;
  const hint = $(".oc-review-hint");
  if (hint) {
    hint.textContent = !hasReview
      ? ""
      : downloaded
        ? `Đã lưu ${pendingOcReview.savedName || "file EDI"}. Bấm Xác nhận Upload để Process Package và Create Transaction trên WFX.`
        : "Tải file EDI xuống máy trước: nếu WFX báo lỗi, bạn có sẵn đúng file để tự Upload lại.";
  }
}

function renderOcUploadReview(result, fileName = "") {
  const review = $(".oc-upload-review");
  if (!review || !result?.ok || !result.review_token) return;
  pendingOcReview = {
    token: result.review_token,
    fileName: fileName || result.source_file || "",
    downloaded: false,
    savedName: "",
  };
  const rows = Number(result.row_count || 0).toLocaleString("en-US");
  $(".oc-review-file").textContent = `${pendingOcReview.fileName} · ${rows} dòng`;
  $(".oc-review-file").dataset.tooltip = pendingOcReview.fileName;
  $(".oc-review-mode").textContent = result.mode === "revise" ? "REVISE" : "NEW";
  $(".oc-review-mode").dataset.mode = result.mode === "revise" ? "revise" : "new";
  $(".oc-review-buyer").textContent = result.buyer || "—";
  $(".oc-review-season").textContent = result.season || "—";
  $(".oc-review-po").textContent = Number(result.po_count || 0).toLocaleString("en-US");
  $(".oc-review-style").textContent = Number(result.style_count || 0).toLocaleString("en-US");
  $(".oc-review-units").textContent = Number(result.total_units || 0).toLocaleString("en-US");
  const warning = $(".oc-review-warning");
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  warning.textContent = warnings.join(" · ");
  warning.hidden = warnings.length === 0;
  syncOcUploadReviewActions();
  review.hidden = false;
  review.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function dropOcUploadReview() {
  pendingOcReview = null;
  syncOcUploadReviewActions();
  hideOcUploadReview();
}

async function uploadOcFile(mode) {
  const selectionRevision = ++ocSelectionRevision;
  const selected = await callQuiet("choose_oc_upload_file", mode);
  if (selectionRevision !== ocSelectionRevision) return null;
  if (!selected || !selected.ok) {
    if (selected && selected.code !== "OC_FILE_DIALOG_CANCELLED") {
      renderOcUploadResult(selected);
      handleResult(selected);
    }
    return selected;
  }
  // Backend bỏ review cũ ngay khi kiểm tra file mới, nên review đang hiện
  // không còn bấm Xác nhận được nữa; ẩn luôn để khỏi nhầm hai file.
  dropOcUploadReview();
  renderOcUploadResult({
    ok: true,
    message: "App đang kiểm tra file và tổng hợp số liệu review…",
  }, selected.file_name, { pending: true });
  const result = await call("review_oc_upload", mode, selected.file_path);
  if (selectionRevision !== ocSelectionRevision) {
    if (result?.review_token) {
      callQuiet("cancel_oc_upload_review", result.review_token);
    }
    return null;
  }
  if (result?.ok) {
    renderOcUploadReview(result, selected.file_name);
    $(".oc-upload-result").hidden = true;
  } else if (result) {
    dropOcUploadReview();
    renderOcUploadResult(result, selected.file_name);
  }
  return result;
}

async function cancelOcUploadReview() {
  ocSelectionRevision += 1;
  const token = pendingOcReview?.token || "";
  dropOcUploadReview();
  if (!token) return null;
  const result = await callQuiet("cancel_oc_upload_review", token);
  if (result) renderOcUploadResult(result);
  return result;
}

async function downloadOcUploadFile() {
  if (!pendingOcReview?.token) return null;
  const { token, fileName } = pendingOcReview;
  const selected = await callQuiet("choose_oc_upload_export_file", fileName);
  if (!selected?.ok) {
    if (selected && selected.code !== "OC_FILE_DIALOG_CANCELLED") {
      renderOcUploadResult(selected, fileName);
      handleResult(selected);
    }
    return selected;
  }
  const saved = await call("save_oc_upload_file", token, selected.file_path);
  if (saved?.code === "OC_UPLOAD_REVIEW_EXPIRED" && pendingOcReview?.token === token) {
    dropOcUploadReview();
  }
  if (saved?.ok && pendingOcReview?.token === token) {
    pendingOcReview.downloaded = true;
    pendingOcReview.savedName = saved.file_name || "";
    syncOcUploadReviewActions();
    if (saved.renamed_for_open_file) {
      setStatus("warning", saved.message || "");
    }
  } else if (saved) {
    renderOcUploadResult(saved, saved.file_name || fileName);
  }
  return saved;
}

async function confirmOcUploadReview() {
  if (!pendingOcReview?.token || !pendingOcReview.downloaded) {
    setStatus("warning", "Hãy tải file EDI xuống máy trước khi Xác nhận Upload.");
    return null;
  }
  const { token, fileName } = pendingOcReview;
  const result = await call("confirm_oc_upload", token);
  dropOcUploadReview();
  if (result) renderOcUploadResult(result, fileName);
  return result;
}

async function confirmOcPending(mode) {
  const result = await call("confirm_oc_pending", mode);
  if (result) renderOcUploadResult(result);
  return result;
}

async function confirmOcFromUploadResult() {
  const mode = $(".oc-upload-next-button")?.dataset.mode === "revision"
    ? "revision"
    : "new";
  return confirmOcPending(mode);
}

async function rejectAllOcPending() {
  const accepted = window.confirm(
    "Reject toàn bộ PO trong tab New hoặc Revision đang mở? " +
    "Ứng dụng sẽ xử lý lần lượt và không thể hoàn tác.",
  );
  if (!accepted) return null;
  const result = await call("reject_all_oc_pending");
  if (result) renderOcUploadResult(result);
  return result;
}
