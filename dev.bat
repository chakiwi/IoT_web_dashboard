@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup.bat
if errorlevel 1 exit /b 1
start "Attenda FastAPI" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000"
start "Attenda React" /D "%~dp0frontend" cmd /k "npm.cmd run dev"
echo Backend at http://127.0.0.1:8000 and Vite at http://127.0.0.1:5173
