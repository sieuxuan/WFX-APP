import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import login
from wfx_panel.automation import browser, catalog, modules, session


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


def test_article_file_tabs_match_requested_wfx_positions():
    assert catalog.ARTICLE_FILE_TAB_INDEXES == (5, 6, 8, 9)


def test_article_file_tabs_click_the_actionable_child_and_confirm_navigation():
    source = (
        Path(catalog.__file__).read_text(encoding="utf-8")
    )
    assert '"a[onclick], button[onclick], a[href], "' in source
    assert "_mark_article_documents(page)" in source
    assert "_article_documents_changed(" in source
    assert "Click {label} nhưng WFX không xác nhận chuyển mục" in source
    assert 'tab.evaluate("element => element.click()")' not in source


def test_company_foc_uses_misc_settings_save_and_persistence_confirmation():
    source = Path(modules.__file__).read_text(encoding="utf-8")
    assert 'onclick*="CurrentTab=4"' in source
    assert 'onclick*="CurrentItem=12"' in source
    assert "#chkAllowToMarkFOCQtyOnRMPOASN" in source
    assert 'td.clsBtnOff[title="Save"] a#lnkSave.clsNavLink' in source
    assert "save_frame, save = _visible_locator_in_frames(" in source
    assert '_mark_document(save_frame, "company-foc-save")' in source
    assert 'frame.locator("a#lnkSave")' not in source
    assert "_document_changed(current_frame, snapshot)" in source
    assert 'method not in {"POST", "PUT", "PATCH"}' in source
    assert '"FOC cho ASN" if wanted else "FOC cho GRN"' in source


def test_visible_locator_reacquires_save_from_the_current_frame():
    save = SimpleNamespace(is_visible=lambda: True)

    class Matches:
        def __init__(self, candidates):
            self.candidates = candidates

        def count(self):
            return len(self.candidates)

        def nth(self, index):
            return self.candidates[index]

    class Frame:
        def __init__(self, candidates):
            self.candidates = candidates

        def locator(self, _selector):
            return Matches(self.candidates)

    stale = SimpleNamespace(is_visible=lambda: False)
    page = SimpleNamespace(
        frames=[Frame([stale]), Frame([save])],
        wait_for_timeout=lambda _milliseconds: None,
    )

    frame, found = modules._visible_locator_in_frames(
        page,
        'td.clsBtnOff[title="Save"] a#lnkSave',
        timeout_s=0.1,
    )

    assert frame is page.frames[1]
    assert found is save


def test_navigation_click_accepts_frame_detach_after_aspnet_navigation(
    monkeypatch,
):
    def detached(_locator):
        raise modules.PlaywrightError("Locator.click: Frame was detached")

    monkeypatch.setattr(modules, "_click", detached)

    modules._click_navigation_control(object())


def test_navigation_click_does_not_hide_unrelated_errors(monkeypatch):
    def failed(_locator):
        raise modules.PlaywrightError("Element is disabled")

    monkeypatch.setattr(modules, "_click", failed)

    with pytest.raises(modules.PlaywrightError, match="disabled"):
        modules._click_navigation_control(object())


def test_attachment_url_is_parsed_and_normalized_from_wfx_onclick():
    url = catalog._attachment_url(
        {
            "href": "",
            "onclick": (
                "xOnClick(this,event);if (!ViewAttachmentFile(this,"
                "'https://prosports.worldfashionexchange.com///Company//"
                "77400//Documents//jacket.pdf')) {return false;}"
            ),
        }
    )

    assert url == (
        "https://prosports.worldfashionexchange.com/"
        "Company/77400/Documents/jacket.pdf"
    )


def test_attachment_url_reads_view_column_and_encodes_spaces():
    url = catalog._attachment_url(
        {
            "href": "",
            "onclick": (
                "xOnClick(this,event);if (!ViewAttachmentFile(this,"
                "'https://prosports.worldfashionexchange.com///Company//"
                "77400//Documents//638542294739583684_"
                "1956-Men ripstop jacket.pdf')) {return false;}"
            ),
        }
    )

    assert url == (
        "https://prosports.worldfashionexchange.com/Company/77400/Documents/"
        "638542294739583684_1956-Men%20ripstop%20jacket.pdf"
    )


def test_attachment_url_rejects_non_wfx_host():
    assert (
        catalog._attachment_url(
            {
                "href": "https://example.com/file.pdf",
                "onclick": "",
            }
        )
        == ""
    )


def test_attachment_download_path_never_overwrites_existing_file(tmp_path):
    existing = tmp_path / "jacket.pdf"
    existing.write_bytes(b"first")

    target = catalog._available_download_path(tmp_path, "jacket.pdf")

    assert target.name == "jacket (1).pdf"
    assert existing.read_bytes() == b"first"


