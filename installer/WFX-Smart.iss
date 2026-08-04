#define MyAppName "WFX Smart"
#define MyAppPublisher "WFX Smart"
#define MyAppExeName "WFX-Panel.exe"

#ifndef AppVersion
  #error AppVersion must be provided with /DAppVersion=x.y.z
#endif
#ifndef SourceDir
  #error SourceDir must be provided with /DSourceDir=path
#endif
#ifndef OutputDir
  #define OutputDir AddBackslash(SourcePath) + "..\dist\installer"
#endif

[Setup]
AppId={{FA15EF75-74AD-463A-AFF0-272145061A2B}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/sieuxuan/WFX-APP
AppSupportURL=https://github.com/sieuxuan/WFX-APP/issues
AppUpdatesURL=https://github.com/sieuxuan/WFX-APP/releases/latest
DefaultDirName={localappdata}\Programs\WFX Smart
DefaultGroupName=WFX Smart
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
RestartApplications=no
SetupIconFile=..\wfx_panel\assets\wfx.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir={#OutputDir}
OutputBaseFilename=WFX-Smart-Setup-v{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WFX Smart"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\WFX Smart"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Open WFX Smart"; Flags: nowait postinstall skipifsilent

[Code]
function WriteCloseAppScript(const ScriptPath: String): Boolean;
var
  Script: String;
begin
  Script :=
    'param([string]$TargetPath)' + #13#10 +
    '$target = [System.IO.Path]::GetFullPath($TargetPath)' + #13#10 +
    'function Get-WfxProcess {' + #13#10 +
    '  @(Get-CimInstance Win32_Process -Filter "Name=''WFX-Panel.exe''" -ErrorAction SilentlyContinue | Where-Object {' + #13#10 +
    '    $process = $_' + #13#10 +
    '    $process.ExecutablePath -and [System.StringComparer]::OrdinalIgnoreCase.Equals(' + #13#10 +
    '      [System.IO.Path]::GetFullPath($process.ExecutablePath), $target)' + #13#10 +
    '  })' + #13#10 +
    '}' + #13#10 +
    '$processes = @(Get-WfxProcess)' + #13#10 +
    'foreach ($process in $processes) {' + #13#10 +
    '  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue' + #13#10 +
    '}' + #13#10 +
    '$deadline = [DateTime]::UtcNow.AddSeconds(5)' + #13#10 +
    'do {' + #13#10 +
    '  $remaining = @(Get-WfxProcess)' + #13#10 +
    '  if ($remaining.Count -eq 0) { exit 0 }' + #13#10 +
    '  Start-Sleep -Milliseconds 100' + #13#10 +
    '} while ([DateTime]::UtcNow -lt $deadline)' + #13#10 +
    'exit 1' + #13#10;
  Result := SaveStringToFile(ScriptPath, Script, False);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  HelperPath: String;
  TargetPath: String;
  ResultCode: Integer;
begin
  Result := '';
  HelperPath := ExpandConstant('{tmp}\wfx-close-installed-app.ps1');
  TargetPath := ExpandConstant('{app}\{#MyAppExeName}');
  if not WriteCloseAppScript(HelperPath) then
  begin
    Result := 'Không thể chuẩn bị đóng WFX Smart để bắt đầu nâng cấp.';
    Exit;
  end;
  if not Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + HelperPath + '" "' + TargetPath + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Result := 'Không thể đóng WFX Smart để bắt đầu nâng cấp.';
  end;
  if (Result = '') and (ResultCode <> 0) then
  begin
    Result := 'WFX Smart chưa đóng được. Hãy thoát ứng dụng rồi thử lại.';
  end;
end;
