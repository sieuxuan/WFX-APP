"use strict";
// Ràng buộc nhập liệu dùng chung của các form nhiều điều kiện.
// Một phần của panel UI — các file trong thư mục này chia chung global
// scope và chạy theo đúng thứ tự index.html khai báo.

const INPUT_VALIDATION_GROUPS = {
  oc: [".oc-query"],
  sample: [
    ".sample-no-query", ".sample-style-query",
    ".sample-created-by-query", ".sample-buyer-query",
  ],
  "sale-asn": [".sale-asn-query"],
  rmpo: [".rmpo-order-query", ".rmpo-supplier-query"],
  "grn-create": [".grn-rmpo-query"],
  "grn-search": [".grn-search-query"],
  indent: [
    ".indent-supplier-query", ".indent-article-query",
    ".indent-no-query", ".indent-style-query",
  ],
  "advance-pr": [
    ".advance-pr-buyer-query", ".advance-pr-supplier-query",
    ".advance-pr-invoice-query", ".advance-pr-order-query",
  ],
  "supplier-invoice": [
    ".supplier-invoice-supplier-query", ".supplier-invoice-no-query",
    ".supplier-invoice-po-query", ".supplier-invoice-asn-grn-query",
  ],
  "supplier-invoice-cancel": [".supplier-invoice-cancel-query"],
  "expense-invoice": [
    ".expense-invoice-supplier-query", ".expense-invoice-no-query",
    ".expense-invoice-created-by-query", ".expense-invoice-status-query",
  ],
  supplier: [".supplier-query"],
  buyer: [".buyer-query"],
};

// Enter trong bất kỳ ô nào của nhóm chạy đúng nút chính của form đó. Nhóm
// không có ở đây (grn-create có hai nút ngang hàng) thì Enter không làm gì.
const INPUT_ENTER_ACTIONS = {
  oc: "oc-search",
  sample: "sample-search",
  "sale-asn": "sale-asn-search",
  rmpo: "rmpo-search",
  "grn-search": "grn-search",
  indent: "indent-search",
  "advance-pr": "advance-pr-search",
  "supplier-invoice": "supplier-invoice-search",
  "supplier-invoice-cancel": "supplier-invoice-cancel",
  "expense-invoice": "expense-invoice-search",
  supplier: "supplier-find",
  buyer: "buyer-find",
};

// Form nhiều ô có nút `Xóa điều kiện` (mỗi nhóm đúng một nút trong index.html).
const CLEARABLE_INPUT_GROUPS = new Set([
  "sample", "rmpo", "indent",
  "advance-pr", "supplier-invoice", "expense-invoice",
]);

// Kết quả cũ trỏ vào điều kiện vừa xóa nên phải ẩn cùng lúc, nếu không user dễ
// bấm thao tác trên dòng của lượt trước. Viết thành hàm (không phải bảng) vì
// các hàm ẩn nằm ở file nạp sau forms.js.
function hideStaleInputGroupResults(group) {
  if (group === "sample") hideSampleFileResults();
  if (group === "rmpo") hideRmpoResults();
}

function inputGroupHasValue(group) {
  return (INPUT_VALIDATION_GROUPS[group] || []).some(
    (selector) => String($(selector)?.value || "").trim().length > 0,
  );
}

function syncInputValidation(group) {
  const valid = inputGroupHasValue(group);
  $$(`[data-validation-group="${group}"]`).forEach((button) => {
    button.disabled = busy || !valid;
    button.setAttribute("aria-disabled", String(busy || !valid));
  });
  // Gợi ý và nút Xóa điều kiện chiếm cùng một hàng và loại trừ nhau, nên gõ
  // ký tự đầu tiên không làm form nhảy chiều cao.
  $$(`[data-validation-hint="${group}"]`).forEach((hint) => {
    hint.hidden = valid;
  });
  $$(`[data-clear-group="${group}"]`).forEach((button) => {
    button.hidden = !valid;
  });
}

function syncAllInputValidation() {
  Object.keys(INPUT_VALIDATION_GROUPS).forEach(syncInputValidation);
}

function clearInputGroup(group) {
  const selectors = INPUT_VALIDATION_GROUPS[group] || [];
  selectors.forEach((selector) => {
    const input = $(selector);
    if (input) input.value = "";
  });
  hideStaleInputGroupResults(group);
  syncInputValidation(group);
  $(selectors[0])?.focus();
}

// Enter chỉ chạy khi nút chính đang bật: form trống hoặc đang bận thì nút đã
// bị disable, và bàn phím không được là lối vòng qua ràng buộc đó.
function runModuleActionFromKeyboard(action) {
  const button = $(`[data-module-action="${action}"]`);
  if (!button || button.disabled) return undefined;
  return withButtonLoading(button, () => moduleActions[action]?.());
}

