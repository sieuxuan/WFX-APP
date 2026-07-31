"""Cập nhật WFX Smart từ GitHub Release chính thức.

Ứng dụng chỉ dùng bản phát hành Stable, tải gói Windows kèm checksum SHA-256,
đóng app, thay file và tự mở lại. Thiết lập người dùng nằm ngoài thư mục cài
đặt nên không bị ảnh hưởng.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from wfx_panel._signing_identity import EXPECTED_SIGNER_THUMBPRINT
from wfx_panel.version import APP_VERSION

REPOSITORY = "sieuxuan/WFX-APP"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
REQUEST_TIMEOUT_SECONDS = 20
ASSET_PATTERN = re.compile(
    r"^WFX-Smart-v(?P<version>\d+\.\d+\.\d+)-win64\.zip$",
    re.IGNORECASE,
)
PACKAGE_PREFIX = "WFX-Smart"
EXPECTED_EXECUTABLE_NAME = "WFX-Panel.exe"
OWNED_INSTALL_ITEMS = (EXPECTED_EXECUTABLE_NAME, "_internal")


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
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com",
        "objects.githubusercontent.com",
    }:
        raise ValueError("Đường dẫn tải bản cập nhật không hợp lệ.")
    return url


def _validate_asset_urls(
    version: str,
    package_url: str,
    checksum_url: str,
    signature_url: str,
) -> None:
    package_name = f"{PACKAGE_PREFIX}-v{version}-win64.zip"
    expected = (
        package_name,
        package_name + ".sha256",
        package_name + ".sha256.p7s",
    )
    actual = tuple(
        Path(urlparse(url).path).name
        for url in (package_url, checksum_url, signature_url)
    )
    if actual != expected:
        raise ValueError("Tên các tệp cập nhật không khớp phiên bản được phát hành.")


def _release_assets(release: dict[str, Any]) -> tuple[str, str, str, str]:
    tag = str(release.get("tag_name") or "").strip()
    version = tag.removeprefix("v")
    _version_tuple(version)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Bản phát hành chưa có gói cài đặt.")

    package_name = f"{PACKAGE_PREFIX}-v{version}-win64.zip"
    checksum_name = package_name + ".sha256"
    signature_name = checksum_name + ".p7s"
    by_name = {
        str(asset.get("name") or ""): str(asset.get("browser_download_url") or "")
        for asset in assets
        if isinstance(asset, dict)
    }
    package_url = _safe_release_url(by_name.get(package_name, ""))
    checksum_url = _safe_release_url(by_name.get(checksum_name, ""))
    signature_url = _safe_release_url(by_name.get(signature_name, ""))
    return version, package_url, checksum_url, signature_url


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
        version, package_url, checksum_url, signature_url = _release_assets(release)
        common = {
            "channel": "stable",
            "version": version,
            "tag": str(release.get("tag_name") or f"v{version}"),
            "notice_id": str(release.get("id") or version),
            "release_url": str(release.get("html_url") or ""),
            "package_url": package_url,
            "checksum_url": checksum_url,
            "signature_url": signature_url,
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
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return {
            "ok": False,
            "code": "UPDATE_CHECK_FAILED",
            "message": ("Chưa thể kiểm tra bản cập nhật. Ứng dụng sẽ tự thử lại sau."),
            "can_update": False,
            "channel": "stable",
            "version": APP_VERSION,
        }


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _data_dir() -> Path:
    return (
        Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        / "WFX-Panel"
    )


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
    signature_url = _safe_release_url(str(state.get("signature_url") or ""))
    _validate_asset_urls(
        version,
        package_url,
        checksum_url,
        signature_url,
    )
    if _version_tuple(version) <= _version_tuple(APP_VERSION):
        raise ValueError("Chỉ được cài phiên bản mới hơn bản đang chạy.")
    target_exe = Path(executable or sys.executable).resolve()
    if target_exe.name.casefold() != EXPECTED_EXECUTABLE_NAME.casefold():
        raise ValueError(
            "Cập nhật tự động chỉ được phép thay WFX-Panel.exe trong bản đóng gói."
        )
    if not target_exe.is_file():
        raise ValueError("Không tìm thấy WFX-Panel.exe đang chạy.")
    internal_dir = target_exe.parent / "_internal"
    if not internal_dir.is_dir():
        raise ValueError("Bản cài đặt hiện tại thiếu thư mục _internal.")
    signer_thumbprint = re.sub(r"[^A-Fa-f0-9]", "", EXPECTED_SIGNER_THUMBPRINT).upper()
    if not re.fullmatch(r"[A-F0-9]{40}", signer_thumbprint):
        raise ValueError(
            "Bản ứng dụng này chưa có danh tính ký số; không thể tự cập nhật an toàn."
        )
    install_dir = target_exe.parent
    pid = int(current_pid or os.getpid())
    if pid <= 0:
        raise ValueError("Process ID của ứng dụng không hợp lệ.")

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "update.log"
    result_path = data_dir / "update-result.json"
    work_dir = Path(tempfile.mkdtemp(prefix=f"wfx-panel-update-{pid}-")).resolve()
    helper = work_dir / "update.ps1"

    exe_args_list = [str(arg) for arg in (executable_args or [])]
    exe_args_ps = (
        ",".join(_ps_quote(arg) for arg in exe_args_list) if exe_args_list else ""
    )

    content = f"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$updateLog = {_ps_quote(log_path)}
$resultPath = {_ps_quote(result_path)}
$packageUrl = {_ps_quote(package_url)}
$checksumUrl = {_ps_quote(checksum_url)}
$signatureUrl = {_ps_quote(signature_url)}
$expectedSigner = {_ps_quote(signer_thumbprint)}
$version = {_ps_quote(version)}
$targetExe = {_ps_quote(target_exe)}
$installDir = {_ps_quote(install_dir)}
$exeArgs = @({exe_args_ps})
$workDir = {_ps_quote(work_dir)}
$zipPath = Join-Path $workDir 'WFX-Panel.zip'
$checksumPath = Join-Path $workDir 'WFX-Panel.zip.sha256'
$signaturePath = Join-Path $workDir 'WFX-Panel.zip.sha256.p7s'
$expandedDir = Join-Path $workDir 'expanded'
$backupDir = Join-Path $workDir 'backup'
$ownedItems = @('WFX-Panel.exe', '_internal')
$installStarted = $false
$allowedRemovePaths = @(
  [System.IO.Path]::GetFullPath($workDir).TrimEnd('\\'),
  [System.IO.Path]::GetFullPath(
    (Join-Path $installDir 'WFX-Panel.exe')
  ).TrimEnd('\\'),
  [System.IO.Path]::GetFullPath(
    (Join-Path $installDir '_internal')
  ).TrimEnd('\\'),
  [System.IO.Path]::GetFullPath(
    $backupDir
  ).TrimEnd('\\'),
  [System.IO.Path]::GetFullPath(
    $expandedDir
  ).TrimEnd('\\')
)

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

$script:updateErrorReport = ''
$btnCopyError = New-Object System.Windows.Forms.Button
$btnCopyError.Location = New-Object System.Drawing.Point(208, 145)
$btnCopyError.Size = New-Object System.Drawing.Size(124, 32)
$btnCopyError.Text = "Sao chép lỗi"
$btnCopyError.FlatStyle = "Flat"
$btnCopyError.BackColor = [System.Drawing.Color]::FromArgb(45, 55, 72)
$btnCopyError.ForeColor = [System.Drawing.Color]::White
$btnCopyError.Visible = $false
$btnCopyError.Add_Click({{
  try {{
    if (-not [string]::IsNullOrWhiteSpace($script:updateErrorReport)) {{
      [System.Windows.Forms.Clipboard]::SetText($script:updateErrorReport)
      $btnCopyError.Text = "Đã sao chép"
    }}
  }} catch {{
    $btnCopyError.Text = "Không thể sao chép"
  }}
}})
$form.Controls.Add($btnCopyError)

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
  $safePath = [System.IO.Path]::GetFullPath($path).TrimEnd('\\')
  if ($allowedRemovePaths -notcontains $safePath) {{
    throw "Từ chối xóa đường dẫn ngoài phạm vi updater: $safePath"
  }}
  if (Test-Path -LiteralPath $safePath) {{
    $item = Get-Item -LiteralPath $safePath -Force
    if (
      ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
    ) {{
      throw "Từ chối xóa reparse point: $safePath"
    }}
  }}
  for ($i = 0; $i -lt 15; $i++) {{
    try {{
      if (Test-Path -LiteralPath $safePath) {{
        Remove-Item -LiteralPath $safePath -Recurse -Force -ErrorAction Stop
      }}
      return
    }} catch {{
      Start-Sleep -Milliseconds 500
    }}
  }}
  if (Test-Path -LiteralPath $safePath) {{
    Remove-Item -LiteralPath $safePath -Recurse -Force -ErrorAction Stop
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

function Import-CmsAssembly {{
  # Windows PowerShell 5.1 cung cấp SignedCms trong System.Security.dll,
  # còn PowerShell 7/.NET mới tách thành System.Security.Cryptography.Pkcs.
  try {{
    Add-Type `
      -AssemblyName System.Security.Cryptography.Pkcs `
      -ErrorAction Stop
  }} catch {{
    Add-Type -AssemblyName System.Security -ErrorAction Stop
  }}
  if (-not ('System.Security.Cryptography.Pkcs.SignedCms' -as [type])) {{
    throw 'Máy này không hỗ trợ xác minh chữ ký CMS của bản cập nhật.'
  }}
}}

function Get-Sha256([string]$path) {{
  # Không dùng cmdlet hash vì nó phụ thuộc module autoload/PSModulePath.
  # API .NET bên dưới có sẵn cả trên Windows PowerShell 5.1 và PowerShell 7.
  $stream = [System.IO.File]::OpenRead($path)
  $sha256 = [System.Security.Cryptography.SHA256]::Create()
  try {{
    return (
      [System.BitConverter]::ToString($sha256.ComputeHash($stream))
    ).Replace('-', '')
  }} finally {{
    $sha256.Dispose()
    $stream.Dispose()
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
    $remainingProcess = Get-Process -Id {pid} -ErrorAction SilentlyContinue
    if ($remainingProcess) {{
      # pywebview/WebView2 đôi khi đã đóng toàn bộ cửa sổ nhưng process cha còn
      # kẹt ở message loop. Chỉ force-stop đúng PID nếu executable vẫn là chính
      # file đang cập nhật; không bao giờ kill theo tên WFX-Panel.
      try {{
        $remainingPath = [System.IO.Path]::GetFullPath($remainingProcess.Path)
      }} catch {{
        throw 'Không xác minh được process ứng dụng đang cập nhật; chưa thay đổi file cài đặt.'
      }}
      if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals(
        $remainingPath,
        [System.IO.Path]::GetFullPath($targetExe)
      )) {{
        throw 'PID ứng dụng đã được process khác sử dụng; chưa thay đổi file cài đặt.'
      }}
      Update-UI "Ứng dụng đóng chậm; đang hoàn tất việc đóng an toàn..." 7
      try {{
        Stop-Process -Id {pid} -Force -ErrorAction Stop
      }} catch {{
        # Process có thể vừa tự đóng giữa lúc xác minh Path và Stop-Process.
        if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{
          throw
        }}
      }}
      $forceDeadline = (Get-Date).AddSeconds(5)
      while (
        (Get-Process -Id {pid} -ErrorAction SilentlyContinue) -and
        (Get-Date) -lt $forceDeadline
      ) {{
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
      }}
    }}
    if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{
      throw 'Không thể đóng ứng dụng chính; chưa thay đổi file cài đặt.'
    }}
    Start-Sleep -Milliseconds 300

    $workItem = Get-Item -LiteralPath $workDir -Force
    if (
      ($workItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
    ) {{
      throw 'Thư mục tạm updater không an toàn.'
    }}
    Update-UI "Đang tải gói cập nhật WFX Smart v$version..."
    Download-WithUi $packageUrl $zipPath
    Download-WithUi $checksumUrl $checksumPath
    Download-WithUi $signatureUrl $signaturePath

    Update-UI "Đang xác minh chữ ký nhà phát hành..." 45
    Import-CmsAssembly
    $signedContent = [System.Security.Cryptography.Pkcs.ContentInfo]::new(
      [System.IO.File]::ReadAllBytes($checksumPath)
    )
    $signedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new(
      $signedContent,
      $true
    )
    $signedCms.Decode([System.IO.File]::ReadAllBytes($signaturePath))
    # Certificate riêng được xác thực bằng chữ ký toán học + thumbprint ghim
    # trong app. Không dựa vào CA store của máy người dùng.
    $signedCms.CheckSignature($true)
    if ($signedCms.SignerInfos.Count -ne 1) {{
      throw 'Chữ ký checksum không có đúng một nhà phát hành.'
    }}
    $signer = $signedCms.SignerInfos[0].Certificate
    $actualSigner = ($signer.Thumbprint -replace '[^A-Fa-f0-9]', '').ToUpperInvariant()
    if ($actualSigner -ne $expectedSigner) {{
      throw 'Certificate ký bản cập nhật không đúng nhà phát hành WFX Smart.'
    }}

    Update-UI "Đang kiểm tra mã checksum SHA-256..." 55
    $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\\s+')[0]
    if ($expectedHash -notmatch '^[A-Fa-f0-9]{{64}}$') {{
      throw 'Tệp checksum SHA-256 không hợp lệ.'
    }}
    $actualHash = Get-Sha256 $zipPath
    if ($actualHash.ToLowerInvariant() -ne $expectedHash.ToLowerInvariant()) {{
      throw 'Mã SHA-256 của gói tải về không trùng khớp.'
    }}

    Update-UI "Đang giải nén gói cập nhật..." 70
    # Destination phải thực sự rỗng. Không tạo sẵn rồi yêu cầu Expand-Archive
    # ghi đè vì một số bản Windows PowerShell hiển thị lỗi "file đã tồn tại"
    # dù đây là lần tải đầu của user.
    Safe-Remove $expandedDir
    Expand-Archive -LiteralPath $zipPath -DestinationPath $expandedDir -Force
    $newExecutables = @(
      Get-ChildItem -LiteralPath $expandedDir -Filter 'WFX-Panel.exe' -Recurse
    )
    if ($newExecutables.Count -ne 1) {{
      throw 'Gói cập nhật phải có đúng một WFX-Panel.exe.'
    }}
    $newExe = $newExecutables[0]
    $newRoot = $newExe.Directory.FullName
    if (-not (Test-Path -LiteralPath (Join-Path $newRoot '_internal') -PathType Container)) {{
      throw 'Gói cập nhật thiếu thư mục _internal.'
    }}
    Update-UI "Đang sao lưu phiên bản hiện tại..." 78
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    foreach ($name in $ownedItems) {{
      $currentItem = Join-Path $installDir $name
      if (-not (Test-Path -LiteralPath $currentItem)) {{
        throw "Bản cài đặt hiện tại thiếu thành phần bắt buộc: $name"
      }}
      Copy-Item -LiteralPath $currentItem -Destination $backupDir -Recurse -Force
    }}
    foreach ($name in $ownedItems) {{
      if (-not (Test-Path -LiteralPath (Join-Path $backupDir $name))) {{
        throw "Sao lưu chưa đầy đủ; chưa thay đổi bản cài đặt: $name"
      }}
    }}

    Update-UI "Đang cài đặt phiên bản mới..." 88
    $installStarted = $true
    foreach ($name in $ownedItems) {{
      $sourceItem = Join-Path $newRoot $name
      $targetItem = Join-Path $installDir $name
      if (-not (Test-Path -LiteralPath $sourceItem)) {{
        throw "Gói cập nhật thiếu thành phần bắt buộc: $name"
      }}
      Safe-Remove $targetItem
      Copy-Item -LiteralPath $sourceItem -Destination $targetItem -Recurse -Force
    }}

    if (
      -not (Test-Path -LiteralPath $targetExe -PathType Leaf) -or
      -not (Test-Path -LiteralPath (Join-Path $installDir '_internal') -PathType Container)
    ) {{
      throw 'Ứng dụng sau cập nhật thiếu thành phần bắt buộc.'
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
    $technicalDetail = $_ | Out-String
    $technicalDetail | Add-Content -LiteralPath $updateLog
    $script:updateErrorReport = @"
WFX Smart updater v$version
Lỗi: $err

$technicalDetail
"@.Trim()
    $recoveryMessage = 'Bản hiện tại chưa bị thay đổi.'
    if ($installStarted) {{
      $recoveryMessage = 'Đang khôi phục phiên bản cũ...'
    }}
    Update-UI "Cập nhật thất bại: $err`n$recoveryMessage" 50 'error'
    try {{
      if ($installStarted) {{
        if (-not (Test-Path -LiteralPath $backupDir -PathType Container)) {{
          throw 'Không tìm thấy bản sao lưu để rollback.'
        }}
        foreach ($name in $ownedItems) {{
          $targetItem = Join-Path $installDir $name
          $backupItem = Join-Path $backupDir $name
          if (-not (Test-Path -LiteralPath $backupItem)) {{
            throw "Bản sao lưu thiếu thành phần: $name"
          }}
          Safe-Remove $targetItem
          Copy-Item -LiteralPath $backupItem -Destination $targetItem -Recurse -Force
        }}
        Write-UpdateResult $false 'UPDATE_ROLLED_BACK' 'Cập nhật thất bại. Đã khôi phục phiên bản trước.'
      }} else {{
        Write-UpdateResult $false 'UPDATE_FAILED' 'Cập nhật thất bại trước khi thay đổi phiên bản hiện tại.'
      }}
    }} catch {{
      $_ | Out-String | Add-Content -LiteralPath $updateLog
      Write-UpdateResult $false 'UPDATE_ROLLBACK_FAILED' 'Không thể hoàn tất cập nhật. Vui lòng tải lại ứng dụng.'
    }}

    $finalMessage = if ($installStarted) {{
      'Đã thử khôi phục phiên bản trước. Vui lòng kiểm tra lại ứng dụng.'
    }} else {{
      'Bản hiện tại chưa bị thay đổi. Vui lòng thử lại.'
    }}
    Update-UI "Lỗi: $err`n$finalMessage" 0 'error'
    if (Test-Path -LiteralPath $targetExe) {{
      if ($exeArgs.Count -gt 0) {{
        Start-Process -FilePath $targetExe -ArgumentList $exeArgs -WorkingDirectory $installDir
      }} else {{
        Start-Process -FilePath $targetExe -WorkingDirectory $installDir
      }}
    }}
    $btnClose.Visible = $true
    $btnCopyError.Text = "Sao chép lỗi"
    $btnCopyError.Visible = $true
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
    try:
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
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return helper
