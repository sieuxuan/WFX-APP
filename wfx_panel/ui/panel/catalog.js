"use strict";
// Catalog: cây folder, tạo Style, tìm và mở kết quả.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

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
  $(".catalog-folder-summary").dataset.tooltip =
    `Sửa vị trí mặc định: ${
      selectedFolder?.path_label || "Mặc định (Master)"
    }`;
  $(".catalog-browse-label").textContent = "Mở Catalog";

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
  renderCatalogStyleGroups();
}

function renderCatalogStyleGroups() {
  const input = $(".catalog-style-group");
  const host = $(".catalog-style-group-list");
  if (!input || !host) return;
  const groups = (catalogFoldersByCategory.get(CATALOG_DEFAULT_CATEGORY) || [])
    .filter((item) => String(item.kind || "").toLowerCase() === "group");
  if (!groups.some((group) => String(group.node_id || "") === catalogStyleGroupId)) {
    const defaultId = String(catalogDefaultFolder?.node_id || "");
    catalogStyleGroupId = groups.some(
      (group) => String(group.node_id || "") === defaultId,
    ) ? defaultId : "";
  }
  input.value = catalogStyleGroupId;
  const selected = groups.find(
    (group) => String(group.node_id || "") === catalogStyleGroupId,
  );
  $(".catalog-style-group-current").textContent = selected?.path_label
    || "Chọn Group Apparel…";
  const summary = $(".catalog-style-group-summary");
  if (summary) {
    summary.dataset.tooltip = selected?.path_label || "Chọn Group Apparel";
  }
  const query = normalizeCatalogSearch($(".catalog-style-group-search")?.value);
  const matches = groups.filter((group) => normalizeCatalogSearch(
    `${group.name || ""} ${group.path_label || ""}`,
  ).includes(query)).slice(0, 120);
  host.innerHTML = matches.length ? matches.map((group) => {
    const nodeId = String(group.node_id || "");
    const isSelected = nodeId === catalogStyleGroupId;
    const path = String(group.path_label || group.name || nodeId);
    return `<button type="button" class="catalog-style-group-choice"
      data-style-group-select="${escapeHtml(nodeId)}" role="option"
      aria-selected="${isSelected}">
      <span><strong>${escapeHtml(group.name || "Group")}</strong>
      <small>${escapeHtml(path)}</small></span>
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-9"/></svg>
    </button>`;
  }).join("") : '<div class="catalog-folder-empty">Không tìm thấy Group phù hợp.</div>';
  host.querySelectorAll("[data-style-group-select]").forEach((button) => {
    button.addEventListener("click", () => {
      if (catalogStyleReview) return;
      catalogStyleGroupId = String(button.dataset.styleGroupSelect || "");
      $(".catalog-style-group-picker").hidden = true;
      $(".catalog-style-group-summary").setAttribute("aria-expanded", "false");
      renderCatalogStyleGroups();
      syncCatalogStepButtons();
    });
  });
  syncCatalogStepButtons();
}

function resetCatalogStyleReview() {
  catalogStyleReview = null;
  catalogStyleRowIndex = 0;
  catalogStyleAwaitingSave = false;
  const review = $(".catalog-style-review");
  if (review) review.hidden = true;
  const choices = $(".catalog-style-copy-choices");
  if (choices) {
    choices.hidden = true;
    choices.innerHTML = "";
  }
  renderCatalogStyleGroups();
  syncCatalogStepButtons();
}

function currentCatalogStyleRow() {
  return catalogStyleReview?.rows?.[catalogStyleRowIndex] || null;
}

function renderCatalogStyleReview() {
  const review = $(".catalog-style-review");
  if (!review || !catalogStyleReview) return;
  const row = currentCatalogStyleRow();
  const count = Number(catalogStyleReview.row_count || catalogStyleReview.rows.length);
  review.hidden = false;
  $(".catalog-style-review-file").textContent =
    `${catalogStyleReview.file_name} · ${catalogStyleReview.group.path_label}`;
  $(".catalog-style-progress").textContent = row
    ? `Dòng ${catalogStyleRowIndex + 1}/${count} · Excel ${row.source_row}`
    : `Hoàn tất ${count}/${count} dòng`;
  $(".catalog-style-row-summary").textContent = row
    ? [
        row.type,
        row.style_copy ? `Nguồn: ${row.style_copy}` : "Tạo mới",
        row.buyer_style_ref ? `Buyer Ref: ${row.buyer_style_ref}` : "",
        row.internal_style_ref ? `Internal Ref: ${row.internal_style_ref}` : "",
      ].filter(Boolean).join(" · ")
    : (catalogStyleAutoSave
      ? "Đã xong. Các Style được Save tự động."
      : "Đã xong. Tự bấm Save trên WFX để lưu.");
  const button = $(".catalog-style-prepare");
  if (!row) {
    button.textContent = "Đã hoàn tất";
    button.disabled = true;
  } else if (catalogStyleAwaitingSave) {
    button.textContent = catalogStyleRowIndex + 1 >= count
      ? "Tôi đã Save · Hoàn tất"
      : "Tôi đã Save · Chuẩn bị dòng tiếp theo";
    button.disabled = false;
  } else {
    button.textContent = catalogStyleRowIndex === 0
      ? (catalogStyleAutoSave ? "Chuẩn bị & Save dòng đầu tiên" : "Chuẩn bị dòng đầu tiên")
      : (catalogStyleAutoSave ? "Chuẩn bị & Save dòng này" : "Chuẩn bị dòng này");
    button.disabled = false;
  }
  renderCatalogStyleGroups();
}

