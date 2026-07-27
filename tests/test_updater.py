import os
import subprocess

import pytest

from wfx_panel import updater


def release_payload(version: str = "1.1.0") -> dict:
    package = f"WFX-Smart-v{version}-win64.zip"
    base = f"https://github.com/sieuxuan/WFX-APP/releases/download/v{version}"
    return {
        "id": 110,
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/sieuxuan/WFX-APP/releases/tag/v{version}",
        "assets": [
            {
                "name": package,
                "browser_download_url": f"{base}/{package}",
            },
            {
                "name": package + ".sha256",
                "browser_download_url": f"{base}/{package}.sha256",
            },
            {
                "name": package + ".sha256.p7s",
                "browser_download_url": f"{base}/{package}.sha256.p7s",
            },
        ],
    }


def update_state(version: str = "1.1.0") -> dict:
    package = f"WFX-Smart-v{version}-win64.zip"
    package_url = (
        f"https://github.com/sieuxuan/WFX-APP/releases/download/v{version}/{package}"
    )
    return {
        "can_update": True,
        "version": version,
        "package_url": package_url,
        "checksum_url": package_url + ".sha256",
        "signature_url": package_url + ".sha256.p7s",
    }


def test_check_for_updates_reports_release_in_plain_language(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload("1.1.0"),
    )

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_AVAILABLE"
    assert result["can_update"] is True
    assert result["version"] == "1.1.0"
    assert result["notice_id"] == "110"
    assert "Phiên bản 1.1.0" in result["message"]
    assert "commit" not in result["message"].lower()
    assert result["package_url"].endswith("WFX-Smart-v1.1.0-win64.zip")
    assert result["checksum_url"].endswith(".zip.sha256")
    assert result["signature_url"].endswith(".zip.sha256.p7s")


def test_current_release_is_up_to_date(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload("1.0.0"),
    )

    result = updater.check_for_updates()

    assert result["code"] == "UP_TO_DATE"
    assert result["can_update"] is False
    assert result["version"] == "1.0.0"
    assert result["message"] == "Bạn đang dùng phiên bản mới nhất."


def test_release_without_checksum_is_not_offered(monkeypatch):
    payload = release_payload("1.1.0")
    payload["assets"] = [
        asset for asset in payload["assets"] if not asset["name"].endswith(".sha256")
    ]
    monkeypatch.setattr(updater, "_load_latest_release", lambda: payload)

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_CHECK_FAILED"
    assert result["can_update"] is False
    assert "tự thử lại" in result["message"]


def test_legacy_package_name_does_not_trigger_the_unsafe_old_update_path(
    monkeypatch,
):
    payload = release_payload("1.1.0")
    for asset in payload["assets"]:
        asset["name"] = asset["name"].replace("WFX-Smart-", "WFX-Panel-")
        asset["browser_download_url"] = asset["browser_download_url"].replace(
            "WFX-Smart-",
            "WFX-Panel-",
        )
    monkeypatch.setattr(updater, "_load_latest_release", lambda: payload)

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_CHECK_FAILED"
    assert result["can_update"] is False


