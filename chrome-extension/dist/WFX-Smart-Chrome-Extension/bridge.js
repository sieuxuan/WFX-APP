"use strict";

(() => {
  const MESSAGE_SOURCE = "wfx-smart-chrome-extension";
  const bridgeToken = crypto.randomUUID();
  let mainReady = false;
  let initialValues = null;
  let bootstrapped = false;
  let pendingToggle = false;
  let contextLostNotified = false;

  const post = (type, payload = {}) => {
    window.postMessage({
      source: MESSAGE_SOURCE,
      type,
      ...payload,
    }, window.location.origin);
  };

  // Khi extension được reload/cập nhật trong khi tab WFX vẫn đang mở, content script cũ mất
  // quyền truy cập chrome.storage/chrome.runtime ("Extension context invalidated") — không có
  // cách nào phục hồi ngoài tải lại trang. window.postMessage() không phải API của extension nên
  // vẫn hoạt động bình thường sau khi bị invalidate; dùng nó để báo panel (MAIN world) hiện toast
  // yêu cầu người dùng F5, thay vì để lỗi rơi thẳng ra console dưới dạng uncaught exception.
  const isExtensionContextValid = () => {
    try {
      return Boolean(chrome.runtime && chrome.runtime.id);
    } catch (_error) {
      return false;
    }
  };

  const notifyContextLost = () => {
    if (contextLostNotified) return;
    contextLostNotified = true;
    console.warn("[WFX Smart] Extension context invalidated — hãy tải lại (F5) trang WFX để tiếp tục dùng panel.");
    try {
      post("extension-context-lost");
    } catch (_error) {
      // window đã đóng hoặc trang đang unload; không còn ai để báo nữa.
    }
  };

  const dispatchBootstrap = () => {
    if (bootstrapped || !mainReady || initialValues === null) return;
    bootstrapped = true;
    post("bootstrap", {
      token: bridgeToken,
      values: initialValues,
    });
    if (pendingToggle) {
      pendingToggle = false;
      post("extension-command", {
        token: bridgeToken,
        command: "toggle-panel",
      });
    }
  };

  const requestPanelToggle = () => {
    if (!bootstrapped) {
      pendingToggle = true;
      return;
    }
    post("extension-command", {
      token: bridgeToken,
      command: "toggle-panel",
    });
  };

  // Hotkey Ctrl+Shift+X do chrome.commands (manifest suggested_key) xử lý ở cấp trình duyệt: nó
  // bắt được cả khi focus đang nằm TRONG iframe của WFX — thứ mà listener keydown in-page (chỉ chạy
  // ở top frame) không làm được. Command -> background.js -> chrome.runtime.sendMessage
  // "wfx-smart-toggle-panel" -> requestPanelToggle() (xem onMessage bên dưới). Không còn bắt keydown
  // ở đây nữa để tránh double-toggle (Chrome command + keydown cùng bắn khi focus ở top frame).

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.origin !== window.location.origin ||
      event.data?.source !== MESSAGE_SOURCE
    ) {
      return;
    }
    const message = event.data;
    if (message.type === "main-ready") {
      mainReady = true;
      dispatchBootstrap();
      return;
    }
    if (
      message.type !== "storage-request" ||
      message.token !== bridgeToken ||
      typeof message.key !== "string"
    ) {
      return;
    }
    if (!isExtensionContextValid()) {
      notifyContextLost();
      return;
    }
    try {
      if (message.operation === "set") {
        chrome.storage.local.set({ [message.key]: message.value }, () => {
          if (chrome.runtime.lastError) {
            console.error(`[WFX Smart] Cannot save "${message.key}":`, chrome.runtime.lastError);
          }
        });
        return;
      }
      if (message.operation === "remove") {
        chrome.storage.local.remove(message.key, () => {
          if (chrome.runtime.lastError) {
            console.error(`[WFX Smart] Cannot remove "${message.key}":`, chrome.runtime.lastError);
          }
        });
      }
    } catch (_error) {
      // Race giữa isExtensionContextValid() và cú gọi thật — context vừa mất ngay lúc này.
      notifyContextLost();
    }
  });

  try {
    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (!bootstrapped || areaName !== "local") return;
      const updates = {};
      for (const [key, change] of Object.entries(changes)) {
        updates[key] = change.newValue;
      }
      post("storage-update", {
        token: bridgeToken,
        updates,
      });
    });
  } catch (_error) {
    notifyContextLost();
  }

  try {
    chrome.storage.local.get(null, (values) => {
      if (chrome.runtime.lastError) {
        console.error("[WFX Smart] Cannot load extension storage:", chrome.runtime.lastError);
        initialValues = {};
      } else {
        initialValues = values || {};
      }
      dispatchBootstrap();
    });
  } catch (_error) {
    notifyContextLost();
    initialValues = {};
    dispatchBootstrap();
  }

  try {
    chrome.runtime.onMessage.addListener((message) => {
      if (message?.type !== "wfx-smart-toggle-panel") return;
      requestPanelToggle();
    });
  } catch (_error) {
    notifyContextLost();
  }

  // Handshake hai chiều để không phụ thuộc thứ tự inject giữa ISOLATED và MAIN world.
  post("bridge-ready");
})();
