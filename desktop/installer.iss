; Inno Setup 6 script (Inno Setup is free: https://jrsoftware.org/isinfo.php)
; Build:  iscc desktop\installer.iss   (after PyInstaller produced dist\Tahqiq)
#define AppName "Tahqiq"
#define AppVersion "1.0.0"

[Setup]
AppId={{6F1B6C1E-3B8E-4C3E-9C55-7A61D0B7E1A2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Tahqiq
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
; Per-user install: no administrator rights needed
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=Tahqiq-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#AppName}

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Tahqiq\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\USER_MANUAL_AR.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Tahqiq.exe"
Name: "{group}\دليل المستخدم"; Filename: "{app}\docs\USER_MANUAL_AR.md"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Tahqiq.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Tahqiq.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Note: the database in %LOCALAPPDATA%\Tahqiq is intentionally NOT removed on
; uninstall, to prevent accidental data loss. Delete it manually if required.