def test_schedule_update_downloads_verifies_and_rolls_back(monkeypatch, tmp_path):
    local_data = tmp_path / "local"
    install_dir = tmp_path / "WFX-Panel"
    install_dir.mkdir()
    executable = install_dir / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    (install_dir / "_internal").mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    real_popen = subprocess.Popen
    launched = []
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda args, **kwargs: launched.append((args, kwargs)),
    )
    state = update_state()

    helper = updater.schedule_update(
        state,
        current_pid=123,
        executable=executable,
    )
    content = helper.read_text(encoding="utf-8-sig")

    assert "DownloadFile" in content
    assert "Get-FileHash" in content
    assert "SignedCms" in content
    assert "$signedCms.CheckSignature($true)" in content
    assert "$signedCms.CheckSignature($false)" not in content
    assert "$expectedSigner" in content
    assert "Expand-Archive" in content
    assert "UPDATE_INSTALLED" in content
    assert "UPDATE_ROLLED_BACK" in content
    assert "Start-Process -FilePath $targetExe" in content
    assert "DownloadFileTaskAsync" in content
    assert "[System.Windows.Forms.Application]::DoEvents()" in content
    assert "$startTimer.Add_Tick" in content
    assert "[System.Threading.Tasks.Task]::Run" not in content
    assert "git " not in content.lower()
    assert "Safe-Remove $installDir" not in content
    assert "$ownedItems = @('WFX-Panel.exe', '_internal')" in content
    assert "$allowedRemovePaths" in content
    assert "ReparsePoint" in content
    assert "Get-AuthenticodeSignature" not in content
    assert "if ($installStarted)" in content
    assert "UPDATE_FAILED" in content
    assert content.count("Safe-Remove $workDir") == 1
    rollback = content.index("if (-not (Test-Path -LiteralPath $backupItem))")
    assert rollback < content.index("Safe-Remove $targetItem", rollback)
    assert helper.parent.name.startswith("wfx-panel-update-123-")
    assert launched
    if os.name == "nt":
        parsed = real_popen(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "$errors=$null; "
                    "[System.Management.Automation.Language.Parser]::"
                    "ParseFile($env:WFX_TEST_HELPER,[ref]$null,"
                    "[ref]$errors)|Out-Null; "
                    "if($errors.Count){$errors|ForEach-Object ToString; exit 1}"
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "WFX_TEST_HELPER": str(helper)},
        )
        stdout, stderr = parsed.communicate(timeout=15)
        assert parsed.returncode == 0, stderr or stdout

        # Chạy chính hàm xóa của helper trong sandbox: đường dẫn ngoài allowlist
        # phải bị chặn, còn đúng file app-owned mới được phép xóa.
        outside = tmp_path / "must-survive.txt"
        outside.write_text("sentinel", encoding="utf-8")
        function_start = content.index("function Safe-Remove")
        function_end = content.index(
            "function Download-WithUi",
            function_start,
        )
        safe_remove_function = content[function_start:function_end]
        harness = tmp_path / "safe-remove-test.ps1"
        harness.write_text(
            "\n".join(
                [
                    "$ErrorActionPreference = 'Stop'",
                    f"$workDir = {updater._ps_quote(helper.parent)}",
                    f"$installDir = {updater._ps_quote(install_dir)}",
                    "$allowedRemovePaths = @(",
                    "  [IO.Path]::GetFullPath($workDir).TrimEnd('\\'),",
                    "  [IO.Path]::GetFullPath((Join-Path $installDir "
                    "'WFX-Panel.exe')).TrimEnd('\\'),",
                    "  [IO.Path]::GetFullPath((Join-Path $installDir "
                    "'_internal')).TrimEnd('\\')",
                    ")",
                    safe_remove_function,
                    "$blocked = $false",
                    "try {",
                    f"  Safe-Remove {updater._ps_quote(outside)}",
                    "} catch { $blocked = $true }",
                    "if (-not $blocked) { exit 2 }",
                    f"if (-not (Test-Path -LiteralPath "
                    f"{updater._ps_quote(outside)})) {{ exit 3 }}",
                    "Safe-Remove (Join-Path $installDir 'WFX-Panel.exe')",
                    "if (Test-Path -LiteralPath (Join-Path $installDir "
                    "'WFX-Panel.exe')) { exit 4 }",
                ]
            ),
            encoding="utf-8-sig",
        )
        isolated = real_popen(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(harness),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = isolated.communicate(timeout=15)
        assert isolated.returncode == 0, stderr or stdout
        assert outside.read_text(encoding="utf-8") == "sentinel"


def test_schedule_update_rejects_non_app_executable(monkeypatch, tmp_path):
    python_exe = tmp_path / "python.exe"
    python_exe.write_bytes(b"python")
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    state = update_state()

    try:
        updater.schedule_update(state, executable=python_exe)
    except ValueError as error:
        assert "WFX-Panel.exe" in str(error)
    else:
        raise AssertionError("Updater must reject python.exe as an install target")


def test_schedule_update_rejects_incomplete_current_install(monkeypatch, tmp_path):
    executable = tmp_path / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)

    with pytest.raises(ValueError, match="_internal"):
        updater.schedule_update(update_state(), executable=executable)


def test_schedule_update_rejects_mismatched_asset_names(monkeypatch, tmp_path):
    executable = tmp_path / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    (tmp_path / "_internal").mkdir()
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    state = update_state()
    state["checksum_url"] = (
        "https://github.com/sieuxuan/WFX-APP/releases/download/v1.1.0/other.zip.sha256"
    )

    with pytest.raises(ValueError, match="không khớp"):
        updater.schedule_update(state, executable=executable)


def test_schedule_update_cleans_private_workdir_if_launch_fails(monkeypatch, tmp_path):
    executable = tmp_path / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    (tmp_path / "_internal").mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)

    def fail_launch(*_args, **_kwargs):
        raise OSError("PowerShell unavailable")

    monkeypatch.setattr(updater.subprocess, "Popen", fail_launch)

    with pytest.raises(OSError, match="PowerShell"):
        updater.schedule_update(update_state(), executable=executable)

    assert not list(tmp_path.glob("wfx-panel-update-*"))


def test_consume_update_result_is_one_shot(tmp_path):
    path = tmp_path / "update-result.json"
    path.write_text(
        '{"ok": true, "code": "UPDATE_INSTALLED"}',
        encoding="utf-8",
    )
    result = updater.consume_update_result(tmp_path)
    assert result["code"] == "UPDATE_INSTALLED"
    assert updater.consume_update_result(tmp_path) is None


def test_version_comparison_accepts_display_and_release_forms():
    assert updater._version_tuple("v1.2.3") == (1, 2, 3)
    assert updater._version_tuple("1.2") == (1, 2, 0)
