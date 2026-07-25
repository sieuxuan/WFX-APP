## WFX Floating Panel (Python, thay extension)

Chạy dev:
    python -m pip install -r requirements-dev.txt
    python -m playwright install chromium
    python -m wfx_panel.panel_app

- Hotkey toàn cục Ctrl+Shift+X: ẩn/hiện panel (kể cả khi focus ở Chrome).
- Nút đóng hoặc hotkey thu panel về system tray; tray có "Hiện panel" / "Thoát".
- Tài khoản lưu ở `.env`; theme/tuỳ chọn ở `prefs.json`.
- App cũ `app.py` (tkinter) vẫn giữ làm dự phòng.
