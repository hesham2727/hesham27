# Builds dist\FBOSINT (PyInstaller) and dist\installer\FBOSINT-Setup-<ver>.exe (Inno Setup 6).
# Requirements: Python 3.12+, Node.js 20+, Inno Setup 6 (iscc on PATH or default location).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r backend\requirements.txt -r desktop\requirements.txt pyinstaller pytest pytest-qt
Push-Location frontend; npm ci; npm run build; Pop-Location
.\.venv\Scripts\python -m pytest backend\tests desktop\tests -q
.\.venv\Scripts\pyinstaller packaging\fbosint.spec --noconfirm
$env:FBO_SELFTEST_LOG = "$PWD\dist\selftest.log"
$p = Start-Process -FilePath dist\FBOSINT\FBOSINT.exe -ArgumentList "--self-test" -Wait -PassThru
Get-Content dist\selftest.log
if ($p.ExitCode -ne 0) { throw "Desktop self-test failed" }
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc packaging\installer.iss
Write-Host "Installer: dist\installer"
