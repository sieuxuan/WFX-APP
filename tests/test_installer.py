from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "WFX-Smart.iss"
BUILD_SCRIPT = ROOT / "build-installer.ps1"
PANEL_BUILD_SCRIPT = ROOT / "build-panel.ps1"


def test_installer_is_per_user_and_keeps_user_data_outside_install_tree():
    source = INSTALLER.read_text(encoding="utf-8")

    assert "AppId={{FA15EF75-74AD-463A-AFF0-272145061A2B}" in source
    assert r"DefaultDirName={localappdata}\Programs\WFX Smart" in source
    assert "PrivilegesRequired=lowest" in source
    assert "{localappdata}\\WFX-Panel" not in source
    assert "[UninstallDelete]" not in source


def test_installer_closes_running_app_and_creates_windows_shortcuts():
    source = INSTALLER.read_text(encoding="utf-8")

    assert "CloseApplications=no" in source
    assert "CloseApplicationsFilter=*.exe,*.dll,*.pyd" not in source
    assert "taskkill.exe" not in source
    assert '-Filter "Name=\'\'WFX-Panel.exe\'\'"' in source
    assert "$process.ExecutablePath" in source
    assert "[System.StringComparer]::OrdinalIgnoreCase.Equals" in source
    assert "Stop-Process -Id $process.ProcessId -Force" in source
    assert "ewWaitUntilTerminated" in source
    assert "exit 1" in source
    assert "RestartApplications=no" in source
    assert "Flags: unchecked" not in source
    # Hai shortcut luôn được tạo, không qua trang tác vụ để người dùng tick.
    assert 'Name: "{group}\\WFX Smart"' in source
    assert 'Name: "{autodesktop}\\WFX Smart"' in source
    assert "[Tasks]" not in source
    assert "Tasks: desktopicon" not in source
    assert 'Filename: "{app}\\{#MyAppExeName}"' in source


def test_installer_runs_without_any_next_click():
    """Bộ cài phải chạy một chạm: bấm đúp là cài xong và tự mở ứng dụng.

    Mỗi trang wizard dưới đây là một lần người dùng phải bấm Next. Bản cập
    nhật trong app đã im lặng nhờ /VERYSILENT, nhưng người tải bộ cài từ
    GitHub thì đi qua wizard đầy đủ nếu không tắt các trang này.
    """
    source = INSTALLER.read_text(encoding="utf-8")

    for page in (
        "DisableWelcomePage=yes",
        "DisableDirPage=yes",
        "DisableProgramGroupPage=yes",
        "DisableReadyPage=yes",
        "DisableFinishedPage=yes",
    ):
        assert page in source, page
    # Trang Finished đã tắt nên cờ postinstall không còn ô tick để kích hoạt;
    # entry phải chạy thẳng trong bước kết thúc cài đặt. Chỉ soi đúng dòng
    # [Run] chứ không quét cả file, vì phần chú thích có nhắc tên cờ này.
    run_line = next(
        line for line in source.splitlines()
        if line.startswith("Filename:") and "Flags:" in line
    )
    assert "postinstall" not in run_line
    # Nhưng vẫn phải bỏ qua khi chạy silent, nếu không bản cập nhật trong app
    # sẽ mở ứng dụng hai lần (updater tự Start-Process sau khi cài).
    assert "skipifsilent" in run_line


def test_installer_contains_complete_pyinstaller_onedir_build():
    source = INSTALLER.read_text(encoding="utf-8")
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'Source: "{#SourceDir}\\*"' in source
    assert "recursesubdirs createallsubdirs" in source
    assert 'Join-Path $SourceDir "WFX-Panel.exe"' in build
    assert 'Join-Path $SourceDir "_internal"' in build
    assert "from wfx_panel.version import APP_VERSION" in build
    assert "JRSoftware.InnoSetup" in build
    assert 'Join-Path $env:LOCALAPPDATA "Programs\\Inno Setup 6\\ISCC.exe"' in build


def test_panel_build_uses_isolated_python_312_environment():
    source = PANEL_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'Join-Path $projectRoot ".build-venv"' in source
    assert 'uv.Source venv --python 3.12' in source
    assert 'uv.Source pip install' in source
    assert '$pythonVersion -ne "3.12"' in source
    assert '& $BuildPython -m PyInstaller' in source
    assert '--workpath (Join-Path $projectRoot "build")' in source
    assert '--distpath (Join-Path $projectRoot "dist")' in source
    assert 'Name = \'WFX-Panel.exe\'' in source
    assert 'Join-Path $runtimeDir "python312.dll"' in source
    assert '$buildSizeMb -gt 180' in source


def test_panel_spec_resolves_project_from_spec_location():
    source = (ROOT / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")

    assert "project = Path(SPECPATH).parent" in source
    assert "project = Path.cwd()" not in source


def test_spec_dong_goi_noi_dung_huong_dan():
    root = Path(__file__).resolve().parent.parent
    spec = (root / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")

    assert '("manual", "wfx_panel/manual")' in spec
