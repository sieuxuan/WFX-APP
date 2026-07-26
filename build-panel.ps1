python -m pip install -r requirements-dev.txt
python wfx_panel/assets/generate_icon.py
python -m PyInstaller --noconfirm --clean wfx_panel/wfx-panel.spec
Write-Host "Build xong: dist/WFX-Panel/WFX-Panel.exe"
