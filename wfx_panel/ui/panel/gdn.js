"use strict";
// (GDN) Dispatch: tiến độ 6 bước và checkpoint EDI.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

const GDN_PROGRESS_STAGES = [
  "report", "download", "workbook", "edi", "package", "transaction",
];

function updateGdnProgress(progress) {
  const card = $(".dispatch-progress-card");
  if (!card || !progress) return;
  card.hidden = false;
  const step = Math.max(1, Math.min(6, Number(progress.step || 1)));
  const state = String(progress.state || "active");
  $(".dispatch-progress-count").textContent = `${step}/6`;
  $(".dispatch-progress-message").textContent = progress.message || "";
  GDN_PROGRESS_STAGES.forEach((stage, index) => {
    const item = $(`[data-dispatch-stage="${stage}"]`);
    if (!item) return;
    item.dataset.state = index + 1 < step
      ? "completed"
      : (index + 1 === step ? state : "waiting");
  });
  const checkpoint = $(".dispatch-checkpoint");
  checkpoint.hidden = !["failed", "pending"].includes(state)
    || progress.stage !== "transaction";
  if (busy && progress.message) {
    setStatus("neutral", progress.message);
  }
}
window.wfxHandleBackendProgress = (progress) => {
  const handler = BACKEND_PROGRESS_HANDLERS[String(progress?.method || "")];
  if (handler) handler(progress);
};

function resetGdnProgress() {
  updateGdnProgress({
    stage: "report",
    message: "Đang khởi tạo luồng GDN…",
    step: 1,
    state: "active",
  });
  $(".dispatch-checkpoint").hidden = true;
}

function finishGdnProgress(result) {
  if (!result || result.code === "GDN_STATUS_READY") return;
  if (result.code === "GDN_DISPATCH_COMPLETED") {
    updateGdnProgress({
      stage: "transaction",
      message: result.message,
      step: 6,
      state: "completed",
    });
    return;
  }
  if (!result.failed_stage) return;
  const step = Number(result.failed_step || (
    GDN_PROGRESS_STAGES.indexOf(result.failed_stage) + 1
  ));
  updateGdnProgress({
    stage: result.failed_stage,
    message: result.message,
    step,
    state: result.checkpoint === "inspect_edi" ? "pending" : "failed",
  });
  $(".dispatch-checkpoint").hidden = result.checkpoint !== "inspect_edi";
}

function syncGdnDispatchAction() {
  const invoice = String($(".gdn-invoice-query")?.value || "").trim();
  const confirmed = $(".gdn-grn-confirm-input")?.checked === true;
  const submit = $(".dispatch-submit-button");
  if (submit) submit.disabled = busy || !invoice || !confirmed;
}

async function submitGdnDispatch() {
  const invoice = String($(".gdn-invoice-query")?.value || "").trim();
  const confirmed = $(".gdn-grn-confirm-input")?.checked === true;
  if (!confirmed) {
    setStatus(
      "warning",
      "Chỉ Submit sau khi GRN xong ít nhất 15 phút.",
    );
    return null;
  }
  if (!invoice) {
    setStatus("warning", "Hãy nhập Invoice GRN trước khi Submit.");
    $(".gdn-invoice-query")?.focus();
    return null;
  }
  resetGdnProgress();
  return runSelectedModuleAction("run_gdn_dispatch", invoice, confirmed);
}
