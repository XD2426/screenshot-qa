# build.ps1 -- Build ScreenshotQA with PyInstaller (+ NSIS installer)
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads .ps1 as GBK when no BOM).
#
# IMPORTANT: default is --onedir, NOT --onefile.
#   onefile + tkinter (calibrate/settings GUI, ~1000 tcl/tk data files) makes the exe
#   take ~25s to exit on this machine (PyInstaller onefile temp-dir cleanup).
#   onedir exits in ~0.4s and starts faster. Use -OneFile only if you really need a
#   single portable exe and can live with the slow exit.

param(
    [string]$Python = "D:\screenshot-qa\.venv\Scripts\python.exe",
    [switch]$SkipInstaller,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path      # ...\screenshot-qa\packaging
$Src  = Split-Path -Parent $Root                             # ...\screenshot-qa
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build"
$Log  = Join-Path $Root "build.log"

function Say($m) {
    $line = "$m"
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

# Run a native command and stream its output into the log.
# Native commands writing to stderr would otherwise trip $ErrorActionPreference=Stop.
function Invoke-Native {
    param([string]$Exe, [string[]]$CmdArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe @CmdArgs *>&1 | ForEach-Object { Say "    $_" }
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return $rc
}

Set-Content -Path $Log -Value "=== ScreenshotQA build $(Get-Date -Format s) ===" -Encoding UTF8

if (-not (Test-Path $Python)) { throw "python not found: $Python" }

Say "1/4 python: $Python"
Invoke-Native $Python @("-c", "import PyInstaller, sys; print('pyinstaller', PyInstaller.__version__, 'on', sys.version.split()[0])") | Out-Null

Say "2/4 icon"
Invoke-Native $Python @((Join-Path $Src "make_icon.py"), (Join-Path $Root "app.ico")) | Out-Null

Say "3/4 pyinstaller"
# Use .NET delete: PowerShell Remove-Item goes through the recycle bin and fails on build dirs.
if (Test-Path $Dist) { [System.IO.Directory]::Delete($Dist, $true) }
if (Test-Path $Work) { [System.IO.Directory]::Delete($Work, $true) }

$mode = "--onedir"
if ($OneFile) { $mode = "--onefile" }

$pyArgs = @(
    "--noconfirm", "--clean", $mode, "--console",
    "--name", "ScreenshotQA",
    "--icon", (Join-Path $Root "app.ico"),
    "--add-data", "$Src\region_config.default.json;.",
    "--hidden-import", "paths",
    "--hidden-import", "hotkey",
    "--hidden-import", "capture",
    "--hidden-import", "calibrate",
    "--hidden-import", "settings_ui",
    "--hidden-import", "PIL._tkinter_finder",
    "--exclude-module", "numpy",
    "--exclude-module", "scipy",
    "--exclude-module", "pandas",
    "--exclude-module", "matplotlib",
    "--exclude-module", "IPython",
    "--exclude-module", "pytest",
    "--exclude-module", "setuptools",
    "--exclude-module", "pip",
    "--version-file", (Join-Path $Root "version_info.txt"),
    "--distpath", $Dist,
    "--workpath", $Work,
    "--specpath", $Work,
    (Join-Path $Src "app.py")
)
$rc = Invoke-Native $Python (@("-m", "PyInstaller") + $pyArgs)
if ($rc -ne 0) { throw "pyinstaller failed with exit code $rc" }

$exe = Join-Path $Dist "ScreenshotQA\ScreenshotQA.exe"
if (-not (Test-Path $exe)) {
    $exe = Join-Path $Dist "ScreenshotQA.exe"   # -OneFile 布局
}
if (-not (Test-Path $exe)) { throw "exe not produced under $Dist" }
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$totalMb = [math]::Round(((Get-ChildItem $Dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Say "    built: $exe  (exe $mb MB / 全部文件 $totalMb MB)"

Say "4/4 self test"
$t0 = Get-Date
$rc = Invoke-Native $exe @("version")
$elapsed = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
Say "    exit after $elapsed s"
if ($elapsed -gt 5) { Say "    !! WARNING: slow exit (>5s) - tkinter in a --onefile build does this" }

if (-not $SkipInstaller) {
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    $mkns = "C:\Program Files (x86)\NSIS\makensis.exe"
    if (Test-Path $mkns) {
        Say "5/5 makensis"
        # NSIS reads .nsi as ANSI when there is no BOM -> force UTF-8 BOM so Chinese strings survive.
        $nsi = Join-Path $Root "installer.nsi"
        $txt = [System.IO.File]::ReadAllText($nsi, [System.Text.Encoding]::UTF8)
        [System.IO.File]::WriteAllText($nsi, $txt, (New-Object System.Text.UTF8Encoding($true)))
        Push-Location $Root
        $rc = Invoke-Native $mkns @($nsi)
        Pop-Location
        if ($rc -ne 0) { throw "makensis failed with exit code $rc" }
    } elseif (Test-Path $iscc) {
        Say "5/5 iscc"
        $rc = Invoke-Native $iscc @((Join-Path $Root "installer.iss"))
        if ($rc -ne 0) { throw "iscc failed with exit code $rc" }
    } else {
        Say "5/5 no installer compiler found (Inno Setup / NSIS) - skipped"
    }
}

Say "DONE"
