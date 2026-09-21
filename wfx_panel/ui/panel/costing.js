"use strict";
// Costing: export, kiểm tra file, dry-run và apply.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function resetCostingPlan() {
  costingPlanToken = "";
  costingPlanDeleteCount = 0;
  costingArticleResolutions = {};
  const plan = $(".catalog-costing-plan");
  if (plan) plan.hidden = true;
  if ($(".catalog-costing-counts")) {
    $(".catalog-costing-counts").innerHTML = "";
  }
  if ($(".catalog-costing-warnings")) {
    $(".catalog-costing-warnings").hidden = true;
    $(".catalog-costing-warnings").textContent = "";
  }
  const resolutions = $(".catalog-costing-resolutions");
  if (resolutions) {
    resolutions.hidden = true;
    resolutions.innerHTML = "";
  }
}

function discardCostingPlan() {
  const token = costingPlanToken;
  resetCostingPlan();
  if (token) {
    Promise.resolve(
      callQuiet("clear_catalog_costing_plan", token)
    ).catch(() => {});
  }
}

function renderCostingPlan(result) {
  costingPlanToken = String(result?.plan_token || "");
  costingPlanDeleteCount = Number(result?.counts?.deletes || 0);
  costingArticleResolutions = {};
  const plan = $(".catalog-costing-plan");
  if (!plan || !costingPlanToken) return;
  const counts = result.counts || {};
  $(".catalog-costing-plan-title").textContent =
    "Dry-run · cập nhật Costing Open";
  $(".catalog-costing-plan-file").textContent =
    `${result.file_name || "Costing"} · ${result.style_code || ""}`;
  const countItems = [
    ["Field", counts.fields_to_set || 0],
    ["Thêm", counts.additions || 0],
    ["Thêm chi phí", counts.cost_line_additions || 0],
    ["Split", counts.splits || 0],
    ["Cập nhật", counts.updates || 0],
    ["Xóa", counts.deletes || 0],
    ["Cảnh báo", (counts.warnings || 0) + (counts.unsupported_fields || 0)],
  ];
  $(".catalog-costing-counts").innerHTML = countItems.map(
    ([label, value]) => `<span><b>${Number(value)}</b>${escapeHtml(label)}</span>`
  ).join("");
  const warningCount = (
    (counts.warnings || 0)
    + (counts.unsupported_fields || 0)
    + (Array.isArray(result.missing_sections) ? result.missing_sections.length : 0)
  );
  const warning = $(".catalog-costing-warnings");
  warning.hidden = warningCount === 0;
  warning.textContent = warningCount
    ? `${warningCount} mục sẽ không được ghi. Xem Log kỹ thuật trước.`
    : "";
  $(".catalog-costing-apply").disabled =
    !costingPlanToken
    || (Array.isArray(result.ambiguous_articles)
      && result.ambiguous_articles.length > 0);
  plan.hidden = false;
  window.setTimeout(() => $(".catalog-costing-apply")?.focus(), 0);
}

function renderCostingAmbiguities(result) {
  const ambiguities = Array.isArray(result?.ambiguous_articles)
    ? result.ambiguous_articles : [];
  if (!ambiguities.length) return;
  costingPlanToken = String(result?.plan_token || costingPlanToken);
  costingArticleResolutions = {};
  const host = $(".catalog-costing-resolutions");
  if (!host) return;
  host.innerHTML = ambiguities.map((item, index) => {
    const itemKey = String(item.import_item_key || item.item_key || `item-${index}`);
    const options = (item.candidates || []).map((candidate) => {
      const code = String(candidate.article_code || "");
      const name = String(candidate.article_name || "");
      return `<option value="${escapeHtml(code)}">`
        + `${escapeHtml(code)} · ${escapeHtml(name)}</option>`;
    }).join("");
    return `<label class="catalog-costing-resolution">
      <strong>${escapeHtml(item.article_name || item.article_code || itemKey)}</strong>
      <select data-costing-resolution="${escapeHtml(itemKey)}">
        <option value="">Chọn đúng Article Code…</option>${options}
      </select>
    </label>`;
  }).join("");
  host.querySelectorAll("[data-costing-resolution]").forEach((select) => {
    select.addEventListener("change", () => {
      const key = String(select.dataset.costingResolution || "");
      const value = String(select.value || "");
      if (value) costingArticleResolutions[key] = value;
      else delete costingArticleResolutions[key];
      $(".catalog-costing-apply").disabled =
        Object.keys(costingArticleResolutions).length !== ambiguities.length;
    });
  });
  host.hidden = false;
  const warning = $(".catalog-costing-warnings");
  warning.hidden = false;
  warning.textContent =
    "WFX tìm thấy nhiều Article trùng tên. Chọn đúng Article Code để tiếp tục.";
  $(".catalog-costing-apply").disabled = true;
  $(".catalog-costing-plan").hidden = false;
}

