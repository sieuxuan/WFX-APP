import os
import subprocess
import sys

import pytest

from wfx_panel import updater
from wfx_panel.version import APP_VERSION


def _next_version() -> str:
    """Một phiên bản chắc chắn mới hơn bản đang chạy.

    Trước đây các test ghi cứng "1.1.0" làm bản mới. Tới đúng lần phát hành
    1.1.0 thì `schedule_update` từ chối vì không mới hơn bản đang chạy, và
    mười test đỏ vì lý do không liên quan gì tới thứ chúng kiểm.
    """
    major, minor, patch = (int(part) for part in APP_VERSION.split("."))
    return f"{major}.{minor}.{patch + 1}"


NEXT_VERSION = _next_version()


def release_payload(version: str = NEXT_VERSION) -> dict:
    package = f"WFX-Smart-v{version}-win64.zip"
    setup = f"WFX-Smart-Setup-v{version}.exe"
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
            {
                "name": setup,
                "browser_download_url": f"{base}/{setup}",
            },
            {
                "name": setup + ".sha256",
                "browser_download_url": f"{base}/{setup}.sha256",
            },
            {
                "name": setup + ".sha256.p7s",
                "browser_download_url": f"{base}/{setup}.sha256.p7s",
            },
        ],
    }


def update_state(
    version: str = NEXT_VERSION,
    update_mode: str = updater.UPDATE_MODE_PORTABLE,
) -> dict:
    package = updater._asset_name(version, update_mode)
    package_url = (
        f"https://github.com/sieuxuan/WFX-APP/releases/download/v{version}/{package}"
    )
    return {
        "can_update": True,
        "version": version,
        "package_url": package_url,
        "checksum_url": package_url + ".sha256",
        "signature_url": package_url + ".sha256.p7s",
        "update_mode": update_mode,
    }


def test_check_for_updates_reports_release_in_plain_language(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload(NEXT_VERSION),
    )

    result = updater.check_for_updates()

    assert result["code"] == "UPDATE_AVAILABLE"
    assert result["can_update"] is True
    assert result["version"] == NEXT_VERSION
    assert result["notice_id"] == "110"
    assert f"Phiên bản {NEXT_VERSION}" in result["message"]
    assert "commit" not in result["message"].lower()
    assert result["package_url"].endswith(
        f"WFX-Smart-v{NEXT_VERSION}-win64.zip"
    )
    assert result["checksum_url"].endswith(".zip.sha256")
    assert result["signature_url"].endswith(".zip.sha256.p7s")
    assert result["update_mode"] == updater.UPDATE_MODE_PORTABLE


def test_setup_install_checks_the_installer_assets(monkeypatch):
    monkeypatch.setattr(
        updater,
        "detect_update_mode",
        lambda _executable=None: updater.UPDATE_MODE_INSTALLER,
    )
    monkeypatch.setattr(
        updater,
        "_load_latest_release",
        lambda: release_payload(NEXT_VERSION),
    )

    result = updater.check_for_updates()

    assert result["can_update"] is True
    assert result["update_mode"] == updater.UPDATE_MODE_INSTALLER
    assert result["package_url"].endswith(
        f"WFX-Smart-Setup-v{NEXT_VERSION}.exe"
    )
    assert result["checksum_url"].endswith(".exe.sha256")
    assert result["signature_url"].endswith(".exe.sha256.p7s")


def test_update_mode_matches_setup_registry_location(monkeypatch, tmp_path):
    install_dir = tmp_path / "Custom WFX"
    install_dir.mkdir()
    executable = install_dir / "WFX-Panel.exe"
    executable.write_bytes(b"app")
    monkeypatch.setattr(updater, "_inno_install_locations", lambda: [install_dir])

    assert (
        updater.detect_update_mode(executable)
        == updater.UPDATE_MODE_INSTALLER
    )


