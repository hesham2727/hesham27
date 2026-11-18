@echo off
REM Usage: restore.bat "C:\path\fbosint-backup-....zip"   (close FBOSINT first)
if "%~1"=="" (echo Usage: restore.bat backup.zip & pause & exit /b 1)
"%~dp0..\FBOSINT-Server.exe" restore "%~1"
pause
