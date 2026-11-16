# install_windows.ps1 - Light-Butler auf einem Windows-PC einrichten (Wunsch von Markus, 15.11.2026).
# Aus dem Download "Windows: frische Installation" im Panel (Einstellungen, ganz unten). ZIP entpacken, im Ordner:
#     powershell -ExecutionPolicy Bypass -File install_windows.ps1
# Keine Administratorrechte noetig.
#
# Was es tut:
#   1. Python 3.9 bis 3.12 suchen, Umgebung <Ziel>\venv mit numpy, PyYAML, sounddevice, mido, python-rtmidi, pyserial.
#      Dazu aubio (Tempo und Takt wie am Pi); laesst es sich nicht bauen, nimmt die Tempo-Erkennung den Ersatz tempo_np.py.
#   2. Programme nach <Ziel>\lichtshow kopieren. Vorhandene Einstellungen, Szenen, Shows, Geraete (fixtures.yaml,
#      homematic.yaml) und Startoptionen (show.conf) werden nie ueberschrieben: noch einmal ausfuehren = aktualisieren.
#   3. Beim ersten Mal: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Laufen zwei Light-Butler im selben Netz und senden
#      beide, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser sendet.
#   4. Aufgabe "Light-Butler" in der Aufgabenplanung: startet beim Anmelden ohne Fenster (start.ps1), Log in
#      %LOCALAPPDATA%\Light-Butler\show.log. Neustart aus dem Panel (Fixtures) startet dieselbe Aufgabe neu.
# Strobe-Erlaubnis, Laser und Nebel bleiben aus, wie bei jeder neuen Anlage.
#
# Optionen:  -Ziel ORDNER      anderer Ort (Standard %USERPROFILE%\Light-Butler)
#            -OhneAutostart    keine Aufgabe anlegen (Start von Hand: <Ziel>\start.ps1)
#            -Entfernen        Aufgabe und Python-Umgebung entfernen; Programme und Daten in <Ziel>\lichtshow bleiben
param(
    [string]$Ziel = (Join-Path $env:USERPROFILE "Light-Butler"),
    [switch]$OhneAutostart,
    [switch]$Entfernen
)
$ErrorActionPreference = "Stop"
$Task = "Light-Butler"
$Src = Join-Path $PSScriptRoot "lichtshow"
$Dest = Join-Path $Ziel "lichtshow"
$Venv = Join-Path $Ziel "venv"
$LogDir = Join-Path $env:LOCALAPPDATA "Light-Butler"
$Start = Join-Path $Ziel "start.ps1"

function Stop-LightButler {
    if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
    }
    # start.ps1, cmd und der Python-Starter der Umgebung tragen den Installationsordner in der Befehlszeile; das eigentliche
    # Python (Kind des Starters) nicht. Darum jeweils mit allen Kindprozessen beenden (taskkill /T). Andere Programme
    # (z. B. der Pegelkurven-Helfer in s2l-stems) haben den Ordner nicht in der Befehlszeile und bleiben.
    $me = $PID
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($Ziel.ToLower()) -and
                       $_.CommandLine -notmatch 'install_windows\.ps1' } |
        ForEach-Object { cmd /c "taskkill /T /F /PID $($_.ProcessId) >nul 2>&1" }   # schon mit dem Elternprozess weg: still
    Start-Sleep -Milliseconds 500
}

if ($Entfernen) {
    Stop-LightButler
    if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $Task -Confirm:$false }
    if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
    if (Test-Path $Start) { Remove-Item -Force $Start }
    $hd = Join-Path $Ziel "helfer"
    if (Test-Path $hd) { Remove-Item -Recurse -Force $hd }
    foreach ($dir in [Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop")) {
        $l = Join-Path $dir "Light-Butler Mixxx.lnk"; if (Test-Path $l) { Remove-Item -Force $l }
    }              # nur Programme; Daten des Helfers in ~\Light-Butler
    Write-Host "Entfernt: Aufgabe '$Task' und $Venv. Programme und Daten bleiben in $Dest (von Hand loeschen, wenn gewuenscht)."
    exit 0
}

if (-not (Test-Path (Join-Path $Src "show.py"))) { throw "lichtshow\show.py fehlt neben diesem Skript (ZIP vollstaendig entpackt?)" }

