python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Không cài được build dependencies." }
python wfx_panel/assets/generate_icon.py
if ($LASTEXITCODE -ne 0) { throw "Không tạo được icon." }
python -m PyInstaller --noconfirm --clean wfx_panel/wfx-panel.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build thất bại." }
Write-Host "Build xong: dist/WFX-Panel/WFX-Panel.exe"
