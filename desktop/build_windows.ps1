# Builds the Windows installer locally. Requirements (all free):
#   Python 3.12+ (python.org), Node.js 20+ LTS, Inno Setup 6 (iscc on PATH)
# Usage (PowerShell, from the repository root):  .\desktop\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\pip install -r backend\requirements-desktop.txt

Push-Location frontend
npm ci
npm run build
Pop-Location

.\.venv-build\Scripts\pyinstaller desktop\tahqiq.spec --noconfirm --distpath dist --workpath build
iscc desktop\installer.iss
Write-Host "Installer: dist\installer\Tahqiq-Setup-1.0.0.exe"
