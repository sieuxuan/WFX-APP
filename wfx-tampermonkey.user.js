// ==UserScript==
// @name         WFX Smart Automation Panel
// @namespace    local.wfx.automation
// @version      1.1.0
// @description  Panel automation đầy đủ, Catalog Quick Search, hotkey và tự đăng nhập WFX ngay trên tab hiện tại.
// @author       WFX Automation
// @match        https://prosports.worldfashionexchange.com/*
// @icon         https://prosports.worldfashionexchange.com/favicon.ico
// @run-at       document-idle
// @noframes
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// ==/UserScript==

(function () {
  "use strict";

  const HOME_URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx";
  const SCRIPT_VERSION = "1.1.0";
  const ROOT_ID = "wfx-smart-automation-root";
  const PENDING_TTL_MS = 2 * 60 * 1000;

  const STORAGE = Object.freeze({
    account: "wfx-smart-account-v1",
    preferences: "wfx-smart-preferences-v1",
    hotkey: "wfx-smart-hotkey-v1",
    pendingLogin: "wfx-smart-pending-login-v1",
    pendingAction: "wfx-smart-pending-action-v1",
    catalog: "wfx-smart-catalog-v1",
  });

  const CATEGORIES = Object.freeze({
    Apparel: "01",
    "Fixed Asset": "04",
    Miscellaneous: "12",
    Services: "06",
    "Textiles/Fabric": "03",
    Trims: "05",
  });

  const DEFAULT_HOTKEY = Object.freeze({
    ctrl: false,
    alt: true,
    shift: true,
    meta: false,
    code: "KeyW",
    key: "W",
  });

  const MODULE_GROUPS = [
    {
      name: "Operation",
      accent: "cyan",
      modules: [
        { name: "Catalog", id: "0003_6200", icon: "CA" },
        { name: "OC List", id: "0004_0050_0020", icon: "OC" },
        { name: "Sample List", id: "0004_0056_4070", icon: "SL" },
        { name: "Sale ASN", id: "0004_0070_0020", icon: "AS" },
        { name: "RMPO List", id: "0005_0050_0020", icon: "RM" },
        { name: "Indent List", id: "0005_0080_0020", icon: "IN" },
        { name: "QA List", id: "0063_0030_0020", icon: "QA" },
      ],
    },
    {
      name: "Finance",
      accent: "violet",
      modules: [
        { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR" },
        { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI" },
        { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI" },
      ],
    },
    {
      name: "Admin",
      accent: "amber",
      modules: [
        { name: "Org Structure", id: "0090_0001", icon: "OR" },
        { name: "System Coding", id: "0090_0250", icon: "SC" },
        { name: "Company Setup", id: "0090_0007", icon: "CO" },
        { name: "Buyer List", id: "0004_0010_1720", icon: "BU" },
        { name: "Supplier List", id: "0005_0010_1290", icon: "SU" },
      ],
    },
  ];

  const ALL_MODULES = MODULE_GROUPS.flatMap((group) =>
    group.modules.map((module) => ({ ...module, group: group.name, accent: group.accent })),
  );

  let ui = null;
  let hotkeyCapture = false;
  let loginInFlight = false;
  let automationInFlight = false;
  let statusTimer = 0;
  const popupWindows = new Set();

  function readValue(key, fallback) {
    try {
      const value = GM_getValue(key);
      return value === undefined || value === null ? fallback : value;
    } catch (error) {
      console.warn("[WFX Smart] Không đọc được thiết lập:", error);
      return fallback;
    }
  }

  function writeValue(key, value) {
    try {
      GM_setValue(key, value);
      return true;
    } catch (error) {
      console.error("[WFX Smart] Không lưu được thiết lập:", error);
      return false;
    }
  }

  function deleteValue(key) {
    try {
      GM_deleteValue(key);
    } catch (error) {
      console.warn("[WFX Smart] Không xóa được trạng thái cũ:", error);
    }
  }

  function getAccount() {
    const value = readValue(STORAGE.account, {});
    return {
      userId: String(value?.userId || "").trim(),
      password: String(value?.password || ""),
      companyId: String(value?.companyId || "psh").trim() || "psh",
    };
  }

  function getPreferences() {
    const value = readValue(STORAGE.preferences, {});
    return {
      autoLoginOnOpen: value?.autoLoginOnOpen !== false,
      closeAfterModule: value?.closeAfterModule !== false,
    };
  }

  function getHotkey() {
    const value = readValue(STORAGE.hotkey, null);
    if (!value || typeof value.code !== "string") return { ...DEFAULT_HOTKEY };
    return {
      ctrl: Boolean(value.ctrl),
      alt: Boolean(value.alt),
      shift: Boolean(value.shift),
      meta: Boolean(value.meta),
      code: value.code,
      key: String(value.key || value.code),
    };
  }

  function isVisible(element) {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  }

  function findVisible(selector) {
    return [...document.querySelectorAll(selector)].find(isVisible) || null;
  }

  function findModuleAnchor(moduleId) {
    const container = document.getElementById(moduleId);
    if (!container) return null;
    if (container.matches("a")) return container;
    return container.querySelector("a");
  }

  function getAuthState() {
    if (
      findModuleAnchor("0003_6200") ||
      findModuleAnchor("0090_0250") ||
      document.querySelector("a[id*='0003_6200']")
    ) {
      return "authenticated";
    }
    if (findVisible("#txtPassword")) return "password";
    if (findVisible("#txtUserID")) return "user";
    return "unknown";
  }

  function authDetails() {
    const account = getAccount();
    const state = getAuthState();
    if (state === "authenticated") {
      return { state, label: "Đã đăng nhập", detail: account.userId || "WFX session", tone: "success" };
    }
    if (!account.userId || !account.password) {
      return { state, label: "Chưa cấu hình", detail: "Thêm tài khoản để tự đăng nhập", tone: "warning" };
    }
    if (state === "user" || state === "password") {
      return { state, label: "Sẵn sàng login", detail: account.userId, tone: "warning" };
    }
    return { state, label: "Chưa xác định", detail: account.userId, tone: "neutral" };
  }

  function setNativeValue(input, value) {
    const prototype = input instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function clickElement(element) {
    if (!element) return false;
    element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
    element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
    element.click();
    return true;
  }

  function startPendingLogin(source) {
    const pending = {
      source: source || "panel",
      attempts: 0,
      startedAt: Date.now(),
      expiresAt: Date.now() + PENDING_TTL_MS,
    };
    writeValue(STORAGE.pendingLogin, pending);
    return pending;
  }

  function getPending(key) {
    const pending = readValue(key, null);
    if (!pending || Number(pending.expiresAt || 0) < Date.now()) {
      deleteValue(key);
      return null;
    }
    return pending;
  }

  function bumpPendingLogin(pending, step) {
    const next = {
      ...pending,
      attempts: Number(pending.attempts || 0) + 1,
      lastStep: step,
      lastAttemptAt: Date.now(),
    };
    writeValue(STORAGE.pendingLogin, next);
    return next;
  }

  function showToast(message, tone = "info", timeout = 3300) {
    if (!ui) return;
    const item = document.createElement("div");
    item.className = `toast toast-${tone}`;
    item.innerHTML = `<span class="toast-dot"></span><span class="toast-text"></span>`;
    item.querySelector(".toast-text").textContent = message;
    ui.toastStack.appendChild(item);
    requestAnimationFrame(() => item.classList.add("toast-visible"));
    window.setTimeout(() => {
      item.classList.remove("toast-visible");
      window.setTimeout(() => item.remove(), 220);
    }, timeout);
  }

  function setBusy(isBusy, text = "Đang xử lý...") {
    loginInFlight = isBusy;
    if (!ui) return;
    ui.loginButton.disabled = isBusy;
    ui.loginButton.classList.toggle("is-loading", isBusy);
    ui.loginButton.querySelector("span").textContent = isBusy ? text : "Kết nối / Login";
  }

  async function continueLogin({ reset = false, source = "panel" } = {}) {
    if (loginInFlight) return false;
    const account = getAccount();
    if (!account.userId || !account.password) {
      openPanel({ skipAutoLogin: true });
      openSettings();
      showToast("Hãy lưu User ID và Password trước.", "warning", 4500);
      return false;
    }

    let pending = reset ? startPendingLogin(source) : getPending(STORAGE.pendingLogin);
    if (!pending) pending = startPendingLogin(source);
    if (Number(pending.attempts || 0) >= 3) {
      deleteValue(STORAGE.pendingLogin);
      setBusy(false);
      openPanel({ skipAutoLogin: true });
      showToast("Đăng nhập chưa thành công. Hãy kiểm tra lại tài khoản.", "error", 5200);
      return false;
    }

    setBusy(true, "Đang đăng nhập...");
    const state = getAuthState();
    if (state === "authenticated") {
      deleteValue(STORAGE.pendingLogin);
      setBusy(false);
      refreshStatus();
      await processPendingAction();
      return true;
    }

    if (state === "password") {
      const passwordInput = findVisible("#txtPassword");
      const loginButton = findVisible("#btlLogin[value='Log In'], input[name='btlLogin'][value='Log In']");
      if (!passwordInput || !loginButton) {
        setBusy(false);
        showToast("Không tìm thấy nút Log In trên trang.", "error");
        return false;
      }
      bumpPendingLogin(pending, "password");
      setNativeValue(passwordInput, account.password);
      showToast("Đang xác thực tài khoản...", "info");
      window.setTimeout(() => clickElement(loginButton), 180);
      return true;
    }

    if (state === "user") {
      const userInput = findVisible("#txtUserID");
      const companyInput = findVisible("#txtCompany");
      const nextButton = findVisible("#btlLogin[value='Next'], input[name='btlLogin'][value='Next']");
      if (!userInput || !nextButton) {
        setBusy(false);
        showToast("Không tìm thấy nút Next trên trang.", "error");
        return false;
      }
      bumpPendingLogin(pending, "user");
      setNativeValue(userInput, account.userId);
      if (companyInput) setNativeValue(companyInput, account.companyId);
      showToast("Đã điền User ID, đang chuyển bước...", "info");
      window.setTimeout(() => clickElement(nextButton), 180);
      return true;
    }

    bumpPendingLogin(pending, "navigate");
    showToast("Đang mở trang đăng nhập WFX...", "info");
    window.location.assign(HOME_URL);
    return true;
  }

  async function waitForModuleAnchor(moduleId, timeoutMs = 6500) {
    const immediate = findModuleAnchor(moduleId);
    if (immediate) return immediate;
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        observer.disconnect();
        resolve(null);
      }, timeoutMs);
      const observer = new MutationObserver(() => {
        const anchor = findModuleAnchor(moduleId);
        if (!anchor) return;
        window.clearTimeout(timeout);
        observer.disconnect();
        resolve(anchor);
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    });
  }

  async function openModule(module) {
    if (!module) return;
    if (getAuthState() !== "authenticated") {
      writeValue(STORAGE.pendingAction, {
        type: "module",
        moduleId: module.id,
        moduleName: module.name,
        expiresAt: Date.now() + PENDING_TTL_MS,
      });
      showToast(`Sẽ mở ${module.name} sau khi đăng nhập.`, "info");
      await continueLogin({ reset: true, source: "module" });
      return;
    }

    const anchor = await waitForModuleAnchor(module.id);
    if (!anchor) {
      showToast(`Không tìm thấy menu ${module.name} trên trang hiện tại.`, "error", 5000);
      return;
    }
    deleteValue(STORAGE.pendingAction);
    showToast(`Đang mở ${module.name}...`, "success");
    if (getPreferences().closeAfterModule) closePanel();
    window.setTimeout(() => clickElement(anchor), 100);
  }

  async function processPendingAction() {
    const action = getPending(STORAGE.pendingAction);
    if (!action || action.type !== "module" || getAuthState() !== "authenticated") return;
    const module = ALL_MODULES.find((item) => item.id === action.moduleId) || {
      id: action.moduleId,
      name: action.moduleName || "module",
    };
    await openModule(module);
  }

  function formatHotkey(hotkey = getHotkey()) {
    const parts = [];
    if (hotkey.ctrl) parts.push("Ctrl");
    if (hotkey.alt) parts.push("Alt");
    if (hotkey.shift) parts.push("Shift");
    if (hotkey.meta) parts.push("Win");
    const key = hotkey.code.startsWith("Key")
      ? hotkey.code.slice(3)
      : hotkey.code.startsWith("Digit")
        ? hotkey.code.slice(5)
        : hotkey.key;
    parts.push(key);
    return parts.join(" + ");
  }

  function eventMatchesHotkey(event, hotkey = getHotkey()) {
    return (
      event.code === hotkey.code &&
      event.ctrlKey === hotkey.ctrl &&
      event.altKey === hotkey.alt &&
      event.shiftKey === hotkey.shift &&
      event.metaKey === hotkey.meta
    );
  }

  function updateHotkeyLabels() {
    if (!ui) return;
    const label = formatHotkey();
    ui.hotkeyLabel.textContent = label;
    ui.hotkeyButton.textContent = hotkeyCapture ? "Nhấn tổ hợp phím..." : label;
    ui.hotkeyButton.classList.toggle("capturing", hotkeyCapture);
  }

  function beginHotkeyCapture() {
    hotkeyCapture = true;
    updateHotkeyLabels();
    showToast("Nhấn tổ hợp mới. Esc để hủy.", "info");
  }

  function handleKeydown(event) {
    if (hotkeyCapture) {
      event.preventDefault();
      event.stopPropagation();
      if (event.code === "Escape") {
        hotkeyCapture = false;
        updateHotkeyLabels();
        return;
      }
      if (["ControlLeft", "ControlRight", "AltLeft", "AltRight", "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight"].includes(event.code)) {
        return;
      }
      const functionKey = /^F(?:[2-9]|1[0-2])$/.test(event.code);
      if (!event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey && !functionKey) {
        showToast("Dùng ít nhất Ctrl, Alt, Shift hoặc phím F2–F12.", "warning", 4200);
        return;
      }
      writeValue(STORAGE.hotkey, {
        ctrl: event.ctrlKey,
        alt: event.altKey,
        shift: event.shiftKey,
        meta: event.metaKey,
        code: event.code,
        key: event.key.length === 1 ? event.key.toUpperCase() : event.key,
      });
      hotkeyCapture = false;
      updateHotkeyLabels();
      showToast(`Đã đặt hotkey: ${formatHotkey()}`, "success");
      return;
    }

    if (eventMatchesHotkey(event)) {
      event.preventDefault();
      event.stopPropagation();
      togglePanel();
    }
  }

  function refreshStatus() {
    if (!ui) return;
    const details = authDetails();
    ui.statusCard.dataset.tone = details.tone;
    ui.statusTitle.textContent = details.label;
    ui.statusDetail.textContent = details.detail;
    ui.accountChip.textContent = getAccount().userId || "Chưa có account";
    ui.loginButton.querySelector("span").textContent = loginInFlight ? "Đang đăng nhập..." : "Kết nối / Login";
  }

  function filterModules(query) {
    if (!ui) return;
    const normalized = String(query || "").trim().toLocaleLowerCase("vi");
    let visibleCount = 0;
    ui.moduleButtons.forEach((button) => {
      const matches = !normalized || button.dataset.search.includes(normalized);
      button.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    ui.groupSections.forEach((section) => {
      section.hidden = ![...section.querySelectorAll(".module-button")].some((button) => !button.hidden);
    });
    ui.emptyState.hidden = visibleCount > 0;
  }

  function openPanel({ skipAutoLogin = false } = {}) {
    if (!ui) return;
    ui.panel.classList.add("panel-open");
    ui.launcher.classList.add("launcher-active");
    ui.panel.setAttribute("aria-hidden", "false");
    refreshStatus();
    window.clearInterval(statusTimer);
    statusTimer = window.setInterval(refreshStatus, 1500);
    window.setTimeout(() => ui.searchInput.focus(), 180);

    const account = getAccount();
    if (!account.userId || !account.password) {
      openSettings();
      return;
    }
    if (!skipAutoLogin && getPreferences().autoLoginOnOpen && getAuthState() !== "authenticated") {
      void continueLogin({ reset: true, source: "panel" });
    }
  }

  function closePanel() {
    if (!ui) return;
    ui.panel.classList.remove("panel-open");
    ui.launcher.classList.remove("launcher-active");
    ui.panel.setAttribute("aria-hidden", "true");
    ui.settingsOverlay.classList.remove("settings-open");
    hotkeyCapture = false;
    updateHotkeyLabels();
    window.clearInterval(statusTimer);
  }

  function togglePanel() {
    if (!ui) return;
    if (ui.panel.classList.contains("panel-open")) closePanel();
    else openPanel();
  }

  function openSettings() {
    if (!ui) return;
    const account = getAccount();
    const preferences = getPreferences();
    ui.userInput.value = account.userId;
    ui.passwordInput.value = account.password;
    ui.companyInput.value = account.companyId;
    ui.autoLoginInput.checked = preferences.autoLoginOnOpen;
    ui.closeAfterModuleInput.checked = preferences.closeAfterModule;
    ui.passwordInput.type = "password";
    ui.togglePasswordButton.textContent = "Hiện";
    updateHotkeyLabels();
    ui.settingsOverlay.classList.add("settings-open");
    window.setTimeout(() => (account.userId ? ui.passwordInput : ui.userInput).focus(), 100);
  }

  function closeSettings() {
    if (!ui) return;
    ui.settingsOverlay.classList.remove("settings-open");
    hotkeyCapture = false;
    updateHotkeyLabels();
  }

  function saveSettings() {
    const userId = ui.userInput.value.trim();
    const password = ui.passwordInput.value;
    const companyId = ui.companyInput.value.trim() || "psh";
    if (!userId || !password) {
      showToast("User ID và Password không được để trống.", "warning");
      return;
    }
    const accountSaved = writeValue(STORAGE.account, { userId, password, companyId });
    const preferencesSaved = writeValue(STORAGE.preferences, {
      autoLoginOnOpen: ui.autoLoginInput.checked,
      closeAfterModule: ui.closeAfterModuleInput.checked,
    });
    if (!accountSaved || !preferencesSaved) {
      showToast("Không thể lưu thiết lập Tampermonkey.", "error");
      return;
    }
    closeSettings();
    refreshStatus();
    showToast("Đã lưu thiết lập.", "success");
    if (ui.autoLoginInput.checked && getAuthState() !== "authenticated") {
      void continueLogin({ reset: true, source: "settings" });
    }
  }

  function buildModuleMarkup() {
    return MODULE_GROUPS.map((group) => `
      <section class="module-group" data-group="${group.name}">
        <div class="group-heading">
          <span class="group-accent accent-${group.accent}"></span>
          <span>${group.name}</span>
          <span class="group-count">${group.modules.length}</span>
        </div>
        <div class="module-grid">
          ${group.modules.map((module) => `
            <button class="module-button" type="button" data-module-id="${module.id}" data-search="${module.name.toLocaleLowerCase("vi")} ${group.name.toLocaleLowerCase("vi")}">
              <span class="module-icon accent-${group.accent}">${module.icon}</span>
              <span class="module-name">${module.name}</span>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
            </button>
          `).join("")}
        </div>
      </section>
    `).join("");
  }

  function createUI() {
    if (document.getElementById(ROOT_ID)) return;
    const host = document.createElement("div");
    host.id = ROOT_ID;
    document.documentElement.appendChild(host);
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>${STYLES}</style>
      <button class="launcher" type="button" aria-label="Mở WFX Smart Automation" title="WFX Smart Automation">
        <svg viewBox="0 0 28 28" aria-hidden="true">
          <path class="logo-frame" d="M5.2 6.7 14 2.4l8.8 4.3v10.6L14 25.6l-8.8-8.3V6.7Z"/>
          <path class="logo-mark" d="m8.6 9.2 2.6 9.2 2.8-6.2 2.8 6.2 2.6-9.2"/>
        </svg>
        <span class="launcher-pulse"></span>
      </button>

      <aside class="panel" aria-hidden="true" aria-label="WFX Smart Automation">
        <div class="panel-glow"></div>
        <header class="panel-header">
          <div class="brand">
            <div class="brand-logo">
              <svg viewBox="0 0 28 28" aria-hidden="true"><path d="M5.2 6.7 14 2.4l8.8 4.3v10.6L14 25.6l-8.8-8.3V6.7Z"/><path class="brand-mark" d="m8.6 9.2 2.6 9.2 2.8-6.2 2.8 6.2 2.6-9.2"/></svg>
            </div>
            <div><strong>WFX Smart</strong><span>Automation workspace</span></div>
          </div>
          <div class="header-actions">
            <button class="icon-button settings-button" type="button" aria-label="Mở cài đặt" title="Cài đặt">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.3a3.3 3.3 0 1 0 0-6.6 3.3 3.3 0 0 0 0 6.6Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V21h-4v-.08A1.7 1.7 0 0 0 8.95 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.58 15 1.7 1.7 0 0 0 3 14H3v-4h.08A1.7 1.7 0 0 0 4.6 8.95a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.58 1.7 1.7 0 0 0 10 3V3h4v.08A1.7 1.7 0 0 0 15.05 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.42 9 1.7 1.7 0 0 0 21 10h.08v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>
            </button>
            <button class="icon-button close-button" type="button" aria-label="Đóng panel" title="Đóng">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
            </button>
          </div>
        </header>

        <div class="panel-body">
          <section class="hero-card">
            <div class="status-card" data-tone="neutral">
              <span class="status-orbit"><span></span></span>
              <div><strong class="status-title">Đang kiểm tra...</strong><span class="status-detail">WFX session</span></div>
            </div>
            <span class="account-chip">Chưa có account</span>
            <button class="primary-button login-button" type="button">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>
              <span>Kết nối / Login</span>
              <i></i>
            </button>
          </section>

          <label class="search-box">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
            <input type="search" placeholder="Tìm nhanh module..." autocomplete="off" />
            <kbd class="hotkey-label">Alt + Shift + W</kbd>
          </label>

          <div class="modules-scroll">
            <div class="module-list">${buildModuleMarkup()}</div>
            <div class="empty-state" hidden>
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
              <strong>Không tìm thấy module</strong><span>Thử một từ khóa khác</span>
            </div>
          </div>
        </div>

        <footer class="panel-footer">
          <span><i></i> Tampermonkey active</span>
          <span>v${SCRIPT_VERSION}</span>
        </footer>

        <div class="settings-overlay" aria-label="Thiết lập WFX">
          <div class="settings-sheet">
            <div class="sheet-handle"></div>
            <div class="sheet-heading"><div><strong>Thiết lập thông minh</strong><span>Lưu riêng trong Tampermonkey trên máy này</span></div><button class="icon-button settings-close-button" type="button" aria-label="Đóng cài đặt"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>
            <div class="form-grid">
              <label><span>User ID</span><input class="user-input" type="text" autocomplete="username" placeholder="WFX User ID" /></label>
              <label><span>Company ID</span><input class="company-input" type="text" autocomplete="organization" value="psh" /></label>
              <label class="password-field"><span>Password</span><div><input class="password-input" type="password" autocomplete="current-password" placeholder="WFX Password" /><button class="toggle-password" type="button">Hiện</button></div></label>
            </div>
            <div class="setting-row hotkey-row"><div><strong>Hotkey mở panel</strong><span>Nhấn nút rồi nhập tổ hợp mới</span></div><button class="hotkey-button" type="button">Alt + Shift + W</button></div>
            <label class="setting-row toggle-row"><div><strong>Tự login khi mở panel</strong><span>Chạy trên chính tab WFX hiện tại</span></div><input class="auto-login-input" type="checkbox" checked /><i></i></label>
            <label class="setting-row toggle-row"><div><strong>Đóng panel sau khi mở module</strong><span>Giữ màn hình làm việc gọn hơn</span></div><input class="close-module-input" type="checkbox" checked /><i></i></label>
            <div class="security-note"><svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg><span>Mật khẩu nằm trong vùng lưu trữ của userscript, không đưa vào DOM hay localStorage của trang WFX.</span></div>
            <button class="save-button" type="button">Lưu thiết lập &amp; kết nối</button>
          </div>
        </div>
      </aside>
      <div class="toast-stack" aria-live="polite"></div>
    `;

    ui = {
      shadow,
      launcher: shadow.querySelector(".launcher"),
      panel: shadow.querySelector(".panel"),
      closeButton: shadow.querySelector(".close-button"),
      settingsButton: shadow.querySelector(".settings-button"),
      loginButton: shadow.querySelector(".login-button"),
      statusCard: shadow.querySelector(".status-card"),
      statusTitle: shadow.querySelector(".status-title"),
      statusDetail: shadow.querySelector(".status-detail"),
      accountChip: shadow.querySelector(".account-chip"),
      searchInput: shadow.querySelector(".search-box input"),
      hotkeyLabel: shadow.querySelector(".hotkey-label"),
      moduleButtons: [...shadow.querySelectorAll(".module-button")],
      groupSections: [...shadow.querySelectorAll(".module-group")],
      emptyState: shadow.querySelector(".empty-state"),
      settingsOverlay: shadow.querySelector(".settings-overlay"),
      settingsCloseButton: shadow.querySelector(".settings-close-button"),
      userInput: shadow.querySelector(".user-input"),
      companyInput: shadow.querySelector(".company-input"),
      passwordInput: shadow.querySelector(".password-input"),
      togglePasswordButton: shadow.querySelector(".toggle-password"),
      hotkeyButton: shadow.querySelector(".hotkey-button"),
      autoLoginInput: shadow.querySelector(".auto-login-input"),
      closeAfterModuleInput: shadow.querySelector(".close-module-input"),
      saveButton: shadow.querySelector(".save-button"),
      toastStack: shadow.querySelector(".toast-stack"),
    };

    ui.launcher.addEventListener("click", togglePanel);
    ui.closeButton.addEventListener("click", closePanel);
    ui.settingsButton.addEventListener("click", openSettings);
    ui.settingsCloseButton.addEventListener("click", closeSettings);
    ui.loginButton.addEventListener("click", () => void continueLogin({ reset: true, source: "login-button" }));
    ui.searchInput.addEventListener("input", (event) => filterModules(event.target.value));
    ui.searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (ui.searchInput.value) {
          ui.searchInput.value = "";
          filterModules("");
        } else closePanel();
      }
    });
    ui.moduleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const module = ALL_MODULES.find((item) => item.id === button.dataset.moduleId);
        void openModule(module);
      });
    });
    ui.settingsOverlay.addEventListener("click", (event) => {
      if (event.target === ui.settingsOverlay) closeSettings();
    });
    ui.togglePasswordButton.addEventListener("click", () => {
      const show = ui.passwordInput.type === "password";
      ui.passwordInput.type = show ? "text" : "password";
      ui.togglePasswordButton.textContent = show ? "Ẩn" : "Hiện";
    });
    ui.hotkeyButton.addEventListener("click", beginHotkeyCapture);
    ui.saveButton.addEventListener("click", saveSettings);
    ui.passwordInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") saveSettings();
    });
    updateHotkeyLabels();
    refreshStatus();
  }

  function registerMenuCommands() {
    if (typeof GM_registerMenuCommand !== "function") return;
    GM_registerMenuCommand("Mở WFX Smart Automation", () => openPanel());
    GM_registerMenuCommand("Thiết lập tài khoản & hotkey", () => {
      openPanel({ skipAutoLogin: true });
      openSettings();
    });
    GM_registerMenuCommand("Đăng nhập trên tab này", () => void continueLogin({ reset: true, source: "menu" }));
  }

  async function resumePendingWork() {
    const pending = getPending(STORAGE.pendingLogin);
    if (!pending) {
      if (getAuthState() === "authenticated") await processPendingAction();
      return;
    }
    window.setTimeout(async () => {
      if (getAuthState() === "authenticated") {
        deleteValue(STORAGE.pendingLogin);
        setBusy(false);
        refreshStatus();
        showToast("Đăng nhập WFX thành công.", "success");
        await processPendingAction();
      } else {
        await continueLogin({ reset: false, source: pending.source });
      }
    }, 350);
  }

  const STYLES = String.raw`
    :host { all: initial; color-scheme: dark; }
    *, *::before, *::after { box-sizing: border-box; }
    button, input { font: inherit; }
    button { -webkit-tap-highlight-color: transparent; }
    .launcher {
      position: fixed; right: 24px; bottom: 24px; z-index: 2147483645; width: 58px; height: 58px;
      display: grid; place-items: center; border: 1px solid rgba(157, 235, 255, .35); border-radius: 19px;
      color: #e9fbff; cursor: pointer; background: linear-gradient(145deg, #0d2637, #091722 62%, #112a39);
      box-shadow: 0 18px 42px rgba(0, 0, 0, .38), inset 0 1px 0 rgba(255, 255, 255, .12);
      transition: transform .24s ease, box-shadow .24s ease, border-color .24s ease;
    }
    .launcher:hover { transform: translateY(-3px) scale(1.03); border-color: rgba(99, 232, 255, .75); box-shadow: 0 22px 48px rgba(0,0,0,.46), 0 0 0 5px rgba(53, 211, 236, .08); }
    .launcher:active { transform: translateY(0) scale(.97); }
    .launcher svg { width: 32px; height: 32px; overflow: visible; }
    .logo-frame { fill: rgba(39, 202, 226, .12); stroke: #65e8fb; stroke-width: 1.4; }
    .logo-mark { fill: none; stroke: #f3fdff; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
    .launcher-pulse { position: absolute; top: -3px; right: -3px; width: 13px; height: 13px; border: 3px solid #0b1c28; border-radius: 50%; background: #36e6a1; box-shadow: 0 0 12px #36e6a1; }
    .launcher-active { transform: scale(.9); opacity: .75; }

    .panel {
      position: fixed; z-index: 2147483646; right: 22px; bottom: 94px; width: min(470px, calc(100vw - 24px)); height: min(760px, calc(100vh - 118px));
      display: flex; flex-direction: column; overflow: hidden; color: #e9f4f8; font-family: Inter, "Segoe UI", system-ui, sans-serif;
      border: 1px solid rgba(164, 220, 235, .18); border-radius: 26px; background: rgba(8, 20, 29, .97);
      box-shadow: 0 32px 90px rgba(0, 0, 0, .56), inset 0 1px 0 rgba(255,255,255,.07);
      opacity: 0; visibility: hidden; pointer-events: none; transform: translateY(20px) scale(.965); transform-origin: right bottom;
      transition: opacity .22s ease, transform .3s cubic-bezier(.2,.85,.25,1), visibility .22s;
    }
    .panel-open { opacity: 1; visibility: visible; pointer-events: auto; transform: translateY(0) scale(1); }
    .panel-glow { position: absolute; inset: -180px -120px auto auto; width: 340px; height: 340px; pointer-events: none; border-radius: 50%; background: rgba(40, 202, 225, .12); filter: blur(55px); }
    .panel-header { position: relative; display: flex; align-items: center; justify-content: space-between; min-height: 78px; padding: 17px 18px 13px 20px; border-bottom: 1px solid rgba(255,255,255,.065); }
    .brand { display: flex; align-items: center; gap: 11px; }
    .brand-logo { width: 42px; height: 42px; display: grid; place-items: center; border: 1px solid rgba(100,229,248,.23); border-radius: 14px; background: rgba(48,204,226,.08); }
    .brand-logo svg { width: 27px; fill: rgba(39,202,226,.08); stroke: #65e8fb; stroke-width: 1.35; }
    .brand-logo .brand-mark { fill: none; stroke: white; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .brand strong, .brand span { display: block; }
    .brand strong { color: #f4fcff; font-size: 16px; line-height: 1.25; letter-spacing: .01em; }
    .brand span { margin-top: 2px; color: #708995; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; }
    .header-actions { display: flex; gap: 7px; }
    .icon-button { width: 35px; height: 35px; display: grid; place-items: center; padding: 0; color: #8fa5af; cursor: pointer; border: 1px solid rgba(255,255,255,.07); border-radius: 11px; background: rgba(255,255,255,.035); transition: .2s ease; }
    .icon-button:hover { color: #ecfbff; border-color: rgba(95,225,244,.26); background: rgba(74,205,225,.1); }
    .icon-button svg { width: 18px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

    .panel-body { min-height: 0; flex: 1; display: flex; flex-direction: column; padding: 14px 17px 0; }
    .hero-card { position: relative; display: grid; grid-template-columns: 1fr auto; gap: 12px; padding: 14px; overflow: hidden; border: 1px solid rgba(107,219,236,.12); border-radius: 18px; background: linear-gradient(135deg, rgba(31,73,91,.52), rgba(14,34,46,.58)); }
    .hero-card::after { content: ""; position: absolute; right: -35px; top: -55px; width: 130px; height: 130px; border-radius: 50%; border: 24px solid rgba(58,211,233,.035); }
    .status-card { position: relative; z-index: 1; display: flex; align-items: center; gap: 9px; min-width: 0; }
    .status-orbit { width: 25px; height: 25px; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid rgba(137,157,167,.28); border-radius: 50%; }
    .status-orbit span { width: 8px; height: 8px; border-radius: 50%; background: #8699a1; box-shadow: 0 0 9px currentColor; }
    .status-card[data-tone="success"] .status-orbit { border-color: rgba(54,230,161,.35); color: #36e6a1; }
    .status-card[data-tone="success"] .status-orbit span { background: #36e6a1; }
    .status-card[data-tone="warning"] .status-orbit { border-color: rgba(255,190,91,.38); color: #ffbe5b; }
    .status-card[data-tone="warning"] .status-orbit span { background: #ffbe5b; }
    .status-card strong, .status-card span { display: block; }
    .status-card strong { overflow: hidden; color: #effbfe; font-size: 13px; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
    .status-detail { max-width: 180px; margin-top: 3px; overflow: hidden; color: #88a0aa; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
    .account-chip { position: relative; z-index: 1; align-self: start; max-width: 145px; padding: 5px 8px; overflow: hidden; color: #91acb6; font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; border: 1px solid rgba(255,255,255,.07); border-radius: 8px; background: rgba(4,13,19,.28); }
    .primary-button { position: relative; z-index: 1; grid-column: 1 / -1; height: 41px; display: flex; align-items: center; justify-content: center; gap: 9px; overflow: hidden; color: #05202a; font-size: 12.5px; font-weight: 750; cursor: pointer; border: 0; border-radius: 12px; background: linear-gradient(105deg, #6ceafb, #4bd5e9 56%, #73edc4); box-shadow: 0 9px 23px rgba(39,202,225,.15); transition: transform .18s ease, filter .18s ease; }
    .primary-button:hover { filter: brightness(1.07); transform: translateY(-1px); }
    .primary-button:active { transform: scale(.985); }
    .primary-button:disabled { cursor: wait; opacity: .78; }
    .primary-button svg { width: 17px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .primary-button i { display: none; width: 14px; height: 14px; border: 2px solid rgba(5,32,42,.25); border-top-color: #05202a; border-radius: 50%; animation: spin .7s linear infinite; }
    .primary-button.is-loading svg { display: none; }
    .primary-button.is-loading i { display: block; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .search-box { height: 43px; display: flex; align-items: center; gap: 9px; margin: 13px 0 8px; padding: 0 11px; border: 1px solid rgba(255,255,255,.075); border-radius: 13px; background: rgba(255,255,255,.035); transition: border-color .2s, background .2s; }
    .search-box:focus-within { border-color: rgba(86,222,242,.38); background: rgba(57,174,194,.065); }
    .search-box svg { width: 17px; flex: 0 0 auto; fill: none; stroke: #718a95; stroke-width: 1.8; stroke-linecap: round; }
    .search-box input { min-width: 0; flex: 1; color: #e8f5f8; font-size: 12px; outline: 0; border: 0; background: transparent; }
    .search-box input::placeholder { color: #647a84; }
    kbd { padding: 4px 6px; color: #79909a; font-family: inherit; font-size: 9.5px; white-space: nowrap; border: 1px solid rgba(255,255,255,.08); border-radius: 6px; background: rgba(4,12,18,.35); }
    .modules-scroll { min-height: 0; flex: 1; overflow: auto; padding: 3px 3px 16px 0; scrollbar-width: thin; scrollbar-color: rgba(93,197,214,.25) transparent; }
    .modules-scroll::-webkit-scrollbar { width: 6px; }
    .modules-scroll::-webkit-scrollbar-thumb { border-radius: 9px; background: rgba(93,197,214,.22); }
    .module-group { margin-top: 12px; }
    .module-group[hidden], .module-button[hidden] { display: none !important; }
    .group-heading { display: flex; align-items: center; gap: 7px; margin: 0 3px 7px; color: #92a9b2; font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    .group-accent { width: 5px; height: 5px; border-radius: 50%; }
    .group-count { margin-left: auto; color: #526770; font-size: 9.5px; }
    .module-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
    .module-button { min-width: 0; min-height: 48px; display: grid; grid-template-columns: 31px minmax(0,1fr) 13px; align-items: center; gap: 8px; padding: 7px 9px; color: #c9d9df; text-align: left; cursor: pointer; border: 1px solid rgba(255,255,255,.065); border-radius: 12px; background: rgba(255,255,255,.027); transition: transform .18s ease, color .18s, border-color .18s, background .18s; }
    .module-button:hover { color: #f2fcff; border-color: rgba(93,218,238,.22); background: rgba(62,180,199,.075); transform: translateY(-1px); }
    .module-button:active { transform: scale(.985); }
    .module-icon { width: 31px; height: 31px; display: grid; place-items: center; font-size: 9px; font-weight: 800; letter-spacing: .03em; border: 1px solid currentColor; border-radius: 9px; background: rgba(255,255,255,.025); }
    .accent-cyan { color: #64deef; background-color: rgba(53,197,220,.09); }
    .accent-violet { color: #b7a0ff; background-color: rgba(145,113,255,.09); }
    .accent-amber { color: #ffc36d; background-color: rgba(255,177,61,.09); }
    .group-accent.accent-cyan { background: #64deef; box-shadow: 0 0 8px #64deef; }
    .group-accent.accent-violet { background: #b7a0ff; box-shadow: 0 0 8px #b7a0ff; }
    .group-accent.accent-amber { background: #ffc36d; box-shadow: 0 0 8px #ffc36d; }
    .module-name { overflow: hidden; font-size: 11.5px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
    .module-button > svg { width: 13px; fill: none; stroke: #536972; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; transition: transform .18s, stroke .18s; }
    .module-button:hover > svg { stroke: #7cdae8; transform: translateX(2px); }
    .empty-state { height: 190px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #667c85; text-align: center; }
    .empty-state[hidden] { display: none; }
    .empty-state svg { width: 28px; margin-bottom: 9px; fill: none; stroke: #566d76; stroke-width: 1.5; }
    .empty-state strong { color: #9aadb5; font-size: 12px; }
    .empty-state span { margin-top: 4px; font-size: 10.5px; }
    .panel-footer { min-height: 37px; display: flex; align-items: center; justify-content: space-between; padding: 0 19px; color: #536a74; font-size: 9.5px; border-top: 1px solid rgba(255,255,255,.05); background: rgba(3,10,15,.22); }
    .panel-footer span:first-child { display: flex; align-items: center; gap: 6px; }
    .panel-footer i { width: 5px; height: 5px; border-radius: 50%; background: #36e6a1; box-shadow: 0 0 7px #36e6a1; }

    .settings-overlay { position: absolute; z-index: 10; inset: 0; display: flex; align-items: flex-end; padding: 10px; visibility: hidden; opacity: 0; background: rgba(1,7,11,.7); backdrop-filter: blur(7px); transition: .2s ease; }
    .settings-open { visibility: visible; opacity: 1; }
    .settings-sheet { width: 100%; max-height: calc(100% - 10px); overflow: auto; padding: 8px 15px 16px; border: 1px solid rgba(255,255,255,.1); border-radius: 21px; background: #0d202b; box-shadow: 0 -20px 60px rgba(0,0,0,.38); transform: translateY(20px); transition: transform .27s cubic-bezier(.2,.85,.25,1); scrollbar-width: thin; }
    .settings-open .settings-sheet { transform: translateY(0); }
    .sheet-handle { width: 38px; height: 4px; margin: 0 auto 9px; border-radius: 9px; background: rgba(255,255,255,.14); }
    .sheet-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; }
    .sheet-heading strong, .sheet-heading span { display: block; }
    .sheet-heading strong { color: #f0fbfe; font-size: 15px; }
    .sheet-heading span { margin-top: 3px; color: #708791; font-size: 10.5px; }
    .form-grid { display: grid; grid-template-columns: 1.45fr .75fr; gap: 9px; }
    .form-grid label { min-width: 0; }
    .form-grid label > span { display: block; margin: 0 0 5px 2px; color: #8fa6af; font-size: 10px; font-weight: 650; }
    .form-grid input { width: 100%; height: 38px; padding: 0 10px; color: #eaf7fa; font-size: 11.5px; outline: 0; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; background: rgba(255,255,255,.035); transition: border-color .2s; }
    .form-grid input:focus { border-color: rgba(83,218,238,.42); }
    .password-field { grid-column: 1 / -1; }
    .password-field > div { position: relative; }
    .password-field input { padding-right: 54px; }
    .toggle-password { position: absolute; right: 5px; top: 5px; height: 28px; padding: 0 8px; color: #70d9e8; font-size: 10px; cursor: pointer; border: 0; border-radius: 7px; background: rgba(59,194,214,.09); }
    .setting-row { min-height: 51px; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 9px; padding: 8px 10px; border: 1px solid rgba(255,255,255,.06); border-radius: 12px; background: rgba(255,255,255,.025); }
    .setting-row strong, .setting-row span { display: block; }
    .setting-row strong { color: #cfe0e5; font-size: 11px; }
    .setting-row span { margin-top: 3px; color: #667e88; font-size: 9.5px; }
    .hotkey-button { min-width: 105px; padding: 7px 8px; color: #71deee; font-size: 10px; font-weight: 700; cursor: pointer; border: 1px solid rgba(89,218,238,.21); border-radius: 8px; background: rgba(56,190,210,.07); }
    .hotkey-button.capturing { color: #ffc36d; border-color: rgba(255,195,109,.35); animation: capture 1s ease infinite alternate; }
    @keyframes capture { to { box-shadow: 0 0 0 3px rgba(255,195,109,.08); } }
    .toggle-row { position: relative; cursor: pointer; }
    .toggle-row input { position: absolute; opacity: 0; pointer-events: none; }
    .toggle-row > i { position: relative; width: 37px; height: 21px; flex: 0 0 auto; border-radius: 20px; background: #243a44; transition: .2s; }
    .toggle-row > i::after { content: ""; position: absolute; left: 3px; top: 3px; width: 15px; height: 15px; border-radius: 50%; background: #76909a; transition: .2s; }
    .toggle-row input:checked + i { background: rgba(52,207,181,.3); }
    .toggle-row input:checked + i::after { left: 19px; background: #58e4bd; box-shadow: 0 0 9px rgba(88,228,189,.4); }
    .security-note { display: flex; gap: 8px; margin: 10px 2px; color: #66808a; font-size: 9.5px; line-height: 1.45; }
    .security-note svg { width: 17px; height: 17px; flex: 0 0 auto; fill: none; stroke: #4fc9d9; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
    .save-button { width: 100%; height: 40px; color: #06222a; font-size: 11.5px; font-weight: 800; cursor: pointer; border: 0; border-radius: 11px; background: linear-gradient(105deg,#68e5f6,#62e0c0); transition: filter .18s, transform .18s; }
    .save-button:hover { filter: brightness(1.07); transform: translateY(-1px); }

    .toast-stack { position: fixed; z-index: 2147483647; right: 28px; bottom: 102px; width: min(340px, calc(100vw - 30px)); display: flex; flex-direction: column; align-items: flex-end; gap: 7px; pointer-events: none; font-family: Inter,"Segoe UI",system-ui,sans-serif; }
    .panel-open + .toast-stack { right: 510px; }
    .toast { max-width: 100%; display: flex; align-items: center; gap: 8px; padding: 10px 12px; color: #dcebef; font-size: 11px; line-height: 1.35; border: 1px solid rgba(255,255,255,.1); border-radius: 11px; background: rgba(10,26,35,.97); box-shadow: 0 13px 34px rgba(0,0,0,.32); opacity: 0; transform: translateY(7px) scale(.98); transition: .2s ease; }
    .toast-visible { opacity: 1; transform: translateY(0) scale(1); }
    .toast-dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #5edced; box-shadow: 0 0 8px currentColor; }
    .toast-success .toast-dot { color: #43e4a7; background: #43e4a7; }
    .toast-warning .toast-dot { color: #ffc066; background: #ffc066; }
    .toast-error .toast-dot { color: #ff6e7d; background: #ff6e7d; }

    @media (max-width: 760px) {
      .launcher { right: 13px; bottom: 13px; }
      .panel { right: 12px; bottom: 82px; width: calc(100vw - 24px); height: calc(100vh - 96px); }
      .panel-open + .toast-stack { right: 18px; bottom: 92px; }
    }
    @media (max-width: 430px) {
      .module-grid { grid-template-columns: 1fr; }
      .panel-body { padding-left: 13px; padding-right: 13px; }
      .hotkey-label { display: none; }
      .form-grid { grid-template-columns: 1fr; }
      .password-field { grid-column: auto; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
    }
  `;

  createUI();
  registerMenuCommands();
  document.addEventListener("keydown", handleKeydown, true);
  window.addEventListener("pageshow", () => {
    refreshStatus();
    void resumePendingWork();
  });
  void resumePendingWork();
})();
