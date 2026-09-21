"use strict";
// Danh sách module, ghim yêu thích, trạng thái bận và overlay.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

function allModules() {
  return visibleModuleGroups().flatMap((group) =>
    group.modules.map((module) => ({ ...module, group: group.name, accent: group.accent })));
}

function visibleModuleGroups() {
  return MODULE_GROUPS.flatMap((group) => {
    if (group.name !== "Admin") return [group];
    if (!adminAccess || !adminMode) return [];
    const modules = group.modules.filter((module) => adminModuleIds.has(module.id));
    return modules.length ? [{ ...group, modules }] : [];
  });
}

function moduleCard(module, group) {
  const isFavorite = favoriteModuleIds.has(module.id);
  const search = `${module.name} ${group.name} ${
    module.description || ""
  }`.toLowerCase();
  return `
    <div class="module-card" data-module-card="${escapeHtml(module.id)}">
      <button class="module-button module--${escapeHtml(module.kind || "generic")} module--${escapeHtml(group.name.toLowerCase())}" type="button"
        data-module-id="${escapeHtml(module.id)}"
        data-search="${escapeHtml(search)}">
        <span class="module-icon accent-${escapeHtml(group.accent)}">${moduleIconSvg(module.icon)}</span>
        <span class="module-copy"><span class="module-name">${escapeHtml(module.name)}</span></span>
      </button>
      <button class="module-favorite-button" type="button"
        data-favorite-module-id="${escapeHtml(module.id)}"
        aria-label="${isFavorite ? "Bỏ ghim" : "Ghim"} ${escapeHtml(module.name)}"
        aria-pressed="${String(isFavorite)}"
        data-tooltip="${isFavorite ? "Bỏ khỏi Yêu thích" : "Ghim lên đầu"}">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>
      </button>
    </div>`;
}

function buildModules() {
  const mainGroups = visibleModuleGroups()
    .map((group) => ({
      ...group,
      modules: group.modules.filter(
        (module) => !favoriteModuleIds.has(module.id),
      ),
    }))
    .filter((group) => group.modules.length > 0);
  $(".module-list").innerHTML = mainGroups.map((group) => `
    <section class="module-group" data-group="${escapeHtml(group.name)}">
      <div class="group-heading"><span class="group-accent accent-${escapeHtml(group.accent)}"></span><span>${escapeHtml(group.name)}</span><span class="group-count">${group.modules.length}</span></div>
      <div class="module-grid">${group.modules.map(
        (module) => moduleCard(module, group)
      ).join("")}</div>
    </section>`).join("");
  const modulesById = new Map(
    allModules().map((module) => [module.id, module]),
  );
  const favorites = [...favoriteModuleIds]
    .map((moduleId) => modulesById.get(moduleId))
    .filter(Boolean);
  $(".favorites-list").innerHTML = favorites.map((module) =>
    moduleCard(module, { name: module.group, accent: module.accent })
  ).join("");
  $(".favorites-section").hidden = favorites.length === 0;
  filterModules($(".search-box input")?.value || "");
}

async function toggleModuleFavorite(moduleId) {
  if (!moduleId) return;
  const wanted = !favoriteModuleIds.has(moduleId);
  const result = await callQuiet("set_module_favorite", moduleId, wanted);
  if (!result?.ok) {
    setStatus("error", result?.message || "Không lưu được module yêu thích.");
    return;
  }
  favoriteModuleIds = new Set(
    Array.isArray(result.favorite_module_ids)
      ? result.favorite_module_ids.map(String)
      : [],
  );
  buildModules();
  setStatus("success", result.message || "Đã cập nhật module yêu thích.");
}

function replayMotion(element, className) {
  if (!element) return;
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
}