Write-Host "== 1/4 Python =="
$Py = $null
foreach ($v in "3.12", "3.11", "3.10", "3.9") {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $Py = @("py", "-$v"); break } } catch { }
}
if (-not $Py) { throw "Kein Python 3.9 bis 3.12 gefunden. Bitte Python 3.12 von python.org installieren (Haken bei 'Add python.exe to PATH')." }
Write-Host "Python:" (& $Py[0] $Py[1] --version)
Stop-LightButler
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Lege die Umgebung an: $Venv"
    & $Py[0] $Py[1] -m venv $Venv
}
$VPy = Join-Path $Venv "Scripts\python.exe"
& $VPy -m pip install -q --upgrade pip
& $VPy -m pip install -q numpy pyyaml sounddevice mido pyserial scipy soundfile
if ($LASTEXITCODE -ne 0) { throw "Python-Pakete liessen sich nicht installieren" }
& $VPy -m pip install -q python-rtmidi
if ($LASTEXITCODE -ne 0) { Write-Host "Hinweis: python-rtmidi fehlt, APC und Lumi per USB gehen dann nicht (alles andere schon)." }
& $VPy -m pip install -q aubio
if ($LASTEXITCODE -ne 0) { Write-Host "Hinweis: aubio liess sich nicht installieren, Tempo und Takt kommen vom Ersatz tempo_np (geht auch)." }

Write-Host "== 2/4 Programme nach $Dest =="
New-Item -ItemType Directory -Force -Path $Dest, $LogDir | Out-Null
$first = -not (Test-Path (Join-Path $Dest "show.py"))
# Programme immer neu; was dieser Anlage gehoert, nie (wie deploy.sh am Pi): *.json, show.conf, backup.conf, Geraete, shows\
robocopy $Src $Dest /E /NFL /NDL /NJH /NJS /NP /XF *.json show.conf backup.conf fixtures.yaml homematic.yaml /XD shows aufnahmen __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)" }
$HelferSrc = Join-Path $PSScriptRoot "helfer"
if (Test-Path (Join-Path $HelferSrc "helper\helper.py")) {           # Musik-Teil des Helfers: nur Programme, Daten in ~\Light-Butler
    robocopy $HelferSrc (Join-Path $Ziel "helfer") /MIR /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Kopieren des Helfers fehlgeschlagen (robocopy $LASTEXITCODE)" }
}
foreach ($f in "fixtures.yaml", "homematic.yaml", "show.conf") {       # nur beim ersten Mal
    if ((Test-Path (Join-Path $Src $f)) -and -not (Test-Path (Join-Path $Dest $f))) {
        Copy-Item (Join-Path $Src $f) (Join-Path $Dest $f)
        Write-Host "  $f angelegt"
    }
}

