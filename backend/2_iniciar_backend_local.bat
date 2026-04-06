@echo off
cd /d "%~dp0"
echo Iniciando API local em http://127.0.0.1:8080
python -m uvicorn license_api.main:app --host 127.0.0.1 --port 8080
pause
