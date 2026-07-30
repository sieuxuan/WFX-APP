"use strict";
(() => {
  let MODULE_GROUPS = [
    { name: "Operation", accent: "cyan", modules: [
      { name: "Catalog", id: "0003_6200", icon: "CA", kind: "catalog", description: "Tìm Style · Season · Costing/BOM." },
      { name: "OC List", id: "0004_0050_0020", icon: "OC", kind: "oc", description: "Mở OC List hoặc tìm theo OC No. và Style." },
      { name: "Sample List", id: "0004_0056_4070", icon: "SL", kind: "sample", description: "Mở Sample List, tìm Sample hoặc tạo Sample Order mới." },
      { name: "Sale ASN", id: "0004_0070_0020", icon: "AS", kind: "sale_asn", description: "Mở Sale ASN List hoặc tạo Sale ASN mới với cấu hình chuẩn." },
      { name: "RMPO List", id: "0005_0050_0020", icon: "RM", kind: "rmpo", description: "Mở RMPO List hoặc lọc kết hợp theo Supplier và RMPO No." },
      { name: "Indent List", id: "0005_0080_0020", icon: "IN", kind: "indent", description: "Mở Indent List hoặc lọc kết hợp theo 4 điều kiện." },
      { name: "User Indent", id: "user_indent_list", icon: "UI", kind: "indent", description: "Mở User Indent List hoặc lọc kết hợp theo 4 điều kiện." },
      { name: "QA List", id: "0063_0030_0020", icon: "QA", kind: "list_new", description: "Mở QA List hoặc tạo QA Request mới." },
    ]},
    { name: "Finance", accent: "violet", modules: [
      { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR", kind: "list_new", description: "Mở danh sách Advance PR hoặc tạo yêu cầu mới." },
      { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI", kind: "generic", description: "Mở danh sách hóa đơn nhà cung cấp." },
      { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI", kind: "list_new", description: "Mở danh sách Expense Invoice hoặc tạo hóa đơn mới." },
    ]},
    { name: "Admin", accent: "amber", modules: [
      { name: "Org Structure", id: "0090_0001", icon: "OR", kind: "generic", description: "Mở cấu trúc tổ chức." },
      { name: "System Coding", id: "0090_0250", icon: "SC", kind: "generic", description: "Mở cấu hình mã hệ thống." },
      { name: "Company Setup", id: "0090_0007", icon: "CO", kind: "company_setup", description: "Mở thiết lập công ty hoặc đổi nơi áp dụng FOC." },
      { name: "Buyer List", id: "0004_0010_1720", icon: "BU", kind: "buyer", description: "Mở Buyers List hoặc tìm và mở Buyer đầu tiên phù hợp." },
      { name: "Supplier List", id: "0005_0010_1290", icon: "SU", kind: "supplier", description: "Mở Supplier theo Category hoặc tìm Supplier trên mọi Category." },
    ]},
  ];

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const settingsOverlay = () => $(".settings-main-overlay");
  const feedbackOverlay = () => $(".feedback-overlay");
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const escapeHtml = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const MODULE_ICON_PATHS = {
    CA: '<path d="M4 7h6l2 2h8v10H4V7Z"/><path d="m9 14 2 2 4-5"/>',
    OC: '<path d="M6 3h9l3 3v15H6V3Z"/><path d="M14 3v4h4"/><path d="m9 14 2 2 4-5"/>',
    SL: '<path d="M9 3h6M10 3v6l-4 7a3 3 0 0 0 2.6 4.5h6.8A3 3 0 0 0 18 16l-4-7V3"/><path d="M7.5 15h9"/>',
    AS: '<path d="M3 6h11v11H3V6Z"/><path d="M14 10h4l3 3v4h-7v-7Z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    RM: '<path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/><path d="m9 14 2 2 4-4"/>',
    IN: '<path d="M4 5h16v14H4V5Z"/><path d="M4 14h4l2 3h4l2-3h4"/><path d="M12 3v8m0 0-3-3m3 3 3-3"/>',
    UI: '<path d="M5 4h14v16H5V4Z"/><circle cx="9" cy="10" r="2"/><path d="M6.5 16a2.5 2.5 0 0 1 5 0M14 9h3M14 13h3"/>',
    QA: '<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/>',
    PR: '<path d="M4 7h16v11H4V7Z"/><path d="M7 7V5h8v2M15 12h5"/><path d="m17 10 3 2-3 2"/>',
    SI: '<path d="M6 3h12v18l-2-1.5L14 21l-2-1.5L10 21l-2-1.5L6 21V3Z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    EI: '<circle cx="12" cy="12" r="9"/><path d="M9 9.5c0-1 1-1.8 3-1.8s3 .8 3 1.8-1 1.7-3 1.7-3 .8-3 1.8 1 1.8 3 1.8 3-.8 3-1.8M12 5.5v13"/>',
    OR: '<rect x="9" y="3" width="6" height="4" rx="1"/><rect x="3" y="17" width="6" height="4" rx="1"/><rect x="15" y="17" width="6" height="4" rx="1"/><path d="M12 7v5M6 17v-5h12v5"/>',
    SC: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
    CO: '<path d="M4 21V5l8-3 8 3v16M8 7h2m4 0h2M8 11h2m4 0h2M8 15h2m4 0h2M10 21v-3h4v3"/>',
    BU: '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5"/>',
    SU: '<path d="M3 21V10l6 3v-3l6 3V6l6 3v12H3Z"/><path d="M7 17h2m3 0h2m3 0h2"/>',
  };
  function moduleIconSvg(icon) {
    const paths = MODULE_ICON_PATHS[String(icon || "").toUpperCase()]
      || '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8 12h8M12 8v8"/>';
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
  }
  // Ngưỡng cứu UI nếu bridge call không phản hồi. Dài hơn tổng deadline hợp lệ
  // của các automation (login + grid settle + filter + mở đích ~ trên phút).
  const CALL_WATCHDOG_MS = 180000;
  let busy = false;
  let hidePanelWhenIdle = false;
  let pointerInsidePanel = false;
  let returnToListAfterAction = false;
  let favoriteModuleIds = new Set();
  let hotkeyLabel = "Ctrl + Shift + X";
  let selectedModule = null;
  let jobs = [];
  let adminAccess = false;
  let adminMode = false;
  let adminModuleIds = new Set();
  let sessionActive = null;
  let currentDivision = null;
  let hasCredentials = false;
  let accountEditing = false;
  let accountUserId = "";
  let feedbackSubmitting = false;
  let bootstrapReceived = false;
  let toastEnabled = true;
  let lastCatalogResult = null;
  let currentCostingStatus = "";
  let catalogKind = "code";
  let catalogPendingDestination = null;
  let costingPlanToken = "";
  let costingPlanDeleteCount = 0;
  let costingArticleResolutions = {};
  let checkedCostingFile = null;
  let catalogThemeChoice = "light";
  let catalogDefaultFolder = null;
  const catalogFoldersByCategory = new Map();
  const catalogExpandedFoldersByCategory = new Map();
  const CATALOG_DEFAULT_CATEGORY = "Apparel";
  let catalogSelectedNodeId = "";
  let catalogFolderScanning = false;
  let catalogFolderSaving = false;
  let catalogFolderScanGeneration = 0;
  let catalogFolderEditorOpen = false;
  const moduleFilterKinds = {
    oc: "oc_no",
    sample: "sample_no",
    sale_asn: "invoice_no",
  };
  const MODULE_RUN_METHODS = new Set([
    "open_chrome", "login", "retry_job", "open_module",
    "prepare_catalog", "scan_catalog_folders", "find_code", "find_buyer_reference",
    "open_catalog_destination", "browse_catalog", "catalog_action",
    "open_sale_asn_new", "open_sample_new", "search_oc", "search_sample",
    "search_sale_asn", "search_rmpo", "search_indent", "open_module_new",
    "open_supplier_category", "find_supplier",
    "find_supplier_in_category", "find_buyer",
    "toggle_company_foc",
  ]);
  const INTERACTIVE_RESULT_CODES = new Set([
    "MULTIPLE_RESULTS",
    "CATALOG_FILES_SCANNED",
    "COSTING_DRY_RUN_READY",
    "COSTING_ARTICLE_AMBIGUOUS",
  ]);
  const BUSY_MESSAGES = {
    open_chrome: "Đang mở và đăng nhập WFX…",
    retry_job: "Đang chạy lại tác vụ…",
    open_module: "Đang mở module trên WFX…",
    prepare_catalog: "Đang chuẩn bị Catalog…",
    scan_catalog_folders: "Đang quét folder Catalog…",
    browse_catalog: "Đang mở vị trí Catalog…",
    catalog_action: "Đang tìm và mở dữ liệu Catalog…",
    find_code: "Đang tìm Style Code…",
    find_buyer_reference: "Đang tìm Buyer Reference…",
    open_catalog_destination: "Đang mở dữ liệu style…",
    download_catalog_file: "Đang tải file đính kèm…",
    export_catalog_costing: "Đang đọc và tải Costing…",
    inspect_active_catalog_costing: "Đang nhận tab Costing hiện tại…",
    validate_catalog_costing_file: "Đang kiểm tra cấu trúc file…",
    prepare_catalog_costing_import: "Đang kiểm tra file và lập dry-run…",
    apply_catalog_costing: "Đang áp dụng Costing và Save…",
    open_sale_asn_new: "Đang mở Sale ASN mới…",
    open_sample_new: "Đang mở Sample Order mới…",
    search_oc: "Đang tìm OC…",
    search_sample: "Đang tìm Sample…",
    search_sale_asn: "Đang tìm Sale ASN…",
    search_rmpo: "Đang lọc RMPO List…",
    search_indent: "Đang lọc Indent List…",
    open_module_new: "Đang mở màn New…",
    open_supplier_category: "Đang mở Supplier…",
    find_supplier: "Đang tìm Supplier…",
    find_supplier_in_category: "Đang tìm Supplier trong Category…",
    find_buyer: "Đang tìm Buyer…",
    toggle_company_foc: "Đang đổi và lưu cấu hình FOC…",
    switch_division: "Đang đổi Division…",
    login: "Đang đăng nhập WFX…",
  };
  // Nhãn tiếng Việt cho lịch sử tác vụ; tránh phơi tên hàm kỹ thuật ra người dùng.
  const JOB_METHOD_LABELS = {
    login: "Đăng nhập WFX",
    check_session: "Kiểm tra phiên",
    open_chrome: "Mở trình duyệt",
    open_module: "Mở module",
    prepare_catalog: "Chuẩn bị Catalog",
    browse_catalog: "Mở vị trí Catalog",
    scan_catalog_folders: "Quét folder Catalog",
    catalog_action: "Tìm Catalog",
    find_code: "Tìm Style Code",
    find_buyer_reference: "Tìm Buyer Reference",
    open_catalog_destination: "Mở Costing / BOM",
    download_catalog_file: "Tải file đính kèm",
    export_catalog_costing: "Tải Costing",
    inspect_active_catalog_costing: "Nhận tab Costing",
    validate_catalog_costing_file: "Kiểm tra file Costing",
    prepare_catalog_costing_import: "Dry-run Costing",
    apply_catalog_costing: "Áp dụng Costing",
    open_sale_asn_new: "Sale ASN mới",
    open_sample_new: "Sample Order mới",
    search_oc: "Tìm OC",
    search_sample: "Tìm Sample",
    search_sale_asn: "Tìm Sale ASN",
    search_rmpo: "Tìm RMPO",
    search_indent: "Tìm Indent",
    open_module_new: "Mở màn New",
    open_supplier_category: "Mở Supplier",
    find_supplier: "Tìm Supplier",
    find_supplier_in_category: "Tìm Supplier theo Category",
    find_buyer: "Tìm Buyer",
    toggle_company_foc: "Đổi FOC Company Setup",
    switch_division: "Đổi Division",
  };
  const jobMethodLabel = (method) =>
    JOB_METHOD_LABELS[String(method || "")] || String(method || "Tác vụ");

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
          title="${isFavorite ? "Bỏ khỏi Yêu thích" : "Ghim lên đầu"}">
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
    }
    const progress = $(".operation-progress");
    const stopButton = $(".stop-action-button");
    if (stopButton) {
      stopButton.hidden = !value;
      if (!value) {
        stopButton.disabled = false;
        stopButton.classList.remove("is-stopping");
      }
    }
    if (progress) {
      progress.hidden = !value;
      $(".operation-progress-text").textContent = message;
      if (value && !wasBusy) replayMotion(progress, "operation-enter");
    }
    $$("button, select, input").forEach((element) => {
      if (element.closest(".settings-overlay")) return;
      if (element.matches(".close-button, .module-back-button")) return;
      if (element.matches(".stop-action-button")) return;
      element.disabled = value;
    });
    if (!value) {
      $$(".division-button").forEach((button) => {
        button.disabled = sessionActive !== true;
      });
      syncCatalogStepButtons();
    }
  }
  window.wfxSetBusy = setBusy;

  function settleBusyUi() {
    setBusy(false);
    if (hidePanelWhenIdle && !pointerInsidePanel) {
      hidePanelWhenIdle = false;
      window.setTimeout(() => api()?.request_panel_hide?.(), 60);
    } else if (pointerInsidePanel) {
      hidePanelWhenIdle = false;
    }
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
        sample: ".sample-query",
        sale_asn: '[data-module-action="sale-asn-list"]',
        rmpo: ".rmpo-supplier-query",
        indent: ".indent-supplier-query",
        list_new: '[data-module-action="list-new-list"]',
        supplier: ".supplier-query",
        buyer: ".buyer-query",
        company_setup: '[data-module-action="company-list"]',
        generic: ".generic-module-open",
      }[selectedModule?.kind] || ".module-back-button";
      $(focusTarget)?.focus();
      return;
    }
    const input = $(".search-box input");
    input.focus();
    input.select();
  }
  window.wfxFocusModuleSearch = focusModuleSearch;

  function setStatus(tone, label) {
    const status = $(".footer-status");
    status.dataset.tone = tone || "neutral";
    $(".footer-status-text").textContent = label || "";
  }
  window.wfxSetStatus = setStatus;

  function setBrowserStatus(alive, available = true, name = null) {
    const health = $(".health-chrome");
    if (health) {
      health.dataset.state = alive ? "ok" : "bad";
      health.title = alive ? `${name || "Chromium"} automation` : "Chưa kết nối trình duyệt automation";
    }
    const banner = $(".browser-banner");
    if (banner) {
      banner.hidden = alive === true;
      $(".browser-banner-message").textContent = available === false
        ? "Không tìm thấy Chrome/Edge/Brave/Chromium. Hãy cài hoặc đặt WFX_CHROME_PATH."
        : `Có thể dùng ${name || "Chrome, Edge, Brave hoặc Chromium"}.`;
      $(".open-chrome-button").textContent = available === false ? "Kiểm tra lại" : "Mở trình duyệt";
    }
  }
  window.wfxSetChromeStatus = (alive) => setBrowserStatus(alive);
  window.wfxSetBrowserStatus = setBrowserStatus;

  function setDivisionState(key, label, name) {
    currentDivision = key || null;
    $$(".division-button").forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(Boolean(currentDivision) && button.dataset.division === currentDivision)
      );
    });
    const current = $(".division-current");
    if (current) {
      current.textContent = label
        ? `${label}${name ? ` · ${name}` : ""}`
        : (sessionActive ? "Chưa nhận diện được Division" : "Đăng nhập để nhận diện");
      current.title = name || "";
    }
  }
  window.wfxSetDivisionState = setDivisionState;

  function setSessionStatus(active) {
    sessionActive = active == null ? null : Boolean(active);
    const node = $(".health-session");
    if (node) node.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
    const divisionLive = $(".division-live");
    if (divisionLive) divisionLive.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
    $$(".division-button").forEach((button) => {
      button.disabled = active !== true;
    });
    const accountIcon = $(".account-status-icon");
    const accountLabel = $(".account-status-label");
    if (accountIcon) accountIcon.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
    if (accountLabel) {
      accountLabel.textContent = active == null
        ? "Chưa kiểm tra"
        : (active ? "Đã đăng nhập" : "Chưa đăng nhập");
    }
    syncAccountView();
    const ready = $(".workspace-ready");
    if (ready) {
      ready.dataset.state = active === true ? "ok" : "setup";
      ready.textContent = active === true ? "ONLINE" : "SETUP";
    }
    if (active !== true) setDivisionState(null, null, null);
  }
  window.wfxSetSessionStatus = setSessionStatus;


  function setAdminAccess(access, moduleIds, enabled) {
    adminAccess = access === true;
    adminModuleIds = new Set(Array.isArray(moduleIds) ? moduleIds : []);
    adminMode = adminAccess && enabled === true;
    const row = $(".admin-mode-row");
    if (row) row.hidden = !adminAccess;
    const input = $(".admin-mode-input");
    if (input) input.checked = adminMode;
    buildModules();
  }
  window.wfxSetAdminAccess = setAdminAccess;

  function pushLog(line) {
    const pre = $(".catalog-log");
    const selection = window.getSelection?.();
    const selectionInLog = Boolean(
      selection
      && !selection.isCollapsed
      && (
        pre.contains(selection.anchorNode)
        || pre.contains(selection.focusNode)
      ),
    );
    const followLatest = (
      pre.scrollHeight - pre.scrollTop - pre.clientHeight <= 28
      && !selectionInLog
    );
    if (pre.textContent === "Chưa có nhật ký hệ thống.") {
      pre.textContent = "";
    }
    pre.append(document.createTextNode(
      `${pre.textContent ? "\n" : ""}${line}`,
    ));
    if (followLatest) pre.scrollTop = pre.scrollHeight;
    if (/(?:ERROR|FAILED|TIMEOUT)/i.test(line) && !$(".log-overlay").classList.contains("log-open")) {
      $(".log-button").classList.add("has-alert");
    }
  }
  window.wfxPushLog = pushLog;

  function resolveTheme(choice) {
    if (choice === "dark") return "dark";
    if (choice === "system") {
      return window.matchMedia
        && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return "light";
  }

  function applyTheme(theme) {
    catalogThemeChoice = ["light", "dark", "system"].includes(theme)
      ? theme
      : "light";
    document.documentElement.dataset.theme = resolveTheme(catalogThemeChoice);
    // Scope vào đúng nút chọn giao diện; nút catalog-kind cũng dùng .seg-button
    // nên KHÔNG được quét chung .seg-button ở đây.
    $$("[data-theme-choice]").forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.themeChoice === catalogThemeChoice),
      ));
  }
  window.wfxApplyTheme = applyTheme;

  function syncAccountView() {
    const needsCredentials = settingsOverlay().classList.contains(
      "credentials-required",
    );
    const connected = sessionActive === true;
    const showEditor = needsCredentials || !connected || accountEditing;
    const connectedView = $(".account-connected-view");
    const editView = $(".account-edit-view");
    const user = accountUserId || $(".user-input").value.trim();
    const statusUser = $(".account-status-user");
    connectedView.hidden = showEditor;
    editView.hidden = !showEditor;
    statusUser.hidden = !user;
    statusUser.textContent = user ? `User ID: ${user}` : "";
  }

  function setAccount(userId) {
    accountUserId = String(userId || "").trim();
    $(".user-input").value = accountUserId;
    syncAccountView();
  }
  window.wfxSetAccount = setAccount;

  function updateFeedbackState() {
    const message = $(".feedback-message");
    const value = message.value;
    const valid = value.trim().length >= 5;
    $(".feedback-character-count").textContent = `${value.length}/2000`;
    message.setAttribute(
      "aria-invalid",
      String(value.length > 0 && !valid),
    );
    $(".feedback-submit-button").disabled =
      feedbackSubmitting || !valid;
  }

  function selectSettingsTab(name) {
    if (settingsOverlay().classList.contains("credentials-required") && name !== "account") return;
    const selected = ["automation", "appearance"].includes(name)
      ? name
      : "account";
    $$(".settings-tab").forEach((button) => {
      const on = button.dataset.settingsTab === selected;
      button.setAttribute("aria-selected", String(on));
      button.tabIndex = on ? 0 : -1;
    });
    $$("[data-settings-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.settingsPanel !== selected;
    });
  }

  function selectActivityTab(name) {
    const selected = name === "log" ? "log" : "jobs";
    $$(".activity-tabs button").forEach((button) => {
      const on = button.dataset.activityTab === selected;
      button.setAttribute("aria-selected", String(on));
      button.tabIndex = on ? 0 : -1;
    });
    $$("[data-activity-view]").forEach((view) => {
      view.hidden = view.dataset.activityView !== selected;
    });
  }

  // Điều hướng tablist bằng phím mũi tên (WAI-ARIA), giữ roving tabindex.
  function bindTablistKeys(container, onSelect) {
    if (!container) return;
    container.addEventListener("keydown", (event) => {
      const tabs = [...container.querySelectorAll('[role="tab"]')];
      const index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      let next = -1;
      if (["ArrowRight", "ArrowDown"].includes(event.key)) next = (index + 1) % tabs.length;
      else if (["ArrowLeft", "ArrowUp"].includes(event.key)) next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      if (next < 0) return;
      event.preventDefault();
      tabs[next].focus();
      onSelect(tabs[next]);
    });
  }

  // #5 Roving ↑/↓/Home/End giữa các option của listbox (kết quả, folder picker).
  // Enter/Space kích hoạt option (đều là <button>); mở rộng group dùng nút expand
  // riêng (Tab tới được, vì focus đã được giam trong overlay).
  function bindListboxKeys(container) {
    if (!container) return;
    container.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const items = [...container.querySelectorAll('[role="option"]')]
        .filter((element) => element.getClientRects().length > 0);
      if (!items.length) return;
      const index = items.indexOf(document.activeElement);
      let next = index;
      if (event.key === "ArrowDown") next = index < 0 ? 0 : Math.min(items.length - 1, index + 1);
      else if (event.key === "ArrowUp") next = index < 0 ? 0 : Math.max(0, index - 1);
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = items.length - 1;
      event.preventDefault();
      items[next].focus();
    });
  }

  async function withButtonLoading(button, run) {
    if (!button) return run();
    button.classList.add("is-loading", "is-action-source");
    try {
      return await run();
    } finally {
      button.classList.remove("is-loading", "is-action-source");
    }
  }

  function openSettings(tabName = "automation") {
    if (!settingsOverlay().classList.contains("settings-open")) {
      overlayReturnFocus = document.activeElement;
    }
    selectSettingsTab(tabName);
    const overlay = settingsOverlay();
    overlay.classList.add("settings-open");
    overlay.setAttribute("aria-hidden", "false");
  }

  function closeSettings() {
    const overlay = settingsOverlay();
    if (overlay.classList.contains("credentials-required")) return;
    if (sessionActive === true) {
      accountEditing = false;
      $(".user-input").value = accountUserId;
      $(".password-input").value = "";
      syncAccountView();
    }
    overlay.classList.remove("settings-open");
    overlay.setAttribute("aria-hidden", "true");
    overlayReturnFocus?.focus?.();
    overlayReturnFocus = null;
  }

  function showCredentialPrompt(code, message) {
    const prompt = $(".auth-prompt");
    const invalid = ["LOGIN_FAILED", "LOGIN_TIMEOUT"].includes(code);
    prompt.hidden = false;
    prompt.dataset.tone = invalid ? "error" : "warning";
    $(".auth-prompt-title").textContent = invalid
      ? "Đăng nhập chưa thành công"
      : "Cần thông tin đăng nhập";
    $(".auth-prompt-message").textContent = message || (
      invalid
        ? "Kiểm tra User ID và nhập lại mật khẩu WFX."
        : "Nhập User ID và Password để WFX Smart bắt đầu làm việc."
    );
    $(".password-input").value = "";
    hasCredentials = false;
    accountEditing = true;
    settingsOverlay().classList.add("credentials-required");
    syncAccountView();
    openSettings("account");
    window.setTimeout(() => {
      const target = $(".user-input").value.trim() ? $(".password-input") : $(".user-input");
      target.focus();
    }, 0);
  }
  window.wfxRequireCredentials = showCredentialPrompt;

  function clearCredentialPrompt() {
    $(".auth-prompt").hidden = true;
    settingsOverlay().classList.remove("credentials-required");
    hasCredentials = true;
    if (sessionActive === true) accountEditing = false;
    syncAccountView();
  }

  function setStyleStatus(style) {
    const node = $(".style-status");
    const costingCurrent = $(".catalog-costing-current");
    if (!node) return;
    if (!style || !style.code) {
      currentCostingStatus = "";
      node.hidden = true;
      if (costingCurrent) costingCurrent.hidden = true;
      syncCatalogStepButtons();
      return;
    }
    currentCostingStatus = String(
      style.internal_costsheet_status || "",
    ).trim();
    $(".style-status-code").textContent = style.code;
    $(".style-status-season").textContent = style.season || "—";
    $(".style-status-costsheet").textContent = style.internal_costsheet_status || "—";
    node.hidden = false;
    if (costingCurrent) {
      $(".catalog-costing-current-code").textContent = style.code;
      const statusNode = $(".catalog-costing-current-status");
      statusNode.textContent = style.internal_costsheet_status || "Unknown";
      statusNode.dataset.open = String(
        currentCostingStatus.toLowerCase() === "open",
      );
      costingCurrent.hidden = false;
    }
    syncCatalogStepButtons();
  }
  window.wfxSetStyleStatus = setStyleStatus;

  function clearCatalogResult() {
    lastCatalogResult = null;
    setStyleStatus(null);
    syncCatalogStepButtons();
  }

  function clearCatalogPreparation() {
    clearCatalogResult();
    catalogPendingDestination = null;
    discardCostingPlan();
  }

  function syncCatalogStepButtons() {
    const category = $(".catalog-category")?.value || "";
    const supportsDefault = category === CATALOG_DEFAULT_CATEGORY;
    const scanned = catalogFoldersByCategory.has(category);
    if ($(".catalog-folder-summary")) {
      $(".catalog-folder-summary").hidden = !supportsDefault;
      $(".catalog-folder-summary").disabled =
        busy || catalogFolderScanning || catalogFolderSaving;
      $(".catalog-folder-summary").setAttribute(
        "aria-expanded",
        String(supportsDefault && catalogFolderEditorOpen),
      );
    }
    if ($(".catalog-folder-field")) {
      $(".catalog-folder-field").hidden =
        !supportsDefault || !catalogFolderEditorOpen;
    }
    if ($(".catalog-folder-search")) {
      $(".catalog-folder-search").disabled =
        busy || catalogFolderScanning || catalogFolderSaving
          || !supportsDefault || !scanned;
    }
    if ($(".catalog-folder-list")) {
      const hasRetry = Boolean(
        $(".catalog-folder-list").querySelector("[data-folder-retry]")
      );
      $(".catalog-folder-list").setAttribute(
        "aria-disabled",
        String(
          hasRetry
            ? busy || catalogFolderScanning
            : busy || catalogFolderScanning || catalogFolderSaving
              || !supportsDefault || !scanned,
        ),
      );
      $$(".catalog-folder-list button").forEach((button) => {
        button.disabled = button.matches("[data-folder-retry]")
          ? busy || catalogFolderScanning
          : busy || catalogFolderScanning || catalogFolderSaving
            || !supportsDefault || !scanned;
      });
    }
    if ($(".catalog-browse-button")) {
      $(".catalog-browse-button").disabled =
        busy || catalogFolderScanning || catalogFolderSaving;
      if (!supportsDefault) {
        $(".catalog-browse-label").textContent = `Mở ${category}`;
      } else if (!scanned) {
        $(".catalog-browse-label").textContent =
          catalogDefaultFolder?.node_id
            ? "Mở folder mặc định"
            : "Mở Master";
      }
    }
    if ($(".catalog-folder-refresh")) {
      $(".catalog-folder-refresh").disabled =
        busy || catalogFolderScanning || catalogFolderSaving;
    }
    $$(".catalog-query-row > button, .catalog-query-actions button").forEach((button) => {
      button.disabled = busy || catalogFolderScanning;
    });
    if ($(".catalog-costing-card")) {
      $(".catalog-costing-card").hidden = !supportsDefault;
    }
    const costingOpen = currentCostingStatus.toLowerCase() === "open";
    const costingStatusKnown = Boolean(currentCostingStatus.trim());
    const costingState = $(".catalog-costing-state");
    if (costingState) {
      costingState.textContent = costingOpen
        ? "Open · sẵn sàng Import"
        : costingStatusKnown
          ? "Có thể Export · Import cần Open"
          : "Có thể Export/Import tab Costing hiện tại";
      costingState.dataset.ready = String(costingOpen);
    }
    $$("[data-costing-action]").forEach((button) => {
      button.disabled = busy || catalogFolderScanning;
    });
  }

  function rememberCatalogResult(result) {
    lastCatalogResult = {
      articleCode: String(result.article_code || ""),
      category: String(result.category || $(".catalog-category").value),
      filterKind: String(result.filter_kind || ""),
      query: String(result.query || "").trim(),
    };
    syncCatalogStepButtons();
  }

  function setUpdateState(state) {
    if (!state) return;
    const banner = $(".update-banner");
    const button = $(".update-banner-button");
    const title = $(".update-banner-title");
    const scheduled = state.code === "UPDATE_SCHEDULED";
    const failed = state.ok === false && (
      ["UPDATE_SCHEDULE_FAILED", "UPDATE_APPLIER_MISSING"].includes(state.code)
      || banner.classList.contains("update-installing")
    );
    banner.hidden = state.can_update !== true && !scheduled && !failed;
    banner.classList.toggle("update-installing", scheduled);
    banner.classList.toggle("update-failed", failed);
    if (scheduled) {
      title.textContent = "Đang cập nhật WFX Smart";
      $(".update-banner-message").textContent =
        "Ứng dụng sẽ đóng trong giây lát và tự mở lại ngay khi cài đặt xong.";
      button.disabled = true;
      button.textContent = "Đang cài đặt…";
    } else if (failed) {
      title.textContent = "Chưa thể cập nhật";
      $(".update-banner-message").textContent =
        state.message || "Vui lòng kiểm tra kết nối và thử lại.";
      button.disabled = false;
      button.textContent = "Thử cập nhật lại";
    } else if (state.can_update) {
      title.textContent = state.version
        ? `Bản cập nhật ${state.version} đã sẵn sàng`
        : "Có bản cập nhật mới";
      $(".update-banner-message").textContent = state.version
        ? "Chỉ cần bấm một lần. WFX Smart sẽ tự tải, cài đặt rồi mở lại."
        : "Một lần bấm để tải, cài đặt và tự mở lại ứng dụng.";
      button.disabled = false;
      button.textContent = "Cập nhật phần mềm mới";
    }
  }
  window.wfxSetUpdateState = setUpdateState;

  function renderJobs(items) {
    jobs = Array.isArray(items) ? items : [];
    const host = $(".job-history");
    if (!jobs.length) {
      host.innerHTML = '<div class="job-empty">Chưa có tác vụ.</div>';
      return;
    }
    host.innerHTML = jobs.map((job) => `
      <article class="job-card" data-ok="${job.ok === true}" data-run-id="${escapeHtml(job.run_id)}">
        <span class="job-tone"></span>
        <div class="job-main">
          <div class="job-title"><strong>${escapeHtml(jobMethodLabel(job.method))}</strong><code>${escapeHtml(job.run_id)}</code></div>
          <div class="job-message">${escapeHtml(job.message)}</div>
          <div class="job-meta">${escapeHtml(job.started_at)} · ${Number(job.elapsed_ms || 0)} ms · ${escapeHtml(job.code)}</div>
        </div>
        <div class="job-actions">
          ${job.has_screenshot ? '<button type="button" data-job-action="screenshot">Ảnh</button>' : ""}
          ${job.retryable ? '<button type="button" data-job-action="retry">Chạy lại</button>' : ""}
        </div>
      </article>`).join("");
  }
  window.wfxSetJobHistory = renderJobs;

  function handleResult(result) {
    if (!result) return;
    if (INTERACTIVE_RESULT_CODES.has(result.code)) {
      hidePanelWhenIdle = false;
    }
    const cancelled = result.code === "ACTION_CANCELLED";
    setStatus(
      cancelled ? "warning" : (result.ok ? "success" : "error"),
      result.message || "",
    );
    if (result.user_id !== undefined) setAccount(result.user_id);
    if (result.chrome_alive !== undefined) {
      setBrowserStatus(Boolean(result.chrome_alive), result.browser_available, result.browser_name);
    }
    if (result.session_active !== undefined) {
      setSessionStatus(result.session_active, result.last_login_at);
    }
    if (result.current_division !== undefined) {
      setDivisionState(
        result.current_division,
        result.division_label,
        result.division_name
      );
    }
    if (result.has_credentials !== undefined) {
      hasCredentials = result.has_credentials === true;
    }
    if (result.style_status) setStyleStatus(result.style_status);
    if (["RESULT_OPENED", "CATALOG_FILES_SCANNED"].includes(result.code)
        && result.article_code) {
      rememberCatalogResult(result);
    } else if ([
      "NO_RESULTS", "MULTIPLE_RESULTS", "CATALOG_RESULT_REQUIRED",
      "CATALOG_RESULT_CHANGED", "CATALOG_RESULT_EXPIRED",
    ].includes(result.code)) {
      clearCatalogResult();
    }
    if ([
      "MULTIPLE_RESULTS", "NO_RESULTS", "RESULT_OPENED",
      "CATALOG_FILES_SCANNED",
    ].includes(result.code)) {
      renderCatalogResults(result);
    }
    if (result.code === "COSTING_DRY_RUN_READY") {
      renderCostingPlan(result);
    } else if (result.code === "COSTING_ARTICLE_AMBIGUOUS") {
      renderCostingAmbiguities(result);
    } else if (result.code === "COSTING_APPLIED") {
      resetCostingPlan();
    }
    if (result.default_folder !== undefined) {
      catalogDefaultFolder = result.default_folder;
      $(".catalog-folder-current").textContent =
        catalogDefaultFolder?.path_label || "Mặc định (Master)";
    }
    if (result.admin_access !== undefined) {
      setAdminAccess(
        result.admin_access,
        result.admin_module_ids,
        result.admin_mode
      );
    }
    if (result.jobs) renderJobs(result.jobs);
    if (result.run_id) refreshJobs();
    if (["MISSING_CREDENTIALS", "PASSWORD_REQUIRED", "USER_ID_REQUIRED",
         "LOGIN_FAILED", "LOGIN_TIMEOUT", "NOT_LOGGED_IN"].includes(result.code)) {
      showCredentialPrompt(result.code, result.message);
    } else if (["LOGGED_IN", "SESSION_REUSED", "SESSION_ACTIVE"].includes(result.code)) {
      clearCredentialPrompt();
    }
  }
  window.wfxHandleBackendResult = (result) => {
    handleResult(result);
    // Result sink là đường hồi phục độc lập với Promise của pywebview. Trên
    // một số phiên WebView2 chạy lâu, backend đã xong và log đã có kết quả
    // nhưng Promise bridge không resolve; nếu không nhả busy tại đây, toàn bộ
    // workflow tiếp theo vẫn bị disabled tới watchdog.
    settleBusyUi();
  };

  async function call(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng");
      return null;
    }
    const busyMessage = BUSY_MESSAGES[method] || "Đang xử lý trên WFX…";
    setBusy(true, busyMessage);
    setStatus("neutral", busyMessage);
    // Watchdog: nếu một bridge call treo (Chrome/WFX không phản hồi, promise
    // không resolve), giải phóng UI thay vì để mọi nút disable vĩnh viễn ("đơ").
    // Backend vẫn giữ run lock; kết quả thật (nếu có) sẽ về sau qua result sink.
    let watchdog;
    const timeout = new Promise((resolve) => {
      watchdog = window.setTimeout(
        () => resolve({ __timeout: true }), CALL_WATCHDOG_MS
      );
    });
    try {
      // Bắt đầu backend ngay; đưa Chrome lên trước chỉ là hiệu ứng song song,
      // không được nằm trên critical path của automation.
      const pending = bridge[method](...args);
      if (MODULE_RUN_METHODS.has(method)) {
        Promise.resolve(api()?.focus_automation_browser?.()).catch(() => {});
      }
      // Nếu watchdog thắng trước, promise gốc reject muộn sẽ không còn ai bắt →
      // gắn no-op catch để tránh "unhandled rejection". Race vẫn bắt lỗi bình thường.
      pending.catch(() => {});
      const result = await Promise.race([pending, timeout]);
      if (result && result.__timeout) {
        setStatus(
          "error",
          "Tác vụ chạy quá lâu và có thể vẫn đang xử lý trên WFX. "
            + "Vui lòng chờ hoặc thử lại sau giây lát.",
        );
        return null;
      }
      handleResult(result);
      return result;
    } catch (error) {
      setStatus("error", String(error));
      return null;
    } finally {
      window.clearTimeout(watchdog);
      settleBusyUi();
    }
  }

  async function callQuiet(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng");
      return null;
    }
    try { return await bridge[method](...args); }
    catch (error) { setStatus("error", String(error)); return null; }
  }

  async function refreshJobs() {
    const result = await callQuiet("get_job_history", 30);
    if (result && result.jobs) renderJobs(result.jobs);
  }

  function openModulePage(moduleId) {
    const module = allModules().find((item) => item.id === moduleId);
    if (!module) return;
    if ($(".module-page").hidden) {
      moduleReturnFocus = document.activeElement;
    }
    selectedModule = module;
    $("#module-page-title").textContent = module.name;
    $(".module-modal-subtitle").textContent =
      module.description || "Mở màn hình WFX.";
    $$('[data-module-view]').forEach((view) => {
      view.hidden = view.dataset.moduleView !== module.kind;
    });
    $(".generic-module-icon").innerHTML = moduleIconSvg(module.icon);
    const page = $(".module-page");
    $(".panel-body").hidden = true;
    page.hidden = false;
    page.setAttribute("aria-hidden", "false");
    replayMotion(page, "view-enter");
    const focusTarget = {
      catalog: ".catalog-query",
      oc: ".oc-query",
      sample: ".sample-query",
      sale_asn: '[data-module-action="sale-asn-list"]',
      rmpo: ".rmpo-supplier-query",
      indent: ".indent-supplier-query",
      list_new: '[data-module-action="list-new-list"]',
      supplier: ".supplier-category",
      buyer: '[data-module-action="buyer-list"]',
      company_setup: '[data-module-action="company-list"]',
      generic: ".generic-module-open",
    }[module.kind] || ".generic-module-open";
    if (module.kind === "list_new") {
      $(".list-new-module-label").textContent = `Mở New từ ${module.name}`;
    }
    setTimeout(() => $(focusTarget)?.focus(), 0);
    if (module.kind === "catalog") {
      catalogFolderEditorOpen = false;
      syncCatalogKind();
      hideCatalogResults();
      syncCatalogStepButtons();
    }
  }

  async function stopCurrentAction() {
    const button = $(".stop-action-button");
    if (!busy || !button || button.disabled) return;
    button.disabled = true;
    button.classList.add("is-stopping");
    setStatus("warning", "Đang dừng tại checkpoint an toàn…");
    const result = await callQuiet("cancel_current_action");
    if (!result?.ok) {
      button.disabled = false;
      button.classList.remove("is-stopping");
      setStatus("warning", result?.message || "Chưa thể dừng tác vụ.");
    }
  }

  function closeModulePage() {
    const page = $(".module-page");
    if (page.hidden) return;
    page.hidden = true;
    page.setAttribute("aria-hidden", "true");
    const panelBody = $(".panel-body");
    panelBody.hidden = false;
    replayMotion(panelBody, "view-enter");
    moduleReturnFocus?.focus?.();
    moduleReturnFocus = null;
  }

  function dismissAfterSuccessfulModule(result) {
    // MULTIPLE_RESULTS tuy ok=true nhưng người dùng còn phải chọn 1 Code trong
    // danh sách ngay trên panel — không được tự thu panel lúc này.
    if (result && [
      "MULTIPLE_RESULTS",
      "CATALOG_FILES_SCANNED",
    ].includes(result.code)) return;
    if (result && result.ok && returnToListAfterAction) {
      closeModulePage();
    }
  }

  async function openModule() {
    if (!selectedModule) return;
    const result = await call("open_module", selectedModule.id);
    dismissAfterSuccessfulModule(result);
  }

  async function openModuleDirect(moduleId) {
    const result = await call("open_module", moduleId);
    dismissAfterSuccessfulModule(result);
    return result;
  }

  async function runSelectedModuleAction(method, ...args) {
    const result = await call(method, ...args);
    dismissAfterSuccessfulModule(result);
    return result;
  }

  const moduleFilterPlaceholders = {
    oc: {
      oc_no: "Nhập OC No.",
      style: "Nhập Style",
    },
    sample: {
      sample_no: "Nhập Sample Order No.",
      style: "Nhập Style",
      created_by: "Nhập Created By",
    },
    sale_asn: {
      invoice_no: "Nhập Invoice No.",
      buyer_order_ref: "Nhập Buyer Order Ref/OC No.",
    },
  };

  function setModuleFilterKind(group, kind) {
    if (!moduleFilterPlaceholders[group]?.[kind]) return;
    moduleFilterKinds[group] = kind;
    $$(`.module-filter-button[data-filter-group="${group}"]`).forEach(
      (button) => button.setAttribute(
        "aria-pressed",
        String(button.dataset.filterKind === kind),
      ),
    );
    const input = $(`.${group.replace("_", "-")}-query`);
    if (input) {
      input.placeholder = moduleFilterPlaceholders[group][kind];
      input.focus();
    }
  }

  const moduleActions = {
    "oc-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "oc-search": () => runSelectedModuleAction(
      "search_oc",
      moduleFilterKinds.oc,
      $(".oc-query").value.trim(),
    ),
    "sample-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "sample-new": () => runSelectedModuleAction("open_sample_new"),
    "sample-search": () => runSelectedModuleAction(
      "search_sample",
      moduleFilterKinds.sample,
      $(".sample-query").value.trim(),
    ),
    "sale-asn-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "sale-asn-new": () => runSelectedModuleAction("open_sale_asn_new"),
    "sale-asn-search": () => runSelectedModuleAction(
      "search_sale_asn",
      moduleFilterKinds.sale_asn,
      $(".sale-asn-query").value.trim(),
    ),
    "rmpo-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "rmpo-search": () => runSelectedModuleAction(
      "search_rmpo",
      $(".rmpo-supplier-query").value.trim(),
      $(".rmpo-order-query").value.trim(),
    ),
    "indent-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "indent-search": () => selectedModule && runSelectedModuleAction(
      "search_indent",
      selectedModule.id,
      $(".indent-supplier-query").value.trim(),
      $(".indent-article-query").value.trim(),
      $(".indent-no-query").value.trim(),
      $(".indent-style-query").value.trim(),
    ),
    "list-new-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "list-new-new": () => selectedModule && runSelectedModuleAction("open_module_new", selectedModule.id),
    // Supplier là luồng 3 bước; giữ panel mở để người dùng tiếp tục bước kế.
    "supplier-list": () => selectedModule && call("open_module", selectedModule.id),
    "supplier-open": () => call("open_supplier_category", $(".supplier-category").value),
    "supplier-find": () => runSelectedModuleAction(
      "find_supplier",
      $(".supplier-query").value.trim(),
    ),
    "buyer-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "buyer-find": () => runSelectedModuleAction("find_buyer", $(".buyer-query").value.trim()),
    "company-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "company-toggle-foc": async () => {
      const result = await runSelectedModuleAction("toggle_company_foc");
      if (result?.foc_mode) {
        $(".company-foc-state").hidden = false;
        $(".company-foc-state strong").textContent = result.foc_mode;
      }
      return result;
    },
  };

  function masterFolder(category) {
    return {
      category_name: category,
      node_id: "",
      name: "Master",
      path_label: "Mặc định (Master)",
      kind: "master",
    };
  }

  function normalizeCatalogSearch(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("vi")
      .trim();
  }

  function catalogFolderTree(folders) {
    const roots = [];
    const stack = [];
    (Array.isArray(folders) ? folders : []).forEach((folder) => {
      const depth = Math.max(
        1,
        Number(folder.depth || (Array.isArray(folder.path) ? folder.path.length : 1)),
      );
      const node = { ...folder, depth, children: [] };
      while (stack.length && stack[stack.length - 1].depth >= depth) {
        stack.pop();
      }
      if (stack.length) stack[stack.length - 1].children.push(node);
      else roots.push(node);
      stack.push(node);
    });
    return roots;
  }

  function expandedCatalogFolders(category) {
    if (!catalogExpandedFoldersByCategory.has(category)) {
      catalogExpandedFoldersByCategory.set(category, new Set());
    }
    return catalogExpandedFoldersByCategory.get(category);
  }

  function catalogFolderIcon(kind) {
    if (kind === "group") {
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>';
    }
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6l2 2h9v10h-17v-12Z"/></svg>';
  }

  function renderCatalogFolderRow(folder, category, searchMode = false) {
    const nodeId = String(folder.node_id || "");
    const isGroup = folder.kind === "group";
    const expanded = expandedCatalogFolders(category).has(nodeId);
    const hasChildren = Array.isArray(folder.children) && folder.children.length > 0;
    const selected = nodeId === catalogSelectedNodeId;
    const parentPath = Array.isArray(folder.path)
      ? folder.path.slice(0, -1).join(" / ")
      : "";
    const depth = searchMode ? 0 : Math.max(0, Number(folder.depth || 1) - 1);
    const detail = searchMode
      ? (parentPath || (isGroup ? "Group" : "Folder"))
      : (isGroup
        ? `${folder.children?.length || 0} mục`
        : (hasChildren ? `${folder.children.length} mục con` : "Folder"));
    const expandButton = hasChildren && !searchMode
      ? `<button class="catalog-folder-expand" type="button"
          data-folder-toggle="${escapeHtml(nodeId)}"
          aria-label="${expanded ? "Thu gọn" : "Mở rộng"} ${escapeHtml(folder.name)}"
          aria-expanded="${expanded}">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7 5 5 5-5 5"/></svg>
        </button>`
      : '<span class="catalog-folder-expand-spacer" aria-hidden="true"></span>';

    if (isGroup) {
      return `<div class="catalog-folder-row catalog-folder-group${
        selected ? " is-selected" : ""
      }"
          data-node-kind="group" style="--folder-depth:${depth}">
        ${expandButton}
        <button class="catalog-group-heading" type="button"
          data-folder-select="${escapeHtml(nodeId)}"
          role="option" aria-selected="${selected}"
          data-catalog-group-action="select">
          <span class="catalog-folder-type-icon">${catalogFolderIcon("group")}</span>
          <span class="catalog-folder-copy">
            <strong>${escapeHtml(folder.name || "Group")}</strong>
            <small>${escapeHtml(detail)}</small>
          </span>
          <svg class="catalog-folder-check" viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-9"/></svg>
        </button>
      </div>`;
    }

    return `<div class="catalog-folder-row${selected ? " is-selected" : ""}"
        data-node-kind="folder" style="--folder-depth:${depth}">
      ${expandButton}
      <button class="catalog-folder-choice" type="button"
        data-folder-select="${escapeHtml(nodeId)}"
        role="option" aria-selected="${selected}">
        <span class="catalog-folder-type-icon">${catalogFolderIcon("folder")}</span>
        <span class="catalog-folder-copy">
          <strong>${escapeHtml(folder.name || "Folder")}</strong>
          <small>${escapeHtml(detail)}</small>
        </span>
        <svg class="catalog-folder-check" viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-9"/></svg>
      </button>
    </div>`;
  }

  function renderCatalogFolderList() {
    const category = $(".catalog-category")?.value || "";
    const host = $(".catalog-folder-list");
    if (!host || !catalogFoldersByCategory.has(category)) return;
    const folders = catalogFoldersByCategory.get(category) || [];
    const query = normalizeCatalogSearch($(".catalog-folder-search")?.value);
    const master = masterFolder(category);
    const selectedFolder = folders.find(
      (folder) => String(folder.node_id || "") === catalogSelectedNodeId,
    );
    $(".catalog-folder-current").textContent = selectedFolder?.path_label
      || "Mặc định (Master)";
    $(".catalog-browse-label").textContent = !selectedFolder
      ? "Mở Master"
      : (selectedFolder.kind === "group"
        ? "Mở group đã chọn"
        : "Mở folder đã chọn");

    const masterSelected = catalogSelectedNodeId === "";
    const masterRow = `<div class="catalog-folder-row catalog-master-row${
      masterSelected ? " is-selected" : ""
    }" data-node-kind="master" style="--folder-depth:0">
      <span class="catalog-folder-expand-spacer" aria-hidden="true"></span>
      <button class="catalog-folder-choice" type="button" data-folder-select=""
        role="option" aria-selected="${masterSelected}">
        <span class="catalog-folder-type-icon">${catalogFolderIcon("folder")}</span>
        <span class="catalog-folder-copy"><strong>${escapeHtml(master.path_label)}</strong><small>Catalog gốc</small></span>
        <svg class="catalog-folder-check" viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-9"/></svg>
      </button>
    </div>`;

    if (query) {
      const matches = folders.filter((folder) =>
        normalizeCatalogSearch(
          `${folder.name || ""} ${folder.path_label || ""}`,
        ).includes(query)
      );
      const visibleMatches = matches.slice(0, 100);
      const rows = visibleMatches.map((folder) =>
        renderCatalogFolderRow({ ...folder, children: [] }, category, true)
      ).join("");
      const more = matches.length > visibleMatches.length
        ? `<div class="catalog-folder-more">Còn ${
          matches.length - visibleMatches.length
        } kết quả — nhập thêm để thu hẹp.</div>`
        : "";
      host.innerHTML = masterRow + (rows || (
        '<div class="catalog-folder-empty">Không tìm thấy folder phù hợp.</div>'
      )) + more;
    } else {
      const expanded = expandedCatalogFolders(category);
      const rows = [];
      const appendVisible = (nodes) => {
        nodes.forEach((folder) => {
          rows.push(renderCatalogFolderRow(folder, category));
          if (folder.children?.length && expanded.has(String(folder.node_id || ""))) {
            appendVisible(folder.children);
          }
        });
      };
      appendVisible(catalogFolderTree(folders));
      host.innerHTML = masterRow + (rows.join("") || (
        '<div class="catalog-folder-empty">Không có folder nào khác.</div>'
      ));
    }
    host.setAttribute("aria-busy", "false");
    syncCatalogStepButtons();
  }

  function renderCatalogFolders(category, folders, preferred = null) {
    if (!$(".catalog-folder-list") || $(".catalog-category").value !== category) return;
    const items = Array.isArray(folders) ? folders : [];
    const wanted = preferred && preferred.category_name === category
      ? String(preferred.node_id || "")
      : "";
    catalogSelectedNodeId = items.some(
      (folder) => String(folder.node_id || "") === wanted
    ) ? wanted : "";
    const selected = items.find(
      (folder) => String(folder.node_id || "") === catalogSelectedNodeId,
    );
    if (selected && Array.isArray(selected.path)) {
      const expanded = expandedCatalogFolders(category);
      items.forEach((folder) => {
        if (
          folder.kind === "group"
          && Array.isArray(folder.path)
          && folder.path.length < selected.path.length
          && folder.path.every((name, index) => name === selected.path[index])
        ) {
          expanded.add(String(folder.node_id || ""));
        }
      });
    }
    renderCatalogFolderList();
  }

  function toggleCatalogFolder(nodeId) {
    const category = $(".catalog-category").value;
    const expanded = expandedCatalogFolders(category);
    if (expanded.has(nodeId)) expanded.delete(nodeId);
    else expanded.add(nodeId);
    renderCatalogFolderList();
  }

  async function selectCatalogFolder(nodeId) {
    if (catalogFolderSaving) return;
    const category = $(".catalog-category").value;
    const folders = catalogFoldersByCategory.get(category) || [];
    const folder = folders.find(
      (item) => String(item.node_id || "") === nodeId,
    );
    const previous = catalogSelectedNodeId;
    catalogSelectedNodeId = nodeId;
    renderCatalogFolderList();
    catalogFolderSaving = true;
    syncCatalogStepButtons();
    try {
      const result = await saveSelectedCatalogFolder();
      if (!result?.ok) {
        catalogSelectedNodeId = previous;
        renderCatalogFolderList();
      } else {
        catalogFolderEditorOpen = false;
      }
    } finally {
      catalogFolderSaving = false;
      syncCatalogStepButtons();
    }
  }

  function handleCatalogFolderClick(event) {
    const retry = event.target.closest("[data-folder-retry]");
    if (retry) {
      scanCatalogFolders(true);
      return;
    }
    const toggle = event.target.closest("[data-folder-toggle]");
    if (toggle) {
      toggleCatalogFolder(String(toggle.dataset.folderToggle || ""));
      return;
    }
    const choice = event.target.closest("[data-folder-select]");
    if (choice) {
      selectCatalogFolder(String(choice.dataset.folderSelect || ""));
    }
  }

  async function scanCatalogFolders(force = false) {
    const category = $(".catalog-category").value;
    if (category !== CATALOG_DEFAULT_CATEGORY) {
      catalogFolderScanning = false;
      syncCatalogStepButtons();
      return;
    }
    // Màn chi tiết có thể đóng/mở lại trong lúc lần scan đầu còn chạy. Không tạo
    // thêm workflow CDP song song; kết quả đầu tiên sẽ tự render khi xong.
    if (catalogFolderScanning) return;
    if (!force && catalogFoldersByCategory.has(category)) {
      renderCatalogFolders(
        category,
        catalogFoldersByCategory.get(category),
        catalogDefaultFolder,
      );
      return;
    }
    const generation = ++catalogFolderScanGeneration;
    catalogFolderScanning = true;
    $(".catalog-folder-list").innerHTML =
      '<div class="catalog-folder-empty">Đang tải danh sách…</div>';
    $(".catalog-folder-list").setAttribute("aria-busy", "true");
    setStatus("neutral", "Đang tải folder…");
    syncCatalogStepButtons();
    const result = await call(
      "scan_catalog_folders",
      category,
      Boolean(force),
    );
    if (generation !== catalogFolderScanGeneration) return;
    catalogFolderScanning = false;
    if (result?.ok && Array.isArray(result.folders)) {
      catalogFoldersByCategory.set(category, result.folders);
      if (result.default_folder !== undefined) {
        catalogDefaultFolder = result.default_folder;
      }
      renderCatalogFolders(category, result.folders, catalogDefaultFolder);
      setStatus("success", "Chọn folder hoặc group bạn thường dùng.");
    } else {
      $(".catalog-folder-list").innerHTML =
        '<div class="catalog-folder-empty">Chưa tải được folder.'
        + '<br><button class="catalog-folder-retry" type="button" '
        + 'data-folder-retry>Thử tải lại</button></div>';
      $(".catalog-folder-list").setAttribute("aria-busy", "false");
      setStatus(
        "error",
        result?.message || "Chưa tải được folder Catalog.",
      );
      syncCatalogStepButtons();
    }
  }

  async function saveSelectedCatalogFolder() {
    const result = await callQuiet(
      "set_catalog_default_folder",
      $(".catalog-category").value,
      catalogSelectedNodeId,
    );
    if (result) {
      handleResult(result);
    }
    return result;
  }

  async function browseCatalog() {
    return runSelectedModuleAction(
      "browse_catalog",
      $(".catalog-category").value,
    );
  }

  async function runCatalogAction(filterKind, query, destination = null) {
    const value = String(query || "").trim();
    if (!value) {
      setStatus("error", "Vui lòng nhập nội dung cần tìm.");
      return null;
    }
    clearCatalogResult();
    hideCatalogResults();
    catalogPendingDestination = destination;
    const result = await runSelectedModuleAction(
      "catalog_action",
      $(".catalog-category").value,
      filterKind,
      value,
      destination,
    );
    if (result?.code !== "MULTIPLE_RESULTS") {
      catalogPendingDestination = null;
    }
    return result;
  }

  function syncCatalogKind() {
    $$(".catalog-kind-button").forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.catalogKind === catalogKind),
      ));
    const input = $(".catalog-query");
    if (input) {
      input.placeholder = catalogKind === "buyer_reference"
        ? "Nhập Buyer Reference"
        : "Ví dụ: ABC123";
    }
  }

  function hideCatalogResults() {
    const wrap = $(".catalog-results");
    if (!wrap) return;
    wrap.hidden = true;
    $(".catalog-results-title").textContent = "Kết quả";
    $(".catalog-results-list").innerHTML = "";
    $(".catalog-results-count").textContent = "";
  }

  // Feature: khi có nhiều Code, hiển thị danh sách ngay trong panel để người
  // dùng chọn thay vì phải tự nhìn grid trên WFX; Không có kết quả thì báo rõ.
  function renderCatalogResults(result) {
    const wrap = $(".catalog-results");
    const list = $(".catalog-results-list");
    if (!wrap || !list) return;
    if (result.code === "MULTIPLE_RESULTS"
        && Array.isArray(result.styles) && result.styles.length) {
      $(".catalog-results-title").textContent = "Chọn Style Code";
      $(".catalog-results-count").textContent = `${result.styles.length} Code`;
      list.innerHTML = result.styles.map((style) => {
        const code = String(style.code || "");
        const parts = [];
        if (style.season) parts.push(`Season <b>${escapeHtml(style.season)}</b>`);
        if (style.internal_costsheet_status) {
          parts.push(`CS <b>${escapeHtml(style.internal_costsheet_status)}</b>`);
        }
        return `<button type="button" class="catalog-result-row" role="option"
          data-result-code="${escapeHtml(code)}">
          <span class="catalog-result-code">${escapeHtml(code)}</span>
          <span class="catalog-result-meta">${parts.join(" · ")}</span>
        </button>`;
      }).join("");
      wrap.hidden = false;
    } else if (result.code === "CATALOG_FILES_SCANNED"
        && Array.isArray(result.files)) {
      $(".catalog-results-title").textContent = "File đính kèm";
      $(".catalog-results-count").textContent = `${result.files.length} file`;
      let previousSection = "";
      list.innerHTML = result.files.length
        ? result.files.map((file) => {
          const section = String(file.section || "File");
          const sectionHeading = section !== previousSection
            ? `<div class="catalog-file-group-label" role="presentation">${
              escapeHtml(section)
            }</div>`
            : "";
          previousSection = section;
          const meta = [
            file.uploaded_on ? `Ngày: ${escapeHtml(file.uploaded_on)}` : "",
            file.uploaded_by ? `Bởi: ${escapeHtml(file.uploaded_by)}` : "",
          ].filter(Boolean).join(" · ");
          const comments = file.comments
            ? `<small>Ghi chú: ${escapeHtml(file.comments)}</small>`
            : "";
          return `${sectionHeading}<button type="button"
            class="catalog-result-row catalog-file-row" role="option"
            data-file-id="${escapeHtml(file.file_id)}">
            <span class="catalog-file-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>
            </span>
            <span class="catalog-file-copy">
              <strong title="${escapeHtml(file.file_name)}">${escapeHtml(file.file_name)}</strong>
              ${meta ? `<small>${meta}</small>` : ""}
              ${comments}
            </span>
          </button>`;
        }).join("")
        : '<div class="catalog-results-empty">'
          + 'Không có file đính kèm trong bốn mục đã kiểm tra.</div>';
      list.querySelectorAll(".catalog-file-row").forEach((row) => {
        row.addEventListener("click", () => downloadCatalogFile(row));
      });
      wrap.hidden = false;
    } else if (result.code === "NO_RESULTS") {
      $(".catalog-results-title").textContent = "Kết quả";
      $(".catalog-results-count").textContent = "";
      list.innerHTML = '<div class="catalog-results-empty">Không tìm thấy kết quả.'
        + ' Kiểm tra lại nội dung, hoặc đổi giữa Style Code và Buyer Reference.</div>';
      wrap.hidden = false;
    } else {
      hideCatalogResults();
    }
  }

  async function openCatalogResultCode(row) {
    const code = String(row?.dataset.resultCode || "");
    if (!code) return;
    $(".catalog-query").value = code;
    catalogKind = "code";
    syncCatalogKind();
    // Mở đúng Code đã chọn: lọc lại grid Master đã chuẩn bị bằng chính Code này.
    const destination = catalogPendingDestination;
    await withButtonLoading(
      row,
      () => runCatalogAction("code", code, destination),
    );
  }

  async function downloadCatalogFile(row) {
    const fileId = String(row?.dataset.fileId || "");
    if (!fileId) return;
    await withButtonLoading(
      row,
      () => call("download_catalog_file", fileId),
    );
  }

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
      ? `${warningCount} mục sẽ không được ghi. Xem Log kỹ thuật trước khi áp dụng.`
      : "";
    $(".catalog-costing-apply").disabled =
      !costingPlanToken
      || (Array.isArray(result.ambiguous_articles)
        && result.ambiguous_articles.length > 0);
    plan.hidden = false;
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

  const costingActions = {
    "export-xlsx": () => exportCatalogCosting(),
    "validate-file": () => validateCatalogCostingFile(),
    "import": () => importCatalogCosting(),
    "cancel-plan": () => discardCostingPlan(),
    "apply": () => applyCatalogCosting(),
  };

  const catalogActions = {
    "refresh-folders": () => scanCatalogFolders(true),
    "browse": () => browseCatalog(),
    "find": () => runCatalogAction(catalogKind, $(".catalog-query").value),
    "costsheet": () => runCatalogAction(
      catalogKind, $(".catalog-query").value, "costsheet"
    ),
    "bom": () => runCatalogAction(
      catalogKind, $(".catalog-query").value, "bom"
    ),
    "files": () => runCatalogAction(
      catalogKind, $(".catalog-query").value, "files"
    ),
  };

  function filterModules(query) {
    const normalized = query.trim().toLowerCase();
    let visibleTotal = $$(".favorites-list .module-button").filter(
      (button) => !normalized || button.dataset.search.includes(normalized),
    ).length;
    $$(".module-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".module-card").forEach((card) => {
        const button = card.querySelector(".module-button");
        const match = !normalized || button.dataset.search.includes(normalized);
        card.hidden = !match;
        if (match) visible += 1;
      });
      group.hidden = visible === 0;
      visibleTotal += visible;
    });
    $(".empty-state").hidden = visibleTotal !== 0;
  }

  function resetHotkeyButton() {
    const button = $(".hotkey-button");
    button.dataset.capturing = "false";
    button.textContent = hotkeyLabel;
  }

  async function installUpdate(button) {
    button.disabled = true;
    button.textContent = "Đang chuẩn bị…";
    $(".update-banner").classList.add("update-installing");
    $(".update-banner-title").textContent = "Đang chuẩn bị cập nhật";
    $(".update-banner-message").textContent =
      "Đang kiểm tra gói cài đặt an toàn. Vui lòng không đóng ứng dụng.";
    const result = await callQuiet("install_update");
    if (result) {
      setUpdateState(result);
      setStatus(result.ok ? "success" : "error", result.message || "");
    }
    if (!result || result.code !== "UPDATE_SCHEDULED") {
      $(".update-banner").classList.remove("update-installing");
      button.disabled = false;
      button.textContent = "Thử cập nhật lại";
    }
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      setStatus("success", "Đã sao chép log");
    } catch {
      setStatus("error", "Không sao chép được");
    }
  }

  function bind() {
    $(".header-actions")?.addEventListener("mousedown", (event) => event.stopPropagation());
    $$("[data-catalog-action]").forEach((button) =>
      button.addEventListener("click", () =>
        withButtonLoading(button, () => catalogActions[button.dataset.catalogAction]?.())));
    $$("[data-costing-action]").forEach((button) =>
      button.addEventListener("click", () =>
        withButtonLoading(button, () => costingActions[button.dataset.costingAction]?.())));
    $$(".catalog-kind-button").forEach((button) =>
      button.addEventListener("click", () => {
        catalogKind = button.dataset.catalogKind === "buyer_reference"
          ? "buyer_reference"
          : "code";
        syncCatalogKind();
        clearCatalogResult();
        catalogPendingDestination = null;
        discardCostingPlan();
        hideCatalogResults();
        $(".catalog-query")?.focus();
      }));
    $(".catalog-results-list").addEventListener("click", (event) => {
      const row = event.target.closest("[data-result-code]");
      if (row) openCatalogResultCode(row);
    });
    bindListboxKeys($(".catalog-results-list"));
    bindListboxKeys($(".catalog-folder-list"));
    $$("[data-module-action]").forEach((button) =>
      button.addEventListener("click", () => moduleActions[button.dataset.moduleAction]?.()));
    $$(".module-filter-button").forEach((button) =>
      button.addEventListener("click", () => setModuleFilterKind(
        button.dataset.filterGroup,
        button.dataset.filterKind,
      )));
    $(".module-list").addEventListener("click", (event) => {
      const favorite = event.target.closest(".module-favorite-button");
      if (favorite) {
        toggleModuleFavorite(favorite.dataset.favoriteModuleId);
        return;
      }
      const button = event.target.closest(".module-button");
      if (!button) return;
      const module = allModules().find(
        (item) => item.id === button.dataset.moduleId,
      );
      if (module?.kind === "generic") {
        withButtonLoading(
          button,
          () => openModuleDirect(button.dataset.moduleId),
        );
        return;
      }
      openModulePage(button.dataset.moduleId);
    });
    $(".favorites-list").addEventListener("click", (event) => {
      const favorite = event.target.closest(".module-favorite-button");
      if (favorite) {
        toggleModuleFavorite(favorite.dataset.favoriteModuleId);
        return;
      }
      const button = event.target.closest(".module-button");
      if (!button) return;
      const module = allModules().find(
        (item) => item.id === button.dataset.moduleId,
      );
      if (module?.kind === "generic") {
        withButtonLoading(
          button,
          () => openModuleDirect(button.dataset.moduleId),
        );
        return;
      }
      openModulePage(button.dataset.moduleId);
    });
    $(".module-back-button").addEventListener("click", closeModulePage);
    $(".oc-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["oc-search"](); });
    $(".sample-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["sample-search"](); });
    $(".sale-asn-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["sale-asn-search"](); });
    [".rmpo-supplier-query", ".rmpo-order-query"].forEach((selector) =>
      $(selector).addEventListener("keydown", (event) => {
        if (event.key === "Enter") moduleActions["rmpo-search"]();
      }));
    [
      ".indent-supplier-query",
      ".indent-article-query",
      ".indent-no-query",
      ".indent-style-query",
    ].forEach((selector) =>
      $(selector).addEventListener("keydown", (event) => {
        if (event.key === "Enter") moduleActions["indent-search"]();
      }));
    $(".supplier-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["supplier-find"](); });
    $(".buyer-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["buyer-find"](); });
    // Click ra ngoài app (mất focus sang cửa sổ khác) → tự thu panel về bubble.
    // Bỏ qua khi đang chạy module (busy) để panel không biến mất giữa chừng;
    // backend còn kiểm tra foreground để không thu khi bấm chính bubble/toast.
    document.documentElement.addEventListener("pointerenter", () => {
      pointerInsidePanel = true;
      hidePanelWhenIdle = false;
    });
    document.documentElement.addEventListener("pointerleave", () => {
      pointerInsidePanel = false;
    });
    window.addEventListener("blur", () => {
      if (pointerInsidePanel) {
        hidePanelWhenIdle = false;
        return;
      }
      if (busy) {
        hidePanelWhenIdle = true;
        return;
      }
      window.setTimeout(() => api()?.request_panel_hide?.(), 130);
    });
    // Nếu người dùng quay lại panel trước khi automation kết thúc thì ý định
    // hiện tại là tiếp tục dùng panel; hủy yêu cầu thu đã ghi nhận lúc blur.
    window.addEventListener("focus", () => {
      hidePanelWhenIdle = false;
    });
    window.addEventListener("keydown", trapOverlayFocus, true);
    $(".generic-module-open").addEventListener("click", openModule);
    $(".catalog-query").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      withButtonLoading($('[data-catalog-action="find"]'), () => catalogActions["find"]());
    });
    $(".catalog-category").addEventListener("change", () => {
      clearCatalogPreparation();
      hideCatalogResults();
      catalogFolderEditorOpen = false;
      $(".catalog-folder-search").value = "";
      syncCatalogStepButtons();
    });
    $(".catalog-folder-summary").addEventListener("click", () => {
      if ($(".catalog-category").value !== CATALOG_DEFAULT_CATEGORY) return;
      catalogFolderEditorOpen = !catalogFolderEditorOpen;
      syncCatalogStepButtons();
      if (catalogFolderEditorOpen) scanCatalogFolders(false);
    });
    $(".catalog-folder-search").addEventListener(
      "input", renderCatalogFolderList
    );
    $(".catalog-folder-list").addEventListener(
      "click", handleCatalogFolderClick
    );
    $(".catalog-query").addEventListener("input", () => {
      clearCatalogResult();
      catalogPendingDestination = null;
      discardCostingPlan();
      hideCatalogResults();
    });
    $(".search-box input").addEventListener("input", (event) => filterModules(event.target.value));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$(".module-page").hidden) closeModulePage();
      if (event.key === "Escape" && feedbackOverlay().classList.contains("feedback-open")) feedbackOverlay().classList.remove("feedback-open");
      if (event.key === "Escape" && settingsOverlay().classList.contains("settings-open")) closeSettings();
      if (event.key === "Escape" && $(".log-overlay").classList.contains("log-open")) $(".log-overlay").classList.remove("log-open");
    });

    $(".settings-button").addEventListener("click", () => openSettings("automation"));
    $(".settings-close-button").addEventListener("click", closeSettings);
    settingsOverlay().addEventListener("mousedown", (event) => {
      if (
        event.target === event.currentTarget
        && !settingsOverlay().classList.contains("credentials-required")
      ) closeSettings();
    });
    $$(".settings-tab").forEach((button) =>
      button.addEventListener("click", () => selectSettingsTab(button.dataset.settingsTab)));
    $(".manual-button").addEventListener("click", async () => {
      const result = await callQuiet("open_wfx_manual");
      if (result) handleResult(result);
    });
    $(".feedback-button").addEventListener("click", () => {
      feedbackOverlay().classList.add("feedback-open");
      $(".feedback-status").textContent = "";
      updateFeedbackState();
      setTimeout(() => $(".feedback-message").focus(), 0);
    });
    $(".feedback-close-button").addEventListener("click", () => feedbackOverlay().classList.remove("feedback-open"));
    feedbackOverlay().addEventListener("mousedown", (event) => {
      if (event.target === event.currentTarget) feedbackOverlay().classList.remove("feedback-open");
    });
    $(".feedback-submit-button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const message = $(".feedback-message").value.trim();
      if (message.length < 5 || feedbackSubmitting) return;
      feedbackSubmitting = true;
      updateFeedbackState();
      button.textContent = "Đang gửi...";
      const result = await callQuiet(
        "submit_feedback",
        $(".feedback-kind").value,
        message,
        $(".feedback-diagnostics-input").checked
      );
      feedbackSubmitting = false;
      button.textContent = "Gửi báo cáo";
      if (result) {
        $(".feedback-status").textContent = result.message || "";
        $(".feedback-status").dataset.tone = result.ok ? "success" : "error";
        if (result.ok) $(".feedback-message").value = "";
      }
      updateFeedbackState();
    });
    $(".feedback-message").addEventListener("input", updateFeedbackState);
    $(".log-button").addEventListener("click", () => {
      $(".log-overlay").classList.add("log-open");
      $(".log-button").classList.remove("has-alert");
      refreshJobs();
    });
    $(".log-close-button").addEventListener("click", () => $(".log-overlay").classList.remove("log-open"));
    $(".close-button").addEventListener("click", () => api()?.hide_panel?.());
    $(".stop-action-button").addEventListener("click", stopCurrentAction);
    $(".open-chrome-button").addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      const result = await call("open_chrome");
      event.currentTarget.disabled = false;
    });

    $(".toggle-password").addEventListener("click", () => {
      const input = $(".password-input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      $(".toggle-password").textContent = show ? "Ẩn" : "Hiện";
    });
    $(".account-change-button").addEventListener("click", () => {
      accountEditing = true;
      $(".account-form-status").textContent = "";
      syncAccountView();
      window.setTimeout(() => {
        $(".user-input").focus();
        $(".user-input").select();
      }, 0);
    });
    // Enter trong ô User ID / Password = Lưu và đăng nhập, không phải rê chuột.
    [".user-input", ".password-input"].forEach((selector) =>
      $(selector).addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !busy) {
          event.preventDefault();
          $(".save-button").click();
        }
      }));
    $(".save-button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const formStatus = $(".account-form-status");
      button.disabled = true;
      formStatus.dataset.tone = "neutral";
      formStatus.textContent = "Đang lưu an toàn trên máy...";
      const saved = await callQuiet(
        "save_account",
        $(".user-input").value.trim(),
        $(".password-input").value
      );
      if (!saved || !saved.ok) {
        if (saved) handleResult(saved);
        formStatus.dataset.tone = "error";
        formStatus.textContent = saved?.message || "Chưa thể lưu tài khoản.";
        button.disabled = false;
        return;
      }
      handleResult(saved);
      formStatus.textContent = "Đang kiểm tra đăng nhập WFX...";
      const loggedIn = await call("login");
      if (loggedIn && loggedIn.ok) {
        formStatus.dataset.tone = "success";
        formStatus.textContent = "Đã đăng nhập thành công.";
        $(".password-input").value = "";
        accountEditing = false;
        syncAccountView();
        window.setTimeout(closeSettings, 450);
      } else {
        formStatus.dataset.tone = "error";
        formStatus.textContent = loggedIn?.message || "Đăng nhập chưa thành công.";
      }
      button.disabled = false;
    });
    $$(".division-button").forEach((button) =>
      button.addEventListener("click", async () => {
        const key = button.dataset.division;
        if (!key || key === currentDivision) return;
        button.classList.add("is-switching");
        const result = await call("switch_division", key);
        button.classList.remove("is-switching");
        if (result && result.ok) setDivisionState(
          result.current_division,
          result.division_label,
          result.division_name
        );
      }));
    $(".return-list-input").addEventListener("change", async (event) => {
      returnToListAfterAction = event.target.checked;
      const result = await callQuiet(
        "set_return_to_list_after_action",
        returnToListAfterAction,
      );
      if (result?.return_to_list_after_action !== undefined) {
        returnToListAfterAction =
          result.return_to_list_after_action === true;
        event.target.checked = returnToListAfterAction;
      }
    });
    [".open-costing-file-input", ".open-costing-folder-input"].forEach(
      (selector) => $(selector).addEventListener("change", async () => {
        const result = await callQuiet(
          "set_costing_export_open_options",
          $(".open-costing-file-input").checked,
          $(".open-costing-folder-input").checked,
        );
        if (!result?.ok) return;
        $(".open-costing-file-input").checked =
          result.open_costing_file_after_export === true;
        $(".open-costing-folder-input").checked =
          result.open_costing_folder_after_export === true;
      }),
    );
    const hotkeyButton = $(".hotkey-button");
    hotkeyButton.addEventListener("click", () => {
      hotkeyButton.dataset.capturing = "true";
      hotkeyButton.textContent = "Đang chờ tổ hợp...";
      hotkeyButton.focus();
    });
    hotkeyButton.addEventListener("blur", () => {
      if (hotkeyButton.dataset.capturing === "true") resetHotkeyButton();
    });
    hotkeyButton.addEventListener("keydown", async (event) => {
      if (hotkeyButton.dataset.capturing !== "true") return;
      event.preventDefault();
      event.stopPropagation();
      if (["Control", "Alt", "Shift", "Meta"].includes(event.key)) return;
      if (event.key === "Escape") { resetHotkeyButton(); return; }
      const result = await callQuiet("set_hotkey", {
        ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey,
        meta: event.metaKey, key: event.key, code: event.code,
      });
      hotkeyButton.dataset.capturing = "false";
      if (result && result.ok) {
        hotkeyLabel = result.hotkey_label;
        setStatus("success", result.message || "");
      } else if (result) setStatus("error", result.message || "");
      resetHotkeyButton();
    });
    $(".autostart-input").addEventListener("change", async (event) => {
      const result = await callQuiet("set_autostart", event.target.checked);
      if (result) {
        event.target.checked = Boolean(result.autostart);
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".start-hidden-input").addEventListener("change", async (event) => {
      const result = await callQuiet("set_start_hidden", event.target.checked);
      if (result) {
        event.target.checked = Boolean(result.start_hidden);
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".toast-input").addEventListener("change", async (event) => {
      const result = await callQuiet("set_toast_enabled", event.target.checked);
      if (result) {
        toastEnabled = Boolean(result.toast_enabled);
        event.target.checked = toastEnabled;
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".focus-chrome-input").addEventListener("change", async (event) => {
      const result = await callQuiet(
        "set_focus_chrome_on_module", event.target.checked
      );
      if (result) {
        event.target.checked = Boolean(result.focus_chrome_on_module);
      }
    });
    $(".always-on-top-input").addEventListener("change", async (event) => {
      const result = await callQuiet(
        "set_always_on_top", event.target.checked
      );
      if (result) {
        event.target.checked = Boolean(result.always_on_top);
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".admin-mode-input").addEventListener("change", async (event) => {
      const result = await callQuiet("set_admin_mode", event.target.checked);
      if (result) {
        setAdminAccess(
          result.admin_access,
          result.admin_module_ids,
          result.admin_mode
        );
        setStatus(result.ok ? "success" : "error", result.message || "");
      }
    });
    $(".health-refresh").addEventListener("click", async () => {
      const result = await callQuiet("refresh_status");
      if (result) {
        setBrowserStatus(result.chrome_alive, result.browser_available, result.browser_name);
        setSessionStatus(result.session_active, result.last_login_at);
      }
    });
    $(".update-banner-button").addEventListener("click", (event) => installUpdate(event.currentTarget));
    $$("[data-theme-choice]").forEach((button) =>
      button.addEventListener("click", () => {
        applyTheme(button.dataset.themeChoice);
        api()?.set_theme?.(button.dataset.themeChoice);
      }));
    // Giao diện "Tự động": bám theo hệ điều hành, cập nhật ngay khi OS đổi theme.
    if (window.matchMedia) {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const onSystemThemeChange = () => {
        if (catalogThemeChoice === "system") {
          document.documentElement.dataset.theme = resolveTheme("system");
        }
      };
      if (media.addEventListener) media.addEventListener("change", onSystemThemeChange);
      else if (media.addListener) media.addListener(onSystemThemeChange);
    }

    $$(".activity-tabs button").forEach((button) =>
      button.addEventListener("click", () => selectActivityTab(button.dataset.activityTab)));
    bindTablistKeys($(".activity-tabs"), (tab) => selectActivityTab(tab.dataset.activityTab));
    bindTablistKeys($(".settings-tabs"), (tab) => selectSettingsTab(tab.dataset.settingsTab));
    $(".history-refresh-button").addEventListener("click", refreshJobs);
    $(".job-history").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-job-action]");
      const card = event.target.closest(".job-card");
      if (!button || !card) return;
      if (button.dataset.jobAction === "screenshot") {
        const result = await callQuiet("open_job_screenshot", card.dataset.runId);
        if (result) setStatus(result.ok ? "success" : "error", result.message || "");
      } else {
        button.disabled = true;
        const result = await call("retry_job", card.dataset.runId);
        button.disabled = false;
      }
    });
    // Xóa lịch sử xoá luôn ảnh lỗi — yêu cầu bấm xác nhận hai bước để tránh mất
    // bằng chứng do lỡ tay. Bấm lần đầu hỏi lại, tự huỷ sau 4 giây.
    let clearHistoryArmed = null;
    $(".clear-history-button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      if (button.dataset.confirm !== "true") {
        button.dataset.confirm = "true";
        button.dataset.label = button.textContent;
        button.textContent = "Bấm lần nữa để xóa";
        button.classList.add("is-danger");
        clearHistoryArmed = window.setTimeout(() => {
          button.dataset.confirm = "false";
          button.textContent = button.dataset.label || "Xóa lịch sử";
          button.classList.remove("is-danger");
        }, 4000);
        return;
      }
      window.clearTimeout(clearHistoryArmed);
      button.dataset.confirm = "false";
      button.textContent = button.dataset.label || "Xóa lịch sử";
      button.classList.remove("is-danger");
      const result = await callQuiet("clear_job_history");
      if (result) {
        renderJobs([]);
        $(".catalog-log").textContent = "Chưa có nhật ký hệ thống.";
        setStatus("success", result.message || "");
      }
    });
    $(".log-toolbar .catalog-log-copy").addEventListener(
      "click", () => copyText($(".catalog-log").textContent)
    );
  }

  window.wfxBootstrap = (state) => {
    if (!state) return;
    bootstrapReceived = true;
    if (state.app_version_label) {
      $(".app-version").textContent = `Phiên bản ${state.app_version_label}`;
      $(".settings-version-badge").textContent = `v${state.app_version_label}`;
    }
    if (Array.isArray(state.module_groups) && state.module_groups.length) {
      MODULE_GROUPS = state.module_groups;
    }
    setAccount(state.user_id);
    hasCredentials = state.has_credentials === true;
    applyTheme(state.theme);
    returnToListAfterAction =
      state.return_to_list_after_action === true;
    $(".return-list-input").checked = returnToListAfterAction;
    favoriteModuleIds = new Set(
      Array.isArray(state.favorite_module_ids)
        ? state.favorite_module_ids.map(String)
        : [],
    );
    buildModules();
    if (state.hotkey_label) {
      hotkeyLabel = state.hotkey_label;
      resetHotkeyButton();
    }
    $(".autostart-input").checked = state.autostart === true;
    $(".start-hidden-input").checked = state.start_hidden === true;
    toastEnabled = state.toast_enabled !== false;
    $(".toast-input").checked = toastEnabled;
    $(".focus-chrome-input").checked =
      state.focus_chrome_on_module !== false;
    $(".open-costing-file-input").checked =
      state.open_costing_file_after_export !== false;
    $(".open-costing-folder-input").checked =
      state.open_costing_folder_after_export === true;
    $(".always-on-top-input").checked = state.always_on_top !== false;
    catalogDefaultFolder = state.catalog_default_folder || null;
    $(".catalog-folder-current").textContent =
      catalogDefaultFolder?.path_label || "Mặc định (Master)";
    if (
      catalogDefaultFolder?.category_name
      && [...$(".catalog-category").options].some(
        (option) => option.value === catalogDefaultFolder.category_name
      )
    ) {
      $(".catalog-category").value = catalogDefaultFolder.category_name;
    }
    setAdminAccess(
      state.admin_access,
      state.admin_module_ids,
      state.admin_mode
    );
    setBrowserStatus(state.chrome_alive, state.browser_available, state.browser_name);
    setSessionStatus(state.session_active, state.last_login_at);
    setDivisionState(
      state.current_division,
      state.division_label,
      state.division_name
    );
    renderJobs(state.jobs || []);
    (state.logs || []).forEach(pushLog);
    if (!hasCredentials) {
      showCredentialPrompt(
        "MISSING_CREDENTIALS",
        "Đây là lần đầu sử dụng hoặc chưa có tài khoản đã lưu. Nhập thông tin WFX để tiếp tục."
      );
    }
  };

  function init() {
    buildModules();
    bind();
    updateFeedbackState();
    // PanelApp chủ động inject bootstrap trong luồng khởi động. Chỉ gọi bridge
    // làm fallback nếu sau một nhịp UI vẫn chưa nhận state, tránh đọc/render
    // cùng một dữ liệu hai lần ở lần mở bình thường.
    const requestFallbackBootstrap = () => window.setTimeout(() => {
      if (bootstrapReceived) return;
      api()?.get_initial_state?.().then((state) => {
        if (!bootstrapReceived) window.wfxBootstrap(state);
      });
    }, 600);
    if (api()) requestFallbackBootstrap();
    else window.addEventListener(
      "pywebviewready", requestFallbackBootstrap, { once: true }
    );
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