def test_update_mode_keeps_unregistered_exe_portable(monkeypatch, tmp_path):
    executable = tmp_path / "WFX-Panel.exe"
    executable.write_bytes(b"app")
    monkeypatch.setattr(updater, "_inno_install_locations", lambda: [])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert updater.detect_update_mode(executable) == updater.UPDATE_MODE_PORTABLE


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
    payload = release_payload(NEXT_VERSION)
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
    payload = release_payload(NEXT_VERSION)
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
    assert "function Get-Sha256" in content
    assert "Get-FileHash" not in content
    assert "[System.Security.Cryptography.SHA256]::Create()" in content
    assert "SignedCms" in content
    assert "function Import-CmsAssembly" in content
    assert "Add-Type -AssemblyName System.Security -ErrorAction Stop" in content
    assert "Import-CmsAssembly" in content
    assert "$signedCms.CheckSignature($true)" in content
    assert "$signedCms.CheckSignature($false)" not in content
    assert "$expectedSigner" in content
    assert "Expand-Archive" in content
    assert "Safe-Remove $expandedDir" in content
    assert content.index("Safe-Remove $expandedDir") < content.index(
        "Expand-Archive -LiteralPath"
    )
    assert "UPDATE_INSTALLED" in content
    assert "UPDATE_ROLLED_BACK" in content
    assert "Start-Process -FilePath $targetExe" in content
    assert "DownloadFileTaskAsync" in content
    assert "[System.Windows.Forms.Application]::DoEvents()" in content
    assert "$startTimer.Add_Tick" in content
    assert '$btnCopyError.Text = "Sao chép lỗi"' in content
    assert "[System.Windows.Forms.Clipboard]::SetText" in content
    assert "$script:updateErrorReport" in content
    assert '$btnCopyError.Text = "Đã sao chép"' in content
    assert "[System.Threading.Tasks.Task]::Run" not in content
    assert "git " not in content.lower()
    assert "Safe-Remove $installDir" not in content
    assert "Stop-Process -Id 123 -Force -ErrorAction Stop" in content
    assert "$remainingProcess.Path" in content
    assert "[System.StringComparer]::OrdinalIgnoreCase.Equals" in content
    assert "Get-Process -Name" not in content
    assert content.index("Stop-Process -Id 123 -Force") < content.index(
        'Update-UI "Đang tải gói cập nhật'
    )
    assert "$ownedItems = @('WFX-Panel.exe', '_internal')" in content
    assert "$allowedRemovePaths" in content
    assert "[System.IO.Path]::GetFullPath(\n    $backupDir" in content
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

        # Chạy đúng loader CMS bằng cả Windows PowerShell 5.1 và PowerShell 7.
        # Bản 5.1 không có assembly Pkcs riêng, nên bắt buộc đi qua fallback
        # System.Security nhưng vẫn phải resolve được SignedCms.
        cms_function_start = content.index("function Import-CmsAssembly")
        cms_function_end = content.index(
            "function Perform-Update",
            cms_function_start,
        )
        cms_loader = tmp_path / "cms-loader-test.ps1"
        cms_loader.write_text(
            "\n".join(
                [
                    "$ErrorActionPreference = 'Stop'",
                    content[cms_function_start:cms_function_end],
                    "Import-CmsAssembly",
                    "if (-not ('System.Security.Cryptography.Pkcs.SignedCms' "
                    "-as [type])) { exit 2 }",
                ]
            ),
            encoding="utf-8-sig",
        )
        for shell in ("powershell", "pwsh"):
            compatible = real_popen(
                [
                    shell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(cms_loader),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = compatible.communicate(timeout=15)
            assert compatible.returncode == 0, (
                f"{shell}: {stderr or stdout}"
            )

        # Hash helper không được phụ thuộc PSModulePath/Get-FileHash. Ép trống
        # module path để mô phỏng tiến trình con kế thừa môi trường không chuẩn.
        hash_function_start = content.index("function Get-Sha256")
        hash_function_end = content.index(
            "function Perform-Update",
            hash_function_start,
        )
        hash_fixture = tmp_path / "sha256-fixture.bin"
        hash_fixture.write_bytes(b"WFX Smart updater")
        hash_harness = tmp_path / "sha256-test.ps1"
        hash_harness.write_text(
            "\n".join(
                [
                    "$ErrorActionPreference = 'Stop'",
                    content[hash_function_start:hash_function_end],
                    f"$actual = Get-Sha256 "
                    f"{updater._ps_quote(hash_fixture)}",
                    "if ($actual -ne "
                    "'B16E8417DCFA641C84CECED46422AF17BE2D3472"
                    "9E476AC95077219ABFE33AC8') { exit 2 }",
                ]
            ),
            encoding="utf-8-sig",
        )
        hash_env = {**os.environ, "PSModulePath": ""}
        for shell in ("powershell", "pwsh"):
            hashed = real_popen(
                [
                    shell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(hash_harness),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=hash_env,
            )
            stdout, stderr = hashed.communicate(timeout=15)
            assert hashed.returncode == 0, f"{shell}: {stderr or stdout}"

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


def test_setup_install_schedules_inno_installer_instead_of_zip_replacement(
    monkeypatch,
    tmp_path,
):
    local_data = tmp_path / "local"
    install_dir = tmp_path / "installed" / "WFX Smart"
    install_dir.mkdir(parents=True)
    executable = install_dir / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    (install_dir / "_internal").mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    monkeypatch.setattr(
        updater,
        "detect_update_mode",
        lambda _executable=None: updater.UPDATE_MODE_INSTALLER,
    )
    launched = []
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda args, **kwargs: launched.append((args, kwargs)),
    )

    helper = updater.schedule_update(
        update_state(update_mode=updater.UPDATE_MODE_INSTALLER),
        current_pid=456,
        executable=executable,
    )
    content = helper.read_text(encoding="utf-8-sig")

    assert "$updateMode = 'installer'" in content
    assert f"WFX-Smart-Setup-v{NEXT_VERSION}.exe" in content
    assert "if ($updateMode -eq 'installer')" in content
    assert "'/VERYSILENT'" in content
    assert "'/SUPPRESSMSGBOXES'" in content
    assert "-FilePath $packagePath" in content
    assert "Bộ cài chưa nâng ứng dụng lên đúng phiên bản" in content
    assert launched


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
        "https://github.com/sieuxuan/WFX-APP/releases/download/"
        f"v{NEXT_VERSION}/other.zip.sha256"
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


# --- đọc release từ GitHub ----------------------------------------------


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.payload


def test_the_latest_release_is_read_from_the_github_api(monkeypatch):
    seen = []

    def urlopen(request, timeout=None):
        seen.append(request)
        return _Response(b'{"tag_name": "v1.1.0"}')

    monkeypatch.setattr(updater, "urlopen", urlopen)

    assert updater._load_latest_release()["tag_name"] == "v1.1.0"
    assert seen[0].full_url == updater.LATEST_RELEASE_API
    assert "WFX-Smart/" in seen[0].headers["User-agent"]


def test_a_release_response_that_is_not_an_object_is_refused(monkeypatch):
    monkeypatch.setattr(
        updater, "urlopen", lambda *_a, **_k: _Response(b'["khong phai release"]')
    )

    with pytest.raises(ValueError, match="không hợp lệ"):
        updater._load_latest_release()


@pytest.mark.parametrize("value", ["", "moi nhat", "1", "v1.2.3.4"])
def test_a_version_string_github_did_not_publish_properly_is_refused(value):
    with pytest.raises(ValueError, match="Phiên bản"):
        updater._version_tuple(value)


def test_a_release_without_an_asset_list_is_refused():
    with pytest.raises(ValueError, match="gói cài đặt"):
        updater._release_assets(
            {"tag_name": "v1.1.0", "assets": None},
            updater.UPDATE_MODE_PORTABLE,
        )


def test_an_unknown_update_mode_has_no_asset_name():
    with pytest.raises(ValueError, match="Chế độ cập nhật"):
        updater._asset_name("1.1.0", "khong-co-that")


# --- nhận diện kiểu cài đặt ----------------------------------------------


def test_a_machine_without_the_windows_registry_has_no_setup_locations(
    monkeypatch,
):
    monkeypatch.setattr(updater.os, "name", "posix")

    assert updater._inno_install_locations() == []


def test_a_python_build_without_winreg_has_no_setup_locations(monkeypatch):
    monkeypatch.setattr(updater.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "winreg", None)

    assert updater._inno_install_locations() == []


def test_an_exe_in_the_default_setup_folder_counts_as_a_setup_install(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "local" / "Programs" / "WFX Smart"
    install_dir.mkdir(parents=True)
    executable = install_dir / updater.EXPECTED_EXECUTABLE_NAME
    executable.write_bytes(b"app")
    monkeypatch.setattr(updater, "_inno_install_locations", lambda: [])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert updater.detect_update_mode(executable) == updater.UPDATE_MODE_INSTALLER


# --- kết quả lần cập nhật trước ------------------------------------------


def test_a_damaged_update_result_is_still_cleared(tmp_path):
    path = tmp_path / "update-result.json"
    path.write_text("{khong phai json", encoding="utf-8")

    assert updater.consume_update_result(tmp_path) is None
    assert not path.exists()


def test_an_update_result_that_is_not_an_object_reads_as_nothing(tmp_path):
    (tmp_path / "update-result.json").write_text('["xong"]', encoding="utf-8")

    assert updater.consume_update_result(tmp_path) is None


def test_an_update_result_file_windows_will_not_release_is_not_fatal(
    tmp_path, monkeypatch
):
    path = tmp_path / "update-result.json"
    path.write_text('{"code": "UPDATE_INSTALLED"}', encoding="utf-8")

    def refuse(self, **_kwargs):
        raise PermissionError("file đang bị khóa")

    monkeypatch.setattr(type(path), "unlink", refuse)

    assert updater.consume_update_result(tmp_path)["code"] == "UPDATE_INSTALLED"


def test_no_previous_update_result_reads_as_nothing(tmp_path):
    assert updater.consume_update_result(tmp_path) is None


# --- những gì updater từ chối làm ----------------------------------------


def _installed(tmp_path):
    executable = tmp_path / "WFX-Panel.exe"
    executable.write_bytes(b"old")
    (tmp_path / "_internal").mkdir()
    return executable


def test_an_update_the_user_cannot_take_is_never_scheduled():
    with pytest.raises(ValueError, match="Không có bản cập nhật"):
        updater.schedule_update({"can_update": False})


def test_a_setup_package_is_never_installed_over_a_portable_build(
    monkeypatch, tmp_path
):
    executable = _installed(tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    monkeypatch.setattr(updater, "_inno_install_locations", lambda: [])
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(ValueError, match="không đúng kiểu cài đặt"):
        updater.schedule_update(
            update_state(update_mode=updater.UPDATE_MODE_INSTALLER),
            executable=executable,
        )


def test_the_running_version_is_never_reinstalled(monkeypatch, tmp_path):
    executable = _installed(tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)

    with pytest.raises(ValueError, match="mới hơn bản đang chạy"):
        updater.schedule_update(
            update_state(version=updater.APP_VERSION), executable=executable
        )


def test_an_executable_that_vanished_stops_the_update(monkeypatch, tmp_path):
    executable = _installed(tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)
    executable.unlink()

    with pytest.raises(ValueError, match="Không tìm thấy WFX-Panel.exe"):
        updater.schedule_update(update_state(), executable=executable)


def test_a_build_without_a_signing_identity_never_self_updates(
    monkeypatch, tmp_path
):
    executable = _installed(tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "")

    with pytest.raises(ValueError, match="ký số"):
        updater.schedule_update(update_state(), executable=executable)


def test_an_impossible_process_id_stops_the_update(monkeypatch, tmp_path):
    executable = _installed(tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "A" * 40)

    with pytest.raises(ValueError, match="Process ID"):
        updater.schedule_update(
            update_state(), current_pid=-1, executable=executable
        )
