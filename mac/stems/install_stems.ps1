# install_stems.ps1 - Pegelkurven-Helfer von Light-Butler am Windows-PC einrichten (Demucs auf der NVIDIA-Grafikkarte).
#
# Die drei Dateien (stems_show.py, stem_curves.py, install_stems.ps1) in einen Ordner legen, sie kommen vom Pi:
#   http://lightbutler.local:8080/helfer/
# Dann in der PowerShell in diesem Ordner:
#   powershell -ExecutionPolicy Bypass -File install_stems.ps1
# Optionen:  -Pi HOST[:PORT]   anderes Ziel (Standard lightbutler.local)
#            -OhneAutostart    keinen Waechter beim Anmelden starten
#            -OhneVorab        Waechter rechnet nur Shows, nicht die Bibliothek vorab
#            -Entfernen        Waechter und Umgebung wieder entfernen
#
# Legt an: %USERPROFILE%\s2l-stems (Python-Umgebung, rund 5 GB mit CUDA), %USERPROFILE%\.light-butler-pi (Ziel),
# Aufgabe "Light-Butler Pegelkurven" (startet beim Anmelden den Waechter ohne Fenster), Log %LOCALAPPDATA%\Light-Butler\stems.log.
# Der Waechter fragt den Pi jede Minute nach Shows ohne Kurven, holt die MP3, rechnet und schickt nur die Kurven zurueck.
# Mit --vorab rechnet er danach Lieder der ganzen Bibliothek vorab, sobald das auf der Seite Statistik gestartet ist
# (MP3s vom Vorhoer-Server am Mac, der Mac mit der Mixxx-Bruecke muss laufen).
# Aufs Licht wirkt das nicht. Keine Administratorrechte noetig.
param(
    [string]$Pi = "lightbutler.local",
    [switch]$OhneAutostart,
    [switch]$OhneVorab,
    [switch]$Entfernen
)
$ErrorActionPreference = "Stop"
$Env = Join-Path $env:USERPROFILE "s2l-stems"
$Helfer = Join-Path $Env "helfer"
$LogDir = Join-Path $env:LOCALAPPDATA "Light-Butler"
$Log = Join-Path $LogDir "stems.log"
$Task = "Light-Butler Pegelkurven"
$Torch = "2.5.1"                       # dieselbe Fassung wie am Mac
$TorchIndex = "https://download.pytorch.org/whl/cu124"   # CUDA 12.4, laeuft mit jedem aktuellen NVIDIA-Treiber

function Stop-Waechter {
    foreach ($t in @($Task)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        }
    }
}

if ($Entfernen) {
    Stop-Waechter
    if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $Task -Confirm:$false }
    if (Test-Path $Env) { Remove-Item -Recurse -Force $Env }
    Write-Host "Entfernt: Aufgabe '$Task' und $Env (Log bleibt in $LogDir)."
    exit 0
}

foreach ($f in "stems_show.py", "stem_curves.py") {
    if (-not (Test-Path (Join-Path $PSScriptRoot $f))) { throw "$f fehlt neben diesem Skript (vom Pi: http://$Pi`:8080/helfer/$f)" }
}

# Python 3.9 bis 3.12 suchen (Torch 2.5 gibt es nicht fuer neuere)
$Py = $null
foreach ($v in "3.12", "3.11", "3.10", "3.9") {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $Py = @("py", "-$v"); break } } catch { }
}
if (-not $Py) { throw "Kein Python 3.9 bis 3.12 gefunden (py -0p zeigt die installierten). Bitte Python 3.12 von python.org installieren." }
Write-Host "Python:" (& $Py[0] $Py[1] --version)

Stop-Waechter
if (-not (Test-Path (Join-Path $Env "Scripts\python.exe"))) {
    Write-Host "Lege die Umgebung an: $Env"
    & $Py[0] $Py[1] -m venv $Env
}
$VPy = Join-Path $Env "Scripts\python.exe"
$VPyw = Join-Path $Env "Scripts\pythonw.exe"
& $VPy -m pip install -q --upgrade pip
Write-Host "Installiere Torch $Torch mit CUDA (gross, dauert ein paar Minuten) ..."
& $VPy -m pip install -q "torch==$Torch" "torchaudio==$Torch" --index-url $TorchIndex
if ($LASTEXITCODE -ne 0) { throw "Torch liess sich nicht installieren" }
& $VPy -m pip install -q demucs soundfile
if ($LASTEXITCODE -ne 0) { throw "Demucs liess sich nicht installieren" }
& $VPy -c "import torch, demucs, soundfile; ok = torch.cuda.is_available(); print('Demucs', demucs.__version__, '| Torch', torch.__version__, '| Grafikkarte:', torch.cuda.get_device_name(0) if ok else 'keine (rechnet auf der CPU)')"

New-Item -ItemType Directory -Force -Path $Helfer, $LogDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot "stems_show.py"), (Join-Path $PSScriptRoot "stem_curves.py") $Helfer -Force
Set-Content -Path (Join-Path $env:USERPROFILE ".light-butler-pi") -Value $Pi -Encoding ascii
$Script = Join-Path $Helfer "stems_show.py"

if (-not $OhneAutostart) {
    $Vorab = if ($OhneVorab) { "" } else { " --vorab" }
    $act = New-ScheduledTaskAction -Execute $VPyw -Argument "`"$Script`" --watch$Vorab --log `"$Log`"" -WorkingDirectory $Helfer
    $trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
           -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $Task -Action $act -Trigger $trg -Settings $set -Force `
        -Description "Light-Butler: rechnet Pegelkurven fuer neue Shows am Pi (Demucs auf der Grafikkarte)" | Out-Null
    Start-ScheduledTask -TaskName $Task
    Write-Host "Waechter laeuft (Aufgabe '$Task', startet bei jeder Anmeldung). Log: $Log"
}
Write-Host ""
Write-Host "Fertig. Stand der Shows:   & `"$VPy`" `"$Script`" --liste"
Write-Host "Eine Show rechnen:         & `"$VPy`" `"$Script`" `"Name der Show`""
