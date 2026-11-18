@echo off
REM Local web mode on Windows (from source). First run: scripts\setup_windows.bat
cd /d "%~dp0..\backend"
call ..\.venv\Scripts\activate.bat
python -m app.serve --host 127.0.0.1 --port 8000
