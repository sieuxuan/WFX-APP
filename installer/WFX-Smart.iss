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
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd
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
