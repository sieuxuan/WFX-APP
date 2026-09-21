"""Vòng đời trình duyệt làm việc: dò, mở, kết nối, giữ alert và đóng.

`wfx_panel/automation/browser.py` ở mức 66%. CLAUDE.md đặt ra đúng những luật
nằm trong phần chưa chạy:

* "`Thoát và đóng trình duyệt` gửi CDP `Browser.close` tới đúng Chrome
  automation để giải phóng RAM… Không kill process theo tên."
* "Chrome automation chạy `--process-per-site`, tối đa 3 renderer, không nạp
  extension"; "Chrome/Chromium 150+ trên Windows phải khởi động với
  `--disable-features=LaunchShellExecuteViaExplorer`".
* "Chrome phải tự quản lý file theo profile và lưu thẳng vào Windows Known
  Folder Downloads."
* "Alert nghiệp vụ phải còn hiển thị trên Chrome để người dùng đọc và xác nhận;
  không auto accept/dismiss mọi dialog."
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation import browser as browser_module


@pytest.fixture(autouse=True)
def _clear_browser_cache(monkeypatch):
    monkeypatch.setattr(browser_module, "_DETECTED_BROWSER", None, raising=False)
    monkeypatch.setattr(browser_module, "_DETECTED_FOR_ENV", None, raising=False)


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, browser_module, _common)


def _quiet():
    return lambda _line: None


def _install(tmp_path, monkeypatch, relative, *, env="PROGRAMFILES"):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"MZ")
    monkeypatch.setenv(env, str(tmp_path))
    return target


def _clear_env(monkeypatch):
    for key in browser_module._BROWSER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(browser_module.shutil, "which", lambda _name: None)


# --- dò trình duyệt -------------------------------------------------------


def test_a_configured_path_wins_over_everything_else(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    configured = tmp_path / "custom" / "brave.exe"
    configured.parent.mkdir(parents=True)
    configured.write_bytes(b"MZ")
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    monkeypatch.setenv("WFX_CHROME_PATH", str(configured))

    found = browser_module.detect_browser()

    assert found.path == configured
    assert found.name == "Trình duyệt đã cấu hình"


def test_chrome_on_the_path_is_found_without_any_program_files(
    tmp_path, monkeypatch
):
    _clear_env(monkeypatch)
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"MZ")
    monkeypatch.setattr(browser_module.shutil, "which", lambda _name: str(chrome))

    assert browser_module.detect_browser().name == "Google Chrome"


@pytest.mark.parametrize(
    ("relative", "name"),
    [
        ("Google/Chrome/Application/chrome.exe", "Google Chrome"),
        ("Microsoft/Edge/Application/msedge.exe", "Microsoft Edge"),
        ("BraveSoftware/Brave-Browser/Application/brave.exe", "Brave"),
        ("Chromium/Application/chrome.exe", "Chromium"),
    ],
)
def test_every_supported_channel_is_recognised(
    tmp_path, monkeypatch, relative, name
):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, relative)

    assert browser_module.detect_browser().name == name


def test_no_browser_anywhere_is_reported_as_none(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))

    assert browser_module.detect_browser() is None


def test_a_configured_path_that_does_not_exist_falls_through(
    tmp_path, monkeypatch
):
    _clear_env(monkeypatch)
    monkeypatch.setenv("WFX_CHROME_PATH", str(tmp_path / "khong-co.exe"))
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")

    assert browser_module.detect_browser().name == "Google Chrome"


def test_the_detection_is_cached_until_an_input_changes(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    chrome = _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    first = browser_module.detect_browser()
    probes: list[int] = []
    original = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda self: probes.append(1) or original(self)
    )

    assert browser_module.detect_browser() is first
    # Chỉ phải kiểm tra lại đúng file đã cache, không quét 30 ứng viên.
    assert len(probes) == 1

    edge = _install(
        tmp_path / "moi", monkeypatch, "Microsoft/Edge/Application/msedge.exe"
    )
    chrome.unlink()

    assert browser_module.detect_browser().path == edge


def test_the_cache_key_covers_every_environment_variable_it_reads(
    tmp_path, monkeypatch
):
    """Khóa cache chỉ theo WFX_CHROME_PATH sẽ trả kết quả cũ khi roots đổi."""
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    browser_module.detect_browser()
    other = tmp_path / "khac"
    edge = _install(other, monkeypatch, "Microsoft/Edge/Application/msedge.exe")

    assert browser_module.detect_browser().path == edge


def test_the_backwards_compatible_alias_returns_the_path(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    chrome = _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")

    assert browser_module._find_chrome() == chrome


def test_the_alias_raises_a_readable_error_without_a_browser(
    tmp_path, monkeypatch
):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="WFX_CHROME_PATH"):
        browser_module._find_chrome()


# --- CDP sẵn sàng ---------------------------------------------------------


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _wire_cdp(monkeypatch, payload):
    def urlopen(_url, timeout=0):
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)

    monkeypatch.setattr(browser_module, "urlopen", urlopen)
    monkeypatch.setattr(
        browser_module.json, "load", lambda stream: json.loads(stream.read())
    )


def test_chrome_is_ready_when_cdp_advertises_a_debugger(monkeypatch):
    _wire_cdp(monkeypatch, {"webSocketDebuggerUrl": "ws://x"})

    assert browser_module._chrome_is_ready() is True


def test_chrome_is_not_ready_without_a_debugger_url(monkeypatch):
    _wire_cdp(monkeypatch, {})

    assert browser_module._chrome_is_ready() is False


def test_a_refused_cdp_port_means_chrome_is_not_ready(monkeypatch):
    _wire_cdp(monkeypatch, OSError("connection refused"))

    assert browser_module._chrome_is_ready() is False


def test_waiting_returns_at_once_when_chrome_is_already_up(clock, monkeypatch):
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: True)

    assert browser_module._wait_for_chrome_ready(5) is True


def test_waiting_gives_up_after_the_grace_period(clock, monkeypatch):
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: False)
    monkeypatch.setattr(browser_module, "_sleep", clock.sleep)

    assert browser_module._wait_for_chrome_ready(1) is False


# --- preferences của profile automation ----------------------------------


def test_the_automation_profile_turns_the_password_manager_off(
    tmp_path, monkeypatch
):
    downloads = tmp_path / "Downloads"
    monkeypatch.setattr(browser_module, "_user_downloads_dir", lambda: downloads)

    browser_module._disable_password_manager(tmp_path / "profile")

    written = json.loads(
        (tmp_path / "profile" / "Default" / "Preferences").read_text(
            encoding="utf-8"
        )
    )
    assert written["profile"]["password_manager_enabled"] is False
    assert written["credentials_enable_service"] is False
    assert written["password_manager_leak_detection"] is False


def test_the_automation_profile_points_downloads_at_the_known_folder(
    tmp_path, monkeypatch
):
    downloads = tmp_path / "Downloads"
    monkeypatch.setattr(browser_module, "_user_downloads_dir", lambda: downloads)

    browser_module._disable_password_manager(tmp_path / "profile")

    written = json.loads(
        (tmp_path / "profile" / "Default" / "Preferences").read_text(
            encoding="utf-8"
        )
    )
    assert written["download"]["default_directory"] == str(downloads)
    assert written["download"]["prompt_for_download"] is False
    assert downloads.is_dir()


def test_an_existing_preferences_file_keeps_its_other_settings(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        browser_module, "_user_downloads_dir", lambda: tmp_path / "Downloads"
    )
    path = tmp_path / "profile" / "Default" / "Preferences"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"intl": {"accept_languages": "vi"}}), encoding="utf-8"
    )

    browser_module._disable_password_manager(tmp_path / "profile")

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["intl"]["accept_languages"] == "vi"
    assert written["credentials_enable_service"] is False


@pytest.mark.parametrize("content", ["{ hỏng", '"chuỗi"', "[1, 2]"])
def test_a_corrupt_preferences_file_is_rebuilt(tmp_path, monkeypatch, content):
    monkeypatch.setattr(
        browser_module, "_user_downloads_dir", lambda: tmp_path / "Downloads"
    )
    path = tmp_path / "profile" / "Default" / "Preferences"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    browser_module._disable_password_manager(tmp_path / "profile")

    assert json.loads(path.read_text(encoding="utf-8"))[
        "credentials_enable_service"
    ] is False


def test_a_non_dict_profile_section_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(
        browser_module, "_user_downloads_dir", lambda: tmp_path / "Downloads"
    )
    path = tmp_path / "profile" / "Default" / "Preferences"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"profile": "hỏng", "download": 5}), encoding="utf-8"
    )

    browser_module._disable_password_manager(tmp_path / "profile")

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["profile"]["password_manager_enabled"] is False
    assert written["download"]["directory_upgrade"] is True


# --- mở Chrome ------------------------------------------------------------


def _wire_launch(monkeypatch, tmp_path, *, ready_after=True):
    launched: list[list[str]] = []
    monkeypatch.setattr(
        browser_module.subprocess,
        "Popen",
        lambda command, **_kwargs: launched.append(list(command)),
    )
    monkeypatch.setattr(
        browser_module, "_disable_password_manager", lambda _dir: None
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    states = [False, ready_after]
    monkeypatch.setattr(
        browser_module,
        "_wait_for_chrome_ready",
        lambda _timeout: states.pop(0) if len(states) > 1 else states[0],
    )
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: False)
    return launched


def test_chrome_is_launched_with_the_memory_and_shell_flags(
    tmp_path, monkeypatch
):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    launched = _wire_launch(monkeypatch, tmp_path)

    browser_module._start_persistent_chrome(_quiet())

    command = launched[0]
    assert "--process-per-site" in command
    assert "--renderer-process-limit=3" in command
    assert "--disable-extensions" in command
    assert any(
        "LaunchShellExecuteViaExplorer" in argument for argument in command
    )
    assert any(
        argument.startswith("--remote-debugging-port=") for argument in command
    )


def test_an_already_running_chrome_is_never_launched_again(
    tmp_path, monkeypatch
):
    launched = _wire_launch(monkeypatch, tmp_path)
    monkeypatch.setattr(browser_module, "_wait_for_chrome_ready", lambda _t: True)

    browser_module._start_persistent_chrome(_quiet())

    assert launched == []


def test_a_missing_browser_raises_before_any_launch(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    launched = _wire_launch(monkeypatch, tmp_path)

    with pytest.raises(FileNotFoundError, match="WFX_CHROME_PATH"):
        browser_module._start_persistent_chrome(_quiet())

    assert launched == []


def test_a_chrome_that_never_opens_cdp_is_reported(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    _wire_launch(monkeypatch, tmp_path, ready_after=False)

    with pytest.raises(TimeoutError, match="cổng điều khiển"):
        browser_module._start_persistent_chrome(_quiet())


# --- start_chrome ---------------------------------------------------------


def test_start_chrome_reports_an_already_open_browser(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    monkeypatch.setattr(browser_module, "_wait_for_chrome_ready", lambda _t: True)
    monkeypatch.setattr(
        browser_module, "_start_persistent_chrome", lambda *a, **kw: None
    )

    result = browser_module.start_chrome(_quiet())

    assert result["code"] == "CHROME_ALREADY_OPEN"
    assert result["chrome_alive"] is True


def test_start_chrome_names_the_browser_it_opened(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    _install(
        tmp_path, monkeypatch, "Microsoft/Edge/Application/msedge.exe"
    )
    monkeypatch.setattr(browser_module, "_wait_for_chrome_ready", lambda _t: False)
    monkeypatch.setattr(
        browser_module, "_start_persistent_chrome", lambda *a, **kw: None
    )

    result = browser_module.start_chrome(_quiet())

    assert result["code"] == "CHROME_OPENED"
    assert result["browser_name"] == "Microsoft Edge"


def test_start_chrome_reports_a_machine_without_any_browser(
    monkeypatch, tmp_path
):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setattr(browser_module, "_wait_for_chrome_ready", lambda _t: False)

    result = browser_module.start_chrome(_quiet())

    assert result["code"] == "BROWSER_NOT_FOUND"
    assert result["browser_available"] is False


def test_start_chrome_reports_a_launch_failure(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    monkeypatch.setattr(browser_module, "_wait_for_chrome_ready", lambda _t: False)
    monkeypatch.setattr(
        browser_module,
        "_start_persistent_chrome",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("không chạy được")),
    )

    result = browser_module.start_chrome(_quiet())

    assert result["code"] == "CHROME_OPEN_FAILED"
    assert result["chrome_alive"] is False


# --- browser_status -------------------------------------------------------


def test_the_status_reports_both_liveness_and_availability(
    monkeypatch, tmp_path
):
    _clear_env(monkeypatch)
    _install(tmp_path, monkeypatch, "Google/Chrome/Application/chrome.exe")
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: True)

    assert browser_module.browser_status() == {
        "chrome_alive": True,
        "browser_available": True,
        "browser_name": "Google Chrome",
    }


def test_the_status_without_a_browser_names_nothing(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: False)

    assert browser_module.browser_status()["browser_name"] is None


# --- đóng Chrome ----------------------------------------------------------


class _Session:
    def __init__(self, sink):
        self._sink = sink

    def send(self, command):
        self._sink.append(command)


class _Browser:
    def __init__(self, sink, contexts=None):
        self._sink = sink
        self.contexts = contexts if contexts is not None else [object()]

    def new_browser_cdp_session(self):
        return _Session(self._sink)


def _wire_close(monkeypatch, *, alive, sink=None):
    sink = sink if sink is not None else []
    states = list(alive)
    monkeypatch.setattr(
        browser_module,
        "_chrome_is_ready",
        lambda: states.pop(0) if len(states) > 1 else states[0],
    )
    monkeypatch.setattr(
        browser_module, "sync_playwright", lambda: _Starter()
    )
    monkeypatch.setattr(
        browser_module,
        "_connect_to_chrome",
        lambda _playwright, **_kw: (_Browser(sink), object()),
    )
    monkeypatch.setattr(browser_module, "invalidate_browser", lambda _b: None)
    return sink


class _Driver:
    def stop(self):
        return None


class _Starter:
    def start(self):
        return _Driver()


def test_closing_an_already_closed_browser_is_a_no_op(monkeypatch):
    sink = _wire_close(monkeypatch, alive=[False])

    result = browser_module.close_chrome(_quiet())

    assert result["code"] == "CHROME_ALREADY_CLOSED"
    assert sink == []


def test_closing_sends_browser_close_over_cdp(monkeypatch):
    """CLAUDE.md: không kill process theo tên."""
    sink = _wire_close(monkeypatch, alive=[True, False])

    result = browser_module.close_chrome(_quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert sink == ["Browser.close"]
    assert result["chrome_alive"] is False


def test_a_browser_that_refuses_to_close_is_reported(monkeypatch, clock):
    _wire_close(monkeypatch, alive=[True])
    monkeypatch.setattr(browser_module.time, "sleep", clock.sleep)

    result = browser_module.close_chrome(_quiet())

    assert result["code"] == "CHROME_CLOSE_TIMEOUT"
    assert result["chrome_alive"] is True


def test_a_cdp_disconnect_after_close_still_counts_as_closed(monkeypatch):
    states = [True, False]
    monkeypatch.setattr(
        browser_module,
        "_chrome_is_ready",
        lambda: states.pop(0) if len(states) > 1 else states[0],
    )
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(
        browser_module,
        "_connect_to_chrome",
        lambda *_a, **_kw: (_ for _ in ()).throw(PlaywrightError("đã ngắt")),
    )

    assert browser_module.close_chrome(_quiet())["code"] == "CHROME_CLOSED"


def test_a_failure_while_chrome_is_still_alive_is_a_real_error(monkeypatch):
    monkeypatch.setattr(browser_module, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(browser_module, "sync_playwright", lambda: _Starter())
    monkeypatch.setattr(
        browser_module,
        "_connect_to_chrome",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("CDP lỗi")),
    )

    result = browser_module.close_chrome(_quiet())

    assert result["code"] == "CHROME_CLOSE_FAILED"
    assert result["chrome_alive"] is True


# --- chọn tab WFX ---------------------------------------------------------


class _Page:
    def __init__(self, url):
        self.url = url
        self.fronted = 0

    def bring_to_front(self):
        self.fronted += 1


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)
        self.timeout = None
        self.new_pages = 0

    def set_default_timeout(self, timeout):
        self.timeout = timeout

    def new_page(self):
        self.new_pages += 1
        page = _Page("about:blank")
        self.pages.append(page)
        return page


def _wire_connect(monkeypatch, context, *, first_fails=False):
    browsers: list[_Browser] = []

    def connect(_playwright, _url):
        instance = _Browser([], contexts=None if not browsers and first_fails else [context])
        if not browsers and first_fails:
            instance.contexts = property(
                lambda _self: (_ for _ in ()).throw(PlaywrightError("rơi"))
            )
        browsers.append(instance)
        return instance

    monkeypatch.setattr(browser_module, "connect_browser", connect)
    monkeypatch.setattr(browser_module, "invalidate_browser", lambda _b: None)
    return browsers


def test_the_main_wfx_tab_is_preferred(monkeypatch):
    other = _Page("https://wfx.test/WFX_Costing.aspx")
    main = _Page("https://wfx.test/wfx/default.aspx")
    context = _Context([other, main])
    _wire_connect(monkeypatch, context)

    _browser, page = browser_module._connect_to_chrome(object())

    assert page is main
    assert page.fronted == 1
    assert context.timeout == browser_module.DEFAULT_TIMEOUT_MS


def test_any_wfx_tab_is_used_when_the_main_one_is_gone(monkeypatch):
    costing = _Page("https://prosports.worldfashionexchange.com/WFX_Costing.aspx")
    context = _Context([_Page("https://google.test"), costing])
    _wire_connect(monkeypatch, context)

    _browser, page = browser_module._connect_to_chrome(object())

    assert page is costing


def test_a_blank_tab_is_reused_before_opening_a_new_one(monkeypatch):
    blank = _Page("about:blank")
    context = _Context([_Page("https://google.test"), blank])
    _wire_connect(monkeypatch, context)

    _browser, page = browser_module._connect_to_chrome(object())

    assert page is blank
    assert context.new_pages == 0


def test_a_new_tab_is_opened_only_as_a_last_resort(monkeypatch):
    context = _Context([_Page("https://google.test")])
    _wire_connect(monkeypatch, context)

    _browser, _page = browser_module._connect_to_chrome(object())

    assert context.new_pages == 1


def test_a_probe_never_fronts_the_tab(monkeypatch):
    main = _Page("https://wfx.test/wfx/default.aspx")
    _wire_connect(monkeypatch, _Context([main]))

    browser_module._connect_to_chrome(object(), bring_to_front=False)

    assert main.fronted == 0


def test_a_browser_without_any_context_is_reported(monkeypatch):
    monkeypatch.setattr(
        browser_module, "connect_browser", lambda *_a: _Browser([], contexts=[])
    )
    monkeypatch.setattr(browser_module, "invalidate_browser", lambda _b: None)

    with pytest.raises(RuntimeError, match="browser context"):
        browser_module._connect_to_chrome(object())


# --- giữ alert của WFX ----------------------------------------------------


class _DialogPage:
    def __init__(self, context=None):
        self.handlers: list[tuple] = []
        self.removed: list[tuple] = []
        self.context = context
        self.fronted = 0

    def on(self, event, handler):
        self.handlers.append((event, handler))

    def remove_listener(self, event, handler):
        self.removed.append((event, handler))

    def bring_to_front(self):
        self.fronted += 1


class _DialogContext:
    def __init__(self, pages):
        self.pages = list(pages)
        self.handlers: list[tuple] = []
        self.removed: list[tuple] = []

    def on(self, event, handler):
        self.handlers.append((event, handler))

    def remove_listener(self, event, handler):
        self.removed.append((event, handler))


def test_the_alert_is_left_on_screen_for_the_user(monkeypatch):
    page = _DialogPage()
    logs: list[str] = []

    browser_module._attach_dialog_handler(page, logs.append)
    _event, handler = page.handlers[0]

    class Dialog:
        message = "Bạn có chắc muốn xóa?"
        page = _DialogPage()
        accepted = False

        def accept(self):
            type(self).accepted = True

        def dismiss(self):
            type(self).accepted = True

    handler(Dialog())

    assert Dialog.accepted is False
    assert any("Chrome đang chờ bạn xác nhận" in line for line in logs)
    assert Dialog.page.fronted == 1


def test_a_previous_handler_is_removed_before_a_new_one_is_attached(
    monkeypatch,
):
    page = _DialogPage()

    browser_module._attach_dialog_handler(page, _quiet())
    first = page.handlers[0][1]
    browser_module._attach_dialog_handler(page, _quiet())

    assert page.removed == [("dialog", first)]
    assert len(page.handlers) == 2


def test_every_open_tab_gets_the_handler(monkeypatch):
    first, second = _DialogPage(), _DialogPage()
    context = _DialogContext([first, second])
    first.context = context

    browser_module._attach_dialog_handler(first, _quiet())

    assert first.handlers and second.handlers


def test_tabs_opened_later_also_get_the_handler(monkeypatch):
    page = _DialogPage()
    context = _DialogContext([page])
    page.context = context

    browser_module._attach_dialog_handler(page, _quiet())
    later = _DialogPage()
    context.handlers[0][1](later)

    assert later.handlers


def test_the_context_handler_is_replaced_not_stacked(monkeypatch):
    page = _DialogPage()
    context = _DialogContext([page])
    page.context = context

    browser_module._attach_dialog_handler(page, _quiet())
    first = context.handlers[0][1]
    browser_module._attach_dialog_handler(page, _quiet())

    assert context.removed == [("page", first)]


# --- PID của Chrome automation -------------------------------------------


def test_the_automation_pid_is_read_from_the_listening_socket(monkeypatch):
    monkeypatch.setattr(browser_module.os, "name", "nt")
    monkeypatch.setattr(browser_module, "CDP_HOST", "127.0.0.1")
    monkeypatch.setattr(browser_module, "CDP_PORT", 9222)
    output = (
        "  Proto  Local Address      Foreign Address    State       PID\n"
        "  TCP    127.0.0.1:9222     0.0.0.0:0          LISTENING   4242\n"
    )
    monkeypatch.setattr(
        browser_module.subprocess,
        "run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, output, ""),
    )

    assert browser_module.automation_browser_pid() == 4242


def test_the_automation_pid_is_none_on_another_host(monkeypatch):
    monkeypatch.setattr(browser_module.os, "name", "nt")
    monkeypatch.setattr(browser_module, "CDP_HOST", "10.0.0.5")

    assert browser_module.automation_browser_pid() is None


def test_the_automation_pid_is_none_when_nothing_listens(monkeypatch):
    monkeypatch.setattr(browser_module.os, "name", "nt")
    monkeypatch.setattr(browser_module, "CDP_HOST", "127.0.0.1")
    monkeypatch.setattr(
        browser_module.subprocess,
        "run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, "", ""),
    )

    assert browser_module.automation_browser_pid() is None
