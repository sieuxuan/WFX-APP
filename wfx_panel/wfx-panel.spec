# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path.cwd()
datas = [
    ("ui", "wfx_panel/ui"),
    ("manual", "wfx_panel/manual"),
    ("assets/wfx.ico", "wfx_panel/assets"),
    ("../Article List.csv", "."),
]
sync_config = project / "wfx_panel" / "assets" / "sync-config.json"
if sync_config.is_file():
    datas.append((str(sync_config), "wfx_panel/assets"))
# Lưu ý: đường dẫn nguồn (script/datas trái/icon) trong spec được PyInstaller
# phân giải tương đối SPECPATH (thư mục chứa chính file .spec này), tức
# wfx_panel/ — không phải theo cwd lúc gọi lệnh build. Vì spec nằm ở
# wfx_panel/wfx-panel.spec nên các đường dẫn nguồn ở đây viết tương đối so
# với wfx_panel/ ("panel_app.py", "ui", "assets/wfx.ico"), còn vế đích của
# datas vẫn giữ "wfx_panel/..." để khớp wfx_panel/prefs.py APP_DIR (parent.parent
# của module đã đóng gói) khi ứng dụng chạy ở dạng frozen.
a = Analysis(
    ["panel_app.py"],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "login",
        "wfx_panel.catalog_controller",
        "wfx_panel.manual_book",
        "wfx_panel._signing_identity",
        "wfx_panel.secret",
        "wfx_panel.automation",
        "wfx_panel.automation.browser",
        "wfx_panel.automation.session",
        "wfx_panel.automation.catalog",
        "wfx_panel.automation.costing",
        "wfx_panel.automation.modules",
        "wfx_panel.automation.oc",
        "wfx_panel.automation.directory",
        "wfx_panel.automation.dispatch",
        "wfx_panel.automation._common",
        "wfx_panel.costing_planner",
        "wfx_panel.costing_workbook",
        "wfx_panel.oc_workbook",
        "openpyxl",
        "pystray._win32",
        "keyboard",
    ],
    hookspath=[],
    runtime_hooks=[],
    # WFX Smart chạy pywebview bằng WebView2/WinForms trên Windows. Các backend
    # Qt cùng dependency phân tích ảnh/ký SSL tùy chọn bị hook của pywebview và
    # Pillow kéo vào dù app không gọi tới; loại chúng giúp giảm hơn 100 MB mà
    # không đụng tới Playwright hoặc pythonnet cần cho runtime thật.
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "numpy",
        "cryptography",
        "yaml",
        "psutil",
        "tkinter",
        "IPython",
        "matplotlib",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WFX-Panel",
          console=False, icon="assets/wfx.ico", version="version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="WFX-Panel")
