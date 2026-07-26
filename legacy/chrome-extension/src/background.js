"use strict";

const WFX_HOSTNAME = "prosports.worldfashionexchange.com";
const WFX_HOME_URL = `https://${WFX_HOSTNAME}/wfx_Home.aspx`;
const lastToggleByTab = new Map();
const injectionInFlight = new Map();

function isWfxUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.protocol === "https:" && parsed.hostname === WFX_HOSTNAME;
  } catch (_error) {
    return false;
  }
}

async function ensureWfxInjected(tabId) {
  if (!tabId) return false;
  if (injectionInFlight.has(tabId)) return injectionInFlight.get(tabId);
  const task = (async () => {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["bridge.js"],
        world: "ISOLATED",
        injectImmediately: true,
      });
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["main.js"],
        world: "MAIN",
        injectImmediately: true,
      });
      return true;
    } catch (_error) {
      // Có thể tab vừa đóng/chuyển origin hoặc Chrome chưa cấp quyền cho document đặc biệt.
      return false;
    } finally {
      injectionInFlight.delete(tabId);
    }
  })();
  injectionInFlight.set(tabId, task);
  return task;
}

async function togglePanelInTab(tab) {
  if (!tab?.id) return;
  const now = Date.now();
  const previous = lastToggleByTab.get(tab.id) || 0;
  // Ctrl+Shift+X có thể đồng thời đi qua chrome.commands và fallback keydown trong bridge.
  // Debounce theo tab để một lần nhấn chỉ toggle đúng một lần.
  if (now - previous < 500) return;
  lastToggleByTab.set(tab.id, now);
  try {
    await chrome.tabs.sendMessage(tab.id, {
      type: "wfx-smart-toggle-panel",
    });
  } catch (_error) {
    // Static content script có thể bị bỏ lỡ ở popup/content-only page. Tự inject rồi gửi lại.
    if (isWfxUrl(tab.url) && await ensureWfxInjected(tab.id)) {
      try {
        await chrome.tabs.sendMessage(tab.id, {
          type: "wfx-smart-toggle-panel",
        });
      } catch (_retryError) {
        // Document vừa chuyển tiếp lần nữa; tabs.onUpdated sẽ thử ở lần complete kế tiếp.
      }
    }
  }
}

async function findOrOpenWfxTab() {
  const [activeTab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  let targetTab = activeTab;
  if (!isWfxUrl(targetTab?.url)) {
    const wfxTabs = await chrome.tabs.query({
      url: "https://prosports.worldfashionexchange.com/*",
    });
    targetTab = wfxTabs[0];
    if (targetTab?.id) {
      await chrome.tabs.update(targetTab.id, { active: true });
      if (targetTab.windowId !== undefined) {
        await chrome.windows.update(targetTab.windowId, { focused: true });
      }
    } else {
      targetTab = await chrome.tabs.create({
        url: WFX_HOME_URL,
        active: true,
      });
      return null;
    }
  }
  return targetTab;
}

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "toggle-panel") return;
  await togglePanelInTab(await findOrOpenWfxTab());
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "wfx-smart-local-hotkey") return;
  void togglePanelInTab(sender.tab);
});

// Một số màn Article/Costing là content-only popup, không có `topsection` và đôi khi Chrome bỏ lỡ
// static content script trong chuỗi about:blank -> redirect. Khi top document WFX hoàn tất, đảm bảo
// bridge + panel đã được inject. Guard trong hai script làm thao tác này idempotent.
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !isWfxUrl(tab.url)) return;
  void ensureWfxInjected(tabId);
});
