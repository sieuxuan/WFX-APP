"use strict";
(() => {
  let MODULE_GROUPS = [
    { name: "Operation", accent: "cyan", modules: [
      { name: "Catalog", id: "0003_6200", icon: "CA", kind: "catalog", description: "Tìm style, kiểm tra Season/CostSheet và mở BOM hoặc Costsheet." },
      { name: "OC List", id: "0004_0050_0020", icon: "OC", kind: "generic", description: "Theo dõi và mở danh sách Order Confirmation." },
      { name: "Sample List", id: "0004_0056_4070", icon: "SL", kind: "generic", description: "Tra cứu và thao tác danh sách sample." },
      { name: "Sale ASN", id: "0004_0070_0020", icon: "AS", kind: "sale_asn", description: "Mở Sale ASN List hoặc tạo Sale ASN mới với cấu hình chuẩn." },
      { name: "RMPO List", id: "0005_0050_0020", icon: "RM", kind: "generic", description: "Theo dõi đơn mua nguyên phụ liệu." },
      { name: "Indent List", id: "0005_0080_0020", icon: "IN", kind: "generic", description: "Mở danh sách Indent." },
      { name: "QA List", id: "0063_0030_0020", icon: "QA", kind: "generic", description: "Mở danh sách kiểm tra chất lượng." },
    ]},
    { name: "Finance", accent: "violet", modules: [
      { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR", kind: "generic", description: "Mở danh sách Advance PR." },
      { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI", kind: "generic", description: "Mở danh sách hóa đơn nhà cung cấp." },
      { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI", kind: "generic", description: "Mở danh sách hóa đơn chi phí." },
    ]},
    { name: "Admin", accent: "amber", modules: [
      { name: "Org Structure", id: "0090_0001", icon: "OR", kind: "generic", description: "Mở cấu trúc tổ chức." },
      { name: "System Coding", id: "0090_0250", icon: "SC", kind: "generic", description: "Mở cấu hình mã hệ thống." },
      { name: "Company Setup", id: "0090_0007", icon: "CO", kind: "generic", description: "Mở thiết lập công ty." },
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
  let busy = false;
  let closeAfterModule = true;
  let hotkeyLabel = "Ctrl + Shift + X";
  let selectedModule = null;
  let jobs = [];
  let adminAccess = false;
  let adminMode = false;
  let adminModuleIds = new Set();
  let sessionActive = null;
  let currentDivision = null;
  let hasCredentials = false;
  let toastEnabled = true;
  let lastCatalogResult = null;
  let catalogKind = "code";
  let catalogThemeChoice = "light";
  let catalogDefaultFolder = null;
  const catalogFoldersByCategory = new Map();
  const catalogExpandedFoldersByCategory = new Map();
  const CATALOG_DEFAULT_CATEGORY = "Apparel";
  let catalogSelectedNodeId = "";
  let catalogFolderScanning = false;
  let catalogFolderSaving = false;
  let catalogFolderScanGeneration = 0;
  const MODULE_RUN_METHODS = new Set([
    "open_module", "prepare_catalog", "find_code", "find_buyer_reference",
    "open_catalog_destination", "browse_catalog", "catalog_action",
    "open_sale_asn_new", "open_supplier_category", "find_supplier", "find_buyer",
  ]);
  const BUSY_MESSAGES = {
    open_module: "Đang mở module trên WFX…",
    prepare_catalog: "Đang chuẩn bị Catalog…",
    browse_catalog: "Đang mở vị trí Catalog…",
    catalog_action: "Đang tìm và mở dữ liệu Catalog…",
    find_code: "Đang tìm Style Code…",
    find_buyer_reference: "Đang tìm Buyer Reference…",
    open_catalog_destination: "Đang mở dữ liệu style…",
    open_sale_asn_new: "Đang mở Sale ASN mới…",
    open_supplier_category: "Đang mở Supplier…",
    find_supplier: "Đang tìm Supplier…",
    find_buyer: "Đang tìm Buyer…",
    switch_division: "Đang đổi Division…",
    login: "Đang đăng nhập WFX…",
  };

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

  function buildModules() {
    $(".module-list").innerHTML = visibleModuleGroups().map((group) => `
      <section class="module-group" data-group="${escapeHtml(group.name)}">
        <div class="group-heading"><span class="group-accent accent-${escapeHtml(group.accent)}"></span><span>${escapeHtml(group.name)}</span><span class="group-count">${group.modules.length}</span></div>
        <div class="module-grid">${group.modules.map((module) => `
          <button class="module-button module--${escapeHtml(module.kind || "generic")} module--${escapeHtml(group.name.toLowerCase())}" type="button"
            data-module-id="${escapeHtml(module.id)}"
            data-search="${escapeHtml(`${module.name} ${group.name} ${module.description || ""}`.toLowerCase())}">
            <span class="module-icon accent-${escapeHtml(group.accent)}">${moduleIconSvg(module.icon)}</span>
            <span class="module-copy"><span class="module-name">${escapeHtml(module.name)}</span></span>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
          </button>`).join("")}</div>
      </section>`).join("");
    filterModules($(".search-box input")?.value || "");
  }

  function setBusy(value, message = "Đang xử lý trên WFX…") {
    busy = value;
    document.body.classList.toggle("is-busy", value);
    const progress = $(".operation-progress");
    if (progress) {
      progress.hidden = !value;
      $(".operation-progress-text").textContent = message;
    }
    $$("button, select, input").forEach((element) => {
      if (element.closest(".settings-overlay")) return;
      if (element.matches(".close-button, .module-close-button")) return;
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

  function focusModuleSearch() {
    if (settingsOverlay().classList.contains("credentials-required")) {
      const target = $(".user-input").value.trim() ? $(".password-input") : $(".user-input");
      target.focus();
      return;
    }
    closeSettings();
    closeModuleModal();
    $(".log-overlay").classList.remove("log-open");
    feedbackOverlay().classList.remove("feedback-open");
    const input = $(".search-box input");
    input.focus();
    input.select();
  }
  window.wfxFocusModuleSearch = focusModuleSearch;

  function setStatus(tone, label) {
    const status = $(".footer-status");
    status.dataset.tone = tone || "neutral";
    $(".footer-status-text").textContent = label || "";
    const modalStatus = $(".module-modal-status");
    if (modalStatus && $(".module-overlay").classList.contains("module-open")) {
      modalStatus.textContent = label || "";
    }
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
    const current = pre.textContent === "Chưa có nhật ký hệ thống." ? "" : pre.textContent;
    pre.textContent = (current ? `${current}\n` : "") + line;
    pre.scrollTop = pre.scrollHeight;
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

  function setAccount(userId) { $(".user-input").value = userId || ""; }
  window.wfxSetAccount = setAccount;

  function selectSettingsTab(name) {
    if (settingsOverlay().classList.contains("credentials-required") && name !== "account") return;
    const selected = name === "app" ? "app" : "account";
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

  async function withButtonLoading(button, run) {
    if (!button) return run();
    button.classList.add("is-loading");
    try {
      return await run();
    } finally {
      button.classList.remove("is-loading");
    }
  }

  function openSettings(tabName = "account") {
    selectSettingsTab(tabName);
    const overlay = settingsOverlay();
    overlay.classList.add("settings-open");
    overlay.setAttribute("aria-hidden", "false");
  }

  function closeSettings() {
    const overlay = settingsOverlay();
    if (overlay.classList.contains("credentials-required")) return;
    overlay.classList.remove("settings-open");
    overlay.setAttribute("aria-hidden", "true");
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
    settingsOverlay().classList.add("credentials-required");
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
  }

  function setStyleStatus(style) {
    const node = $(".style-status");
    if (!node) return;
    if (!style || !style.code) {
      node.hidden = true;
      return;
    }
    $(".style-status-code").textContent = style.code;
    $(".style-status-season").textContent = style.season || "—";
    $(".style-status-costsheet").textContent = style.internal_costsheet_status || "—";
    node.hidden = false;
  }
  window.wfxSetStyleStatus = setStyleStatus;

  function clearCatalogResult() {
    lastCatalogResult = null;
    setStyleStatus(null);
    syncCatalogStepButtons();
  }

  function clearCatalogPreparation() {
    clearCatalogResult();
  }

  function syncCatalogStepButtons() {
    const category = $(".catalog-category")?.value || "";
    const supportsDefault = category === CATALOG_DEFAULT_CATEGORY;
    const scanned = catalogFoldersByCategory.has(category);
    if ($(".catalog-browse-card")) {
      $(".catalog-browse-card").hidden = !supportsDefault;
    }
    if ($(".catalog-folder-search")) {
      $(".catalog-folder-search").disabled =
        busy || catalogFolderScanning || catalogFolderSaving
          || !supportsDefault || !scanned;
    }
    if ($(".catalog-folder-list")) {
      $(".catalog-folder-list").setAttribute(
        "aria-disabled",
        String(
          busy || catalogFolderScanning || catalogFolderSaving
            || !supportsDefault || !scanned,
        ),
      );
      $$(".catalog-folder-list button").forEach((button) => {
        button.disabled =
          busy || catalogFolderScanning || catalogFolderSaving
            || !supportsDefault || !scanned;
      });
    }
    if ($(".catalog-browse-button")) {
      $(".catalog-browse-button").disabled =
        busy || catalogFolderScanning || catalogFolderSaving
          || !supportsDefault || !scanned;
    }
    if ($(".catalog-folder-refresh")) {
      $(".catalog-folder-refresh").disabled =
        busy || catalogFolderScanning || catalogFolderSaving;
    }
    $$(".catalog-query-actions button").forEach((button) => {
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
          <div class="job-title"><strong>${escapeHtml(job.method)}</strong><code>${escapeHtml(job.run_id)}</code></div>
          <div class="job-message">${escapeHtml(job.message)}</div>
          <div class="job-meta">${escapeHtml(job.started_at)} · ${Number(job.elapsed_ms || 0)} ms · ${escapeHtml(job.code)}</div>
        </div>
        <div class="job-actions">
          ${job.has_screenshot ? '<button type="button" data-job-action="screenshot">Ảnh</button>' : ""}
          ${job.ok ? "" : '<button type="button" data-job-action="retry">Chạy lại</button>'}
        </div>
      </article>`).join("");
  }
  window.wfxSetJobHistory = renderJobs;

  function handleResult(result) {
    if (!result) return;
    setStatus(result.ok ? "success" : "error", result.message || "");
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
    if (result.code === "RESULT_OPENED" && result.article_code) {
      rememberCatalogResult(result);
    } else if ([
      "NO_RESULTS", "MULTIPLE_RESULTS", "CATALOG_RESULT_REQUIRED",
      "CATALOG_RESULT_CHANGED", "CATALOG_RESULT_EXPIRED",
    ].includes(result.code)) {
      clearCatalogResult();
    }
    if (["MULTIPLE_RESULTS", "NO_RESULTS", "RESULT_OPENED"].includes(result.code)) {
      renderCatalogResults(result);
    }
    if (result.default_folder !== undefined) {
      catalogDefaultFolder = result.default_folder;
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
  window.wfxHandleBackendResult = handleResult;

  async function call(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng");
      return null;
    }
    const busyMessage = BUSY_MESSAGES[method] || "Đang xử lý trên WFX…";
    setBusy(true, busyMessage);
    setStatus("neutral", busyMessage);
    try {
      if (MODULE_RUN_METHODS.has(method)) {
        await api()?.focus_automation_browser?.();
      }
      const result = await bridge[method](...args);
      handleResult(result);
      return result;
    } catch (error) {
      setStatus("error", String(error));
      return null;
    } finally {
      setBusy(false);
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

  function openModuleModal(moduleId) {
    const module = allModules().find((item) => item.id === moduleId);
    if (!module) return;
    selectedModule = module;
    const icon = $(".module-modal-icon");
    icon.className = `module-modal-icon accent-${module.accent}`;
    icon.innerHTML = moduleIconSvg(module.icon);
    $("#module-modal-title").textContent = module.name;
    $(".module-modal-subtitle").textContent =
      module.description || "Mở màn hình WFX.";
    $$('[data-module-view]').forEach((view) => {
      view.hidden = view.dataset.moduleView !== module.kind;
    });
    $(".generic-module-icon").innerHTML = moduleIconSvg(module.icon);
    $(".module-modal-status").textContent = "";
    const overlay = $(".module-overlay");
    overlay.classList.add("module-open");
    overlay.setAttribute("aria-hidden", "false");
    const focusTarget = {
      catalog: ".catalog-query",
      sale_asn: '[data-module-action="sale-asn-list"]',
      supplier: ".supplier-category",
      buyer: '[data-module-action="buyer-list"]',
      generic: ".generic-module-open",
    }[module.kind] || ".generic-module-open";
    setTimeout(() => $(focusTarget)?.focus(), 0);
    if (module.kind === "catalog") {
      syncCatalogKind();
      hideCatalogResults();
      syncCatalogStepButtons();
      if ($(".catalog-category").value === CATALOG_DEFAULT_CATEGORY) {
        setTimeout(() => scanCatalogFolders(false), 0);
      }
    }
  }

  function closeModuleModal() {
    const overlay = $(".module-overlay");
    overlay.classList.remove("module-open");
    overlay.setAttribute("aria-hidden", "true");
  }

  function dismissAfterSuccessfulModule(result) {
    // MULTIPLE_RESULTS tuy ok=true nhưng người dùng còn phải chọn 1 Code trong
    // danh sách ngay trên panel — không được tự thu panel lúc này.
    if (result && result.code === "MULTIPLE_RESULTS") return;
    if (result && result.ok && closeAfterModule) {
      window.setTimeout(() => api()?.hide_panel?.(), 120);
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
  }

  async function runSelectedModuleAction(method, ...args) {
    const result = await call(method, ...args);
    dismissAfterSuccessfulModule(result);
    return result;
  }

  const moduleActions = {
    "sale-asn-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "sale-asn-new": () => runSelectedModuleAction("open_sale_asn_new"),
    "supplier-open": () => runSelectedModuleAction("open_supplier_category", $(".supplier-category").value),
    "supplier-find": () => runSelectedModuleAction("find_supplier", $(".supplier-query").value.trim()),
    "buyer-list": () => selectedModule && runSelectedModuleAction("open_module", selectedModule.id),
    "buyer-find": () => runSelectedModuleAction("find_buyer", $(".buyer-query").value.trim()),
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
      }
    } finally {
      catalogFolderSaving = false;
      syncCatalogStepButtons();
    }
  }

  function handleCatalogFolderClick(event) {
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
    // Modal có thể đóng/mở lại trong lúc lần scan đầu còn chạy. Không tạo
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
    $(".module-modal-status").textContent = "Đang tải folder…";
    syncCatalogStepButtons();
    const result = await callQuiet(
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
      $(".module-modal-status").textContent =
        "Chọn folder hoặc group bạn thường dùng.";
    } else {
      $(".catalog-folder-list").innerHTML =
        '<div class="catalog-folder-empty">Chưa tải được folder.</div>';
      $(".catalog-folder-list").setAttribute("aria-busy", "false");
      $(".module-modal-status").textContent =
        result?.message || "Chưa tải được folder Catalog.";
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
      $(".module-modal-status").textContent = result.message || "";
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
    return runSelectedModuleAction(
      "catalog_action",
      $(".catalog-category").value,
      filterKind,
      value,
      destination,
    );
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
    } else if (result.code === "NO_RESULTS") {
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
    await withButtonLoading(row, () => runCatalogAction("code", code));
  }

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
  };

  function filterModules(query) {
    const normalized = query.trim().toLowerCase();
    let visibleTotal = 0;
    $$(".module-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".module-button").forEach((button) => {
        const match = !normalized || button.dataset.search.includes(normalized);
        button.hidden = !match;
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
    $$(".catalog-kind-button").forEach((button) =>
      button.addEventListener("click", () => {
        catalogKind = button.dataset.catalogKind === "buyer_reference"
          ? "buyer_reference"
          : "code";
        syncCatalogKind();
        clearCatalogResult();
        hideCatalogResults();
        $(".catalog-query")?.focus();
      }));
    $(".catalog-results-list").addEventListener("click", (event) => {
      const row = event.target.closest("[data-result-code]");
      if (row) openCatalogResultCode(row);
    });
    $$("[data-module-action]").forEach((button) =>
      button.addEventListener("click", () => moduleActions[button.dataset.moduleAction]?.()));
    $(".module-list").addEventListener("click", (event) => {
      const button = event.target.closest(".module-button");
      if (!button) return;
      const module = allModules().find(
        (item) => item.id === button.dataset.moduleId
      );
      if (module && ["catalog", "sale_asn", "supplier", "buyer"].includes(module.kind)) {
        openModuleModal(button.dataset.moduleId);
      } else {
        openModuleDirect(button.dataset.moduleId);
      }
    });
    $(".module-close-button").addEventListener("click", closeModuleModal);
    $(".supplier-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["supplier-find"](); });
    $(".buyer-query").addEventListener("keydown", (event) => { if (event.key === "Enter") moduleActions["buyer-find"](); });
    // Click ra ngoài app (mất focus sang cửa sổ khác) → tự thu panel về bubble.
    // Bỏ qua khi đang chạy module (busy) để panel không biến mất giữa chừng;
    // backend còn kiểm tra foreground để không thu khi bấm chính bubble/toast.
    window.addEventListener("blur", () => {
      if (busy) return;
      window.setTimeout(() => api()?.request_panel_hide?.(), 130);
    });
    $(".module-overlay").addEventListener("mousedown", (event) => {
      if (event.target === event.currentTarget) closeModuleModal();
    });
    $(".generic-module-open").addEventListener("click", openModule);
    $(".catalog-query").addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      withButtonLoading($('[data-catalog-action="find"]'), () => catalogActions["find"]());
    });
    $(".catalog-category").addEventListener("change", () => {
      clearCatalogPreparation();
      hideCatalogResults();
      $(".catalog-folder-search").value = "";
      $(".module-modal-status").textContent = "";
      syncCatalogStepButtons();
      if ($(".catalog-category").value === CATALOG_DEFAULT_CATEGORY) {
        scanCatalogFolders(false);
      }
    });
    $(".catalog-folder-search").addEventListener(
      "input", renderCatalogFolderList
    );
    $(".catalog-folder-list").addEventListener(
      "click", handleCatalogFolderClick
    );
    $(".catalog-query").addEventListener("input", () => {
      clearCatalogResult();
      hideCatalogResults();
    });
    $(".search-box input").addEventListener("input", (event) => filterModules(event.target.value));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && $(".module-overlay").classList.contains("module-open")) closeModuleModal();
      if (event.key === "Escape" && feedbackOverlay().classList.contains("feedback-open")) feedbackOverlay().classList.remove("feedback-open");
      if (event.key === "Escape" && settingsOverlay().classList.contains("settings-open")) closeSettings();
      if (event.key === "Escape" && $(".log-overlay").classList.contains("log-open")) $(".log-overlay").classList.remove("log-open");
    });

    $(".settings-button").addEventListener("click", () => openSettings("account"));
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
      setTimeout(() => $(".feedback-message").focus(), 0);
    });
    $(".feedback-close-button").addEventListener("click", () => feedbackOverlay().classList.remove("feedback-open"));
    feedbackOverlay().addEventListener("mousedown", (event) => {
      if (event.target === event.currentTarget) feedbackOverlay().classList.remove("feedback-open");
    });
    $(".feedback-submit-button").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const message = $(".feedback-message").value.trim();
      button.disabled = true;
      button.textContent = "Đang gửi...";
      const result = await callQuiet(
        "submit_feedback",
        $(".feedback-kind").value,
        message,
        $(".feedback-diagnostics-input").checked
      );
      button.disabled = false;
      button.textContent = "Gửi báo cáo";
      if (result) {
        $(".feedback-status").textContent = result.message || "";
        $(".feedback-status").dataset.tone = result.ok ? "success" : "error";
        if (result.ok) $(".feedback-message").value = "";
      }
    });
    $(".log-button").addEventListener("click", () => {
      $(".log-overlay").classList.add("log-open");
      $(".log-button").classList.remove("has-alert");
      refreshJobs();
    });
    $(".log-close-button").addEventListener("click", () => $(".log-overlay").classList.remove("log-open"));
    $(".close-button").addEventListener("click", () => api()?.hide_panel?.());
    $(".open-chrome-button").addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      const result = await callQuiet("open_chrome");
      if (result) handleResult(result);
      event.currentTarget.disabled = false;
    });

    $(".toggle-password").addEventListener("click", () => {
      const input = $(".password-input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      $(".toggle-password").textContent = show ? "Ẩn" : "Hiện";
    });
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
      const loggedIn = await callQuiet("login");
      if (loggedIn) handleResult(loggedIn);
      if (loggedIn && loggedIn.ok) {
        formStatus.dataset.tone = "success";
        formStatus.textContent = "Đã đăng nhập thành công.";
        $(".password-input").value = "";
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
    $(".close-module-input").addEventListener("change", (event) => {
      closeAfterModule = event.target.checked;
      api()?.set_close_after_module?.(closeAfterModule);
    });
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
        const result = await callQuiet("retry_job", card.dataset.runId);
        if (result) handleResult(result);
        button.disabled = false;
      }
    });
    $(".clear-history-button").addEventListener("click", async () => {
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
    if (state.app_version_label) {
      $(".app-version").textContent = `Phiên bản ${state.app_version_label}`;
      $(".settings-version-badge").textContent = `v${state.app_version_label}`;
    }
    if (Array.isArray(state.module_groups) && state.module_groups.length) {
      MODULE_GROUPS = state.module_groups;
      buildModules();
    }
    setAccount(state.user_id);
    hasCredentials = state.has_credentials === true;
    applyTheme(state.theme);
    closeAfterModule = state.close_after_module !== false;
    $(".close-module-input").checked = closeAfterModule;
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
    $(".always-on-top-input").checked = state.always_on_top !== false;
    catalogDefaultFolder = state.catalog_default_folder || null;
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
    const ready = () => api()?.get_initial_state?.().then(window.wfxBootstrap);
    if (api()) ready();
    else window.addEventListener("pywebviewready", ready);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
