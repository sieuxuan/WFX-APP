"use strict";

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "toggle-panel") return;
  const [activeTab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  if (!activeTab?.id) return;
  try {
    await chrome.tabs.sendMessage(activeTab.id, {
      type: "wfx-smart-toggle-panel",
    });
  } catch (_error) {
    // Tab hiện tại không phải WFX hoặc chưa reload sau khi cài extension.
  }
});
