"use strict";
(() => {
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const bubble = document.querySelector(".bubble");
  const DRAG_THRESHOLD = 4;

  let pressOrigin = null;
  let dragging = false;
  let suppressClick = false;

  function resetDragState() {
    pressOrigin = null;
    dragging = false;
    document.body.classList.remove("is-dragging");
  }

  bubble.addEventListener("mousedown", (event) => {
    api()?.note_bubble_interaction?.();
    if (event.button !== 0) return;
    pressOrigin = { x: event.screenX, y: event.screenY };
    dragging = false;
    suppressClick = false;
  });

  // pywebview tự dời mọi phần tử .pywebview-drag-region. Đo quãng đường ở
  // đây chỉ để phân biệt click với drag; không gọi bridge bất đồng bộ mỗi frame.
  window.addEventListener("mousemove", (event) => {
    if (!pressOrigin || (event.buttons & 1) === 0) return;
    const distance = Math.hypot(
      event.screenX - pressOrigin.x,
      event.screenY - pressOrigin.y,
    );
    if (!dragging && distance >= DRAG_THRESHOLD) {
      dragging = true;
      suppressClick = true;
      document.body.classList.add("is-dragging");
    }
  });

  window.addEventListener("mouseup", (event) => {
    if (event.button !== 0 || !pressOrigin) return;
    const moved = dragging;
    resetDragState();
    if (moved) api()?.save_bubble_position?.();
  });

  bubble.addEventListener("click", (event) => {
    if (suppressClick) {
      event.preventDefault();
      event.stopPropagation();
      suppressClick = false;
      return;
    }
    api()?.toggle_panel?.();
  });

  bubble.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    resetDragState();
    suppressClick = false;
    api()?.note_bubble_interaction?.();
    api()?.bubble_context_menu?.();
  });

  window.addEventListener("blur", resetDragState);
  bubble.addEventListener("dragstart", (event) => event.preventDefault());
})();
