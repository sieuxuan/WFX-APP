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

function syncInputValidation(group) {
  const selectors = INPUT_VALIDATION_GROUPS[group] || [];
  const valid = selectors.some(
    (selector) => String($(selector)?.value || "").trim().length > 0,
  );
  $$(`[data-validation-group="${group}"]`).forEach((button) => {
    button.disabled = busy || !valid;
    button.setAttribute("aria-disabled", String(busy || !valid));
  });
  $$(`[data-validation-hint="${group}"]`).forEach((hint) => {
    hint.hidden = valid;
  });
}

function syncAllInputValidation() {
  Object.keys(INPUT_VALIDATION_GROUPS).forEach(syncInputValidation);
}