function setBusy(value, message = "Đang xử lý trên WFX…") {
  const wasBusy = busy;
  busy = value;
  document.body.classList.toggle("is-busy", value);
  // Chỉ giữ một spinner tiến trình. Các nút có inline spinner được dọn ngay
  // khi workflow dài bật thanh tiến trình, tránh nhiều vòng xoay cùng lúc
  // trên máy WebView/GPU chậm.
  if (value) {
    $$("button.is-loading").forEach((button) =>
      button.classList.remove("is-loading"));
  } else {
    // Result sink có thể nhả busy trước khi Promise pywebview resolve. Xóa
    // luôn dấu vết nút khởi chạy để UI không còn highlight/aria-busy cũ.
    $$("button.is-action-source").forEach((button) => {
      button.classList.remove("is-loading", "is-action-source");
      button.removeAttribute("aria-busy");
    });
  }
  const stopButton = $(".stop-action-button");
  if (stopButton) {
    stopButton.hidden = !value;
    if (!value) {
      stopButton.disabled = false;
      stopButton.classList.remove("is-stopping");
    }
  }
  if (value && !wasBusy) setStatus("neutral", message);
  $$("button, select, input").forEach((element) => {
    if (element.closest(".settings-overlay")) return;
    if (element.matches(".close-button, .module-back-button")) return;
    // Manual, log và trợ giúp là các bề mặt chỉ đọc, rất hữu ích khi user
    // đang chờ automation; cho phép mở mà không ảnh hưởng flow WFX.
    if (element.matches(
      ".manual-button, .log-button, .module-help-button, .footer-help-button"
    )) return;
    if (element.matches(".stop-action-button")) return;
    element.disabled = value;
  });
  if (!value) {
    $$(".division-button").forEach((button) => {
      button.disabled = sessionActive !== true;
    });
    syncCatalogStepButtons();
    syncGdnDispatchAction();
    syncAllInputValidation();
    syncGrnStepActions();
    syncSaleAsnCreate();
    const continueButton = $('[data-module-action="sale-asn-continue"]');
    if (continueButton) {
      const choices = $$(".sale-asn-candidate-select");
      continueButton.disabled = choices.length
        ? !choices.some((choice) => choice.checked)
        : false;
    }
  }
}
window.wfxSetBusy = setBusy;

function settleBusyUi() {
  setBusy(false);
}

const OVERLAY_SPECS = [
  { el: () => feedbackOverlay(), openClass: "feedback-open" },
  { el: () => settingsOverlay(), openClass: "settings-open" },
  { el: () => $(".log-overlay"), openClass: "log-open" },
];

function activeOverlay() {
  for (const spec of OVERLAY_SPECS) {
    const element = spec.el();
    if (element && element.classList.contains(spec.openClass)) return element;
  }
  return null;
}

function focusableIn(container) {
  return [...container.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]),'
    + ' select:not([disabled]), textarea:not([disabled]),'
    + ' [tabindex]:not([tabindex="-1"])'
  )].filter((element) => element.getClientRects().length > 0);
}

// #6 Giam Tab trong overlay đang mở để bàn phím không lọt ra panel nền.
function trapOverlayFocus(event) {
  if (event.key !== "Tab") return;
  if ($(".hotkey-button")?.dataset.capturing === "true") return;
  const overlay = activeOverlay();
  if (!overlay) return;
  const focusable = focusableIn(overlay);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (!overlay.contains(active)) {
    event.preventDefault();
    first.focus();
  } else if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
}

let overlayReturnFocus = null;
let moduleReturnFocus = null;

function focusModuleSearch() {
  if (settingsOverlay().classList.contains("credentials-required")) {
    const target = $(".user-input").value.trim() ? $(".password-input") : $(".user-input");
    target.focus();
    return;
  }
  closeSettings();
  $(".log-overlay").classList.remove("log-open");
  feedbackOverlay().classList.remove("feedback-open");
  if (!$(".module-page").hidden) {
    const focusTarget = {
      catalog: ".catalog-query",
      oc: ".oc-query",
      gdn_dispatch: ".gdn-invoice-query",
      sample: ".sample-no-query",
      advance_pr: ".advance-pr-buyer-query",
      supplier_invoice: ".supplier-invoice-supplier-query",
      expense_invoice: ".expense-invoice-supplier-query",
      sale_asn: ".sale-asn-buyer",
      rmpo: ".rmpo-supplier-query",
      indent: ".indent-supplier-query",
      list_new: '[data-module-action="list-new-list"]',
      supplier: ".supplier-query",
      buyer: ".buyer-query",
      company_setup: '[data-module-action="company-list"]',
    }[selectedModule?.kind] || ".module-back-button";
    $(focusTarget)?.focus();
    return;
  }
  const input = $(".search-box input");
  input.focus();
  input.select();
}
window.wfxFocusModuleSearch = focusModuleSearch;
