from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "WFX-Smart.iss"
BUILD_SCRIPT = ROOT / "build-installer.ps1"


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
    assert 'Name: "desktopicon"' in source
    assert "Flags: unchecked" not in source
    assert 'Name: "{group}\\WFX Smart"' in source
    assert 'Name: "{autodesktop}\\WFX Smart"' in source
    assert 'Filename: "{app}\\{#MyAppExeName}"' in source
    assert "postinstall" in source


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


def test_spec_dong_goi_noi_dung_huong_dan():
    root = Path(__file__).resolve().parent.parent
    spec = (root / "wfx_panel" / "wfx-panel.spec").read_text(encoding="utf-8")

    assert '("manual", "wfx_panel/manual")' in spec
