@echo off
cd /d "%~dp0"
python --version >nul 2>&1 || (
  echo Python nao encontrado no PATH.
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install --user -r requirements.txt
python -m playwright install chromium
python main.py