async function downloadCatalogStyleTemplate() {
  const groupId = String(catalogStyleGroupId || "");
  if (!groupId) {
    setStatus("error", "Hãy chọn một Group để app lấy danh sách dropdown.");
    $(".catalog-style-group-summary")?.focus();
    return null;
  }
  const result = await call("download_style_template", groupId);
  if (result) handleResult(result);
  return result;
}

async function importCatalogStyles() {
  const groupId = String(catalogStyleGroupId || "");
  if (!groupId) {
    setStatus("error", "Hãy chọn đúng một Group Apparel trước khi Import.");
    $(".catalog-style-group-summary")?.focus();
    return null;
  }
  const selected = await callQuiet("choose_style_import_file");
  if (!selected?.ok) {
    if (selected?.code !== "STYLE_FILE_DIALOG_CANCELLED") handleResult(selected);
    return selected;
  }
  const result = await call(
    "review_catalog_style_import",
    selected.file_path,
    groupId,
  );
  if (result?.code === "STYLE_IMPORT_REVIEW_READY") {
    catalogStyleReview = result;
    catalogStyleRowIndex = 0;
    catalogStyleAwaitingSave = false;
    renderCatalogStyleReview();
  }
  return result;
}

async function cancelCatalogStyleReview() {
  const token = String(catalogStyleReview?.review_token || "");
  if (token) await callQuiet("clear_catalog_style_import", token);
  resetCatalogStyleReview();
  setStatus("warning", "Đã hủy danh sách Tạo Style; app chưa Save trên WFX.");
}

function renderCatalogStyleCopyChoices(result) {
  const host = $(".catalog-style-copy-choices");
  if (!host) return;
  const choices = Array.isArray(result?.choices) ? result.choices : [];
  host.innerHTML = choices.map((choice) => (
    `<button type="button" data-style-copy-choice="${Number(choice.choice_index)}">${escapeHtml(
      choice.label || choice.article_code || choice.buyer_reference || "Style nguồn",
    )}</button>`
  )).join("");
  host.hidden = !choices.length;
  $(".catalog-style-prepare").disabled = Boolean(choices.length);
}

async function prepareCatalogStyleRow(copyChoice = null) {
  if (!catalogStyleReview) return null;
  if (catalogStyleAwaitingSave) {
    catalogStyleAwaitingSave = false;
    catalogStyleRowIndex += 1;
    if (!currentCatalogStyleRow()) {
      await callQuiet(
        "clear_catalog_style_import",
        catalogStyleReview.review_token,
      );
      renderCatalogStyleReview();
      setStatus("success", "Đã hoàn tất danh sách. App không tự Save Style nào.");
      return null;
    }
    renderCatalogStyleReview();
  }
  const row = currentCatalogStyleRow();
  if (!row) return null;
  const result = await call(
    "prepare_catalog_style_row",
    catalogStyleReview.review_token,
    row.source_row,
    copyChoice,
    catalogStyleAutoSave,
  );
  if (result?.code === "STYLE_COPY_MULTIPLE_RESULTS") {
    renderCatalogStyleCopyChoices(result);
  } else if (result?.code === "STYLE_FORM_READY") {
    const choices = $(".catalog-style-copy-choices");
    choices.hidden = true;
    choices.innerHTML = "";
    if (catalogStyleAutoSave && result?.saved === true) {
      catalogStyleRowIndex += 1;
      if (!currentCatalogStyleRow()) {
        await callQuiet(
          "clear_catalog_style_import",
          catalogStyleReview.review_token,
        );
        renderCatalogStyleReview();
        setStatus("success", "Đã chuẩn bị và Save toàn bộ danh sách Style.");
        return result;
      }
      catalogStyleAwaitingSave = false;
    } else {
      catalogStyleAwaitingSave = true;
    }
    renderCatalogStyleReview();
  }
  return result;
}