Write-Host "== 3/4 Einstellungen =="
$Settings = Join-Path $Dest "settings.json"
if (-not (Test-Path $Settings)) {
    [IO.File]::WriteAllText($Settings, "{`n `"ola_out`": 0.0,`n `"wled_out`": 0.0,`n `"nano_out`": 0.0`n}`n", (New-Object Text.UTF8Encoding $false))
    [IO.File]::WriteAllText((Join-Path $Dest "sicherheit.json"), "{`"ok`": false}`n", (New-Object Text.UTF8Encoding $false))   # Sicherheitshinweis (safety.py)
    Write-Host "  Neue Anlage: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Einschalten im Panel: Einstellungen -> Ausgabe."
} else {
    Write-Host "  Vorhandene Einstellungen bleiben."
}

# Startskript: liest show.conf, startet den Light-Butler und startet ihn neu, wenn er mit Code 3 endet (Neustart aus dem Panel)
$StartText = @'
# start.ps1 - startet den Light-Butler (von install_windows.ps1 angelegt). Optionen in lichtshow\show.conf (SHOW_ARGS=...).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = Join-Path $Here "lichtshow"
$VPy = Join-Path $Here "venv\Scripts\python.exe"
$LogDir = Join-Path $env:LOCALAPPDATA "Light-Butler"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "show.log"
$env:PYTHONUTF8 = "1"
$env:LB_RESTART_EXIT = "1"
# Musik-Teil des Helfers (HELFER=1 in show.conf): eigener Prozess ohne Fenster, Log helfer.log. Laeuft schon einer, beendet
# er sich selbst (Prozessdatei). APC, Lumi und Ton haengen am PC direkt am Light-Butler, Pegelkurven: install_stems.ps1.
$Helfer = Join-Path $Here "helfer\helper\helper.py"
$hl = Get-Content (Join-Path $Dest "show.conf") -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*HELFER=' } | Select-Object -Last 1
if ((Test-Path $Helfer) -and -not ($hl -and ($hl -replace '^\s*HELFER=', '').Trim() -eq '0')) {
    $hlog = Join-Path $LogDir "helfer.log"
    Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -WorkingDirectory (Split-Path $Helfer) -ArgumentList ('/c ""' + $VPy + '" -u "' + $Helfer + '" 127.0.0.1 --no-apc --no-lumi --no-audio --no-stems >> "' + $hlog + '" 2>&1"')
}
Set-Location $Dest
do {
    $line = Get-Content (Join-Path $Dest "show.conf") -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*SHOW_ARGS=' } | Select-Object -Last 1
    $args = @()
    if ($line) { $args = @(($line -replace '^\s*SHOW_ARGS=', '').Trim() -split '\s+' | Where-Object { $_ }) }
    Add-Content -Path $Log -Encoding UTF8 -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] Start: show.py " + ($args -join " "))
    # ueber cmd umleiten: PowerShell 5.1 wuerde das Log in UTF-16 schreiben und Fehlerzeilen umwickeln
    $q = ($args | ForEach-Object { '"' + $_ + '"' }) -join " "
    cmd /c ('"' + '"' + $VPy + '" -u show.py ' + $q + ' >> "' + $Log + '" 2>&1' + '"')
    $code = $LASTEXITCODE
} while ($code -eq 3)
Add-Content -Path $Log -Encoding UTF8 -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] Ende (Code $code)")
'@
[IO.File]::WriteAllText($Start, $StartText.Replace("`n", "`r`n"), (New-Object Text.UTF8Encoding $true))

# Verknuepfung "Light-Butler Mixxx" (Startmenue und Desktop): startet Mixxx mit der Mixxx-Bruecke (mixxx_start.py), nur wenn
# Mixxx installiert ist. Braucht loopMIDI mit dem Anschluss "Light-Butler" (siehe LIESMICH).
$MxStart = Join-Path $Ziel "helfer\mixxx_bridge\mixxx_start.py"
$MxBin = Join-Path $env:ProgramFiles "Mixxx\mixxx.exe"
if ((Test-Path $MxStart) -and (Test-Path $MxBin)) {
    $sh = New-Object -ComObject WScript.Shell
    foreach ($dir in [Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop")) {
        $lnk = $sh.CreateShortcut((Join-Path $dir "Light-Butler Mixxx.lnk"))
        $lnk.TargetPath = Join-Path $Venv "Scripts\pythonw.exe"
        $lnk.Arguments = '"' + $MxStart + '"'
        $lnk.WorkingDirectory = Split-Path $MxStart
        $lnk.IconLocation = "$MxBin,0"
        $lnk.Description = "Mixxx mit der Light-Butler Mixxx-Bruecke starten"
        $lnk.Save()
    }
    Write-Host "  Verknuepfung 'Light-Butler Mixxx' angelegt (Startmenue und Desktop)"
}

Write-Host "== 4/4 Start =="
if (-not $OhneAutostart) {
    $act = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Start`"" -WorkingDirectory $Ziel
    $trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
           -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $Task -Action $act -Trigger $trg -Settings $set -Force `
        -Description "Light-Butler: Lichtsteuerung mit Web-Panel auf Port 8080 (startet beim Anmelden)" | Out-Null
    Start-ScheduledTask -TaskName $Task
    Write-Host "Light-Butler laeuft (Aufgabe '$Task', startet bei jeder Anmeldung). Log: $LogDir\show.log"
} else {
    Write-Host "Ohne Autostart. Starten:  powershell -ExecutionPolicy Bypass -File `"$Start`""
}
Write-Host ""
Write-Host "Panel: http://localhost:8080/  (Handy/iPad im Heimnetz: http://$env:COMPUTERNAME`:8080/)"
Write-Host "Windows fragt beim ersten Start evtl. nach der Firewall: 'Private Netzwerke' zulassen, sonst erreichen Handy,"
Write-Host "iPad und der Ton vom Mac den PC nicht."
Write-Host "Erste Schritte: Einstellungen -> Verbindungen (Audio-Eingang), Fixtures (Geraete anlegen), dann Ausgabe einschalten."
