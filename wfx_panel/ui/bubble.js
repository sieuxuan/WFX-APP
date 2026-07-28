"use strict";
(() => {
  const api = () => (window.pywebview && window.pywebview.api) || null;
  const bubble = document.querySelector(".bubble");
  const DRAG_THRESHOLD = 4;

  let pressOrigin = null;
  let dragging = false;
  let suppressClick = false;

  function resetDragState(notifyBackend = false) {
    const hadInteraction = pressOrigin !== null;
    pressOrigin = null;
    dragging = false;
    document.body.classList.remove("is-dragging");
    if (notifyBackend && hadInteraction) api()?.end_bubble_interaction?.();
  }

  bubble.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    api()?.begin_bubble_interaction?.();
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
    resetDragState(true);
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
    resetDragState(true);
    suppressClick = false;
    api()?.note_bubble_interaction?.();
    api()?.bubble_context_menu?.();
  });

  window.addEventListener("blur", () => resetDragState(true));
  window.addEventListener("pointercancel", () => resetDragState(true));
  bubble.addEventListener("dragstart", (event) => event.preventDefault());
})();
