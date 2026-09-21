"""Chạy thật hai script JS của luồng Cancel Supplier Invoice.

`_SUPPLIER_INVOICE_ROWS_JS` đọc danh sách dòng, `_CLICK_SUPPLIER_INVOICE_ROW_JS`
chọn lại đúng dòng đó rồi app bấm Delete/Cancel. Hai script phải nhìn thấy cùng
một danh sách, nếu không `row_key` dạng chỉ số sẽ trỏ sang dòng khác. Không fake
Python nào kiểm được điều đó vì logic nằm hẳn trong JS, nên test này thực thi
chính chuỗi được gửi vào Chrome bằng Node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from wfx_panel.automation import modules

HARNESS = Path(__file__).parent / "js" / "supplier_invoice_row_scan.js"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(
    node is None,
    reason="Cần Node để chạy chính script JS được gửi vào Chrome",
)


def test_reading_and_clicking_a_row_agree_on_the_same_invoice(tmp_path):
    scripts = tmp_path / "scripts.json"
    scripts.write_text(
        json.dumps(
            {
                "rows": modules._SUPPLIER_INVOICE_ROWS_JS,
                "click": modules._CLICK_SUPPLIER_INVOICE_ROW_JS,
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [node, str(HARNESS), str(scripts)],
        capture_output=True,
        text=True,
        # Harness in tiếng Việt; locale Windows là cp1252 nên phải nói rõ UTF-8.
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_both_scripts_are_built_from_one_scan_function():
    """Chống hồi quy ở mức cấu trúc cho máy không có Node."""
    assert modules._SUPPLIER_INVOICE_SCAN_JS in modules._SUPPLIER_INVOICE_ROWS_JS
    assert modules._SUPPLIER_INVOICE_SCAN_JS in modules._CLICK_SUPPLIER_INVOICE_ROW_JS
    assert "scanRows" in modules._SUPPLIER_INVOICE_SCAN_JS
