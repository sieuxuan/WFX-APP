"use strict";
(() => {
  const MODULE_GROUPS = [
    { name: "Operation", accent: "cyan", modules: [
      { name: "Catalog", id: "0003_6200", icon: "CA" },
      { name: "OC List", id: "0004_0050_0020", icon: "OC" },
      { name: "Sample List", id: "0004_0056_4070", icon: "SL" },
      { name: "Sale ASN", id: "0004_0070_0020", icon: "AS" },
      { name: "RMPO List", id: "0005_0050_0020", icon: "RM" },
      { name: "Indent List", id: "0005_0080_0020", icon: "IN" },
      { name: "QA List", id: "0063_0030_0020", icon: "QA" },
    ]},
    { name: "Finance", accent: "violet", modules: [
      { name: "Advance PR List", id: "0065_0880_0010_0020", icon: "PR" },
      { name: "Supplier Inv List", id: "0065_0880_0020_0020", icon: "SI" },
      { name: "Expense Inv List", id: "0065_0880_0030_0020", icon: "EI" },
    ]},
    { name: "Admin", accent: "amber", modules: [
      { name: "Org Structure", id: "0090_0001", icon: "OR" },
      { name: "System Coding", id: "0090_0250", icon: "SC" },
      { name: "Company Setup", id: "0090_0007", icon: "CO" },
      { name: "Buyer List", id: "0004_0010_1720", icon: "BU" },
      { name: "Supplier List", id: "0005_0010_1290", icon: "SU" },
    ]},
  ];

  const $ = (sel) => document.querySelector(sel);
  const api = () => (window.pywebview && window.pywebview.api) || null;
  let busy = false;
  // Theo dõi pref "Đóng panel sau khi mở module" ở state module — được nạp từ
  // wfxBootstrap và cập nhật khi người dùng đổi checkbox — để openModule() có
  // thể quyết định gọi hide_panel() sau khi mở module thành công.
  let closeAfterModule = true;

  function buildModules() {
    $(".module-list").innerHTML = MODULE_GROUPS.map((group) => `
      <section class="module-group" data-group="${group.name}">
        <div class="group-heading"><span class="group-accent accent-${group.accent}"></span><span>${group.name}</span><span class="group-count">${group.modules.length}</span></div>
        <div class="module-grid">${group.modules.map((m) => `
          <button class="module-button" type="button" data-module-id="${m.id}" data-search="${m.name.toLowerCase()} ${group.name.toLowerCase()}">
            <span class="module-icon accent-${group.accent}">${m.icon}</span>
            <span class="module-name">${m.name}</span>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5-5 5"/></svg>
          </button>`).join("")}</div>
      </section>`).join("");
  }

  function setBusy(value) {
    busy = value;
    document.body.classList.toggle("is-busy", value);
    document.querySelectorAll("button, select, input").forEach((el) => {
      if (el.closest(".settings-overlay")) return;
      el.disabled = value;
    });
  }
  window.wfxSetBusy = setBusy;

  function setStatus(tone, label) {
    const status = $(".footer-status");
    status.dataset.tone = tone || "neutral";
    $(".footer-status-text").textContent = label || "";
  }
  window.wfxSetStatus = setStatus;

  function pushLog(line) {
    const pre = $(".catalog-log");
    const current = pre.textContent === "Chưa có nhật ký hệ thống." ? "" : pre.textContent;
    pre.textContent = (current ? current + "\n" : "") + line;
    pre.scrollTop = pre.scrollHeight;
    if (/(?:ERROR|FAILED|TIMEOUT)/i.test(line) && !$(".log-overlay").classList.contains("open")) {
      $(".log-button").classList.add("has-alert");
    }
  }
  window.wfxPushLog = pushLog;

  function applyTheme(theme) {
    const value = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = value;
    document.querySelectorAll(".seg-button").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.themeChoice === value)));
  }
  window.wfxApplyTheme = applyTheme;

  function setAccount(userId) { $(".user-input").value = userId || ""; }
  window.wfxSetAccount = setAccount;

  function handleResult(result) {
    if (!result) return;
    setStatus(result.ok ? "success" : "error", result.message || "");
    if (result.user_id !== undefined) setAccount(result.user_id);
  }

  async function call(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng"); return;
    }
    setBusy(true);
    setStatus("neutral", "Đang xử lý...");
    try {
      handleResult(await bridge[method](...args));
    } catch (error) {
      setStatus("error", String(error));
    } finally {
      setBusy(false);
    }
  }

  async function openModule(moduleId) {
    const bridge = api();
    if (!bridge || typeof bridge.open_module !== "function") {
      setStatus("error", "Bridge chưa sẵn sàng"); return;
    }
    setBusy(true);
    setStatus("neutral", "Đang xử lý...");
    try {
      const result = await bridge.open_module(moduleId);
      handleResult(result);
      if (result && result.ok && closeAfterModule) api()?.hide_panel?.();
    } catch (error) {
      setStatus("error", String(error));
    } finally {
      setBusy(false);
    }
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
    const q = query.trim().toLowerCase();
    let visibleTotal = 0;
    document.querySelectorAll(".module-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".module-button").forEach((btn) => {
        const match = !q || btn.dataset.search.includes(q);
        btn.hidden = !match;
        if (match) visible += 1;
      });
      group.hidden = visible === 0;
      visibleTotal += visible;
    });
    $(".empty-state").hidden = visibleTotal !== 0;
  }

  function bind() {
    // panel-header mang class pywebview-drag-region để pywebview (easy_drag=False)
    // cho phép kéo cửa sổ frameless bằng mousedown trên header (xem
    // webview/js/customize.js: querySelectorAll('.pywebview-drag-region')).
    // mousedown bubble từ nút bên trong header lên tới chính header sẽ bị
    // hiểu nhầm thành thao tác kéo cửa sổ — chặn bubble tại header-actions để
    // log/settings/close vẫn click được bình thường.
    $(".header-actions")?.addEventListener("mousedown", (e) => e.stopPropagation());

    document.querySelectorAll("[data-catalog-action]").forEach((btn) =>
      btn.addEventListener("click", () => catalogActions[btn.dataset.catalogAction]?.()));
    $(".module-list").addEventListener("click", (event) => {
      const btn = event.target.closest(".module-button");
      if (btn) openModule(btn.dataset.moduleId);
    });
    $(".catalog-code").addEventListener("keydown", (e) => { if (e.key === "Enter") catalogActions["code-find"](); });
    $(".catalog-buyer-reference").addEventListener("keydown", (e) => { if (e.key === "Enter") catalogActions["buyer-find"](); });
    $(".search-box input").addEventListener("input", (e) => filterModules(e.target.value));

    $(".settings-button").addEventListener("click", () => $(".settings-overlay:not(.log-overlay)").classList.add("open"));
    $(".settings-close-button").addEventListener("click", () => $(".settings-overlay:not(.log-overlay)").classList.remove("open"));
    $(".log-button").addEventListener("click", () => { $(".log-overlay").classList.add("open"); $(".log-button").classList.remove("has-alert"); });
    $(".log-close-button").addEventListener("click", () => $(".log-overlay").classList.remove("open"));
    $(".close-button").addEventListener("click", () => api()?.hide_panel?.());

    $(".toggle-password").addEventListener("click", () => {
      const input = $(".password-input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      $(".toggle-password").textContent = show ? "Ẩn" : "Hiện";
    });
    $(".save-button").addEventListener("click", async () => {
      await call("save_account", $(".user-input").value.trim(), $(".password-input").value);
      $(".settings-overlay:not(.log-overlay)").classList.remove("open");
      call("login");
    });
    $(".close-module-input").addEventListener("change", (e) => {
      closeAfterModule = e.target.checked;
      api()?.set_close_after_module?.(closeAfterModule);
    });
    document.querySelectorAll(".seg-button").forEach((btn) =>
      btn.addEventListener("click", () => { applyTheme(btn.dataset.themeChoice); api()?.set_theme?.(btn.dataset.themeChoice); }));
    $(".catalog-log-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText($(".catalog-log").textContent); setStatus("success", "Đã sao chép log"); }
      catch { setStatus("error", "Không sao chép được"); }
    });
  }

  window.wfxBootstrap = (state) => {
    if (!state) return;
    setAccount(state.user_id);
    applyTheme(state.theme);
    closeAfterModule = state.close_after_module !== false;
    $(".close-module-input").checked = closeAfterModule;
    if (state.hotkey_label) { $(".hotkey-label").textContent = state.hotkey_label; $(".hotkey-button").textContent = state.hotkey_label; }
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
