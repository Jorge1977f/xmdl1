@echo off
REM ============================================================================
REM XML Downloader - Script de Setup Automático para Windows
REM ============================================================================
REM
REM Este script cria um ambiente virtual e instala todas as dependências
REM automaticamente. Execute uma única vez antes de usar a aplicação.
REM
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                                                                    ║
echo ║              XML DOWNLOADER - SETUP AUTOMÁTICO                    ║
echo ║                                                                    ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERRO: Python não está instalado ou não está no PATH
    echo.
    echo Por favor, instale Python 3.11+ de https://www.python.org
    echo Certifique-se de marcar "Add Python to PATH" durante a instalação
    echo.
    pause
    exit /b 1
)

echo ✅ Python encontrado
python --version
echo.

REM Verifica se o ambiente virtual já existe
if exist "venv" (
    echo ✅ Ambiente virtual já existe
    echo.
) else (
    echo 📦 Criando ambiente virtual...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ ERRO ao criar ambiente virtual
        pause
        exit /b 1
    )
    echo ✅ Ambiente virtual criado com sucesso
    echo.
)

REM Ativa o ambiente virtual
echo 🔄 Ativando ambiente virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ ERRO ao ativar ambiente virtual
    pause
    exit /b 1
)
echo ✅ Ambiente virtual ativado
echo.

REM Atualiza pip
echo 📦 Atualizando pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo ⚠️  Aviso ao atualizar pip, continuando...
)
echo ✅ pip atualizado
echo.

REM Instala dependências
echo 📦 Instalando dependências...
echo    (isso pode levar alguns minutos na primeira vez)
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ ERRO ao instalar dependências
    pause
    exit /b 1
)
echo ✅ Dependências instaladas com sucesso
echo.

REM Instala Playwright
echo 📦 Instalando Playwright...
python -m playwright install chromium
if errorlevel 1 (
    echo ⚠️  Aviso ao instalar Playwright, continuando...
)
echo ✅ Playwright instalado
echo.

echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                                                                    ║
echo ║                   ✅ SETUP CONCLUÍDO COM SUCESSO!                ║
echo ║                                                                    ║
echo ║  Para executar a aplicação, use um dos comandos abaixo:           ║
echo ║                                                                    ║
echo ║  Windows (PowerShell):                                            ║
echo ║    .\venv\Scripts\Activate.ps1                                    ║
echo ║    python main.py                                                 ║
echo ║                                                                    ║
echo ║  Windows (CMD):                                                   ║
echo ║    venv\Scripts\activate.bat                                      ║
echo ║    python main.py                                                 ║
echo ║                                                                    ║
echo ║  Ou simplesmente execute: run.bat                                 ║
echo ║                                                                    ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

pause
