"use strict";
// Lọc module, hotkey, cập nhật, gắn sự kiện và khởi động.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

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
  $(".update-banner-title").textContent = "Đang chuẩn bị";
  $(".update-banner-message").textContent =
    "Đang kiểm tra gói cài. Đừng đóng app.";
  const result = await callQuiet("install_update");
  if (result) {
    setUpdateState(result);
    setStatus(result.ok ? "success" : "error", result.message || "");
  }
  if (!result || result.code !== "UPDATE_SCHEDULED") {
    $(".update-banner").classList.remove("update-installing");
    button.disabled = false;
    button.textContent = "Thử lại";
  }
}

async function checkUpdateNow(button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Đang kiểm tra…";
  const result = await callQuiet("check_for_updates");
  if (result) {
    setUpdateState(result);
    setStatus(
      result.ok ? "success" : "warning",
      result.message || "Đã kiểm tra cập nhật.",
    );
  }
  button.disabled = false;
  button.textContent = originalText;
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
  $$("[data-catalog-space]").forEach((button) =>
    button.addEventListener("click", () =>
      showCatalogSpace(button.dataset.catalogSpace)));
  $$("[data-catalog-action]").forEach((button) =>
    button.addEventListener("click", () =>
      withButtonLoading(button, () => catalogActions[button.dataset.catalogAction]?.())));
  $$("[data-costing-action]").forEach((button) =>
    button.addEventListener("click", () =>
      withButtonLoading(button, () => costingActions[button.dataset.costingAction]?.())));
  $$("[data-style-action]").forEach((button) =>
    button.addEventListener("click", () =>
      withButtonLoading(button, () => styleActions[button.dataset.styleAction]?.())));
  $(".catalog-style-group-summary")?.addEventListener("click", () => {
    if (catalogStyleReview) return;
    const picker = $(".catalog-style-group-picker");
    picker.hidden = !picker.hidden;
    $(".catalog-style-group-summary").setAttribute(
      "aria-expanded", String(!picker.hidden),
    );
    if (!picker.hidden) {
      if (!catalogFoldersByCategory.has(CATALOG_DEFAULT_CATEGORY)) {
        scanCatalogFolders(false);
      } else {
        renderCatalogStyleGroups();
        window.setTimeout(() => $(".catalog-style-group-search")?.focus(), 0);
      }
    }
  });
  $(".catalog-style-group-search")?.addEventListener(
    "input", renderCatalogStyleGroups,
  );
  $(".catalog-style-autosave-input")?.addEventListener("change", (event) => {
    catalogStyleAutoSave = event.target.checked === true;
    $(".catalog-style-mode-copy").textContent = catalogStyleAutoSave
      ? "Chuẩn bị từng dòng và tự Save sau khi điền"
      : "Chuẩn bị từng dòng và dừng trước Save";
    $(".catalog-style-save-reminder").textContent = catalogStyleAutoSave
      ? "App tự bấm Save. Chỉ bật khi đã kiểm tra file Excel."
      : "Kiểm tra trên WFX và tự bấm Save rồi mới tiếp tục.";
    renderCatalogStyleReview();
  });
  $(".catalog-style-copy-choices")?.addEventListener("click", (event) => {
    const choice = event.target.closest("[data-style-copy-choice]");
    if (!choice) return;
    withButtonLoading(
      choice,
      () => prepareCatalogStyleRow(Number(choice.dataset.styleCopyChoice)),
    );
  });
  $(".catalog-special-rescan-input")?.addEventListener(
    "change",
    async (event) => {
      const result = await callQuiet(
        "set_costing_special_options_rescan",
        event.target.checked,
      );
      if (result) handleResult(result);
      else event.target.checked = !event.target.checked;
    },
  );
  $$(".catalog-kind-button").forEach((button) =>
    button.addEventListener("click", () => {
      catalogKind = ["buyer_reference", "article_name"].includes(
        button.dataset.catalogKind,
      ) ? button.dataset.catalogKind : "code";
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
  $(".sample-file-results-list").addEventListener("click", (event) => {
    const choice = event.target.closest("[data-sample-choice-id]");
    if (choice) {
      openSampleFileChoice(choice);
      return;
    }
    const file = event.target.closest("[data-file-id]");
    if (file) downloadCatalogFile(file);
  });
  $(".supplier-invoice-cancel-results-list").addEventListener("click", (event) => {
    const choice = event.target.closest("[data-supplier-invoice-cancel-choice]");
    if (choice) cancelSupplierInvoiceChoice(choice);
  });
  $(".catalog-article-suggestions").addEventListener("click", (event) => {
    const row = event.target.closest("[data-suggestion-value]");
    if (!row) return;
    const exactArticleCode = String(row.dataset.articleCode || "").trim();
    $(".catalog-query").value =
      exactArticleCode || row.dataset.suggestionValue || "";
    if (exactArticleCode) {
      // Buyer Reference/Article Name chỉ là cách tìm gợi ý. Khi user đã
      // chọn một dòng cụ thể, dùng exact Article Code để WFX không trả lại
      // danh sách gần giống và bắt chọn lần hai.
      catalogKind = "code";
      syncCatalogKind();
    }
    hideArticleSuggestions();
    clearCatalogResult();
    $(".catalog-query").focus();
  });
  bindListboxKeys($(".catalog-results-list"));
  bindListboxKeys($(".sample-file-results-list"));
  bindListboxKeys($(".supplier-invoice-cancel-results-list"));
  bindListboxKeys($(".catalog-folder-list"));
  bindListboxKeys($(".catalog-article-suggestions"));
  $(".gdn-invoice-query")?.addEventListener("input", syncGdnDispatchAction);
  $(".gdn-grn-confirm-input")?.addEventListener("change", syncGdnDispatchAction);
  Object.entries(INPUT_VALIDATION_GROUPS).forEach(([group, selectors]) => {
    selectors.forEach((selector) => {
      $(selector)?.addEventListener("input", () => syncInputValidation(group));
      $(selector)?.addEventListener("change", () => syncInputValidation(group));
    });
  });
  syncAllInputValidation();
  $$('[data-sale-asn-view]').forEach((button) =>
    button.addEventListener("click", () => showSaleAsnView(button.dataset.saleAsnView)));
  $$('[data-sale-asn-stage]').forEach((input) =>
    input.addEventListener("change", () => {
      if (saleAsnReviewToken) cancelSaleAsnReview();
      resetSaleAsnProgress();
      syncSaleAsnCreate();
      callQuiet("set_sale_asn_stages", selectedSaleAsnStages());
    }));
  $$('[data-sale-asn-po-search-field]').forEach((input) =>
    input.addEventListener("change", async () => {
      let fields = selectedSaleAsnPoSearchFields();
      if (!fields.length) {
        fields = [...SALE_ASN_PO_SEARCH_FIELDS];
        applySaleAsnPoSearchFields(fields);
      }
      const result = await callQuiet("set_sale_asn_po_search_fields", fields);
      applySaleAsnPoSearchFields(result?.sale_asn_po_search_fields || fields);
    }));
  $(".sale-asn-buyer")?.addEventListener("input", () => {
    if (saleAsnReviewToken) cancelSaleAsnReview();
    renderSaleAsnBuyerSuggestions();
    syncSaleAsnCreate();
  });
  $(".sale-asn-buyer")?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideSaleAsnBuyerSuggestions();
      return;
    }
    if (event.key !== "ArrowDown") return;
    // Từ ô nhập đi thẳng xuống danh sách; trong danh sách thì bindListboxKeys lo.
    let first = $(".sale-asn-buyer-suggestions")
      ?.querySelector('[role="option"]');
    if (!first) {
      renderSaleAsnBuyerSuggestions({ showAll: true });
      first = $(".sale-asn-buyer-suggestions")?.querySelector('[role="option"]');
    }
    if (!first) return;
    event.preventDefault();
    first.focus();
  });
  $(".sale-asn-buyer")?.addEventListener("blur", () => {
    // Chờ click chọn gợi ý xong mới đóng danh sách.
    setTimeout(() => {
      if (!$(".sale-asn-buyer-box")?.contains(document.activeElement)
          && !$(".sale-asn-buyer-suggestions")?.contains(document.activeElement)) {
        hideSaleAsnBuyerSuggestions();
      }
    }, 120);
  });
  $(".sale-asn-buyer-dropdown")?.addEventListener("click", () => {
    const host = $(".sale-asn-buyer-suggestions");
    if (!host?.hidden) {
      hideSaleAsnBuyerSuggestions();
      return;
    }
    renderSaleAsnBuyerSuggestions({ showAll: true });
  });
  $(".sale-asn-buyer-suggestions")?.addEventListener("click", (event) => {
    const option = event.target.closest("[data-buyer-value]");
    if (!option) return;
    const input = $(".sale-asn-buyer");
    input.value = option.dataset.buyerValue || "";
    hideSaleAsnBuyerSuggestions();
    syncSaleAsnCreate();
    input.focus();
  });
  bindListboxKeys($(".sale-asn-buyer-suggestions"));
  $(".sale-asn-candidate-list")?.addEventListener("change", (event) => {
    if (event.target.matches(".sale-asn-candidate-select")) {
      syncSaleAsnCandidateAction();
    }
  });
  $(".reports-back-button")?.addEventListener("click", showReportList);
  $$("[data-module-action]").forEach((button) =>
    button.addEventListener("click", () =>
      withButtonLoading(
        button,
        () => moduleActions[button.dataset.moduleAction]?.(),
      )));
  $$(".color-report-level").forEach((select) =>
    select.addEventListener("change", () =>
      loadColorReportOptions(select.dataset.level || "")));
  $(".color-report-style-filter")?.addEventListener(
    "input", applyColorReportFilter,
  );
  $(".color-report-batch-toggle")?.addEventListener(
    "change", renderColorReportStyles,
  );
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
  const runModuleActionFromKeyboard = (action) => withButtonLoading(
    $(`[data-module-action="${action}"]`),
    () => moduleActions[action]?.(),
  );
  $(".oc-query").addEventListener("keydown", (event) => { if (event.key === "Enter") runModuleActionFromKeyboard("oc-search"); });
  $(".gdn-invoice-query")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$(".dispatch-submit-button")?.disabled) {
      runModuleActionFromKeyboard("gdn-dispatch-submit");
    }
  });
  [
    ".sample-no-query",
    ".sample-style-query",
    ".sample-created-by-query",
    ".sample-buyer-query",
  ].forEach((selector) =>
    $(selector).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runModuleActionFromKeyboard("sample-search");
    }));
  $(".sale-asn-query").addEventListener("keydown", (event) => { if (event.key === "Enter") runModuleActionFromKeyboard("sale-asn-search"); });
  [".rmpo-supplier-query", ".rmpo-order-query"].forEach((selector) =>
    {
      $(selector).addEventListener("input", hideRmpoResults);
      $(selector).addEventListener("keydown", (event) => {
        if (event.key === "Enter") runModuleActionFromKeyboard("rmpo-search");
      });
    });
  $(".grn-rmpo-query")?.addEventListener("input", (event) => {
    const linkedRmpo = selectedRmpoChoice?.order_no || "";
    if (event.target.value.trim() !== linkedRmpo) {
      grnLinkedChoiceId = "";
      grnLinkedSupplier = "";
      $(".grn-linked-context").hidden = true;
    }
    grnReceiptToken = "";
    $(".grn-sourcing-checkpoint").hidden = true;
    $(".grn-site-step").hidden = true;
    $(".grn-done").hidden = true;
  });
  $(".grn-search-query")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runModuleActionFromKeyboard("grn-search");
  });
  $(".grn-site-select")?.addEventListener("change", () => {
    syncGrnStepActions();
  });
  [
    ".indent-supplier-query",
    ".indent-article-query",
    ".indent-no-query",
    ".indent-style-query",
  ].forEach((selector) =>
    $(selector).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runModuleActionFromKeyboard("indent-search");
    }));
  [
    ".advance-pr-buyer-query",
    ".advance-pr-supplier-query",
    ".advance-pr-invoice-query",
    ".advance-pr-order-query",
  ].forEach((selector) =>
    $(selector).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runModuleActionFromKeyboard("advance-pr-search");
    }));
  [
    ".supplier-invoice-supplier-query",
    ".supplier-invoice-no-query",
    ".supplier-invoice-po-query",
    ".supplier-invoice-asn-grn-query",
  ].forEach((selector) =>
    $(selector).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runModuleActionFromKeyboard("supplier-invoice-search");
    }));
  $(".supplier-invoice-cancel-query").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runModuleActionFromKeyboard("supplier-invoice-cancel");
  });
  [
    ".expense-invoice-supplier-query",
    ".expense-invoice-no-query",
    ".expense-invoice-created-by-query",
    ".expense-invoice-status-query",
  ].forEach((selector) =>
    $(selector).addEventListener("keydown", (event) => {
      if (event.key === "Enter") runModuleActionFromKeyboard("expense-invoice-search");
    }));
  $(".supplier-query").addEventListener("keydown", (event) => { if (event.key === "Enter") runModuleActionFromKeyboard("supplier-find"); });
  $(".buyer-query").addEventListener("keydown", (event) => { if (event.key === "Enter") runModuleActionFromKeyboard("buyer-find"); });
  // Click ra ngoài app (mất focus sang cửa sổ khác) → tự thu panel về bubble,
  // kể cả khi automation đang chạy, để user có thể theo dõi trực tiếp trên WFX.
  // Backend còn kiểm tra foreground để không thu khi bấm chính bubble/toast.
  document.documentElement.addEventListener("pointerenter", () => {
    pointerInsidePanel = true;
    api()?.set_panel_pointer_inside?.(true);
  });
  document.documentElement.addEventListener("pointerleave", () => {
    pointerInsidePanel = false;
    api()?.set_panel_pointer_inside?.(false);
  });
  window.addEventListener("blur", () => {
    if (pointerInsidePanel) {
      return;
    }
    window.setTimeout(() => api()?.request_panel_hide?.(), 130);
  });
  window.addEventListener("keydown", trapOverlayFocus, true);
  $(".catalog-query").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    hideArticleSuggestions();
    withButtonLoading($('[data-catalog-action="find"]'), () => catalogActions["find"]());
  });
  $(".catalog-category").addEventListener("change", () => {
    clearCatalogPreparation();
    hideCatalogResults();
    hideArticleSuggestions();
    catalogFolderEditorOpen = false;
    $(".catalog-folder-search").value = "";
    syncCatalogKind();
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
    scheduleArticleSuggestions();
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
    const manualButton = $(".manual-button");
    manualButton.classList.remove("has-alert");
    manualButton.setAttribute("aria-label", "Mở hướng dẫn sử dụng WFX");
    manualButton.dataset.tooltip = "Mở hướng dẫn sử dụng";
    $(".manual-alert").dataset.active = "false";
    if (result) handleResult(result);
  });
  $(".footer-help-button").addEventListener("click", () => {
    callQuiet("open_wfx_manual", lastErrorCode);
  });
  $(".module-help-button").addEventListener("click", async () => {
    const moduleId = selectedModule?.id || "";
    const found = await callQuiet("get_manual_entry_for_module", moduleId);
    const result = await callQuiet("open_wfx_manual", found?.entry || "");
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
    button.textContent = "Đang gửi…";
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
    const logButton = $(".log-button");
    logButton.classList.remove("has-alert");
    logButton.setAttribute("aria-label", "Trạng thái hoạt động");
    logButton.dataset.tooltip = "Trạng thái hoạt động";
    refreshJobs();
  });
  $(".log-close-button").addEventListener("click", () => $(".log-overlay").classList.remove("log-open"));
  $(".close-button").addEventListener("click", () => api()?.hide_panel?.());
  $(".stop-action-button").addEventListener("click", stopCurrentAction);
  $(".open-chrome-button").addEventListener("click", async (event) => {
    // event.currentTarget là null ngay sau await (dispatch đã kết thúc), nên
    // phải giữ tham chiếu nút TRƯỚC khi gọi bridge; nếu không nút kẹt
    // disabled vĩnh viễn và lần Chrome đóng sau không bấm lại được.
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await call("open_chrome");
    } finally {
      button.disabled = false;
    }
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
    formStatus.textContent = "Đang lưu…";
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
    formStatus.textContent = "Đang đăng nhập…";
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
  $(".open-excel-file-input").addEventListener("change", async () => {
    const result = await callQuiet(
      "set_excel_file_after_download",
      $(".open-excel-file-input").checked,
    );
    if (!result?.ok) return;
    $(".open-excel-file-input").checked =
      result.open_excel_file_after_download === true;
  });
  $(".check-update-button")?.addEventListener(
    "click",
    (event) => checkUpdateNow(event.currentTarget),
  );
  const hotkeyButton = $(".hotkey-button");
  hotkeyButton.addEventListener("click", () => {
    hotkeyButton.dataset.capturing = "true";
    hotkeyButton.textContent = "Đang chờ tổ hợp phím…";
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
  $(".toast-test-button")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    const result = await callQuiet("show_test_notification");
    button.disabled = false;
    if (result) setStatus(result.ok ? "success" : "warning", result.message || "");
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
  $(".reference-sync-button")?.addEventListener("click", async (event) => {
    const result = await withButtonLoading(
      event.currentTarget,
      () => call("sync_reference_data", true),
    );
    if (result) setReferenceSyncStatus(result);
  });
  $(".reference-sync-save-key")?.addEventListener("click", async (event) => {
    const keyInput = $(".reference-sync-admin-key");
    const key = String(keyInput?.value || "").trim();
    if (!key) {
      setStatus("warning", "Hãy nhập Admin key cần lưu trên máy này.");
      keyInput?.focus();
      return;
    }
    const result = await withButtonLoading(
      event.currentTarget,
      () => call("save_sync_admin_key", key),
    );
    if (keyInput) keyInput.value = "";
    if (result) setReferenceSyncStatus(result);
  });
  $(".reference-sync-publish")?.addEventListener("click", async (event) => {
    if (!window.confirm(
      "Publish sẽ thay thế snapshot Article/Style hiện tại trên server. Tiếp tục?"
    )) return;
    const result = await withButtonLoading(
      event.currentTarget,
      () => call("publish_reference_data"),
    );
    if (result) setReferenceSyncStatus(result);
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
  $$(".job-history").forEach((history) =>
    history.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-job-action]");
      const card = event.target.closest(".job-card");
      if (!button || !card) return;
      if (button.dataset.jobAction === "screenshot") {
        const result = await callQuiet("open_job_screenshot", card.dataset.runId);
        if (result) setStatus(result.ok ? "success" : "error", result.message || "");
        return;
      }
      button.disabled = true;
      if (button.dataset.jobAction === "inspect_gdn") {
        await call("open_gdn_status");
      } else {
        await call("retry_job", card.dataset.runId);
      }
      button.disabled = false;
    }));
  // Xóa lịch sử xóa luôn ảnh lỗi — yêu cầu bấm xác nhận hai bước để tránh mất
  // bằng chứng do lỡ tay. Bấm lần đầu hỏi lại, tự hủy sau 4 giây.
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
      $(".catalog-log").textContent = LOG_PLACEHOLDER;
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
  if (state.version) {
    $(".app-version").textContent = `Phiên bản ${state.version}`;
    $(".settings-version-badge").textContent = `v${state.version}`;
  }
  if (Array.isArray(state.module_groups) && state.module_groups.length) {
    MODULE_GROUPS = state.module_groups;
  }
  if (Array.isArray(state.manual_error_codes)) {
    manualErrorCodes = new Set(state.manual_error_codes);
  }
  applySaleAsnStages(state.sale_asn_stages);
  applySaleAsnPoSearchFields(state.sale_asn_po_search_fields);
  renderSaleAsnBuyers(state.sale_asn_buyers);
  const hasManualNews = state.manual_has_news === true;
  const manualButton = $(".manual-button");
  manualButton.classList.toggle("has-alert", hasManualNews);
  manualButton.setAttribute(
    "aria-label",
    hasManualNews ? "Mở hướng dẫn sử dụng WFX · có nội dung mới" : "Mở hướng dẫn sử dụng WFX",
  );
  manualButton.dataset.tooltip = hasManualNews
    ? "Hướng dẫn có nội dung mới"
    : "Mở hướng dẫn sử dụng";
  $(".manual-alert").dataset.active = String(hasManualNews);
  setAccount(state.user_id);
  hasCredentials = state.has_credentials === true;
  applyTheme(state.theme);
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
  $(".open-excel-file-input").checked =
    state.open_excel_file_after_download !== false;
  colorReportState.outputDir = String(state.report_export_dir || "");
  $(".color-report-dir-path").textContent = colorReportState.outputDir
    || "Chưa chọn thư mục lưu";
  $(".always-on-top-input").checked = state.always_on_top !== false;
  catalogDefaultFolder = state.catalog_default_folder || null;
  const folderLabel =
    catalogDefaultFolder?.path_label || "Mặc định (Master)";
  $(".catalog-folder-summary").dataset.tooltip =
    `Sửa vị trí mặc định: ${folderLabel}`;
  setArticleLibraryStatus(state.article_library || {});
  setReferenceSyncStatus(state.reference_sync || {});
  setCostingSpecialOptionsState(state.costing_special_options || {});
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
      state.credential_state === "unreadable"
        ? "Mật khẩu đã lưu không mở được trên tài khoản Windows này. Nhập lại mật khẩu WFX."
        : "Nhập User ID và mật khẩu WFX để bắt đầu."
    );
  }
};

function init() {
  buildModules();
  bindTooltips();
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
