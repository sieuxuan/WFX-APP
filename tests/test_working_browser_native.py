"""Exercise the working profile and CDP against real Chrome on a local site."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import sync_playwright

from wfx_panel.automation import browser as launcher
from wfx_panel.automation import runtime


class WorkingSite(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        if self.path.startswith("/file"):
            name = self.path.removeprefix("/") + ".txt"
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            body = b"WFX native download"
        else:
            self.send_header("Content-Type", "text/html; charset=utf-8")
            script = ""
            if self.path == "/popup":
                # No user gesture: the WFX origin's popup exception is needed.
                script = "setTimeout(() => window.open('/child'), 200)"
            body = f"<html><body>Local WFX test<script>{script}</script></body></html>".encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def working_chrome(tmp_path, monkeypatch):
    executable = launcher.detect_browser()
    if executable is None:
        pytest.skip("Chrome/Chromium is not installed")
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkingSite)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    cdp_url = f"http://127.0.0.1:{port}"
    downloads = tmp_path / "Downloads"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(launcher, "URL", origin)
    monkeypatch.setattr(launcher, "CDP_PORT", port)
    monkeypatch.setattr(launcher, "CDP_URL", cdp_url)
    monkeypatch.setattr(launcher, "detect_browser", lambda: executable)
    monkeypatch.setattr(launcher, "_user_downloads_dir", lambda: downloads)
    monkeypatch.setattr(runtime, "_user_downloads_dir", lambda: downloads)
    real_popen = subprocess.Popen
    processes = []

    def launch_headless(command, **kwargs):
        # Same production launcher/profile; headless only avoids visible test
        # windows. Do not use Playwright.launch's popup/download overrides.
        process = real_popen([*command[:-1], "--headless=new", command[-1]], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(launcher.subprocess, "Popen", launch_headless)
    try:
        launcher._start_persistent_chrome(lambda _message: None, grace_checked=True)
        # Playwright's own Node process must not receive Chrome's headless flag.
        monkeypatch.setattr(launcher.subprocess, "Popen", real_popen)
        yield origin, cdp_url, downloads
    finally:
        monkeypatch.setattr(launcher.subprocess, "Popen", real_popen)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(
                    cdp_url, no_defaults=True, timeout=3000
                )
                browser.new_browser_cdp_session().send("Browser.close")
        except Exception:
            pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()  # Only the disposable test browser PID.
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_popup_dialogs_and_downloads_survive_automation(working_chrome):
    origin, cdp_url, downloads = working_chrome
    engine = runtime.AutomationRuntime()
    with sync_playwright() as pw:
        browser = engine.connect_browser(pw, cdp_url)
        page = browser.contexts[0].pages[0]
        with page.context.expect_page() as opened:
            page.goto(origin + "/popup")
        popup = opened.value
        popup.wait_for_url(origin + "/child")

        # No per-flow handler: only the runtime's context listener protects
        # dialogs in both the original tab and the newly created popup.
        for target in (page, popup):
            session = target.context.new_cdp_session(target)
            opened_dialogs, closed_dialogs = [], []
            session.send("Page.enable")
            session.on(
                "Page.javascriptDialogOpening",
                lambda event, sink=opened_dialogs: sink.append(event),
            )
            session.on(
                "Page.javascriptDialogClosed",
                lambda event, sink=closed_dialogs: sink.append(event),
            )
            for kind in ("alert", "confirm", "prompt"):
                count = len(opened_dialogs)
                target.evaluate(f"setTimeout(() => {kind}('WFX test'), 20)")
                deadline = time.monotonic() + 5
                while len(opened_dialogs) == count and time.monotonic() < deadline:
                    target.wait_for_timeout(50)
                target.wait_for_timeout(250)
                assert len(opened_dialogs) == count + 1
                assert opened_dialogs[-1]["type"] == kind
                assert closed_dialogs == []  # Still waiting for the user.
                session.send("Page.handleJavaScriptDialog", {"accept": True})
                target.wait_for_timeout(50)
                closed_dialogs.clear()
            session.detach()

        before = runtime.snapshot_downloads()
        page.evaluate("""() => {
            for (const name of ['file1', 'file2']) {
                const link = document.createElement('a');
                link.href = '/' + name;
                link.download = name + '.txt';
                document.body.append(link);
                link.click();
            }
        }""")
        for name in ("file1.txt", "file2.txt"):
            saved = runtime.wait_for_native_download(
                before, suggested_name=name, timeout=10
            )
            assert saved.read_bytes() == b"WFX native download"

    # Stopping Playwright must leave real files and the working browser alive.
    assert launcher._chrome_is_ready()
    assert {p.name for p in downloads.iterdir()} == {"file1.txt", "file2.txt"}
    with sync_playwright() as pw:
        browser = engine.connect_browser(pw, cdp_url)
        assert len(browser.contexts[0].pages) == 2


def test_reconnecting_does_not_close_an_existing_user_alert(working_chrome):
    _origin, cdp_url, _downloads = working_chrome
    errors = []

    def reconnect():
        try:
            with sync_playwright() as pw:
                browser = runtime.AutomationRuntime().connect_browser(pw, cdp_url)
                browser.contexts[0].pages[0].wait_for_timeout(300)
        except Exception as exc:
            errors.append(exc)

    with sync_playwright() as pw:
        browser = runtime.AutomationRuntime().connect_browser(pw, cdp_url)
        page = browser.contexts[0].pages[0]
        session = page.context.new_cdp_session(page)
        closed = []
        session.send("Page.enable")
        session.on("Page.javascriptDialogClosed", lambda event: closed.append(event))
        with page.expect_event("dialog"):
            page.evaluate("setTimeout(() => alert('Keep this alert'), 20)")
        thread = threading.Thread(target=reconnect)
        thread.start()
        try:
            page.wait_for_timeout(1000)
            assert closed == []
        finally:
            # Chrome can defer attaching while a modal is open. The user
            # confirms it; the pending automation connection may then finish.
            session.send("Page.handleJavaScriptDialog", {"accept": True})
            thread.join(timeout=15)
        assert not thread.is_alive()
        assert errors == []
