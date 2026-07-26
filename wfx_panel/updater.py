"""Updater Git có khóa commit, stable channel và rollback.

Không dùng GitHub Release và tuyệt đối không push. App fetch remote, chốt SHA
được phép cài, rồi helper độc lập chờ app thoát, fast-forward/build/restart.
Settings nằm ở %LOCALAPPDATA%/WFX-Panel nên không bị thay bởi checkout/build.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REMOTE = "origin"
STABLE_BRANCH = os.getenv("WFX_UPDATE_STABLE_BRANCH", "main")
GIT_TIMEOUT_SECONDS = 60


def _git(root: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=(
            subprocess.CREATE_NO_WINDOW
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        ),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise RuntimeError(detail[0] if detail else "Lệnh Git thất bại.")
    return completed.stdout.strip()


def _git_optional(root: Path, *args: str) -> str:
    try:
        return _git(root, *args)
    except RuntimeError:
        return ""


def find_repo_root(start: Path | None = None) -> Path | None:
    candidates = []
    if start is not None:
        candidates.append(Path(start).resolve())
    candidates.extend(
        [
            Path.cwd().resolve(),
            Path(sys.executable).resolve().parent,
            Path(__file__).resolve().parent,
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        for folder in (candidate, *candidate.parents):
            if folder in seen:
                continue
            seen.add(folder)
            if (folder / ".git").exists():
                return folder
    return None


def _target_branch(channel: str, current_branch: str) -> str:
    return current_branch if channel == "current" else STABLE_BRANCH


def check_for_updates(
    root: Path | None = None,
    *,
    channel: str = "stable",
) -> dict[str, Any]:
    root = find_repo_root(root)
    channel = "current" if channel == "current" else "stable"
    if root is None or shutil.which("git") is None:
        return {
            "ok": False,
            "code": "GIT_NOT_AVAILABLE",
            "message": "Không tìm thấy Git repository để cập nhật.",
            "can_update": False,
            "channel": channel,
        }
    try:
        current_branch = _git(root, "branch", "--show-current")
        if not current_branch:
            return {
                "ok": False,
                "code": "GIT_DETACHED_HEAD",
                "message": "Repository đang ở detached HEAD; không thể tự cập nhật.",
                "can_update": False,
                "channel": channel,
            }
        target_branch = _target_branch(channel, current_branch)
        dirty = bool(_git(root, "status", "--porcelain"))
        previous_sha = _git(root, "rev-parse", "HEAD")
        _git(root, "fetch", "--quiet", REMOTE, target_branch)
        remote_ref = f"refs/remotes/{REMOTE}/{target_branch}"
        expected_sha = _git(root, "rev-parse", remote_ref)
        _git(root, "cat-file", "-e", f"{expected_sha}^{{commit}}")

        require_signed = os.getenv("WFX_REQUIRE_SIGNED_UPDATES") == "1"
        signature_verified = False
        if require_signed:
            _git(root, "verify-commit", expected_sha)
            signature_verified = True

        configured_remote = os.getenv("WFX_UPDATE_REMOTE_URL", "").strip()
        remote_url = _git(root, "remote", "get-url", REMOTE)
        if configured_remote and remote_url.casefold() != configured_remote.casefold():
            return {
                "ok": False,
                "code": "UPDATE_REMOTE_MISMATCH",
                "message": "Remote Git không khớp nguồn cập nhật đã cấu hình.",
                "can_update": False,
                "channel": channel,
            }

        local_target_sha = _git_optional(
            root, "rev-parse", f"refs/heads/{target_branch}"
        )
        already_target = (
            current_branch == target_branch and previous_sha == expected_sha
        )
        behind = 0
        if local_target_sha:
            behind = int(
                _git(
                    root,
                    "rev-list",
                    "--count",
                    f"{local_target_sha}..{expected_sha}",
                )
                or 0
            )
        elif not already_target:
            behind = 1

        common = {
            "channel": channel,
            "branch": target_branch,
            "target_branch": target_branch,
            "previous_branch": current_branch,
            "previous_sha": previous_sha,
            "expected_sha": expected_sha,
            "version": expected_sha[:10],
            "signature_verified": signature_verified,
            "remote_url": remote_url,
            "dirty": dirty,
            "repo_root": str(root),
            "behind": behind,
        }
        if already_target:
            return {
                **common,
                "ok": True,
                "code": "UP_TO_DATE",
                "message": (
                    f"Đang dùng bản Stable mới nhất ({expected_sha[:10]})."
                    if channel == "stable"
                    else f"Nhánh hiện tại đã mới nhất ({expected_sha[:10]})."
                ),
                "can_update": False,
            }
        if dirty:
            return {
                **common,
                "ok": False,
                "code": "WORKTREE_DIRTY",
                "message": (
                    "Có bản cập nhật nhưng repository đang có thay đổi chưa "
                    "commit; app sẽ không ghi đè."
                ),
                "can_update": False,
            }
        return {
            **common,
            "ok": True,
            "code": "UPDATE_AVAILABLE",
            "message": (
                f"Có bản Stable mới {expected_sha[:10]}."
                if channel == "stable"
                else f"Có bản mới {expected_sha[:10]} trên {target_branch}."
            ),
            "can_update": True,
        }
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        return {
            "ok": False,
            "code": "GIT_CHECK_FAILED",
            "message": f"Không kiểm tra được bản mới: {error}",
            "can_update": False,
            "channel": channel,
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
    """Tạo helper cập nhật; caller thoát app sau khi helper khởi chạy."""
    if not state.get("can_update"):
        raise ValueError("Không có bản cập nhật hợp lệ để cài.")

    root = Path(str(state["repo_root"])).resolve()
    if not (root / ".git").exists():
        raise ValueError("Repository cập nhật không hợp lệ.")
    target_branch = str(state["target_branch"])
    previous_branch = str(state["previous_branch"])
    previous_sha = str(state["previous_sha"])
    expected_sha = str(state["expected_sha"])
    for sha in (previous_sha, expected_sha):
        if len(sha) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
            raise ValueError("Commit hash cập nhật không hợp lệ.")

    build_script = root / "build-panel.ps1"
    target_exe = (
        Path(executable).resolve()
        if executable is not None
        else root / "dist" / "WFX-Panel" / "WFX-Panel.exe"
    )
    if not build_script.is_file():
        raise FileNotFoundError("Không tìm thấy build-panel.ps1.")

    pid = int(current_pid or os.getpid())
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "update.log"
    result_path = data_dir / "update-result.json"
    helper = Path(tempfile.gettempdir()) / f"wfx-panel-update-{pid}.ps1"
    content = f"""$ErrorActionPreference = 'Stop'
