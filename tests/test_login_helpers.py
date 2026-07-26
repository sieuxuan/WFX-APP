import login
import json


def test_style_status_suffix_includes_both_grid_fields():
    suffix = login._style_status_suffix(
        {
            "season": "FW26",
            "internal_costsheet_status": "Done",
        }
    )
    assert "Season: FW26" in suffix
    assert "CostSheet: Done" in suffix


def test_style_status_suffix_handles_empty_cells():
    suffix = login._style_status_suffix({})
    assert suffix.count("—") == 2


def test_detect_browser_accepts_edge_on_windows_layout(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    edge = local / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"edge")
    monkeypatch.delenv("WFX_CHROME_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "ProgramFiles"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "ProgramFilesX86"))
    monkeypatch.setattr(login.shutil, "which", lambda _name: None)
    found = login.detect_browser()
    assert found is not None
    assert found.name == "Microsoft Edge"
    assert found.path == edge


def test_start_chrome_explains_when_no_compatible_browser(monkeypatch):
    monkeypatch.setattr(login, "_chrome_is_ready", lambda: False)
    monkeypatch.setattr(login, "detect_browser", lambda: None)
    result = login.start_chrome(lambda _message: None)
    assert result["code"] == "BROWSER_NOT_FOUND"
    assert result["browser_available"] is False
    assert "Edge" in result["message"]


def test_automation_browser_pid_reads_cdp_listener(monkeypatch):
    class Completed:
        stdout = (
            "TCP 127.0.0.1:9222 0.0.0.0:0 LISTENING 4567\n"
            "TCP 127.0.0.1:50000 127.0.0.1:9222 ESTABLISHED 9999\n"
        )

    monkeypatch.setattr(login.os, "name", "nt")
    monkeypatch.setattr(
        login.subprocess, "run", lambda *args, **kwargs: Completed()
    )
    assert login.automation_browser_pid() == 4567


def test_automation_profile_disables_password_manager(tmp_path):
    profile = tmp_path / "ChromeProfile"
    preferences = profile / "Default" / "Preferences"
    preferences.parent.mkdir(parents=True)
    preferences.write_text(
        '{"homepage":"https://example.test","profile":{"name":"WFX"}}',
        encoding="utf-8",
    )
    login._disable_password_manager(profile)
    loaded = json.loads(preferences.read_text(encoding="utf-8"))
    assert loaded["homepage"] == "https://example.test"
    assert loaded["profile"]["name"] == "WFX"
    assert loaded["profile"]["password_manager_enabled"] is False
    assert loaded["credentials_enable_service"] is False
    assert loaded["password_manager_leak_detection"] is False


def test_chrome_launch_uses_password_prompt_suppression_flags(
    tmp_path, monkeypatch
):
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"exe")
    calls = iter([False, True])
    command = []

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(login, "_chrome_is_ready", lambda: next(calls))
    monkeypatch.setattr(
        login,
        "detect_browser",
        lambda: login.BrowserExecutable("Google Chrome", executable),
    )
    monkeypatch.setattr(
        login.subprocess,
        "Popen",
        lambda args, **_kwargs: command.extend(args),
    )
    login._start_persistent_chrome(lambda _message: None)
    assert "--disable-save-password-bubble" in command
    assert any(
        arg.startswith("--disable-features=")
        and "PasswordManagerOnboarding" in arg
        for arg in command
    )


def test_division_is_detected_from_company_name_title():
    woven = login._division_for_text(
        "PRO SPORTS (H.K) LTD (PRO SPORTS - WOVEN HANOI)"
    )
    knit = login._division_for_text(
        "PRO SPORTS (H.K) LTD (PRO SPORTS - KNIT HANOI)"
    )
    pssg = login._division_for_text(
        "PRO SPORTS (H.K) LTD (Pro Sports - Singapore)"
    )
    assert woven and woven["current_division"] == "woven"
    assert knit and knit["current_division"] == "knit"
    assert pssg and pssg["current_division"] == "pssg"


def test_unknown_company_name_does_not_fake_a_division():
    assert login._division_for_text("PRO SPORTS (H.K) LTD") is None
