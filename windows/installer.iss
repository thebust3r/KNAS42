; KNAS 42 for Windows installer (Inno Setup 6). Built by .github/workflows/windows-app.yml:
;   ISCC /DMyVersion=1.2.0 windows\installer.iss
#ifndef MyVersion
  #define MyVersion "1.0.0"
#endif

[Setup]
AppId={{8B5D6A2E-42C1-4F0A-9A42-4B4E41533432}
AppName=KNAS 42
AppVersion={#MyVersion}
AppVerName=KNAS 42 {#MyVersion}
AppPublisher=thebust3r
AppPublisherURL=https://github.com/thebust3r/knas42
AppSupportURL=https://github.com/thebust3r/knas42
DefaultDirName={autopf}\KNAS 42
DefaultGroupName=KNAS 42
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=KNAS42-Setup-{#MyVersion}
SetupIconFile=..\build\knas.ico
UninstallDisplayIcon={app}\KNAS42.exe
UninstallDisplayName=KNAS 42
WizardStyle=modern
WizardImageFile=..\build\wizard-0.bmp,..\build\wizard-1.bmp,..\build\wizard-2.bmp,..\build\wizard-3.bmp,..\build\wizard-4.bmp
WizardSmallImageFile=..\build\wizard-small-0.bmp,..\build\wizard-small-1.bmp,..\build\wizard-small-2.bmp,..\build\wizard-small-3.bmp,..\build\wizard-small-4.bmp
WizardImageStretch=yes
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Messages]
WelcomeLabel1=Welcome to KNAS 42
WelcomeLabel2=Your own 90s cable TV, with a channel guide, the local weather channel, sports and more.%n%nThis takes about a minute. When it's done, KNAS opens its setup page so you can pick your town and connect ErsatzTV.
FinishedHeadingLabel=KNAS 42 is ready
FinishedLabel=KNAS runs in the background, with its icon by the clock. Right-click it any time for setup, the TV address, and more.%n%nOn a TV or phone, go to the address KNAS shows you (it ends in :8642/tv).
ClickFinish=Click Finish to tune in.

[Tasks]
Name: "startup"; Description: "Start KNAS when Windows starts (recommended, so your TVs always have it)"; GroupDescription: "Extras:"
Name: "desktopicon"; Description: "Put a KNAS 42 icon on the desktop"; GroupDescription: "Extras:"

[Files]
Source: "..\dist\KNAS42\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\KNAS 42"; Filename: "{app}\KNAS42.exe"
Name: "{group}\KNAS 42 folder"; Filename: "{localappdata}\KNAS42"
Name: "{group}\Uninstall KNAS 42"; Filename: "{uninstallexe}"
Name: "{autodesktop}\KNAS 42"; Filename: "{app}\KNAS42.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KNAS 42"; ValueData: """{app}\KNAS42.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
; let TVs and phones on your home network reach KNAS, without a firewall pop-up
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""KNAS 42"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""KNAS 42"" dir=in action=allow program=""{app}\KNAS42.exe"" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated
Filename: "{app}\KNAS42.exe"; Description: "Start KNAS 42 now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im KNAS42.exe /f"; Flags: runhidden; RunOnceId: "StopKNAS"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""KNAS 42"""; Flags: runhidden; RunOnceId: "Firewall"

[UninstallDelete]
; your KNAS folder (settings, music) in %LOCALAPPDATA%\KNAS42 is kept, in case you reinstall
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer;
begin
  // installing over a running KNAS: stop it first so its files can be replaced
  if CurStep = ssInstall then
    Exec(ExpandConstant('{cmd}'), '/c taskkill /im KNAS42.exe /f', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
