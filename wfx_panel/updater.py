"""Cập nhật WFX Smart từ GitHub Release chính thức.

Ứng dụng chỉ dùng bản phát hành Stable, tải gói Windows kèm checksum SHA-256,
đóng app, thay file và tự mở lại. Thiết lập người dùng nằm ngoài thư mục cài
đặt nên không bị ảnh hưởng.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from wfx_panel.version import APP_VERSION

REPOSITORY = "sieuxuan/WFX-APP"
LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
)
REQUEST_TIMEOUT_SECONDS = 20
ASSET_PATTERN = re.compile(
    r"^WFX-Panel-v(?P<version>\d+\.\d+\.\d+)-win64\.zip$",
    re.IGNORECASE,
)


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", str(value).strip())
    if not match:
        raise ValueError("Phiên bản không hợp lệ.")
    return tuple(int(part or 0) for part in match.groups())


def _load_latest_release() -> dict[str, Any]:
    request = Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"WFX-Smart/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Phản hồi bản phát hành không hợp lệ.")
    return payload


def _safe_release_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "objects.githubusercontent.com"}
    ):
        raise ValueError("Đường dẫn tải bản cập nhật không hợp lệ.")
    return url


def _release_assets(release: dict[str, Any]) -> tuple[str, str, str]:
    tag = str(release.get("tag_name") or "").strip()
    version = tag.removeprefix("v")
    _version_tuple(version)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Bản phát hành chưa có gói cài đặt.")

    package_name = f"WFX-Panel-v{version}-win64.zip"
    checksum_name = package_name + ".sha256"
    by_name = {
        str(asset.get("name") or ""): str(
            asset.get("browser_download_url") or ""
        )
        for asset in assets
        if isinstance(asset, dict)
    }
    package_url = _safe_release_url(by_name.get(package_name, ""))
    checksum_url = _safe_release_url(by_name.get(checksum_name, ""))
    return version, package_url, checksum_url


def check_for_updates(
    root: Path | None = None,
    *,
    channel: str = "stable",
) -> dict[str, Any]:
    """Kiểm tra GitHub Release Stable mới nhất.

    ``root`` và ``channel`` được giữ để tương thích bridge cũ; updater phát
    hành không còn phụ thuộc Git repository trên máy người dùng.
    """
    _ = root, channel
    try:
        release = _load_latest_release()
        version, package_url, checksum_url = _release_assets(release)
        common = {
            "channel": "stable",
            "version": version,
            "tag": str(release.get("tag_name") or f"v{version}"),
            "notice_id": str(release.get("id") or version),
            "release_url": str(release.get("html_url") or ""),
            "package_url": package_url,
            "checksum_url": checksum_url,
        }
        if _version_tuple(version) <= _version_tuple(APP_VERSION):
            return {
                **common,
                "ok": True,
                "code": "UP_TO_DATE",
                "message": "Bạn đang dùng phiên bản mới nhất.",
                "can_update": False,
            }
        return {
            **common,
            "ok": True,
            "code": "UPDATE_AVAILABLE",
            "message": (
                f"Phiên bản {version} đã sẵn sàng. "
                "Bấm “Cập nhật ngay”; ứng dụng sẽ tự mở lại sau khi hoàn tất."
            ),
            "can_update": True,
        }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return {
            "ok": False,
            "code": "UPDATE_CHECK_FAILED",
            "message": (
                "Chưa thể kiểm tra bản cập nhật. "
                "Ứng dụng sẽ tự thử lại sau."
            ),
            "can_update": False,
            "channel": "stable",
            "version": APP_VERSION,
        }


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _data_dir() -> Path:
    return Path(
        os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    ) / "WFX-Panel"


def consume_update_result(base_dir: Path | None = None) -> dict | None:
    path = Path(base_dir or _data_dir()) / "update-result.json"
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        result = None
    try:
        path.unlink()
    except OSError:
        pass
    return result if isinstance(result, dict) else None


def schedule_update(
    state: dict[str, Any],
    *,
    current_pid: int | None = None,
    executable: Path | None = None,
    executable_args: list[str] | None = None,
) -> Path:
    """Tạo helper GUI độc lập để thay bản app và hiển thị tiến trình trực quan."""
    if not state.get("can_update"):
        raise ValueError("Không có bản cập nhật để cài.")

    version = str(state.get("version") or "").strip()
    _version_tuple(version)
    package_url = _safe_release_url(str(state.get("package_url") or ""))
    checksum_url = _safe_release_url(str(state.get("checksum_url") or ""))
    target_exe = Path(executable or os.sys.executable).resolve()
    install_dir = target_exe.parent
    pid = int(current_pid or os.getpid())

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "update.log"
    result_path = data_dir / "update-result.json"
    helper = Path(tempfile.gettempdir()) / f"wfx-panel-update-{pid}.ps1"

    exe_args_list = [str(arg) for arg in (executable_args or [])]
    exe_args_ps = (
        ",".join(_ps_quote(arg) for arg in exe_args_list)
        if exe_args_list
        else ""
    )

    content = f"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$updateLog = {_ps_quote(log_path)}
$resultPath = {_ps_quote(result_path)}
$packageUrl = {_ps_quote(package_url)}
$checksumUrl = {_ps_quote(checksum_url)}
$version = {_ps_quote(version)}
$targetExe = {_ps_quote(target_exe)}
$installDir = {_ps_quote(install_dir)}
$exeArgs = @({exe_args_ps})
$workDir = Join-Path $env:TEMP 'wfx-panel-update-{pid}'
$zipPath = Join-Path $workDir 'WFX-Panel.zip'
$checksumPath = Join-Path $workDir 'WFX-Panel.zip.sha256'
$expandedDir = Join-Path $workDir 'expanded'
$backupDir = "$installDir.backup-{pid}"

function Write-UpdateResult([bool]$ok, [string]$code, [string]$message) {{
  @{{ok=$ok; code=$code; message=$message; version=$version}} |
    ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}}

$form = New-Object System.Windows.Forms.Form
$form.Text = "WFX Smart - Cập nhật phiên bản $version"
$form.Size = New-Object System.Drawing.Size(480, 240)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 28, 36)
$form.ForeColor = [System.Drawing.Color]::White

$lblHeader = New-Object System.Windows.Forms.Label
$lblHeader.Location = New-Object System.Drawing.Point(24, 20)
$lblHeader.Size = New-Object System.Drawing.Size(420, 28)
$lblHeader.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$lblHeader.Text = "Đang cập nhật WFX Smart v$version"
$lblHeader.ForeColor = [System.Drawing.Color]::White
$form.Controls.Add($lblHeader)

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(24, 55)
$lblStatus.Size = New-Object System.Drawing.Size(420, 42)
$lblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$lblStatus.Text = "Đang khởi tạo tiến trình cập nhật..."
$lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(180, 195, 215)
$form.Controls.Add($lblStatus)

$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(24, 105)
$progressBar.Size = New-Object System.Drawing.Size(420, 22)
$progressBar.Style = "Marquee"
$progressBar.MarqueeAnimationSpeed = 30
$form.Controls.Add($progressBar)

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Location = New-Object System.Drawing.Point(344, 145)
$btnClose.Size = New-Object System.Drawing.Size(100, 32)
$btnClose.Text = "Đóng"
$btnClose.FlatStyle = "Flat"
$btnClose.BackColor = [System.Drawing.Color]::FromArgb(45, 55, 72)
$btnClose.ForeColor = [System.Drawing.Color]::White
$btnClose.Visible = $false
$btnClose.Add_Click({{ $form.Close() }})
$form.Controls.Add($btnClose)

function Update-UI([string]$text, [int]$percent = -1, [string]$tone = 'info') {{
  # Perform-Update chạy trên chính WinForms/PowerShell runspace. Cập nhật
  # control trực tiếp rồi bơm message loop để cửa sổ không bị "Not responding".
  $lblStatus.Text = $text
  if ($tone -eq 'error') {{
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(255, 110, 110)
  }} elseif ($tone -eq 'success') {{
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(100, 220, 140)
  }} else {{
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(180, 195, 215)
  }}
  if ($percent -ge 0) {{
    $progressBar.Style = "Blocks"
    $progressBar.Value = [math]::Min(100, [math]::Max(0, $percent))
  }} else {{
    $progressBar.Style = "Marquee"
    $progressBar.MarqueeAnimationSpeed = 30
  }}
  $form.Refresh()
  [System.Windows.Forms.Application]::DoEvents()
}}

function Safe-Remove([string]$path) {{
  for ($i = 0; $i -lt 15; $i++) {{
    try {{
      if (Test-Path -LiteralPath $path) {{
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
      }}
      return
    }} catch {{
      Start-Sleep -Milliseconds 500
    }}
  }}
  if (Test-Path -LiteralPath $path) {{
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
  }}
}}

function Download-WithUi([string]$url, [string]$path) {{
  $webClient = New-Object System.Net.WebClient
  $webClient.Headers.Add("User-Agent", "WFX-Smart-Updater")
  try {{
    $task = $webClient.DownloadFileTaskAsync([Uri]$url, $path)
    while (-not $task.IsCompleted) {{
      [System.Windows.Forms.Application]::DoEvents()
      Start-Sleep -Milliseconds 80
    }}
    # GetResult ném lại lỗi HTTP/network thật thay vì để task fault im lặng.
    $task.GetAwaiter().GetResult()
  }} finally {{
    $webClient.Dispose()
  }}
}}

function Perform-Update {{
  try {{
    Update-UI "Đang chờ ứng dụng chính đóng..." 5
    $waitDeadline = (Get-Date).AddSeconds(15)
    while (
      (Get-Process -Id {pid} -ErrorAction SilentlyContinue) -and
      (Get-Date) -lt $waitDeadline
    ) {{
      [System.Windows.Forms.Application]::DoEvents()
      Start-Sleep -Milliseconds 120
    }}
    Start-Sleep -Milliseconds 300

    Safe-Remove $workDir
    Safe-Remove $backupDir
    New-Item -ItemType Directory -Path $expandedDir -Force | Out-Null

    Update-UI "Đang tải gói cập nhật WFX Smart v$version..."
    Download-WithUi $packageUrl $zipPath
    Download-WithUi $checksumUrl $checksumPath

    Update-UI "Đang kiểm tra mã checksum SHA-256..." 50
    $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\\s+')[0]
    if ($expectedHash -notmatch '^[A-Fa-f0-9]{{64}}$') {{
      throw 'Tệp checksum SHA-256 không hợp lệ.'
    }}
    $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
    if ($actualHash.ToLowerInvariant() -ne $expectedHash.ToLowerInvariant()) {{
      throw 'Mã SHA-256 của gói tải về không trùng khớp.'
    }}

    Update-UI "Đang giải nén gói cập nhật..." 70
    Expand-Archive -LiteralPath $zipPath -DestinationPath $expandedDir -Force
    $newExe = Get-ChildItem -LiteralPath $expandedDir -Filter 'WFX-Panel.exe' -Recurse | Select-Object -First 1
    if (-not $newExe) {{
      throw 'Không tìm thấy WFX-Panel.exe trong gói cài đặt.'
    }}
    $newRoot = $newExe.Directory.FullName

    Update-UI "Đang cài đặt phiên bản mới..." 85
    Copy-Item -LiteralPath $installDir -Destination $backupDir -Recurse -Force
    Safe-Remove $installDir
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Copy-Item -Path (Join-Path $newRoot '*') -Destination $installDir -Recurse -Force

    if (-not (Test-Path -LiteralPath $targetExe)) {{
      throw 'Tệp ứng dụng sau cập nhật không tồn tại.'
    }}

    Write-UpdateResult $true 'UPDATE_INSTALLED' "Đã cập nhật thành công lên phiên bản $version."
    Update-UI "Cập nhật thành công! Đang tự động mở lại WFX Smart..." 100 'success'
    Start-Sleep -Seconds 1.5

    if ($exeArgs.Count -gt 0) {{
      Start-Process -FilePath $targetExe -ArgumentList $exeArgs -WorkingDirectory $installDir
    }} else {{
      Start-Process -FilePath $targetExe -WorkingDirectory $installDir
    }}

    Safe-Remove $backupDir
    $form.Close()
  }} catch {{
    $err = $_.Exception.Message
    $_ | Out-String | Add-Content -LiteralPath $updateLog
    Update-UI "Cập nhật thất bại: $err`nĐang khôi phục phiên bản cũ..." 50 'error'
    try {{
      if (Test-Path -LiteralPath $backupDir) {{
        Safe-Remove $installDir
        Move-Item -LiteralPath $backupDir -Destination $installDir -Force
      }}
      Write-UpdateResult $false 'UPDATE_ROLLED_BACK' 'Cập nhật thất bại. Đã khôi phục phiên bản trước.'
    }} catch {{
      $_ | Out-String | Add-Content -LiteralPath $updateLog
      Write-UpdateResult $false 'UPDATE_ROLLBACK_FAILED' 'Không thể hoàn tất cập nhật. Vui lòng tải lại ứng dụng.'
    }}

    Update-UI "Lỗi: $err`nĐã khôi phục phiên bản trước. Vui lòng thử lại." 0 'error'
    if (Test-Path -LiteralPath $targetExe) {{
      if ($exeArgs.Count -gt 0) {{
        Start-Process -FilePath $targetExe -ArgumentList $exeArgs -WorkingDirectory $installDir
      }} else {{
        Start-Process -FilePath $targetExe -WorkingDirectory $installDir
      }}
    }}
    $btnClose.Visible = $true
    $progressBar.Visible = $false
    $form.Refresh()
  }} finally {{
    Safe-Remove $workDir
  }}
}}

$startTimer = New-Object System.Windows.Forms.Timer
$startTimer.Interval = 120
$startTimer.Add_Tick({{
  $startTimer.Stop()
  Perform-Update
}})
$form.Add_Shown({{
  $startTimer.Start()
}})

$form.ShowDialog() | Out-Null
"""
    helper.write_text(content, encoding="utf-8-sig")
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    return helper

