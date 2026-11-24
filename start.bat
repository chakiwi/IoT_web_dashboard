@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua setup; dang chay setup.bat...
  call setup.bat
  if errorlevel 1 goto :failed
)
if not exist "frontend\dist\index.html" (
  echo Chua build frontend; dang chay npm.cmd run build...
  cd frontend
  if not exist node_modules call npm.cmd install --no-audit --no-fund
  if errorlevel 1 goto :failed
  call npm.cmd run build
  if errorlevel 1 goto :failed
  cd ..
)
if not exist ".env" copy /y ".env.example" ".env" >nul
start "" /min cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"
echo.
echo ATTENDA LAN LOCAL: http://127.0.0.1:8000
echo API DOCUMENTATION: http://127.0.0.1:8000/docs
echo Nhan CTRL+C tai day de dung server.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
:failed
cd /d "%~dp0"
echo [ERROR] Khong khoi dong duoc. Chay lai setup.bat va xem thong bao loi.
pause
exit /b 1
