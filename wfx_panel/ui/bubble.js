"use strict";
(() => {
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const bubble = document.querySelector(".bubble");

  let holdTimer = null;
  let dragging = false;

  function clearHold() {
    if (holdTimer !== null) {
      window.clearTimeout(holdTimer);
      holdTimer = null;
    }
  }

  bubble.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    dragging = false;
    // Giữ ~180ms để bắt đầu kéo; nhả sớm hơn coi như "click mở panel".
    holdTimer = window.setTimeout(() => {
      dragging = true;
      document.body.classList.add("is-dragging");
      api()?.begin_bubble_drag?.();
    }, 180);
  });

  bubble.addEventListener("mouseup", () => {
    clearHold();
    if (dragging) {
      // Kết thúc kéo — nuốt click để không mở panel ngay sau khi thả.
      window.setTimeout(() => {
        dragging = false;
        document.body.classList.remove("is-dragging");
      }, 300);
    }
  });

  bubble.addEventListener("click", (event) => {
    if (dragging) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    api()?.toggle_panel?.();
  });

  bubble.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    clearHold();
    dragging = false;
    document.body.classList.remove("is-dragging");
    api()?.bubble_context_menu?.();
  });

  // Không cho kéo-thả ảnh/text mặc định của trình duyệt làm phiền thao tác.
  bubble.addEventListener("dragstart", (event) => event.preventDefault());
})();
