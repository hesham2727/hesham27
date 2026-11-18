@echo off
REM Creates a zip backup (database + media) in %APPDATA%\FBOSINT\backups
"%~dp0..\FBOSINT-Server.exe" backup
pause
