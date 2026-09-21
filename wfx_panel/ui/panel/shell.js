"use strict";
// Giao diện khung: theme, tài khoản, Cài đặt, cập nhật, thẻ job.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

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
  const selected = ["jobs", "log"].includes(name)
    ? name
    : "jobs";
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
  button.setAttribute("aria-busy", "true");
  try {
    return await run();
  } finally {
    button.classList.remove("is-loading", "is-action-source");
    button.removeAttribute("aria-busy");
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
  const mismatch = code === "SESSION_USER_MISMATCH";
  const invalid = mismatch
    || ["LOGIN_FAILED", "LOGIN_TIMEOUT"].includes(code);
  prompt.hidden = false;
  prompt.dataset.tone = invalid ? "error" : "warning";
  $(".auth-prompt-title").textContent = mismatch
    ? "Trình duyệt đang mở tài khoản khác"
    : (invalid ? "Đăng nhập chưa thành công" : "Cần thông tin đăng nhập");
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

function showCatalogSpace(space, { focus = true } = {}) {
  const requested = ["costing", "styles"].includes(space) ? space : "search";
  const apparelSpaceAllowed =
    ($(".catalog-category")?.value || "") === CATALOG_DEFAULT_CATEGORY;
  catalogSpace = requested !== "search" && !apparelSpaceAllowed
    ? "search"
    : requested;
  $$("[data-catalog-space]").forEach((button) => {
    const selected = button.dataset.catalogSpace === catalogSpace;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $$("[data-catalog-space-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.catalogSpacePanel !== catalogSpace;
  });
  if (
    catalogSpace === "styles"
    && !catalogFoldersByCategory.has(CATALOG_DEFAULT_CATEGORY)
    && !catalogFolderScanning
  ) {
    scanCatalogFolders(false);
  }
  if (!focus) return;
  window.setTimeout(() => {
    if (catalogSpace === "costing") {
      $('[data-costing-action="import"]')?.focus();
    } else if (catalogSpace === "styles") {
      $(".catalog-style-group")?.focus();
    } else {
      $(".catalog-query")?.focus();
    }
  }, 0);
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
    $(".catalog-browse-label").textContent = "Mở Catalog";
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
  const costingSpaceButton = $('[data-catalog-space="costing"]');
  if (costingSpaceButton) {
    costingSpaceButton.hidden = !supportsDefault;
    costingSpaceButton.disabled = busy || catalogFolderScanning;
  }
  const searchSpaceButton = $('[data-catalog-space="search"]');
  if (searchSpaceButton) {
    searchSpaceButton.disabled = busy || catalogFolderScanning;
  }
  const styleSpaceButton = $('[data-catalog-space="styles"]');
  if (styleSpaceButton) {
    styleSpaceButton.hidden = !supportsDefault;
    styleSpaceButton.disabled = busy || catalogFolderScanning;
  }
  if (!supportsDefault && catalogSpace !== "search") {
    showCatalogSpace("search", { focus: false });
  }
  const styleGroupLocked = busy || catalogFolderScanning
    || Boolean(catalogStyleReview)
    || !catalogFoldersByCategory.has(CATALOG_DEFAULT_CATEGORY);
  if ($(".catalog-style-group-summary")) {
    $(".catalog-style-group-summary").disabled = styleGroupLocked;
  }
  if ($(".catalog-style-group-search")) {
    $(".catalog-style-group-search").disabled = styleGroupLocked;
  }
  if ($(".catalog-style-autosave-input")) {
    $(".catalog-style-autosave-input").disabled = busy;
  }
  $$("[data-style-action]").forEach((button) => {
    button.disabled = busy || catalogFolderScanning;
  });
  $$("[data-costing-action]").forEach((button) => {
    button.disabled = busy || catalogFolderScanning;
  });
  if ($(".catalog-special-rescan-input")) {
    $(".catalog-special-rescan-input").disabled =
      busy || catalogFolderScanning;
  }
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
    title.textContent = "Đang cập nhật";
    $(".update-banner-message").textContent =
      "App sẽ đóng rồi tự mở lại.";
    button.disabled = true;
    button.textContent = "Đang cài…";
  } else if (failed) {
    title.textContent = "Chưa cập nhật được";
    $(".update-banner-message").textContent =
      state.message || "Kiểm tra kết nối mạng rồi thử lại.";
    button.disabled = false;
    button.textContent = "Thử lại";
  } else if (state.can_update) {
    title.textContent = state.version
      ? `Đã có bản ${state.version}`
      : "Có bản cập nhật mới";
    $(".update-banner-message").textContent =
      "Tải, cài rồi tự mở lại. Không mất dữ liệu.";
    button.disabled = false;
    button.textContent = "Cập nhật ngay";
  }
}
window.wfxSetUpdateState = setUpdateState;

function renderJobCards(host, items, emptyMessage) {
  if (!host) return;
  if (!items.length) {
    host.innerHTML = `<div class="job-empty">${escapeHtml(emptyMessage)}</div>`;
    return;
  }
  host.innerHTML = items.map((job) => `
    <article class="job-card" data-ok="${job.ok === true}" data-attention="${escapeHtml(job.attention_kind || "")}" data-run-id="${escapeHtml(job.run_id)}">
      <span class="job-tone"></span>
      <div class="job-main">
        <div class="job-title"><strong>${escapeHtml(jobMethodLabel(job.method))}</strong><code>${escapeHtml(job.run_id)}</code></div>
        <div class="job-message">${escapeHtml(job.message)}</div>
        <div class="job-meta">${escapeHtml(job.started_at)} · ${Number(job.elapsed_ms || 0)} ms · ${escapeHtml(job.code)}</div>
      </div>
      <div class="job-actions">
        ${job.has_screenshot ? '<button type="button" data-job-action="screenshot">Ảnh</button>' : ""}
        ${job.attention_action ? `<button type="button" data-job-action="${escapeHtml(job.attention_action)}">${escapeHtml(job.attention_action_label)}</button>` : (job.retryable ? '<button type="button" data-job-action="retry">Chạy lại</button>' : "")}
      </div>
    </article>`).join("");
}

function renderJobs(items) {
  jobs = Array.isArray(items) ? items : [];
  renderJobCards(
    $('[data-activity-view="jobs"]'),
    jobs,
    "Chưa có tác vụ.",
  );
}
window.wfxSetJobHistory = renderJobs;
