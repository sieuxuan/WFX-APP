"use strict";
(() => {
  const root = document.documentElement;
  const notification = document.querySelector(".notification");
  const title = document.querySelector(".notification-title");
  const message = document.querySelector(".notification-message");
  const detail = document.querySelector(".notification-detail");

  const resolveTheme = (value) => {
    if (value === "dark") return "dark";
    if (value === "system") {
      return window.matchMedia
        && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return "light";
  };

  window.wfxShowNotification = (payload = {}) => {
    root.dataset.theme = resolveTheme(payload.theme);
    notification.classList.toggle("notification-error", payload.tone === "error");
    notification.classList.toggle("notification-success", payload.tone !== "error");
    title.textContent = payload.title || "Đã hoàn thành";
    message.textContent = payload.message || "Tác vụ WFX đã hoàn tất.";
    detail.textContent = payload.detail || "";
    detail.hidden = !detail.textContent;
    // Cửa sổ notification còn hidden tại thời điểm backend gọi hàm này.
    // requestAnimationFrame có thể bị WebView hoãn vô hạn, khiến toast hiện
    // nhưng opacity vẫn bằng 0. Bật visible đồng bộ trước khi native show.
    notification.classList.add("notification-visible");
  };

  document.querySelector(".notification-close").addEventListener("click", () => {
    notification.classList.remove("notification-visible");
    window.setTimeout(() => window.pywebview?.api?.dismiss?.(), 150);
  });
})();
