"use strict";

document.querySelector("#open-wfx").addEventListener("click", () => {
  chrome.tabs.create({
    url: "https://prosports.worldfashionexchange.com/wfx_Home.aspx",
  });
});
