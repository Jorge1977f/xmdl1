@echo off
REM ============================================================================
REM XML Downloader - Execucao simples (com ou sem venv)
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python nao foi encontrado no PATH.
    echo Instale o Python 3.11+ e marque "Add Python to PATH".
    pause
    exit /b 1
)

set "PYTHON_CMD=python"
set "PIP_INSTALL_ARGS=--user -r requirements.txt"
if exist "venv\Scripts\python.exe" (
    set "PYTHON_CMD=venv\Scripts\python.exe"
    set "PIP_INSTALL_ARGS=-r requirements.txt"
)

echo Verificando dependencias...
%PYTHON_CMD% -c "import PySide6, playwright, sqlalchemy, lxml, dotenv, pypdf, pandas, reportlab" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias no Python atual...
    %PYTHON_CMD% -m pip install --upgrade pip
    if errorlevel 1 goto pip_error
    %PYTHON_CMD% -m pip install %PIP_INSTALL_ARGS%
    if errorlevel 1 goto pip_error
    %PYTHON_CMD% -m playwright install chromium
)

echo Iniciando XML Downloader...
%PYTHON_CMD% main.py
exit /b %errorlevel%

:pip_error
echo Falha ao instalar dependencias automaticamente.
echo Tente executar novamente como administrador ou rode manualmente:
echo    python -m pip install --user -r requirements.txt
echo    python -m playwright install chromium
pause
exit /b 1
