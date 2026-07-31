param(
  [switch]$SkipAppBuild,
  [string]$SourceDir = "",
  [string]$OutputDir = "",
  [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

if (-not $SkipAppBuild) {
  & (Join-Path $projectRoot "build-panel.ps1")
  if ($LASTEXITCODE -ne 0) {
    throw "Không build được ứng dụng Windows."
  }
}

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
  $SourceDir = Join-Path $projectRoot "dist\WFX-Panel"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path $projectRoot "dist\installer"
}
$SourceDir = [IO.Path]::GetFullPath($SourceDir)
$OutputDir = [IO.Path]::GetFullPath($OutputDir)

$mainExe = Join-Path $SourceDir "WFX-Panel.exe"
$runtimeDir = Join-Path $SourceDir "_internal"
if (-not (Test-Path -LiteralPath $mainExe -PathType Leaf)) {
  throw "Thiếu file build: $mainExe"
}
if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) {
  throw "Thiếu runtime PyInstaller: $runtimeDir"
}

if ([string]::IsNullOrWhiteSpace($InnoCompiler)) {
  $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
  if ($null -ne $command) {
    $InnoCompiler = $command.Source
  }
}
if ([string]::IsNullOrWhiteSpace($InnoCompiler)) {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  )
  $InnoCompiler = $candidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
}
if (
  [string]::IsNullOrWhiteSpace($InnoCompiler) -or
  -not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)
) {
  throw (
    "Chưa có Inno Setup. Cài bằng: " +
    "winget install --id JRSoftware.InnoSetup --exact"
  )
}

$version = (& python -c "from wfx_panel.version import APP_VERSION; print(APP_VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Không đọc được APP_VERSION."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$installerScript = Join-Path $projectRoot "installer\WFX-Smart.iss"
$arguments = @(
  "/DAppVersion=$version",
  "/DSourceDir=$SourceDir",
  "/DOutputDir=$OutputDir",
  $installerScript
)
& $InnoCompiler @arguments
if ($LASTEXITCODE -ne 0) {
  throw "Inno Setup build thất bại."
}

$setupPath = Join-Path $OutputDir "WFX-Smart-Setup-v$version.exe"
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
  throw "Không tìm thấy bộ cài sau khi build: $setupPath"
}
$setupHash = (Get-FileHash -LiteralPath $setupPath -Algorithm SHA256).Hash
Write-Host "Build xong: $setupPath"
Write-Host "SHA256: $setupHash"