$updateLog = {_ps_quote(log_path)}
$resultPath = {_ps_quote(result_path)}
$root = {_ps_quote(root)}
$targetBranch = {_ps_quote(target_branch)}
$previousBranch = {_ps_quote(previous_branch)}
$previousSha = {_ps_quote(previous_sha)}
$expectedSha = {_ps_quote(expected_sha)}
$targetExe = {_ps_quote(target_exe)}
$buildScript = {_ps_quote(build_script)}
function Write-UpdateResult([bool]$ok, [string]$code, [string]$message) {{
  @{{ok=$ok; code=$code; message=$message; version=$expectedSha.Substring(0,10)}} |
    ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}}
try {{
  Wait-Process -Id {pid} -ErrorAction SilentlyContinue
  Set-Location -LiteralPath $root
  $currentBranch = (& git branch --show-current).Trim()
  $currentSha = (& git rev-parse HEAD).Trim()
  if ($currentBranch -ne $previousBranch -or $currentSha -ne $previousSha) {{
    throw 'Repository changed after update approval.'
  }}
  if ((& git status --porcelain)) {{
    throw 'Working tree is no longer clean.'
  }}
  & git fetch --quiet {REMOTE} $targetBranch *>> $updateLog
  if ($LASTEXITCODE -ne 0) {{ throw 'Git fetch failed.' }}
  $actualSha = (& git rev-parse "refs/remotes/{REMOTE}/$targetBranch").Trim()
  if ($LASTEXITCODE -ne 0) {{ throw 'Cannot resolve remote commit.' }}
  if ($actualSha -ne $expectedSha) {{
    throw 'Remote commit changed; update cancelled. Check again in the app.'
  }}
  & git cat-file -e "$expectedSha^{{commit}}"
  if ($LASTEXITCODE -ne 0) {{ throw 'Approved commit object is missing.' }}
  & git show-ref --verify --quiet "refs/heads/$targetBranch"
  if ($LASTEXITCODE -eq 0) {{
    & git switch $targetBranch *>> $updateLog
    if ($LASTEXITCODE -ne 0) {{ throw 'Cannot switch update branch.' }}
  }} else {{
    & git switch -c $targetBranch --track "{REMOTE}/$targetBranch" *>> $updateLog
    if ($LASTEXITCODE -ne 0) {{ throw 'Cannot create update branch.' }}
  }}
  & git pull --ff-only {REMOTE} $targetBranch *>> $updateLog
  if ($LASTEXITCODE -ne 0) {{ throw 'Fast-forward pull failed.' }}
  if ((& git rev-parse HEAD).Trim() -ne $expectedSha) {{
    throw 'Installed commit does not match approved hash.'
  }}
  & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript *>> $updateLog
  if ($LASTEXITCODE -ne 0) {{ throw 'New version build failed.' }}
  if (-not (Test-Path -LiteralPath $targetExe)) {{
    throw 'Build finished without WFX-Panel.exe.'
  }}
  Write-UpdateResult $true 'UPDATE_INSTALLED' "Đã cập nhật lên $($expectedSha.Substring(0,10)). Thiết lập cũ được giữ nguyên."
  Start-Process -FilePath $targetExe
}} catch {{
  $_ | Out-String | Add-Content -LiteralPath $updateLog
  try {{
    Set-Location -LiteralPath $root
    & git switch $previousBranch *>> $updateLog
    if ($LASTEXITCODE -ne 0) {{ throw 'Cannot restore previous branch.' }}
    & git reset --hard $previousSha *>> $updateLog
    if ($LASTEXITCODE -ne 0) {{ throw 'Cannot restore previous commit.' }}
    & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript *>> $updateLog
    if ($LASTEXITCODE -ne 0) {{ throw 'Previous version rebuild failed.' }}
    Write-UpdateResult $false 'UPDATE_ROLLED_BACK' 'Cập nhật lỗi; app đã rollback về bản trước. Xem update.log để biết chi tiết.'
  }} catch {{
    $_ | Out-String | Add-Content -LiteralPath $updateLog
    Write-UpdateResult $false 'UPDATE_ROLLBACK_FAILED' 'Cập nhật và rollback đều lỗi. Xem update.log.'
  }}
  if (Test-Path -LiteralPath $targetExe) {{
    Start-Process -FilePath $targetExe
  }}
}} finally {{
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
