@echo off
REM One-time setup from source (Python 3.12+ and Node.js 20.19+ required, both free).
cd /d "%~dp0.."
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
pip install -r backend\requirements-dev.txt || goto :err
pip install PySide6==6.12.0 || goto :err
cd frontend
call npm ci || goto :err
call npm run build || goto :err
echo.
echo Done. Web mode: scripts\run_web_windows.bat   Desktop: python desktop\tahqiq_desktop.py
goto :eof
:err
echo Setup failed.
exit /b 1
