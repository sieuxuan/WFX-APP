"""Shim tương thích ngược: login.py giờ chỉ re-export lớp automation.

Toàn bộ code automation đã chuyển vào package wfx_panel/automation/. Giữ
module `login` để `import login` (tests, panel_api, PyInstaller hiddenimports)
vẫn hoạt động không đổi.
"""

from wfx_panel.automation import *  # noqa: F401,F403
from wfx_panel.automation import __all__  # noqa: F401
