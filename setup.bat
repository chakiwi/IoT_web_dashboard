@echo off
setlocal
cd /d "%~dp0"
echo.
echo === ATTENDA - CAI DAT LAN DAU ===
echo.
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo [OK] Tao .env tu cau hinh demo
)
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m database.setup
if errorlevel 1 goto :failed
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Khong tim thay Node.js. Cai Node.js LTS tai https://nodejs.org
  goto :failed
)
cd frontend
call npm.cmd install --no-audit --no-fund
if errorlevel 1 goto :failed
call npm.cmd run build
if errorlevel 1 goto :failed
cd ..
echo.
echo [OK] Da cai xong, chay start.bat de mo Dashboard!
exit /b 0
:failed
cd /d "%~dp0"
echo.
echo [ERROR] Setup that bai. Gui anh man hinh CMD de kiem tra.
pause
exit /b 1
