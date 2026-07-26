# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path.cwd()
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
    datas=[
        ("ui", "wfx_panel/ui"),
        ("assets/wfx.ico", "wfx_panel/assets"),
    ],
    hiddenimports=["login", "pystray._win32", "keyboard"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WFX-Panel",
          console=False, icon="assets/wfx.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="WFX-Panel")
