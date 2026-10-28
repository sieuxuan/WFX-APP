"""Quét dropdown Expense Invoice từ WFX để đóng gói làm dữ liệu ban đầu.

Mở một form Expense Invoice - New trên Chrome automation (CDP 9222) rồi chạy:

    python scripts/seed_expense_options.py

Chỉ đọc qua handler dropdown của WFX, không đổi form. Kết quả ghi vào
``wfx_panel/assets/templates/Expense-Invoice-options.json``; mỗi tài khoản sẽ
tự thay bằng danh sách thật của mình sau lượt điền hóa đơn đầu tiên.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from wfx_panel.automation.expense_invoice import read_expense_options  # noqa: E402
from wfx_panel.workbooks.expense_invoice import OPTIONS_SEED  # noqa: E402

CDP_URL = os.getenv("WFX_CDP_URL", "http://127.0.0.1:9222")


def main() -> int:
    with sync_playwright() as playwright:
        # Không gửi Browser.setDownloadBehavior: xem CLAUDE.md mục CDP.
        browser = playwright.chromium.connect_over_cdp(CDP_URL, no_defaults=True)
        frames = [
            frame
            for page in browser.contexts[0].pages
            for frame in page.frames
            if urlsplit(frame.url).path.casefold().endswith("/wfxexpenseinvoice.aspx")
        ]
        if len(frames) != 1:
            print("Hãy mở đúng một form Expense Invoice trên WFX rồi chạy lại.")
            return 1
        options = read_expense_options(frames[0])
    OPTIONS_SEED.write_text(
        json.dumps(
            {"generated": date.today().isoformat(), "options": options},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    counts = ", ".join(f"{key}={len(values)}" for key, values in options.items())
    print(f"Đã ghi {OPTIONS_SEED.name}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
