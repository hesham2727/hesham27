@echo off
REM Create or reset a user (password prompted): create-admin.bat <username> [admin|investigator|viewer]
set ROLE=%2
if "%ROLE%"=="" set ROLE=admin
"%~dp0..\FBOSINT-Server.exe" create-admin %1 --role %ROLE%
pause
