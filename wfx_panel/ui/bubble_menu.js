"use strict";
(() => {
  const api = () => (window.pywebview && window.pywebview.api) || null;

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action || "";
      await api()?.choose?.(action);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      api()?.dismiss?.();
    }
  });
})();
