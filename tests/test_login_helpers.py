import json
from types import SimpleNamespace

import login
from wfx_panel.automation import browser, catalog, session


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
    # start_chrome gọi _chrome_is_ready/detect_browser cùng module, nên phải
    # patch tại wfx_panel.automation.browser (không phải shim login).
    monkeypatch.setattr(browser, "_chrome_is_ready", lambda: False)
    monkeypatch.setattr(browser, "detect_browser", lambda: None)
    result = browser.start_chrome(lambda _message: None)
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
    monkeypatch.setattr(browser, "_chrome_is_ready", lambda: next(calls))
    monkeypatch.setattr(
        browser,
        "detect_browser",
        lambda: browser.BrowserExecutable("Google Chrome", executable),
    )
    monkeypatch.setattr(
        browser.subprocess,
        "Popen",
        lambda args, **_kwargs: command.extend(args),
    )
    browser._start_persistent_chrome(lambda _message: None)
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


def test_division_is_detected_from_exact_base_setting_route():
    detected = session._division_for_base_setting_url(
        "https://prosports.worldfashionexchange.com/wfx/"
        "wfx_BaseSetting.aspx?ChangeBaseSetting=1"
        "&MemberCompanyCode=77400&folderID=7740002"
        "&blnShowNewMenu=true"
    )

    assert detected and detected["current_division"] == "knit"


def test_division_route_does_not_accept_partial_folder_id():
    detected = session._division_for_base_setting_url(
        "https://prosports.worldfashionexchange.com/wfx/"
        "wfx_BaseSetting.aspx?ChangeBaseSetting=1"
        "&MemberCompanyCode=77400&folderID=77400020"
    )

    assert detected is None


def test_division_confirmation_timeout_is_bounded_and_retries_early():
    assert session.DIVISION_CONFIRM_TIMEOUT_SECONDS <= 8
    assert (
        0
        < session.DIVISION_RETRY_AFTER_SECONDS
        < session.DIVISION_CONFIRM_TIMEOUT_SECONDS
    )


def test_catalog_destination_uses_existing_article_popup(monkeypatch):
    calls = []

    class PlaywrightRuntime:
        def stop(self):
            calls.append(("stop",))

    class PlaywrightStarter:
        def start(self):
            return PlaywrightRuntime()

    context = object()
    browser_instance = SimpleNamespace(contexts=[context])
    page = object()
    monkeypatch.setattr(catalog, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(catalog, "sync_playwright", PlaywrightStarter)
    monkeypatch.setattr(
        catalog,
        "_connect_to_chrome",
        lambda _playwright: (browser_instance, page),
    )
    monkeypatch.setattr(catalog, "_attach_dialog_handler", lambda *_args: None)
    monkeypatch.setattr(catalog, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(
        catalog,
        "_open_article_destination",
        lambda actual_context, destination, previous, _log, timeout_seconds: (
            calls.append(
                (
                    "destination",
                    actual_context,
                    destination,
                    previous,
                    timeout_seconds,
                )
            )
            or "BOM"
        ),
    )

    result = catalog.open_catalog_destination("ABC123", "bom")

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert calls == [
        ("destination", context, "bom", [], 8),
        ("stop",),
    ]


def test_catalog_search_uses_existing_grid_without_reopening_module(monkeypatch):
    calls = []

    class PlaywrightRuntime:
        def stop(self):
            calls.append(("stop",))

    class PlaywrightStarter:
        def start(self):
            return PlaywrightRuntime()

    page = object()
    grid = object()
    monkeypatch.setattr(catalog, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(catalog, "sync_playwright", PlaywrightStarter)
    monkeypatch.setattr(
        catalog,
        "_connect_to_chrome",
        lambda _playwright: (object(), page),
    )
    monkeypatch.setattr(catalog, "_attach_dialog_handler", lambda *_args: None)
    monkeypatch.setattr(catalog, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(
        catalog,
        "_show_catalog_floating_filter",
        lambda actual_page, _log: (
            calls.append(("existing-grid", actual_page)) or grid
        ),
    )
    monkeypatch.setattr(
        catalog,
        "_filter_grid_and_maybe_open",
        lambda actual_grid, kind, query, _log: (
            calls.append(("filter", actual_grid, kind, query))
            or {
                "ok": True,
                "code": "RESULT_OPENED",
                "article_code": "ABC123",
            }
        ),
    )

    result = catalog.find_in_open_catalog(
        "Apparel",
        "code",
        "ABC123",
    )

    assert result["code"] == "RESULT_OPENED"
    assert calls == [
        ("existing-grid", page),
        ("filter", grid, "code", "ABC123"),
        ("stop",),
    ]


def test_catalog_folder_rejects_non_numeric_node_before_browser_access():
    result = catalog.open_catalog_folder(
        "Apparel",
        "01",
        '1"] unsafe',
    )
    assert result["code"] == "CATALOG_FOLDER_INVALID"


def test_catalog_folder_scan_uses_tree_without_clicking_master(monkeypatch):
    calls = []

    class PlaywrightRuntime:
        def stop(self):
            calls.append(("stop",))

    class PlaywrightStarter:
        def start(self):
            return PlaywrightRuntime()

    page = object()
    frame = object()
    folders = [
        {
            "node_id": "101",
            "path": ["KNIT", "DEV"],
            "path_label": "KNIT / DEV",
            "kind": "group",
        }
    ]
    monkeypatch.setattr(catalog, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(catalog, "sync_playwright", PlaywrightStarter)
    monkeypatch.setattr(
        catalog,
        "_connect_to_chrome",
        lambda _playwright: (object(), page),
    )
    monkeypatch.setattr(catalog, "_attach_dialog_handler", lambda *_args: None)
    monkeypatch.setattr(catalog, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(
        catalog,
        "_open_catalog_tree_on_page",
        lambda actual_page, category, value, _log: (
            calls.append(("tree", actual_page, category, value)) or frame
        ),
    )
    monkeypatch.setattr(
        catalog,
        "_catalog_folder_nodes",
        lambda actual_frame: (
            calls.append(("scan", actual_frame)) or folders
        ),
    )
    monkeypatch.setattr(
        catalog,
        "_click_catalog_master",
        lambda *_args, **_kwargs: calls.append(("master",)),
    )

    result = catalog.scan_catalog_folders("Apparel", "01")

    assert result["code"] == "CATALOG_FOLDERS_SCANNED"
    assert result["folders"] == folders
    assert ("master",) not in calls
    assert calls == [
        ("tree", page, "Apparel", "01"),
        ("scan", frame),
        ("stop",),
    ]