def test_attachment_download_uses_http_ranges_for_large_files(tmp_path):
    payload = b"0123456789"

    class Response:
        def __init__(self, start, end):
            self.status = 206
            self._body = payload[start : end + 1]
            self.headers = {
                "content-range": (
                    f"bytes {start}-{start + len(self._body) - 1}/"
                    f"{len(payload)}"
                )
            }
            self.disposed = False

        def body(self):
            return self._body

        def dispose(self):
            self.disposed = True

    class Request:
        def __init__(self):
            self.ranges = []
            self.responses = []

        def get(self, _url, *, headers, **_kwargs):
            value = headers["Range"]
            self.ranges.append(value)
            start, end = (
                int(part)
                for part in value.removeprefix("bytes=").split("-")
            )
            end = min(end, len(payload) - 1)
            response = Response(start, end)
            self.responses.append(response)
            return response

    request = Request()
    target = tmp_path / "download.bin"
    with target.open("wb") as handle:
        size = catalog._download_attachment_in_chunks(
            request,
            "https://prosports.worldfashionexchange.com/file.bin",
            handle,
            lambda _line: None,
            chunk_size=4,
        )

    assert size == len(payload)
    assert target.read_bytes() == payload
    assert request.ranges == ["bytes=0-3", "bytes=4-7", "bytes=8-9"]
    assert all(response.disposed for response in request.responses)


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


def test_detect_browser_finds_edge_under_program_files_x86(tmp_path, monkeypatch):
    # Regression: env var name is ProgramFiles(x86); a missing ")" meant browsers
    # installed only under "C:\\Program Files (x86)\\" (common for Edge) were never
    # detected, wrongly reporting "no compatible browser".
    x86 = tmp_path / "ProgramFilesX86"
    edge = x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"edge")
    monkeypatch.delenv("WFX_CHROME_PATH", raising=False)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "ProgramFiles"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(x86))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(login.shutil, "which", lambda _name: None)
    found = login.detect_browser()
    assert found is not None
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


def test_wfx_dialog_stays_visible_for_user_and_handler_is_not_duplicated():
    handlers = []
    removed = []
    logs = []

    class FakePage:
        def on(self, event, handler):
            assert event == "dialog"
            handlers.append(handler)

        def remove_listener(self, event, handler):
            removed.append((event, handler))

    class FakeDialog:
        message = "Thông báo nghiệp vụ"

        def accept(self):
            raise AssertionError("System alert must wait for the user")

        def dismiss(self):
            raise AssertionError("System alert must wait for the user")

    page = FakePage()
    browser._attach_dialog_handler(page, logs.append)
    first = handlers[-1]
    browser._attach_dialog_handler(page, logs.append)
    second = handlers[-1]
    second(FakeDialog())

    assert removed == [("dialog", first)]
    assert "Chrome đang chờ bạn xác nhận" in logs[-1]


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


def test_detached_article_frame_refreshes_only_the_cdp_connection(monkeypatch):
    calls = []

    class DetachedTop:
        def locator(self, _selector):
            raise catalog.PlaywrightError("Frame was detached")

    article_page = SimpleNamespace(
        url="https://example.test/wfx/wfx_ArticleDetail.aspx",
        frame=lambda name: DetachedTop() if name == "ArticleTop" else None,
    )
    stale_browser = SimpleNamespace(
        contexts=[SimpleNamespace(pages=[article_page])]
    )
    refreshed_browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[])])
    refreshed_page = object()
    playwright = object()
    page = object()

    monkeypatch.setattr(
        catalog,
        "invalidate_browser",
        lambda browser: calls.append(("invalidate", browser)),
    )
    monkeypatch.setattr(
        catalog,
        "_connect_to_chrome",
        lambda actual: (
            calls.append(("connect", actual))
            or (refreshed_browser, refreshed_page)
        ),
    )
    monkeypatch.setattr(
        catalog,
        "_attach_dialog_handler",
        lambda actual_page, _log: calls.append(("dialogs", actual_page)),
    )

    result = catalog._refresh_article_context(
        playwright,
        stale_browser,
        page,
        lambda _line: None,
    )

    assert result == (refreshed_browser, refreshed_page)
    assert calls == [
        ("invalidate", stale_browser),
        ("connect", playwright),
        ("dialogs", refreshed_page),
    ]


def test_healthy_article_frame_still_refreshes_before_popup_navigation(monkeypatch):
    class HealthyBody:
        def count(self):
            return 1

    article_page = SimpleNamespace(
        url="https://example.test/wfx/wfx_ArticleDetail.aspx",
        frame=lambda name: (
            SimpleNamespace(locator=lambda _selector: HealthyBody())
            if name == "ArticleTop"
            else None
        ),
    )
    browser_instance = SimpleNamespace(
        contexts=[SimpleNamespace(pages=[article_page])]
    )
    page = object()
    refreshed_browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[])])
    refreshed_page = object()
    calls = []
    monkeypatch.setattr(
        catalog,
        "invalidate_browser",
        lambda browser: calls.append(("invalidate", browser)),
    )
    monkeypatch.setattr(
        catalog,
        "_connect_to_chrome",
        lambda actual: (
            calls.append(("connect", actual))
            or (refreshed_browser, refreshed_page)
        ),
    )
    monkeypatch.setattr(
        catalog,
        "_attach_dialog_handler",
        lambda actual_page, _log: calls.append(("dialogs", actual_page)),
    )

    playwright = object()
    result = catalog._refresh_article_context(
        playwright,
        browser_instance,
        page,
        lambda _line: None,
    )

    assert result == (refreshed_browser, refreshed_page)
    assert calls == [
        ("invalidate", browser_instance),
        ("connect", playwright),
        ("dialogs", refreshed_page),
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
