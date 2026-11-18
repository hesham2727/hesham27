@echo off
REM Network mode: serves API + web dashboard to the local network.
REM TLS: run "FBOSINT-Server.exe gen-cert --ip <this-PC-IP>" once, then set the two variables below.
if exist "%APPDATA%\FBOSINT\tls\server.crt" (
  set FBO_TLS_CERTFILE=%APPDATA%\FBOSINT\tls\server.crt
  set FBO_TLS_KEYFILE=%APPDATA%\FBOSINT\tls\server.key
)
set FBO_MODE=network
"%~dp0..\FBOSINT-Server.exe" serve --host 0.0.0.0 --port 8765
pause
