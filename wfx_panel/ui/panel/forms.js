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
  rmpo: [".rmpo-supplier-query", ".rmpo-order-query"],
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

function bindInputValidationGroups() {
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
