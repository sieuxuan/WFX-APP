"use strict";
(() => {
  const root = document.documentElement;
  const notification = document.querySelector(".notification");
  const title = document.querySelector(".notification-title");
  const message = document.querySelector(".notification-message");

  window.wfxShowNotification = (payload = {}) => {
    root.dataset.theme = payload.theme === "dark" ? "dark" : "light";
    notification.classList.toggle("notification-error", payload.tone === "error");
    notification.classList.toggle("notification-success", payload.tone !== "error");
    title.textContent = payload.title || "Đã hoàn thành";
    message.textContent = payload.message || "Tác vụ WFX đã hoàn tất.";
    notification.classList.remove("notification-visible");
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        notification.classList.add("notification-visible");
      });
    });
  };

  document.querySelector(".notification-close").addEventListener("click", () => {
    notification.classList.remove("notification-visible");
    window.setTimeout(() => window.pywebview?.api?.dismiss?.(), 150);
  });
})();
