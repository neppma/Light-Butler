; Light-Butler-Setup.exe (Inno Setup 6, 16.11.2026): installiert die Exe aus windows\build_exe.py fuer den angemeldeten
; Benutzer, ohne Administrator-Rechte, nach %LOCALAPPDATA%\Programs\Light-Butler (dort darf der Light-Butler seine
; Einstellungen, Szenen und Shows in lichtshow\ neben den Programmen speichern).
; Bau (GitHub Actions, .github/workflows/windows-setup.yml, oder am PC nach build_exe.py):
;     ISCC.exe /DAppVersion=1.0 windows\light-butler.iss      -> windows\build\Light-Butler-Setup.exe
; Erneut installieren = aktualisieren: Programme werden ersetzt; Einstellungen (*.json), shows\, fixtures.yaml und
; show.conf bleiben. Deinstallieren entfernt die Programme, die eigenen Daten bleiben im Ordner.

#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{6B0E8B9E-3C1F-4F43-9D3E-6C2B7A5D4E21}
AppName=Light-Butler
AppVersion={#AppVersion}
AppVerName=Light-Butler {#AppVersion}
AppPublisher=Markus Nepp
AppPublisherURL=https://github.com/neppma/Light-Butler
AppSupportURL=https://github.com/neppma/Light-Butler
AppCopyright=Copyright (C) 2026 Markus Nepp, GPLv3
DefaultDirName={localappdata}\Programs\Light-Butler
DefaultGroupName=Light-Butler
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
OutputDir=build
OutputBaseFilename=Light-Butler-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=light-butler.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Light-Butler.exe
UninstallDisplayName=Light-Butler
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.DesktopIcon=Symbol auf dem Desktop
en.DesktopIcon=Desktop icon
de.Autostart=Beim Anmelden an Windows starten
en.Autostart=Start when signing in to Windows
de.Extra=Zusätzlich:
en.Extra=Additional:
de.OpenPanel=Light-Butler jetzt starten (das Panel öffnet sich im Browser)
en.OpenPanel=Start Light-Butler now (the panel opens in the browser)
de.Readme=Kurzanleitung (LIESMICH)
en.Readme=Quick guide (LIESMICH)
de.Uninstall=Light-Butler deinstallieren
en.Uninstall=Uninstall Light-Butler
de.DelData=Auch die eigenen Daten löschen (Einstellungen, Szenen, Shows, Geräte)?%n%nNein = sie bleiben für eine spätere Installation erhalten.
en.DelData=Also delete your own data (settings, scenes, shows, devices)?%n%nNo = they stay for a later installation.

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Extra}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:Extra}"; Flags: unchecked

[Files]
; Programme (ersetzt bei jedem Update); Einstellungen entstehen erst beim Start und gehoeren nicht dazu
Source: "build\dist\Light-Butler\*"; DestDir: "{app}"; Excludes: "\lichtshow\fixtures.yaml,\lichtshow\show.conf"; Flags: ignoreversion recursesubdirs createallsubdirs
; Geraete und Startoptionen: nur bei der ersten Installation, danach gehoeren sie dem Benutzer
Source: "build\dist\Light-Butler\lichtshow\fixtures.yaml"; DestDir: "{app}\lichtshow"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "build\dist\Light-Butler\lichtshow\show.conf"; DestDir: "{app}\lichtshow"; Flags: onlyifdoesntexist uninsneveruninstall

Source: "light-butler.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Light-Butler"; Filename: "{app}\Light-Butler.exe"; Parameters: "--browser"; WorkingDir: "{app}"; IconFilename: "{app}\light-butler.ico"
Name: "{group}\{cm:Readme}"; Filename: "{app}\LIESMICH.txt"
Name: "{group}\{cm:Uninstall}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Light-Butler"; Filename: "{app}\Light-Butler.exe"; Parameters: "--browser"; WorkingDir: "{app}"; IconFilename: "{app}\light-butler.ico"; Tasks: desktopicon
Name: "{userstartup}\Light-Butler"; Filename: "{app}\Light-Butler.exe"; WorkingDir: "{app}"; IconFilename: "{app}\light-butler.ico"; Tasks: autostart

[Run]
; aeltere Installation per PowerShell (Aufgabe "Light-Butler", install_windows.ps1) abmelden, sonst liefen zwei Light-Butler
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Light-Butler"" /F"; Flags: runhidden
Filename: "{app}\Light-Butler.exe"; Parameters: "--browser"; WorkingDir: "{app}"; Description: "{cm:OpenPanel}"; Flags: nowait postinstall skipifsilent

[Code]
function StopRunning(): Boolean;
var
  rc: Integer;
begin
  { laufenden Light-Butler aus diesem Ordner beenden (auch den Helfer), sonst bleiben Dateien gesperrt }
  Result := Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Get-Process Light-Butler -ErrorAction SilentlyContinue | Where-Object { $_.Path -like ''' + ExpandConstant('{app}') + '\*'' } | Stop-Process -Force; Start-Sleep -Milliseconds 800"', '', SW_HIDE, ewWaitUntilTerminated, rc);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunning();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopRunning();
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{app}')) and not UninstallSilent then
    if MsgBox(CustomMessage('DelData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{app}'), True, True, True);
end;
