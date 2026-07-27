import json
import re

from wfx_panel import log_bridge


def test_js_string_escapes_quotes_and_newlines():
    out = log_bridge.js_string('he said "hi"\nline2\\end')
    # Kết quả phải parse lại được bằng JSON để đảm bảo escape đúng.
    assert json.loads(out) == 'he said "hi"\nline2\\end'


def test_js_string_handles_unicode():
    assert json.loads(log_bridge.js_string("Đăng nhập")) == "Đăng nhập"


def test_format_log_line_adds_timestamp():
    line = log_bridge.format_log_line("[SESSION] ok")
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] \[SESSION\] ok$", line)


def test_format_log_line_keeps_existing_timestamp():
    original = "[10:11:12] already stamped"
    assert log_bridge.format_log_line(original) == original


def test_log_redacts_business_queries_credentials_and_url_queries():
    line = log_bridge.format_log_line(
        "query='STYLE-123' password=secret "
        "https://example.test/path?SessionID=abc"
    )
    assert "STYLE-123" not in line
    assert "secret" not in line
    assert "SessionID=abc" not in line
    assert "query=[REDACTED]" in line
    assert "password=[REDACTED]" in line


def test_log_redacts_contextual_catalog_details():
    line = log_bridge.format_log_line(
        "[CODE] Kết quả grid: ['ABC123', 'ABC124']"
    )
    assert "ABC123" not in line
    assert "Kết quả grid: [REDACTED]" in line
