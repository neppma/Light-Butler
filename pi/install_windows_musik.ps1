# install_windows_musik.ps1 - Windows-PC als Musik-Rechner (Gegenstueck zu install_mac.sh): Light-Butler Helfer und
# Mixxx-Bruecke, OHNE den Light-Butler selbst. Das Licht macht der Pi oder ein anderer Rechner.
# Ohne Administratorrechte. Aufruf im entpackten Ordner:
#   powershell -ExecutionPolicy Bypass -File install_windows_musik.ps1 [-LightButler NAME] [-OhneAutostart] [-Entfernen]
# Programme nach %USERPROFILE%\Light-Butler-Musik, Daten (Analysen, Mixxx-Kopie) in %USERPROFILE%\Light-Butler,
# Meldungen in %LOCALAPPDATA%\Light-Butler (helfer.log, bridge.log, launcher.log).
param(
    [string]$LightButler = "",
    [string]$Ziel = (Join-Path $env:USERPROFILE "Light-Butler-Musik"),
    [switch]$OhneAutostart,
    [switch]$Entfernen
)
$ErrorActionPreference = "Stop"
$Task = "Light-Butler Helfer"
$Venv = Join-Path $Ziel "venv"
$Helfer = Join-Path $Ziel "helfer"
$LogDir = Join-Path $env:LOCALAPPDATA "Light-Butler"
$PiFile = Join-Path $env:USERPROFILE ".light-butler-pi"
$Links = @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))

function Stop-Helfer {
    # nur Prozesse aus diesem Programmordner (Befehlszeile enthaelt $Ziel); Pegelkurven-Waechter und Light-Butler bleiben
    if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($Ziel.ToLower()) -and
                       $_.CommandLine -notmatch 'install_windows_musik\.ps1' } |
        ForEach-Object { & taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null }
}

if ($Entfernen) {
    Stop-Helfer
    if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $Task -Confirm:$false }
    foreach ($d in $Links) { $l = Join-Path $d "Light-Butler Mixxx.lnk"; if (Test-Path $l) { Remove-Item -Force $l } }
    foreach ($d in $Venv, $Helfer) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
    Write-Host "Entfernt: Aufgabe '$Task', Verknuepfung, Programme und Python-Umgebung. Daten bleiben in %USERPROFILE%\Light-Butler."
    exit 0
}

$Src = Join-Path $PSScriptRoot "helfer"
if (-not (Test-Path (Join-Path $Src "helper\helper.py"))) { throw "helfer\helper\helper.py fehlt neben diesem Skript (ZIP vollstaendig entpackt?)" }

Write-Host "== 1/4 Light-Butler-Rechner =="
$Default = "lightbutler.local"
if (Test-Path $PiFile) { $old = (Get-Content $PiFile -TotalCount 1).Trim(); if ($old) { $Default = $old } }
if (-not $LightButler) {
    $LightButler = Read-Host "Name oder Adresse des Light-Butler (Pi oder PC mit dem Licht) [$Default]"
    if (-not $LightButler) { $LightButler = $Default }
}
$LightButler = $LightButler.Trim()
if ($LightButler -notmatch '^[A-Za-z0-9._-]+$') { throw "Ungueltiger Name: $LightButler" }
[IO.File]::WriteAllText($PiFile, $LightButler + "`n", (New-Object Text.UTF8Encoding $false))
Write-Host "  Light-Butler: $LightButler (gemerkt in $PiFile)"