const styleActions = {
  "refresh-groups": () => scanCatalogFolders(true),
  template: () => downloadCatalogStyleTemplate(),
  import: () => importCatalogStyles(),
  cancel: () => cancelCatalogStyleReview(),
  "prepare-row": () => prepareCatalogStyleRow(),
};

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
      result?.message || "Chưa tải được thư mục Catalog.",
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
  const category = $(".catalog-category")?.value || "";
  const secondaryKind = category === "Apparel"
    ? "buyer_reference"
    : "article_name";
  const secondaryButton = $(".catalog-secondary-kind");
  if (secondaryButton) {
    secondaryButton.dataset.catalogKind = secondaryKind;
    secondaryButton.textContent = secondaryKind === "buyer_reference"
      ? "Buyer Reference"
      : "Article Name";
  }
  if (catalogKind !== "code") catalogKind = secondaryKind;
  $$(".catalog-kind-button").forEach((button) =>
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.catalogKind === catalogKind),
    ));
  const input = $(".catalog-query");
  if (input) {
    input.placeholder = {
      buyer_reference: "Nhập Buyer Reference",
      article_name: "Nhập Article Name",
      code: "Ví dụ: F0000001",
    }[catalogKind];
  }
  hideArticleSuggestions();
}

function setArticleLibraryStatus(state) {
  const host = $(".catalog-article-library");
  const label = $(".catalog-article-library-status");
  if (!host || !label) return;
  const ready = state?.available === true;
  host.dataset.ready = String(ready);
  if (!ready) {
    label.textContent = "Chưa có dữ liệu server; dropdown vẫn cho phép nhập tay.";
    return;
  }
  const count = Number(state.article_count || 0).toLocaleString("vi-VN");
  const synced = Number(state.synced_at || 0);
  const timeLabel = synced > 0
    ? new Date(synced * 1000).toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
    : "";
  label.textContent = `${count} Article · tự động cập nhật${
    timeLabel ? ` ${timeLabel}` : ""
  }`;
}
window.wfxSetArticleLibraryStatus = setArticleLibraryStatus;

function setCostingSpecialOptionsState(state) {
  const input = $(".catalog-special-rescan-input");
  const host = $(".catalog-special-rescan");
  if (!input || !host) return;
  const pending = state?.rescan_next === true;
  input.checked = pending;
  host.dataset.pending = String(pending);
  if (pending) {
    host.dataset.tooltip = "Sẽ quét mới CM · Production · Indirect ở lần Costing kế tiếp";
    return;
  }
  const saved = Number(state?.saved_at || 0);
  host.dataset.tooltip = state?.available === true && saved > 0
    ? `Đang dùng cache tuần từ ${new Date(saved * 1000).toLocaleDateString("vi-VN")}`
    : "Quét lại CM, Production, Indirect ở lần sau.";
}
window.wfxSetCostingSpecialOptionsState = setCostingSpecialOptionsState;

function hideArticleSuggestions() {
  const host = $(".catalog-article-suggestions");
  if (!host) return;
  host.hidden = true;
  host.innerHTML = "";
}

function renderArticleSuggestions(result) {
  const host = $(".catalog-article-suggestions");
  const suggestions = Array.isArray(result?.suggestions)
    ? result.suggestions
    : [];
  if (!host || !suggestions.length) {
    hideArticleSuggestions();
    return;
  }
  host.innerHTML = suggestions.map((item) => `
    <button type="button" class="catalog-article-suggestion" role="option"
      data-suggestion-value="${escapeHtml(item.value || "")}"
      data-article-code="${escapeHtml(item.article_code || "")}">
      <strong>${escapeHtml(item.article_code || "—")}</strong>
      <small>${escapeHtml([
        item.article_name,
        item.buyer_reference
          ? `Buyer Ref: ${item.buyer_reference}`
          : "",
      ].filter(Boolean).join(" · "))}</small>
    </button>`).join("");
  host.hidden = false;
}

function scheduleArticleSuggestions() {
  window.clearTimeout(articleSuggestionTimer);
  const query = String($(".catalog-query")?.value || "").trim();
  if (query.length < 2) {
    hideArticleSuggestions();
    return;
  }
  const generation = ++articleSuggestionGeneration;
  articleSuggestionTimer = window.setTimeout(async () => {
    const result = await callQuiet(
      "suggest_articles",
      $(".catalog-category")?.value || "",
      catalogKind,
      query,
      20,
    );
    if (
      generation !== articleSuggestionGeneration
      || String($(".catalog-query")?.value || "").trim() !== query
    ) return;
    renderArticleSuggestions(result);
  }, 180);
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
    $(".catalog-results-title").textContent = "Chọn Article Code";
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
            <strong data-tooltip="${escapeHtml(file.file_name)}">${escapeHtml(file.file_name)}</strong>
            ${meta ? `<small>${meta}</small>` : ""}
            ${comments}
          </span>
        </button>`;
      }).join("")
      : '<div class="catalog-results-empty">'
        + 'Không có file đính kèm trong 4 mục đã kiểm tra.</div>';
    list.querySelectorAll(".catalog-file-row").forEach((row) => {
      row.addEventListener("click", () => downloadCatalogFile(row));
    });
    wrap.hidden = false;
  } else if (result.code === "NO_RESULTS") {
    $(".catalog-results-title").textContent = "Kết quả";
    $(".catalog-results-count").textContent = "";
    list.innerHTML = '<div class="catalog-results-empty">Không tìm thấy.'
      + ' Thử đổi nội dung hoặc kiểu tìm.</div>';
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
