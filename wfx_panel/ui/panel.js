"use strict";
(() => {
  let MODULE_GROUPS = [
    { name: "Operation", accent: "cyan", modules: [
      { name: "Catalog", id: "0003_6200", icon: "CA", kind: "catalog", description: "Tìm style, kiểm tra Season/CostSheet và mở BOM hoặc Costsheet." },
      { name: "OC List", id: "0004_0050_0020", icon: "OC", kind: "generic", description: "Theo dõi và mở danh sách Order Confirmation." },
      { name: "Sample List", id: "0004_0056_4070", icon: "SL", kind: "generic", description: "Tra cứu và thao tác danh sách sample." },
      { name: "Sale ASN", id: "0004_0070_0020", icon: "AS", kind: "generic", description: "Mở danh sách Sale ASN." },
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
      { name: "Buyer List", id: "0004_0010_1720", icon: "BU", kind: "generic", description: "Mở danh sách buyer." },
      { name: "Supplier List", id: "0005_0010_1290", icon: "SU", kind: "generic", description: "Mở danh sách nhà cung cấp." },
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
  let busy = false;
  let closeAfterModule = true;
  let hotkeyLabel = "Ctrl + Shift + X";
  let selectedModule = null;
  let jobs = [];
  let adminAccess = false;
  let adminMode = false;
  let adminModuleIds = new Set();

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
            <span class="module-icon accent-${escapeHtml(group.accent)}">${escapeHtml(module.icon)}</span>
            <span class="module-copy"><span class="module-name">${escapeHtml(module.name)}</span><span class="module-kind">${escapeHtml(module.kind === "catalog" ? "Workflow nâng cao" : group.name)}</span></span>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
          </button>`).join("")}</div>
      </section>`).join("");
    filterModules($(".search-box input")?.value || "");
  }

  function setBusy(value) {
    busy = value;
    document.body.classList.toggle("is-busy", value);
    $$("button, select, input").forEach((element) => {
      if (element.closest(".settings-overlay")) return;
      element.disabled = value;
    });
  }
  window.wfxSetBusy = setBusy;

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

  function setSessionStatus(active) {
    const node = $(".health-session");
    if (node) node.dataset.state = active == null ? "unknown" : (active ? "ok" : "bad");
  }
  window.wfxSetSessionStatus = setSessionStatus;

  function setCompactMode(enabled) {
    document.body.classList.toggle("compact-mode", enabled === true);
  }
  window.wfxSetCompactMode = setCompactMode;

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

  function applyTheme(theme) {
    const value = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = value;
    $$(".seg-button").forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === value)));
  }
  window.wfxApplyTheme = applyTheme;

  function setAccount(userId) { $(".user-input").value = userId || ""; }
  window.wfxSetAccount = setAccount;

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

  function setUpdateState(state) {
    if (!state) return;
    const banner = $(".update-banner");
    banner.hidden = state.can_update !== true;
    if (state.can_update) {
      $(".update-banner-message").textContent = state.version
        ? `Phiên bản ${state.version} đã sẵn sàng. Ứng dụng sẽ tự mở lại sau khi cập nhật.`
        : "Bản mới đã sẵn sàng. Ứng dụng sẽ tự mở lại sau khi cập nhật.";
      $(".update-banner-button").textContent = "Cập nhật ngay";
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
    if (result.style_status) setStyleStatus(result.style_status);
    else if (["NO_RESULTS", "MULTIPLE_RESULTS"].includes(result.code)) setStyleStatus(null);
    if (result.admin_access !== undefined) {
      setAdminAccess(
        result.admin_access,
        result.admin_module_ids,
        result.admin_mode
      );
    }
    if (result.jobs) renderJobs(result.jobs);
    if (result.run_id) refreshJobs();
  }
  window.wfxHandleBackendResult = handleResult;

  async function call(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng");
      return null;
    }
    setBusy(true);
    setStatus("neutral", "Đang xử lý...");
    try {
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
    icon.textContent = module.icon;
    $(".module-modal-kicker").textContent = module.group;
    $("#module-modal-title").textContent = module.name;
    $(".module-modal-description").textContent = module.description || "";
    const isCatalog = module.kind === "catalog";
    $("[data-module-view='catalog']").hidden = !isCatalog;
    $("[data-module-view='generic']").hidden = isCatalog;
    $(".generic-module-code").textContent = module.icon;
    $(".module-modal-status").textContent = "";
    const overlay = $(".module-overlay");
    overlay.classList.add("module-open");
    overlay.setAttribute("aria-hidden", "false");
    setTimeout(() => (isCatalog ? $(".catalog-code") : $(".generic-module-open")).focus(), 0);
  }

  function closeModuleModal() {
    const overlay = $(".module-overlay");
    overlay.classList.remove("module-open");
    overlay.setAttribute("aria-hidden", "true");
  }

  async function openModule() {
    if (!selectedModule) return;
    const result = await call("open_module", selectedModule.id);
    if (result && result.ok && closeAfterModule) api()?.dismiss_panel?.();
  }

  async function openModuleDirect(moduleId) {
    const result = await call("open_module", moduleId);
    if (result && result.ok && closeAfterModule) api()?.dismiss_panel?.();
  }

  const catalogActions = {
    "prepare": () => call("prepare_catalog", $(".catalog-category").value),
    "code-find": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), null),
    "code-costsheet": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), "costsheet"),
    "code-bom": () => call("find_code", $(".catalog-category").value, $(".catalog-code").value.trim(), "bom"),
    "buyer-find": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), null),
    "buyer-costsheet": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), "costsheet"),
    "buyer-bom": () => call("find_buyer_reference", $(".catalog-category").value, $(".catalog-buyer-reference").value.trim(), "bom"),
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
    button.textContent = "Đang cập nhật...";
    const result = await callQuiet("install_update");
    if (result) {
      setUpdateState(result);
      setStatus(result.ok ? "success" : "error", result.message || "");
    }
    if (!result || result.code !== "UPDATE_SCHEDULED") {
      button.disabled = false;
      button.textContent = "Cập nhật ngay";
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
      button.addEventListener("click", () => catalogActions[button.dataset.catalogAction]?.()));
    $(".module-list").addEventListener("click", (event) => {
      const button = event.target.closest(".module-button");
      if (!button) return;
      const module = allModules().find(
        (item) => item.id === button.dataset.moduleId
      );
      if (module && module.kind === "catalog") {
        openModuleModal(button.dataset.moduleId);
      } else {
        openModuleDirect(button.dataset.moduleId);
      }
    });
    $(".module-close-button").addEventListener("click", closeModuleModal);
    $(".compact-launcher").addEventListener("click", () => api()?.expand_from_browser_icon?.());
    $(".module-overlay").addEventListener("mousedown", (event) => {
      if (event.target === event.currentTarget) closeModuleModal();
    });
    $(".generic-module-open").addEventListener("click", openModule);
    $(".catalog-code").addEventListener("keydown", (event) => { if (event.key === "Enter") catalogActions["code-find"](); });
    $(".catalog-buyer-reference").addEventListener("keydown", (event) => { if (event.key === "Enter") catalogActions["buyer-find"](); });
    $(".search-box input").addEventListener("input", (event) => filterModules(event.target.value));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && $(".module-overlay").classList.contains("module-open")) closeModuleModal();
      if (event.key === "Escape" && feedbackOverlay().classList.contains("feedback-open")) feedbackOverlay().classList.remove("feedback-open");
      if (event.key === "Escape" && settingsOverlay().classList.contains("settings-open")) settingsOverlay().classList.remove("settings-open");
      if (event.key === "Escape" && $(".log-overlay").classList.contains("log-open")) $(".log-overlay").classList.remove("log-open");
    });

    $(".settings-button").addEventListener("click", () => settingsOverlay().classList.add("settings-open"));
    $(".settings-close-button").addEventListener("click", () => settingsOverlay().classList.remove("settings-open"));
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
    $(".close-button").addEventListener("click", () => api()?.dismiss_panel?.());
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
    $(".save-button").addEventListener("click", async () => {
      const saved = await call("save_account", $(".user-input").value.trim(), $(".password-input").value);
      if (saved && saved.ok) {
        settingsOverlay().classList.remove("settings-open");
        call("login");
      }
    });
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
        $(".hotkey-label").textContent = hotkeyLabel;
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
        event.target.checked = Boolean(result.toast_enabled);
        setStatus(result.ok ? "success" : "error", result.message || "");
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
    $(".stick-browser-input").addEventListener("change", async (event) => {
      const result = await callQuiet(
        "set_stick_to_browser", event.target.checked
      );
      if (result) {
        event.target.checked = Boolean(result.stick_to_browser);
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
    $$(".seg-button").forEach((button) =>
      button.addEventListener("click", () => {
        applyTheme(button.dataset.themeChoice);
        api()?.set_theme?.(button.dataset.themeChoice);
      }));

    $$(".activity-tabs button").forEach((button) => button.addEventListener("click", () => {
      $$(".activity-tabs button").forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)));
      $$("[data-activity-view]").forEach((view) =>
        view.hidden = view.dataset.activityView !== button.dataset.activityTab);
    }));
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
    }
    if (Array.isArray(state.module_groups) && state.module_groups.length) {
      MODULE_GROUPS = state.module_groups;
      buildModules();
    }
    setAccount(state.user_id);
    applyTheme(state.theme);
    closeAfterModule = state.close_after_module !== false;
    $(".close-module-input").checked = closeAfterModule;
    if (state.hotkey_label) {
      hotkeyLabel = state.hotkey_label;
      $(".hotkey-label").textContent = hotkeyLabel;
      resetHotkeyButton();
    }
    $(".autostart-input").checked = state.autostart === true;
    $(".start-hidden-input").checked = state.start_hidden === true;
    $(".toast-input").checked = state.toast_enabled !== false;
    $(".always-on-top-input").checked = state.always_on_top !== false;
    $(".stick-browser-input").checked = state.stick_to_browser === true;
    setAdminAccess(
      state.admin_access,
      state.admin_module_ids,
      state.admin_mode
    );
    setBrowserStatus(state.chrome_alive, state.browser_available, state.browser_name);
    setSessionStatus(state.session_active, state.last_login_at);
    renderJobs(state.jobs || []);
    (state.logs || []).forEach(pushLog);
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
