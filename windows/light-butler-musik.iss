; Light-Butler-Musik-Setup.exe (Inno Setup 6, 16.11.2026): Windows-PC als Musik-Rechner, ohne den Light-Butler selbst.
; Dieselbe Exe wie light-butler.iss (windows\build_exe.py), aber ohne lichtshow\: Light-Butler Helfer (Musik-Datenbank,
; Vorhoeren, Analyse, Datenpflege, APC, Lumi, Ton an den Light-Butler) und Mixxx mit der Mixxx-Bruecke.
; Fragt nach der Adresse des Light-Butler und merkt sie in %USERPROFILE%\.light-butler-pi (wie am Mac).
;     ISCC.exe /DAppVersion=1.0 windows\light-butler-musik.iss   -> windows\build\Light-Butler-Musik-Setup.exe

#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{B3C2E4A1-7D59-4C8E-9A61-2F0D8E5B7C34}
AppName=Light-Butler Musik-Rechner
AppVersion={#AppVersion}
AppVerName=Light-Butler Musik-Rechner {#AppVersion}
AppPublisher=Markus Nepp
AppPublisherURL=https://github.com/neppma/Light-Butler
AppSupportURL=https://github.com/neppma/Light-Butler
AppCopyright=Copyright (C) 2026 Markus Nepp, GPLv3
DefaultDirName={localappdata}\Programs\Light-Butler-Musik
DefaultGroupName=Light-Butler
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
OutputDir=build
OutputBaseFilename=Light-Butler-Musik-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=light-butler.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Light-Butler.exe
UninstallDisplayName=Light-Butler Musik-Rechner
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.DesktopIcon=Symbol „Mixxx mit Light-Butler“ auf dem Desktop
en.DesktopIcon=Desktop icon "Mixxx with Light-Butler"
de.Autostart=Helfer beim Anmelden an Windows starten (empfohlen)
en.Autostart=Start the Helper when signing in to Windows (recommended)
de.Extra=Zusätzlich:
en.Extra=Additional:
de.MixxxLink=Mixxx mit Light-Butler
en.MixxxLink=Mixxx with Light-Butler
de.HelperLink=Light-Butler Helfer starten
en.HelperLink=Start Light-Butler Helper
de.StartNow=Helfer jetzt starten
en.StartNow=Start the Helper now
de.Uninstall=Light-Butler Musik-Rechner deinstallieren
en.Uninstall=Uninstall Light-Butler music computer
de.PiTitle=Light-Butler im Netzwerk
en.PiTitle=Light-Butler in the network
de.PiDesc=Wohin gehen Ton, Lieder und Tasten?
en.PiDesc=Where do sound, songs and keys go?
de.PiText=Name oder IP-Adresse des Rechners mit dem Light-Butler (Raspberry Pi, PC oder Mac). Steht im Panel unter Einstellungen; meist lightbutler.local.
en.PiText=Name or IP address of the computer running the Light-Butler (Raspberry Pi, PC or Mac). Shown in the panel under Settings; usually lightbutler.local.
de.PiLabel=Light-Butler:
en.PiLabel=Light-Butler:
de.PiBad=Bitte nur Buchstaben, Ziffern, Punkt, Bindestrich und Unterstrich eingeben.
en.PiBad=Please use only letters, digits, dot, hyphen and underscore.

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Extra}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:Extra}"

[Files]
; nur Python (Exe) und der Musik-Teil; der Light-Butler selbst (lichtshow\) laeuft auf einem anderen Rechner
Source: "build\dist\Light-Butler\*"; DestDir: "{app}"; Excludes: "\lichtshow,\LIESMICH.txt"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "light-butler.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{cm:MixxxLink}"; Filename: "{app}\Light-Butler.exe"; Parameters: """{app}\helfer\mixxx_bridge\mixxx_start.py"""; WorkingDir: "{app}\helfer\mixxx_bridge"; IconFilename: "{app}\light-butler.ico"
Name: "{group}\{cm:HelperLink}"; Filename: "{app}\Light-Butler.exe"; Parameters: "--musik"; WorkingDir: "{app}"; IconFilename: "{app}\light-butler.ico"
Name: "{group}\{cm:Uninstall}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{cm:MixxxLink}"; Filename: "{app}\Light-Butler.exe"; Parameters: """{app}\helfer\mixxx_bridge\mixxx_start.py"""; WorkingDir: "{app}\helfer\mixxx_bridge"; IconFilename: "{app}\light-butler.ico"; Tasks: desktopicon
Name: "{userstartup}\Light-Butler Helfer"; Filename: "{app}\Light-Butler.exe"; Parameters: "--musik"; WorkingDir: "{app}"; IconFilename: "{app}\light-butler.ico"; Tasks: autostart

[Run]
; aeltere Installation per PowerShell (Aufgabe "Light-Butler Helfer") abmelden, sonst liefen zwei Helfer
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Light-Butler Helfer"" /F"; Flags: runhidden
Filename: "{app}\Light-Butler.exe"; Parameters: "--musik"; WorkingDir: "{app}"; Description: "{cm:StartNow}"; Flags: nowait postinstall skipifsilent runhidden

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
  if CurUninstallStep = usPostUninstall then
    DelTree(ExpandConstant('{app}'), True, True, True);   { nur Programme, die Daten liegen in Light-Butler-Daten }
end;

var
  PiPage: TInputQueryWizardPage;

function PiFile: String;
begin
  Result := ExpandConstant('{%USERPROFILE}\.light-butler-pi');
end;

function ValidHost(S: String): Boolean;
var
  i: Integer;
  c: Char;
begin
  Result := Length(S) > 0;
  for i := 1 to Length(S) do
  begin
    c := S[i];
    if not (((c >= 'a') and (c <= 'z')) or ((c >= 'A') and (c <= 'Z')) or ((c >= '0') and (c <= '9'))
            or (c = '.') or (c = '-') or (c = '_')) then
      Result := False;
  end;
end;

procedure InitializeWizard;
var
  Old: AnsiString;
  Def: String;
begin
  PiPage := CreateInputQueryPage(wpSelectTasks, CustomMessage('PiTitle'), CustomMessage('PiDesc'), CustomMessage('PiText'));
  PiPage.Add(CustomMessage('PiLabel'), False);
  Def := 'lightbutler.local';
  if LoadStringFromFile(PiFile, Old) then
  begin
    Old := Trim(Old);
    if ValidHost(Old) then
      Def := Old;
  end;
  PiPage.Values[0] := Def;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PiPage.ID) and not ValidHost(Trim(PiPage.Values[0])) then
  begin
    MsgBox(CustomMessage('PiBad'), mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    SaveStringToFile(PiFile, Trim(PiPage.Values[0]) + #10, False);
end;
