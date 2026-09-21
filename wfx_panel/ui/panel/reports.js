"use strict";
// Reports: tham số, xuất Excel và báo cáo phối màu.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function showReportList() {
  selectedReportId = "";
  $(".reports-list").hidden = false;
  $(".reports-detail").hidden = true;
  $(".report-parameters").hidden = true;
  $(".color-report-workspace").hidden = true;
  resetColorReportProgress();
}

function showReportDetail(reportId, title) {
  selectedReportId = reportId;
  $(".reports-list").hidden = true;
  $(".reports-detail").hidden = false;
  $(".reports-detail-title").textContent = title;
  $(".report-parameters").hidden = reportId !== "shipment_summary";
  $(".color-report-workspace").hidden =
    reportId !== "color_combination_production";
}

function renderReportParameters(result) {
  selectedReportId = String(result.report_id || "");
  const savedValues = result.saved_parameters || {};
  if (Object.keys(savedValues).length) {
    reportParameterCache.set(selectedReportId, savedValues);
  }
  const cachedValues = reportParameterCache.get(selectedReportId) || {};
  const section = $(".report-parameters");
  const fields = $(".report-parameters-fields");
  if (!section || !fields || !selectedReportId) return;
  $(".report-parameters-title").textContent =
    `Tham số: ${result.report_name || "báo cáo"}`;
  fields.innerHTML = (Array.isArray(result.parameters) ? result.parameters : [])
    .map((parameter) => {
      const key = escapeHtml(parameter.key || "");
      const label = escapeHtml(parameter.label || parameter.key || "Tham số");
      const required = parameter.required ? " required" : "";
      if (["select", "select_popup"].includes(parameter.type)) {
        const options = (parameter.options || []).map((option) => {
          const selected = String(option.value) === String(
            cachedValues[parameter.key] ?? parameter.value ?? ""
          )
            ? " selected" : "";
          return `<option value="${escapeHtml(option.value)}"${selected}>${escapeHtml(option.label)}</option>`;
        }).join("");
        return `<label class="report-parameter-field"><span>${label}</span><select data-report-parameter="${key}"${required}>${options}</select></label>`;
      }
      if (parameter.type === "multiselect") {
        const selectedValues = new Set(
          Array.isArray(cachedValues[parameter.key])
            ? cachedValues[parameter.key].map(String)
            : (Array.isArray(parameter.value) ? parameter.value.map(String) : [])
        );
        const available = Array.isArray(parameter.options) ? parameter.options : [];
        const optionRows = available.map((option) => `
          <label class="report-multi-option-row">
            <input type="checkbox" class="report-multi-option" value="${escapeHtml(option.value)}"${selectedValues.has(String(option.value)) ? " checked" : ""}/>
            <span>${escapeHtml(option.label)}</span>
          </label>`).join("");
        const allChecked = available.length > 0 && selectedValues.size === available.length;
        return `<div class="report-parameter-field" data-report-multiselect="${key}">
          <span>${label}</span>
          <details class="report-multi-dropdown">
            <summary><span class="report-multi-summary">Đã chọn ${selectedValues.size}/${available.length}</span></summary>
            <div class="report-multi-menu">
              <label class="report-multi-option-row report-multi-all">
                <input type="checkbox" class="report-multi-select-all"${allChecked ? " checked" : ""}/>
                <span>Chọn tất cả</span>
              </label>
              ${optionRows}
            </div>
          </details>
        </div>`;
      }
      if (parameter.type === "checkbox") {
        const checked = cachedValues[parameter.key] ?? parameter.value;
        return `<label class="report-parameter-field report-parameter-check"><input type="checkbox" data-report-parameter="${key}"${checked ? " checked" : ""}/><span>${label}</span></label>`;
      }
      const type = ["date", "number", "text"].includes(parameter.type)
        ? parameter.type : "text";
      let value = cachedValues[parameter.key] ?? parameter.value ?? "";
      if (type === "date") {
        const match = String(value).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (match) {
          value = `${match[3]}-${match[1].padStart(2, "0")}-${match[2].padStart(2, "0")}`;
        }
        return `<label class="report-parameter-field"><span>${label}</span>
          <span class="report-date-control">
            <input type="date" data-report-parameter="${key}" value="${escapeHtml(value)}"${required}/>
            <button type="button" class="report-date-picker-button" data-report-date-picker="${key}" aria-label="Mở lịch chọn ${label}">📅</button>
          </span>
        </label>`;
      }
      return `<label class="report-parameter-field"><span>${label}</span><input type="${type}" data-report-parameter="${key}" value="${escapeHtml(value)}"${required}/></label>`;
    }).join("") || "<small>Report này không yêu cầu tham số.</small>";
  fields.querySelectorAll('[data-report-multiselect]').forEach((wrapper) => {
    const sync = () => {
      const options = [...wrapper.querySelectorAll('.report-multi-option')];
      const checked = options.filter((option) => option.checked).length;
      wrapper.querySelector('.report-multi-summary').textContent =
        `Đã chọn ${checked}/${options.length}`;
      wrapper.querySelector('.report-multi-select-all').checked =
        options.length > 0 && checked === options.length;
    };
    wrapper.querySelector('.report-multi-select-all').addEventListener('change', (event) => {
      wrapper.querySelectorAll('.report-multi-option').forEach((option) => {
        option.checked = event.target.checked;
      });
      sync();
    });
    wrapper.querySelectorAll('.report-multi-option').forEach((option) =>
      option.addEventListener('change', sync));
    sync();
  });
  fields.querySelectorAll('.report-date-picker-button').forEach((button) => {
    button.addEventListener('click', () => {
      const input = fields.querySelector(
        `[data-report-parameter="${CSS.escape(button.dataset.reportDatePicker || "")}"]`
      );
      if (!input) return;
      input.focus();
      try {
        if (typeof input.showPicker === "function") input.showPicker();
        else input.click();
      } catch (_error) {
        input.click();
      }
    });
  });
  section.hidden = false;
}

