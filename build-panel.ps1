param(
  [switch]$SkipDependencies,
  [string]$BuildPython = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$buildVenv = Join-Path $projectRoot ".build-venv"
$venvPython = Join-Path $buildVenv "Scripts\python.exe"
$buildRoot = Join-Path $projectRoot "dist\WFX-Panel"
$buildExe = Join-Path $buildRoot "WFX-Panel.exe"

$runningBuild = Get-CimInstance Win32_Process `
  -Filter "Name = 'WFX-Panel.exe'" `
  -ErrorAction SilentlyContinue |
  Where-Object {
    [StringComparer]::OrdinalIgnoreCase.Equals($_.ExecutablePath, $buildExe)
  } |
  Select-Object -First 1
if ($null -ne $runningBuild) {
  throw (
    "Hãy đóng WFX Smart đang chạy từ dist trước khi build " +
    "(PID $($runningBuild.ProcessId))."
  )
}

if ([string]::IsNullOrWhiteSpace($BuildPython)) {
  if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
      & $launcher.Source -3.12 -c "import sys" *> $null
      if ($LASTEXITCODE -eq 0) {
        & $launcher.Source -3.12 -m venv $buildVenv
      }
    }
    if (
      $LASTEXITCODE -ne 0 -or
      -not (Test-Path -LiteralPath $venvPython -PathType Leaf)
    ) {
      $uv = Get-Command "uv.exe" -ErrorAction SilentlyContinue
      if ($null -eq $uv) {
        throw (
          "Cần Python 3.12 để build giống CI. Hãy cài Python 3.12 hoặc uv."
        )
      }
      & $uv.Source venv --python 3.12 $buildVenv
    }
    if (
      $LASTEXITCODE -ne 0 -or
      -not (Test-Path -LiteralPath $venvPython -PathType Leaf)
    ) {
      throw "Không tạo được môi trường build Python 3.12."
    }
  }
  $BuildPython = $venvPython
}

$BuildPython = [IO.Path]::GetFullPath($BuildPython)
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
  throw "Không tìm thấy Python build: $BuildPython"
}
$pythonVersion = (& $BuildPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.12") {
  throw "Build release yêu cầu Python 3.12; đang dùng Python $pythonVersion."
}

if (-not $SkipDependencies) {
  & $BuildPython -m pip --version *> $null
  if ($LASTEXITCODE -eq 0) {
    & $BuildPython -m pip install -r (
      Join-Path $projectRoot "requirements-dev.txt"
    )
  } else {
    $uv = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($null -eq $uv) {
      throw "Môi trường build chưa có pip và không tìm thấy uv."
    }
    & $uv.Source pip install `
      --python $BuildPython `
      -r (Join-Path $projectRoot "requirements-dev.txt")
  }
  if ($LASTEXITCODE -ne 0) { throw "Không cài được build dependencies." }
}
& $BuildPython (Join-Path $projectRoot "wfx_panel\assets\generate_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Không tạo được icon." }
& $BuildPython -m PyInstaller `
  --noconfirm `
  --clean `
  --workpath (Join-Path $projectRoot "build") `
  --distpath (Join-Path $projectRoot "dist") `
  (Join-Path $projectRoot "wfx_panel\wfx-panel.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build thất bại." }

$runtimeDir = Join-Path $buildRoot "_internal"
if (-not (Test-Path -LiteralPath $buildExe -PathType Leaf)) {
  throw "Bản build thiếu WFX-Panel.exe."
}
if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) {
  throw "Bản build thiếu thư mục _internal."
}
if (-not (Test-Path -LiteralPath (Join-Path $runtimeDir "python312.dll"))) {
  throw "Bản build không chứa Python 3.12 runtime."
}
if (Test-Path -LiteralPath (Join-Path $runtimeDir "python314.dll")) {
  throw "Bản build còn Python 3.14 runtime ngoài chuẩn release."
}
$buildBytes = (
  Get-ChildItem -LiteralPath $buildRoot -Recurse -File |
    Measure-Object -Property Length -Sum
).Sum
$buildSizeMb = [math]::Round($buildBytes / 1MB, 1)
if ($buildSizeMb -gt 180) {
  throw "Bản đóng gói vượt giới hạn 180 MB: $buildSizeMb MB."
}
Write-Host "Build xong: dist/WFX-Panel/WFX-Panel.exe ($buildSizeMb MB)"
