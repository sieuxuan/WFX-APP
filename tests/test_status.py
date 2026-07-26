import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wfx_panel import status


def _serve(payload: bytes, status_code: int = 200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture
def cdp_env(monkeypatch):
    def _apply(server):
        host, port = server.server_address
        monkeypatch.setenv("WFX_CDP_HOST", host)
        monkeypatch.setenv("WFX_CDP_PORT", str(port))

    return _apply


def test_cdp_url_defaults(monkeypatch):
    monkeypatch.delenv("WFX_CDP_HOST", raising=False)
    monkeypatch.delenv("WFX_CDP_PORT", raising=False)
    assert status.cdp_url() == "http://127.0.0.1:9222"


def test_cdp_url_honours_env(monkeypatch):
    monkeypatch.setenv("WFX_CDP_HOST", "10.0.0.5")
    monkeypatch.setenv("WFX_CDP_PORT", "9333")
    assert status.cdp_url() == "http://10.0.0.5:9333"


def test_alive_when_cdp_reports_websocket(cdp_env):
    server = _serve(json.dumps({"webSocketDebuggerUrl": "ws://x"}).encode())
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is True
    finally:
        server.shutdown()


def test_not_alive_when_payload_lacks_websocket(cdp_env):
    server = _serve(json.dumps({"Browser": "Chrome/1"}).encode())
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is False
    finally:
        server.shutdown()


def test_not_alive_when_payload_is_garbage(cdp_env):
    server = _serve(b"<html>not json</html>")
    cdp_env(server)
    try:
        assert status.chrome_alive(timeout=2) is False
    finally:
        server.shutdown()


def test_not_alive_when_port_is_closed(monkeypatch):
    monkeypatch.setenv("WFX_CDP_HOST", "127.0.0.1")
    monkeypatch.setenv("WFX_CDP_PORT", "9")
    assert status.chrome_alive(timeout=1) is False
