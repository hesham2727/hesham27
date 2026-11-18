; Inno Setup 6 script — builds FBOSINT-Setup-<version>.exe
; Compile:  iscc packaging\installer.iss   (after PyInstaller produced dist\FBOSINT)
#define AppName "FBOSINT Analyzer"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "FBOSINT"
#define AppExe "FBOSINT.exe"

[Setup]
; Fixed AppId => newer installers upgrade in place (easy updates); user data in %APPDATA%\FBOSINT is preserved
AppId={{6C1E5B9A-4F0D-4C7E-9A61-2B8C0F3D7E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\FBOSINT
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\fbosint.ico
OutputDir=..\dist\installer
OutputBaseFilename=FBOSINT-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=commandline dialog
CloseApplications=yes
ShowLanguageDialog=auto

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Arabic.isl")
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "firewall"; Description: "Allow FBOSINT-Server through Windows Firewall (Network mode only)"; Flags: unchecked

[Files]
Source: "..\dist\FBOSINT\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\windows\*.bat"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\docs\INSTALL_AR.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\USER_MANUAL_AR.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{group}\FBOSINT Server (Network mode)"; Filename: "{app}\tools\start-network-server.bat"; IconFilename: "{app}\FBOSINT-Server.exe"
Name: "{group}\Backup now"; Filename: "{app}\tools\backup.bat"
Name: "{group}\User manual (Arabic)"; Filename: "{app}\docs\USER_MANUAL_AR.md"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""FBOSINT Server"" dir=in action=allow program=""{app}\FBOSINT-Server.exe"" enable=yes profile=private"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""FBOSINT Server"""; Flags: runhidden; RunOnceId: "fw"
