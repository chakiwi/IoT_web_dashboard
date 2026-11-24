@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Chay setup.bat truoc.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" scripts\check_lan_security.py
if errorlevel 1 (
  echo [BLOCKED] Hay doi mat khau va cac khoa trong .env truoc khi mo LAN.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
 echo Khong thay frontend build. Chay setup.bat truoc.
 pause
 exit /b 1
)
echo.
echo LAN SERVER: http://DIA_CHI_IP_LAPTOP:8000
 echo Windows Firewall phai cho phep cong 8000 tren Private network.
echo KHONG cau hinh port forwarding tren router.
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