function setColorReportLevelsBusy(fromKey) {
  const order = ["division", "buyer", "season"];
  const from = order.indexOf(fromKey);
  order.slice(Math.max(0, from + 1)).forEach((key) => {
    const select = $(`.color-report-level[data-level="${key}"]`);
    if (!select) return;
    select.disabled = true;
    select.innerHTML = '<option value="">Đang tải…</option>';
  });
  colorReportState.styleRefs = [];
  colorReportState.selected = new Set();
  renderColorReportStyles();
}

function renderColorReportLevels(result) {
  const levels = result?.levels || {};
  ["division", "buyer", "season"].forEach((key) => {
    const select = $(`.color-report-level[data-level="${key}"]`);
    if (!select) return;
    const options = Array.isArray(levels[key]?.options) ? levels[key].options : [];
    colorReportState.levels[key] = options;
    select.innerHTML = ['<option value="">— chọn —</option>'].concat(
      options.map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`),
    ).join("");
    select.value = String(levels[key]?.value || "");
    select.disabled = options.length === 0;
  });
  colorReportState.styleRefs = Array.isArray(levels.style_ref?.options)
    ? levels.style_ref.options : [];
  colorReportState.selected = new Set(
    colorReportState.styleRefs.map((option) => String(option.value)),
  );
  renderColorReportStyles();
}

function applyColorReportFilter() {
  const needle = ($(".color-report-style-filter")?.value || "")
    .trim().toLocaleLowerCase("vi");
  $(".color-report-style-list")?.querySelectorAll("label").forEach((row) => {
    row.hidden = Boolean(needle)
      && !row.textContent.toLocaleLowerCase("vi").includes(needle);
  });
}

function updateColorReportCount() {
  const count = $(".color-report-style-count");
  if (count) count.textContent =
    `${colorReportState.selected.size}/${colorReportState.styleRefs.length}`;
}

function renderColorReportStyles() {
  const list = $(".color-report-style-list");
  const single = $(".color-report-single-select");
  const batchToggle = $(".color-report-batch-toggle");
  if (!list || !single || !batchToggle) return;
  const batch = batchToggle.checked;
  list.innerHTML = colorReportState.styleRefs.map((option) => {
    const value = escapeHtml(option.value);
    const checked = colorReportState.selected.has(String(option.value));
    return `<label><input type="checkbox" class="color-report-style" value="${value}"${checked ? " checked" : ""} /><span>${escapeHtml(option.label)}</span></label>`;
  }).join("");
  single.innerHTML = ['<option value="">— chọn style —</option>'].concat(
    colorReportState.styleRefs.map((option) =>
      `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`),
  ).join("");
  $(".color-report-style-block").hidden = !batch;
  $(".color-report-single-style").hidden = batch;
  list.querySelectorAll(".color-report-style").forEach((box) =>
    box.addEventListener("change", () => {
      if (box.checked) colorReportState.selected.add(box.value);
      else colorReportState.selected.delete(box.value);
      updateColorReportCount();
    }),
  );
  applyColorReportFilter();
  updateColorReportCount();
}

function setColorReportSelection(selected) {
  $(".color-report-style-list")?.querySelectorAll("label").forEach((row) => {
    if (row.hidden) return;
    const box = row.querySelector(".color-report-style");
    if (!box) return;
    box.checked = selected;
    if (selected) colorReportState.selected.add(box.value);
    else colorReportState.selected.delete(box.value);
  });
  updateColorReportCount();
}

function colorReportSelection() {
  return Object.fromEntries(["division", "buyer", "season"].map((key) => [
    key,
    $(`.color-report-level[data-level="${key}"]`)?.value || "",
  ]));
}

function resetColorReportProgress({ show = false, total = 0 } = {}) {
  const card = $(".color-report-progress-card");
  if (card) {
    card.hidden = !show;
    $(".color-report-progress-count").textContent = `0/${total}`;
    $(".color-report-progress-style").textContent = "";
    $(".color-report-progress-track > i").style.width = "0%";
  }
  $(".color-report-result-card").hidden = true;
  $(".color-report-result-card").innerHTML = "";
}

function updateColorReportProgress(progress) {
  const card = $(".color-report-progress-card");
  if (!card || !progress || !colorReportRunActive) return;
  card.hidden = false;
  const counter = /(\d+\/\d+)\s*$/.exec(String(progress.message || ""));
  const step = Math.max(1, Number(progress.step || 1));
  const total = Math.max(1, Number(progress.total || 1));
  $(".color-report-progress-count").textContent = counter
    ? counter[1] : `${step}/${total}`;
  $(".color-report-progress-style").textContent =
    String(progress.message || "").replace(/\s*\d+\/\d+\s*$/, "");
  $(".color-report-progress-track > i").style.width =
    `${Math.round((step / total) * 100)}%`;
  if (busy && progress.message) {
    setStatus("neutral", progress.message);
  }
}

function renderColorReportResult(result) {
  const card = $(".color-report-result-card");
  if (!card || !result) return;
  $(".color-report-progress-card").hidden = true;
  const saved = Array.isArray(result.saved) ? result.saved : [];
  const failed = Array.isArray(result.failed) ? result.failed : [];
  if (!saved.length && !failed.length) {
    card.hidden = true;
    return;
  }
  const failedRows = failed.map((item) =>
    `<div class="color-report-result-row"><strong>${escapeHtml(item.style_ref)}</strong><span>${escapeHtml(item.message)}</span></div>`,
  ).join("");
  const savedRows = saved.map((item) =>
    `<div class="color-report-result-row"><strong>${escapeHtml(item.style_ref)}</strong><span>${escapeHtml(item.file_name)}</span></div>`,
  ).join("");
  card.innerHTML = `
    <div class="color-report-result-row"><span class="chip">${saved.length} thành công</span><span class="chip">${failed.length} lỗi</span></div>
    ${failedRows}
    ${saved.length ? `<details><summary>${saved.length} style đã tải</summary>${savedRows}</details>` : ""}
    <div class="color-report-result-actions">
      ${failed.length ? `<button type="button" class="module-secondary-button" data-color-report-result-action="retry">Chạy lại ${failed.length} style lỗi</button>` : ""}
      <button type="button" class="module-secondary-button" data-color-report-result-action="open-dir">Mở thư mục</button>
    </div>`;
  card.dataset.failedRefs = JSON.stringify(
    failed.map((item) => String(item.style_ref)),
  );
  card.querySelector('[data-color-report-result-action="retry"]')?.addEventListener(
    "click", () => runColorReportBatch(
      JSON.parse(card.dataset.failedRefs || "[]"),
    ),
  );
  card.querySelector('[data-color-report-result-action="open-dir"]')?.addEventListener(
    "click", () => callQuiet("open_report_export_dir", colorReportState.outputDir),
  );
  card.hidden = false;
}

async function loadColorReportOptions(fromKey = "") {
  const revision = ++colorReportOptionsRevision;
  if (fromKey) setColorReportLevelsBusy(fromKey);
  if (!fromKey) {
    showReportDetail(
      "color_combination_production", "Color Combination - Production",
    );
  }
  const result = await call("load_color_report_options", colorReportSelection());
  if (revision !== colorReportOptionsRevision) return result;
  // Kể cả mùa không có style, backend vẫn trả các cấp cascade để user có
  // thể nhìn thấy và chọn lại Season thay vì bị kẹt ở danh sách cũ.
  if (result?.levels) renderColorReportLevels(result);
  return result;
}

async function chooseColorReportDir() {
  const result = await callQuiet("choose_report_export_dir");
  if (result?.ok) {
    colorReportState.outputDir = String(result.output_dir || "");
    $(".color-report-dir-path").textContent = colorReportState.outputDir;
  }
  return result;
}

async function runColorReportBatch(onlyRefs = null) {
  const batch = $(".color-report-batch-toggle").checked;
  const refs = onlyRefs || (batch
    ? colorReportState.styleRefs.map((option) => String(option.value))
      .filter((value) => colorReportState.selected.has(value))
    : [$(".color-report-single-select").value].filter(Boolean));
  resetColorReportProgress({ show: true, total: refs.length });
  colorReportRunActive = true;
  let result = null;
  try {
    result = await call(
      "run_color_report_batch",
      colorReportSelection(), refs, colorReportState.outputDir,
    );
    return result;
  } finally {
    colorReportRunActive = false;
    if (result) renderColorReportResult(result);
  }
}

async function loadShipmentSummaryReport() {
  if (selectedReportId) {
    reportParameterCache.set(selectedReportId, reportParameterValues());
  }
  showReportDetail("shipment_summary", "Shipment Summary");
  const result = await runSelectedModuleAction(
    "load_report_parameters", "shipment_summary"
  );
  if (result?.ok) renderReportParameters(result);
  return result;
}

function reportParameterValues() {
  const values = {};
  $$('[data-report-parameter]').forEach((field) => {
    values[field.dataset.reportParameter] = field.type === "checkbox"
      ? field.checked : field.value;
  });
  $$('[data-report-multiselect]').forEach((wrapper) => {
    values[wrapper.dataset.reportMultiselect] = [
      ...wrapper.querySelectorAll('.report-multi-option:checked')
    ].map((option) => option.value);
  });
  return values;
}

function exportSelectedReport() {
  if (!selectedReportId) {
    setStatus("warning", "Hãy chọn báo cáo để tải tham số trước.");
    return null;
  }
  const values = reportParameterValues();
  reportParameterCache.set(selectedReportId, values);
  return runSelectedModuleAction("export_report_excel", selectedReportId, values);
}

function setReportLastMonth() {
  const dateFields = [...$(".report-parameters-fields").querySelectorAll(
    'input[type="date"][data-report-parameter]'
  )];
  if (dateFields.length < 2) {
    setStatus("warning", "Báo cáo chưa tải đủ hai tham số ngày.");
    return null;
  }
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last = new Date(now.getFullYear(), now.getMonth(), 0);
  const format = (date) => [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
  dateFields[0].value = format(first);
  dateFields[dateFields.length - 1].value = format(last);
  setStatus("success", "Đã chọn toàn bộ tháng trước.");
  return { ok: true };
}

async function saveSelectedReportParameters() {
  if (!selectedReportId) {
    setStatus("warning", "Hãy chọn báo cáo để tải tham số trước.");
    return null;
  }
  const values = reportParameterValues();
  const result = await call("save_report_parameters", selectedReportId, values);
  if (result?.ok) reportParameterCache.set(selectedReportId, values);
  return result;
}
