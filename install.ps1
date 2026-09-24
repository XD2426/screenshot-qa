# install.ps1 - one-time setup: venv + deps + output dir
# ASCII only. Run in PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $base
$log = Join-Path $base "install.log"
function Say($m) { Write-Host $m; Add-Content -Path $log -Value $m -Encoding UTF8 }

Say "== screenshot-qa install =="
Say "base: $base"

# 1) locate a Python that ships tkinter (needed by calibrate.py's drag-select window)
$cands = @(
    "C:\Python314\python.exe",
    "C:\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
)
$py = $null
foreach ($c in $cands) {
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $py) { Say "ERROR: no python found. Install Python 3.11+ from python.org (with tkinter)."; exit 1 }

$hasTk = & $py -c "import tkinter; print('yes')" 2>$null
if ($hasTk -ne "yes") {
    Say "WARN: $py has no tkinter -> calibrate.py cannot run with it."
    Say "      Install the official python.org build (tkinter included) and rerun."
}
Say "python: $py"

# 2) venv
$venv = Join-Path $base ".venv"
if (-not (Test-Path $venv)) {
    & $py -m venv $venv
    Say "venv created: $venv"
} else {
    Say "venv exists: $venv"
}
$vpy = Join-Path $venv "Scripts\python.exe"
$vpyw = Join-Path $venv "Scripts\pythonw.exe"

# 3) deps
& $vpy -m pip install --upgrade pip | Out-Null
& $vpy -m pip install -r (Join-Path $base "requirements.txt")
Say "deps installed"

# 4) output dir
$out = "D:\screenshots"
if (-not (Test-Path $out)) { New-Item -ItemType Directory -Path $out | Out-Null }
Say "output dir ready: $out"

Say ""
Say "NEXT:"
Say "  1) $vpy calibrate.py      (drag the question area, Enter to save)"
Say "  2) $vpyw capture.py       (run in background; or double-click start_capture.vbs)"
Say "  3) press F8 to shoot -> $out\latest.png"
Say ""
Say "NOTE: global hotkey is implemented with ctypes in hotkey.py (no third-party lib,"
Say "      admin rights are NOT required). Self-test it with:"
Say "        $vpy hotkey.py f8"
Say "      then press F8; it should print HIT. Ctrl+C to exit."