function renderCostingFileCheck(result, fileName = "") {
  const host = $(".catalog-costing-file-check");
  if (!host) return;
  const errors = Array.isArray(result?.validation_errors)
    ? result.validation_errors.filter(Boolean)
    : [];
  host.dataset.valid = String(Boolean(result?.ok));
  if (result?.ok) {
    host.innerHTML =
      `<strong>${escapeHtml(fileName || result.file_name || "File")} hợp lệ</strong>`
      + `${Number(result.section_count || 0)} section · `
      + `${Number(result.item_count || 0)} Article · `
      + `${Number(result.field_count || 0)} field`;
  } else {
    const details = errors.length
      ? `<ul>${errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";
    host.innerHTML =
      `<strong>${escapeHtml(result?.message || "File chưa hợp lệ")}</strong>`
      + details;
  }
  host.hidden = false;
}

async function inspectCurrentCosting() {
  return call(
    "inspect_active_catalog_costing",
    $(".catalog-category").value,
  );
}

async function exportCatalogCosting() {
  const inspected = await inspectCurrentCosting();
  if (!inspected?.ok) return inspected;
  const preferredName = inspected.style_name
    || inspected.article_code
    || "Current Style";
  const selected = await callQuiet(
    "choose_costing_export_file",
    preferredName,
  );
  if (!selected?.ok) {
    if (selected?.code !== "COSTING_FILE_DIALOG_CANCELLED") {
      handleResult(selected);
    }
    return selected;
  }
  return runSelectedModuleAction(
    "export_catalog_costing",
    $(".catalog-category").value,
    catalogKind,
    "",
    selected.file_path,
  );
}

async function validateCatalogCostingFile() {
  const selected = await callQuiet("choose_costing_import_file");
  if (!selected?.ok) {
    if (selected?.code !== "COSTING_FILE_DIALOG_CANCELLED") {
      handleResult(selected);
    }
    return selected;
  }
  checkedCostingFile = {
    path: selected.file_path,
    name: selected.file_name,
    valid: false,
  };
  const result = await call(
    "validate_catalog_costing_file",
    selected.file_path,
  );
  checkedCostingFile.valid = Boolean(result?.ok);
  renderCostingFileCheck(result, selected.file_name);
  return result;
}

async function importCatalogCosting() {
  discardCostingPlan();
  showCatalogSpace("costing", { focus: false });
  const inspected = await inspectCurrentCosting();
  if (!inspected?.ok) return inspected;
  if (String(
    inspected.style_status?.internal_costsheet_status || "",
  ).toLowerCase() !== "open") {
    const blocked = {
      ok: false,
      code: "COSTING_NOT_OPEN",
      message: "Chỉ CostSheet Open mới được Import/Apply.",
      style_status: inspected.style_status,
    };
    handleResult(blocked);
    return blocked;
  }
  const selected = checkedCostingFile?.valid
    ? {
        ok: true,
        file_path: checkedCostingFile.path,
        file_name: checkedCostingFile.name,
      }
    : await callQuiet("choose_costing_import_file");
  if (!selected?.ok) {
    if (selected?.code !== "COSTING_FILE_DIALOG_CANCELLED") {
      handleResult(selected);
    }
    return selected;
  }
  return runSelectedModuleAction(
    "prepare_catalog_costing_import",
    $(".catalog-category").value,
    catalogKind,
    "",
    selected.file_path,
  );
}

async function applyCatalogCosting() {
  if (!costingPlanToken) return null;
  if (costingPlanDeleteCount > 0) {
    const confirmed = window.confirm(
      `Costing sẽ xóa ${costingPlanDeleteCount} Article đã đánh dấu DELETE. `
        + "Chỉ tiếp tục khi bạn đã kiểm tra đúng các dòng cần xóa.",
    );
    if (!confirmed) return null;
  }
  return runSelectedModuleAction(
    "apply_catalog_costing",
    costingPlanToken,
    costingArticleResolutions,
  );
}

async function clearCatalogCostingDependencies() {
  const confirmed = window.confirm(
    "Xác nhận Clear toàn bộ Color/Size Dependency của Costing đang chọn và Save? "
      + "Thao tác này không thể hoàn tác từ panel.",
  );
  if (!confirmed) return null;
  const inspected = await inspectCurrentCosting();
  if (!inspected?.ok) return inspected;
  if (String(
    inspected.style_status?.internal_costsheet_status || "",
  ).toLowerCase() !== "open") {
    const blocked = {
      ok: false,
      code: "COSTING_NOT_OPEN",
      message: "Chỉ CostSheet Open mới được Clear All Dependency.",
      style_status: inspected.style_status,
    };
    handleResult(blocked);
    return blocked;
  }
  return runSelectedModuleAction("clear_catalog_costing_dependencies");
}

const costingActions = {
  "export-xlsx": () => exportCatalogCosting(),
  "validate-file": () => validateCatalogCostingFile(),
  "import": () => importCatalogCosting(),
  "cancel-plan": () => discardCostingPlan(),
  "apply": () => applyCatalogCosting(),
  "clear-dependencies": () => clearCatalogCostingDependencies(),
};

const catalogActions = {
  "refresh-folders": () => scanCatalogFolders(true),
  "browse": () => browseCatalog(),
  "find": () => runCatalogAction(catalogKind, $(".catalog-query").value),
  "costsheet": async () => {
    const result = await runCatalogAction(
      catalogKind, $(".catalog-query").value, "costsheet"
    );
    if (result?.ok && result?.code === "CATALOG_DESTINATION_OPENED") {
      showCatalogSpace("costing");
    }
    return result;
  },
  "bom": () => runCatalogAction(
    catalogKind, $(".catalog-query").value, "bom"
  ),
  "files": () => runCatalogAction(
    catalogKind, $(".catalog-query").value, "files"
  ),
};
