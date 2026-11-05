; SharePoint Navigator installer for Windows (Inno Setup 6). Built by build_app.py, which passes
; AppVersion, SourceExe, IconFile, OutputDir and OutputName; see `make_windows_release` there.
;
; Installs for the current user only (no administrator needed) into
; %LOCALAPPDATA%\Programs\SharePoint Navigator, adds a Start menu entry (and a desktop shortcut if
; ticked), and registers an uninstaller in Settings > Apps. The settings folder
; %USERPROFILE%\.sharepoint-navigator is left alone on uninstall, as most apps do; the product page
; says how to remove it. Not signed (owner's decision), so SmartScreen asks once.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "SharePoint Navigator"
#define AppExe "SharePoint Navigator.exe"

[Setup]
; Fixed for good: Windows recognises later versions as updates of the same app by this id.
AppId={{0844FC58-06A8-4C79-B70A-888A4984591E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Yusung Chang
AppPublisherURL=https://yusungchang.com/sharepoint-navigator
AppSupportURL=https://github.com/yusungchang/sharepoint-navigator/issues
AppUpdatesURL=https://yusungchang.com/sharepoint-navigator
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
; Per-user install: {autopf} becomes %LOCALAPPDATA%\Programs and {autoprograms} the user's Start menu.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; A running copy holds its .exe open, so setup closes it first (it has no window to ask from).
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
; Korean ships with recent Inno Setup versions; older ones simply install in English.
#if FileExists(CompilerPath + "Languages\Korean.isl")
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; "Launch SharePoint Navigator" on the last page; it opens in the browser.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop a running copy so its .exe can be removed. The one-file app runs as two processes of the
; same name; /T and /IM end both. Nothing happens when it isn't running.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#AppExe}"""; Flags: runhidden; RunOnceId: "StopApp"