Write-Host "== 2/4 Python =="
$Py = $null
foreach ($v in "3.12", "3.11", "3.10", "3.9") {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $Py = @("py", "-$v"); break } } catch { }
}
if (-not $Py) { throw "Kein Python 3.9 bis 3.12 gefunden. Bitte Python 3.12 von python.org installieren (Haken bei 'Add python.exe to PATH')." }
Write-Host "Python:" (& $Py[0] $Py[1] --version)
Stop-Helfer
New-Item -ItemType Directory -Force -Path $Ziel, $LogDir | Out-Null
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Lege die Umgebung an: $Venv"
    & $Py[0] $Py[1] -m venv $Venv
}
$VPy = Join-Path $Venv "Scripts\python.exe"
$VPyw = Join-Path $Venv "Scripts\pythonw.exe"
& $VPy -m pip install -q --upgrade pip
& $VPy -m pip install -q numpy scipy soundfile sounddevice mido
if ($LASTEXITCODE -ne 0) { throw "Python-Pakete liessen sich nicht installieren" }
& $VPy -m pip install -q python-rtmidi
if ($LASTEXITCODE -ne 0) { Write-Host "Hinweis: python-rtmidi fehlt: Mixxx-Bruecke, APC und Lumi gehen dann nicht." }

Write-Host "== 3/4 Programme nach $Helfer =="
robocopy $Src $Helfer /MIR /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)" }
$MxStart = Join-Path $Helfer "mixxx_bridge\mixxx_start.py"
$MxBin = Join-Path $env:ProgramFiles "Mixxx\mixxx.exe"
$sh = New-Object -ComObject WScript.Shell
foreach ($d in $Links) {
    $lnk = $sh.CreateShortcut((Join-Path $d "Light-Butler Mixxx.lnk"))
    $lnk.TargetPath = $VPyw
    $lnk.Arguments = '"' + $MxStart + '"'
    $lnk.WorkingDirectory = Split-Path $MxStart
    if (Test-Path $MxBin) { $lnk.IconLocation = "$MxBin,0" }
    $lnk.Description = "Mixxx mit der Light-Butler Mixxx-Bruecke starten"
    $lnk.Save()
}
Write-Host "  Verknuepfung 'Light-Butler Mixxx' (Startmenue und Desktop)"
if (-not (Test-Path $MxBin)) { Write-Host "  Hinweis: Mixxx nicht in $MxBin gefunden. Anderer Ort: %USERPROFILE%\Light-Butler\config.json, Feld mixxx_bin." }

Write-Host "== 4/4 Helfer =="
# Helfer: Liedliste, Vorhoeren (Port 9025), Analyse, Datenpflege, APC/Lumi an diesem PC und Ton an den Light-Butler.
# Pegelkurven macht das eigene Paket light-butler-windows.zip (install_stems.ps1).
$Run = Join-Path $Ziel "helfer_start.cmd"
$cmd = "@echo off`r`nset PYTHONUTF8=1`r`ncd /d `"$Helfer\helper`"`r`n`"$VPy`" -u helper.py $LightButler --no-stems >> `"$LogDir\helfer.log`" 2>&1`r`n"
[IO.File]::WriteAllText($Run, $cmd, (New-Object Text.ASCIIEncoding))
if (-not $OhneAutostart) {
    $act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Run`"" -WorkingDirectory $Ziel
    $trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
           -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $Task -Action $act -Trigger $trg -Settings $set -Force `
        -Description "Light-Butler Helfer: Musik, APC, Lumi und Ton an den Light-Butler (startet beim Anmelden)" | Out-Null
    Start-ScheduledTask -TaskName $Task
    Write-Host "Helfer laeuft (Aufgabe '$Task', startet bei jeder Anmeldung). Log: $LogDir\helfer.log"
} else {
    Write-Host "Ohne Autostart. Starten: $Run"
}
Write-Host ""
Write-Host "Mixxx: einmalig loopMIDI (tobias-erichsen.de) installieren, Anschluss 'Light-Butler' anlegen; in Mixxx"
Write-Host "Einstellungen -> Controller -> Light-Butler aktivieren, Mapping 'Light-Butler Bridge'. Dann Mixxx immer ueber"
Write-Host "'Light-Butler Mixxx' starten."
Write-Host "Ton an den Light-Butler: VB-Cable, Stereomix oder Line-In (der Reihe nach gesucht); am Light-Butler im Panel"
Write-Host "den Audio-Eingang 'Musik-Rechner (Netzwerk)' waehlen. Windows fragt evtl. nach der Firewall: nur 'Private Netzwerke' zulassen."