function handleSearchInputKeydown(event, group) {
  // Bộ gõ tiếng Việt kiểu IME dùng Enter để chốt chữ đang gõ.
  if (event.isComposing) return;
  if (event.key === "Enter") {
    const action = INPUT_ENTER_ACTIONS[group];
    if (action) runModuleActionFromKeyboard(action);
    return;
  }
  // Esc trong ô đang có chữ chỉ xóa ô đó; Esc lần nữa mới đóng màn module.
  if (event.key === "Escape" && event.target.value) {
    event.preventDefault();
    event.stopPropagation();
    event.target.value = "";
    event.target.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

// Hàng `Gần đây` dưới mỗi form Tìm, giống Catalog. Backend lưu giá trị đúng
// thứ tự ô trong INPUT_VALIDATION_GROUPS cùng một `kind`: kiểu lọc của
// segmented control (OC, Sale ASN, GRN), Category Supplier, module Indent hoặc
// `files` khi lượt đó là Xem file đính kèm của Sample.
const RECENT_SEARCH_FILTER_GROUPS = {
  oc: "oc",
  "sale-asn": "sale_asn",
  "grn-search": "grn",
};

function recentSearchKindLabel(group, kind) {
  if (!kind) return "";
  const filterGroup = RECENT_SEARCH_FILTER_GROUPS[group];
  if (filterGroup) {
    return $$(`.module-filter-button[data-filter-group="${filterGroup}"]`)
      .find((button) => button.dataset.filterKind === kind)
      ?.textContent.trim() || "";
  }
  if (group === "sample" && kind === "files") return "File";
  if (group === "supplier") return kind;
  return "";
}

function recentSearchFieldLabel(selector) {
  const input = $(selector);
  return input?.closest("label")?.querySelector("span")?.textContent.trim()
    || input?.getAttribute("aria-label") || "";
}

// Indent List và User Indent dùng chung form: chỉ hiện lượt tìm của đúng module.
function visibleRecentSearches(group, items) {
  const list = Array.isArray(items)
    ? items.filter((item) => Array.isArray(item?.values) && item.values.some(Boolean))
    : [];
  if (group !== "indent") return list;
  return list.filter((item) => item.kind === selectedModule?.id);
}

function renderRecentSearches(group, items) {
  const host = $(`.search-recent[data-recent-group="${group}"]`);
  const list = host?.querySelector(".search-recent-list");
  if (!host || !list) return;
  const selectors = INPUT_VALIDATION_GROUPS[group] || [];
  const visible = visibleRecentSearches(group, items);
  host.hidden = !visible.length;
  list.innerHTML = visible.map((item) => {
    const values = selectors.map((_, index) => String(item.values[index] || ""));
    const kindLabel = recentSearchKindLabel(group, item.kind);
    const text = [kindLabel, ...values.filter(Boolean)].filter(Boolean).join(" · ");
    const details = selectors
      .map((selector, index) => values[index]
        ? `${recentSearchFieldLabel(selector) || "Điều kiện"}: ${values[index]}`
        : "")
      .filter(Boolean);
    if (kindLabel) details.unshift(kindLabel);
    return `<button type="button" class="search-recent-chip"
      data-recent-values="${escapeHtml(JSON.stringify(values))}"
      data-recent-kind="${escapeHtml(String(item.kind || ""))}"
      data-tooltip="${escapeHtml(details.join(" · "))}"
      aria-label="${escapeHtml(`Tìm lại ${details.join(", ")}`)}"
      >${escapeHtml(text)}</button>`;
  }).join("");
}

async function loadRecentSearches(group) {
  const result = await callQuiet("recent_searches", group);
  const payload = result?.recent_searches;
  if (payload?.group === group) renderRecentSearches(group, payload.items);
}

function loadModuleRecentSearches(kind) {
  $$(`[data-module-view="${kind}"] .search-recent[data-recent-group]`)
    .forEach((host) => loadRecentSearches(host.dataset.recentGroup));
}

// Đặt lại kind rồi trả nút cần chạy. Sample `files` chạy Xem file đính kèm;
// Supplier có Category chạy tìm trong đúng Category đó.
function applyRecentSearchKind(group, kind) {
  const filterGroup = RECENT_SEARCH_FILTER_GROUPS[group];
  if (filterGroup && kind) setModuleFilterKind(filterGroup, kind);
  if (group === "sample" && kind === "files") return "sample-check-file";
  if (group === "supplier" && kind) {
    const category = $(".supplier-category");
    if (category && [...category.options].some((option) => option.value === kind)) {
      category.value = kind;
      return "supplier-find-category";
    }
  }
  return INPUT_ENTER_ACTIONS[group];
}

async function runRecentSearch(chip) {
  const host = chip?.closest(".search-recent[data-recent-group]");
  const group = host?.dataset.recentGroup || "";
  if (!group || busy) return undefined;
  let values = [];
  try {
    values = JSON.parse(chip.dataset.recentValues || "[]");
  } catch {
    return undefined;
  }
  (INPUT_VALIDATION_GROUPS[group] || []).forEach((selector, index) => {
    const input = $(selector);
    if (input) input.value = String(values[index] || "");
  });
  hideStaleInputGroupResults(group);
  const action = applyRecentSearchKind(group, chip.dataset.recentKind || "");
  syncInputValidation(group);
  if (!action || !moduleActions[action]) return undefined;
  return withButtonLoading(chip, () => moduleActions[action]());
}

function bindInputValidationGroups() {
  $$(".search-recent-list").forEach((list) =>
    list.addEventListener("click", (event) => {
      const chip = event.target.closest(".search-recent-chip");
      if (chip) runRecentSearch(chip);
    }));
  Object.entries(INPUT_VALIDATION_GROUPS).forEach(([group, selectors]) => {
    selectors.forEach((selector) => {
      const input = $(selector);
      if (!input) return;
      input.addEventListener("input", () => syncInputValidation(group));
      input.addEventListener("change", () => syncInputValidation(group));
      input.addEventListener(
        "keydown",
        (event) => handleSearchInputKeydown(event, group),
      );
    });
  });
  $$("[data-clear-group]").forEach((button) =>
    button.addEventListener(
      "click",
      () => clearInputGroup(button.dataset.clearGroup),
    ));
  syncAllInputValidation();
}
