"use strict";
// Upload OC New/Revise, Confirm và Reject All.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function renderOcUploadResult(result, fileName = "") {
  const panel = $(".oc-upload-result");
  if (!panel || !result) return;
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const details = [...warnings, ...errors].slice(0, 12);
  panel.dataset.valid = String(Boolean(result.ok));
  panel.innerHTML = `
    <strong>${escapeHtml(result.ok ? "Hoàn tất" : "Cần kiểm tra")}</strong>
    <span>${escapeHtml(result.message || "")}</span>
    ${fileName ? `<small>${escapeHtml(fileName)}</small>` : ""}
    ${result.buyer ? `<small>Buyer: ${escapeHtml(result.buyer)} · ${escapeHtml(result.row_count || 0)} dòng</small>` : ""}
    ${details.length ? `<ul>${details.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
  panel.hidden = false;
}

function hideOcUploadReview() {
  const review = $(".oc-upload-review");
  if (review) review.hidden = true;
}

function syncOcUploadReviewActions() {
  const hasReview = Boolean(pendingOcReview?.token);
  const downloadButton = $('[data-module-action="oc-review-download"]');
  const confirmButton = $('[data-module-action="oc-review-confirm"]');
  if (downloadButton) downloadButton.disabled = !hasReview;
  if (confirmButton) {
    confirmButton.disabled = !hasReview || !pendingOcReview.downloaded;
  }
}

function renderOcUploadReview(result, fileName = "") {
  const review = $(".oc-upload-review");
  if (!review || !result?.ok || !result.review_token) return;
  pendingOcReview = {
    token: result.review_token,
    fileName: fileName || result.source_file || "",
    downloaded: false,
  };
  $(".oc-review-file").textContent = pendingOcReview.fileName;
  $(".oc-review-mode").textContent = result.mode === "revise" ? "REVISE" : "NEW";
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
  renderOcUploadResult({
    ok: true,
    message: "Đã chọn file; app đang kiểm tra và tổng hợp review…",
  }, selected.file_name);
  const result = await call("review_oc_upload", mode, selected.file_path);
  if (selectionRevision !== ocSelectionRevision) {
    if (result?.review_token) {
      callQuiet("cancel_oc_upload_review", result.review_token);
    }
    return null;
  }
  if (result?.ok) {
    renderOcUploadReview(result, selected.file_name);
    renderOcUploadResult({
      ...result,
      message: "File hợp lệ. Hãy tải form EDI xuống máy trước khi tự Upload.",
    }, selected.file_name);
  } else if (result) {
    pendingOcReview = null;
    hideOcUploadReview();
    renderOcUploadResult(result, selected.file_name);
  }
  return result;
}

async function cancelOcUploadReview() {
  ocSelectionRevision += 1;
  const token = pendingOcReview?.token || "";
  pendingOcReview = null;
  syncOcUploadReviewActions();
  hideOcUploadReview();
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
  if (saved?.ok && pendingOcReview?.token === token) {
    pendingOcReview.downloaded = true;
    syncOcUploadReviewActions();
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
  pendingOcReview = null;
  syncOcUploadReviewActions();
  hideOcUploadReview();
  if (result) renderOcUploadResult(result, fileName);
  return result;
}

async function confirmOcPending(mode) {
  const result = await call("confirm_oc_pending", mode);
  if (result) renderOcUploadResult(result);
  return result;
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
