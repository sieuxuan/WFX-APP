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
) -> Path:
    """Tạo helper độc lập để thay bản app sau khi process hiện tại thoát."""
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
    content = f"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$updateLog = {_ps_quote(log_path)}
$resultPath = {_ps_quote(result_path)}
$packageUrl = {_ps_quote(package_url)}
$checksumUrl = {_ps_quote(checksum_url)}
$version = {_ps_quote(version)}
$targetExe = {_ps_quote(target_exe)}
$installDir = {_ps_quote(install_dir)}
$workDir = Join-Path $env:TEMP 'wfx-panel-update-{pid}'
$zipPath = Join-Path $workDir 'WFX-Panel.zip'
$checksumPath = Join-Path $workDir 'WFX-Panel.zip.sha256'
$expandedDir = Join-Path $workDir 'expanded'
$backupDir = "$installDir.backup-{pid}"
function Write-UpdateResult([bool]$ok, [string]$code, [string]$message) {{
  @{{ok=$ok; code=$code; message=$message; version=$version}} |
    ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}}
try {{
  Wait-Process -Id {pid} -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path $expandedDir -Force | Out-Null
  Invoke-WebRequest -Uri $packageUrl -OutFile $zipPath -UseBasicParsing
  Invoke-WebRequest -Uri $checksumUrl -OutFile $checksumPath -UseBasicParsing
  $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\\s+')[0]
  if ($expectedHash -notmatch '^[A-Fa-f0-9]{{64}}$') {{
    throw 'Invalid checksum file.'
  }}
  $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
  if ($actualHash -ne $expectedHash) {{
    throw 'Downloaded package checksum mismatch.'
  }}
  Expand-Archive -LiteralPath $zipPath -DestinationPath $expandedDir -Force
  $newExe = Get-ChildItem -LiteralPath $expandedDir -Filter 'WFX-Panel.exe' -Recurse |
    Select-Object -First 1
  if (-not $newExe) {{ throw 'WFX-Panel.exe is missing from the update package.' }}
  $newRoot = $newExe.Directory.FullName
  Copy-Item -LiteralPath $installDir -Destination $backupDir -Recurse -Force
  Remove-Item -LiteralPath $installDir -Recurse -Force
  New-Item -ItemType Directory -Path $installDir -Force | Out-Null
  Copy-Item -Path (Join-Path $newRoot '*') -Destination $installDir -Recurse -Force
  if (-not (Test-Path -LiteralPath $targetExe)) {{
    throw 'Updated application could not be installed.'
  }}
  Write-UpdateResult $true 'UPDATE_INSTALLED' "Đã cập nhật lên phiên bản $version. Cài đặt cũ vẫn được giữ nguyên."
  Start-Process -FilePath $targetExe
  Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
  $_ | Out-String | Add-Content -LiteralPath $updateLog
  try {{
    if (Test-Path -LiteralPath $backupDir) {{
      Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
      Move-Item -LiteralPath $backupDir -Destination $installDir -Force
    }}
    Write-UpdateResult $false 'UPDATE_ROLLED_BACK' 'Cập nhật chưa thành công. Ứng dụng đã trở lại phiên bản trước và cài đặt của bạn vẫn được giữ nguyên.'
  }} catch {{
    $_ | Out-String | Add-Content -LiteralPath $updateLog
    Write-UpdateResult $false 'UPDATE_ROLLBACK_FAILED' 'Không thể hoàn tất cập nhật. Vui lòng tải lại WFX Smart từ trang phát hành.'
  }}
  if (Test-Path -LiteralPath $targetExe) {{
    Start-Process -FilePath $targetExe
  }}
}} finally {{
  Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}}
"""
    helper.write_text(content, encoding="utf-8-sig")
    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
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
