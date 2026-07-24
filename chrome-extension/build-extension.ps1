[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$extensionRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $extensionRoot ".."))
$sourceRoot = Join-Path $extensionRoot "src"
$distRoot = Join-Path $extensionRoot "dist"
$packageRoot = Join-Path $distRoot "WFX-Smart-Chrome-Extension"
$zipPath = Join-Path $distRoot "WFX-Smart-Chrome-Extension-v1.9.1.zip"
$userscriptPath = Join-Path $projectRoot "wfx-tampermonkey.user.js"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

foreach ($target in @($distRoot, $packageRoot, $zipPath)) {
    $fullTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $fullTarget.StartsWith($extensionRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build target outside extension root: $fullTarget"
    }
}

if (-not (Test-Path -LiteralPath $userscriptPath -PathType Leaf)) {
    throw "Missing userscript source: $userscriptPath"
}

if (Test-Path -LiteralPath $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

$manifest = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot "manifest.json") | ConvertFrom-Json
$userscript = Get-Content -Raw -LiteralPath $userscriptPath
$versionMatch = [regex]::Match($userscript, '(?m)^// @version\s+([0-9.]+)\s*$')
if (-not $versionMatch.Success) {
    throw "Cannot read @version from userscript."
}
$userscriptVersion = $versionMatch.Groups[1].Value
if ($manifest.version -ne $userscriptVersion) {
    throw "Version mismatch: manifest=$($manifest.version), userscript=$userscriptVersion"
}

$core = [regex]::Replace(
    $userscript,
    '(?s)^\s*// ==UserScript==.*?// ==/UserScript==\s*',
    ''
)
$core = $core.Replace("Tampermonkey", "Chrome Extension")
$core = $core.Replace("userscript", "extension")

$adapterPrefix = @'
"use strict";

// Generated Chrome MV3 main-world adapter. Source of truth: ../../wfx-tampermonkey.user.js
(() => {
  if (window.__wfxSmartChromeExtensionLoaded) return;
  window.__wfxSmartChromeExtensionLoaded = true;

  const MESSAGE_SOURCE = "wfx-smart-chrome-extension";
  let started = false;
  let applyStorageUpdate = () => {};
  let handleExtensionCommand = () => {};

  const post = (type, payload = {}) => {
    window.postMessage({
      source: MESSAGE_SOURCE,
      type,
      ...payload,
    }, window.location.origin);
  };

  const start = (bridgeToken, initialValues) => {
    if (started) return;
    started = true;
    const extensionCache = { ...(initialValues || {}) };
    const unsafeWindow = window;

    const GM_getValue = (key) => extensionCache[key];
    const GM_setValue = (key, value) => {
      extensionCache[key] = value;
      post("storage-request", {
        token: bridgeToken,
        operation: "set",
        key,
        value,
      });
    };
    const GM_deleteValue = (key) => {
      delete extensionCache[key];
      post("storage-request", {
        token: bridgeToken,
        operation: "remove",
        key,
      });
    };
    const GM_registerMenuCommand = () => {};
    applyStorageUpdate = (token, updates) => {
      if (token !== bridgeToken || !updates) return;
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined) delete extensionCache[key];
        else extensionCache[key] = value;
      }
    };
    handleExtensionCommand = (token, command) => {
      if (token !== bridgeToken || command !== "toggle-panel") return;
      document.dispatchEvent(new CustomEvent("wfx-smart-extension-toggle-panel"));
    };

'@

$adapterSuffix = @'

  };

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.origin !== window.location.origin ||
      event.data?.source !== MESSAGE_SOURCE
    ) {
      return;
    }
    const message = event.data;
    if (message.type === "bridge-ready") {
      post("main-ready");
      return;
    }
    if (message.type === "bootstrap" && typeof message.token === "string") {
      start(message.token, message.values);
      return;
    }
    if (message.type === "storage-update") {
      applyStorageUpdate(message.token, message.updates);
      return;
    }
    if (message.type === "extension-command") {
      handleExtensionCommand(message.token, message.command);
      return;
    }
    if (message.type === "extension-context-lost") {
      // Bridge (ISOLATED world) mất quyền truy cập chrome.storage/chrome.runtime vì extension
      // vừa được reload/cập nhật trong khi tab này vẫn mở. Không còn cách nào tự phục hồi — báo
      // cho core script (đã chạy trong scope start() bên dưới) qua CustomEvent trên `document`,
      // giống cách handleExtensionCommand chuyển tiếp lệnh toggle-panel.
      document.dispatchEvent(new CustomEvent("wfx-smart-extension-context-lost"));
    }
  });
  post("main-ready");
})();
'@

$content = $adapterPrefix + $core + $adapterSuffix
[System.IO.File]::WriteAllText((Join-Path $packageRoot "main.js"), $content, $utf8NoBom)

foreach ($file in @("manifest.json", "background.js", "bridge.js", "popup.html", "popup.css", "popup.js")) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination (Join-Path $packageRoot $file)
}
Copy-Item -LiteralPath (Join-Path $extensionRoot "README.md") -Destination (Join-Path $packageRoot "README.md")

Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host "Chrome extension built successfully:"
Write-Host "  Folder: $packageRoot"
Write-Host "  ZIP:    $zipPath"
