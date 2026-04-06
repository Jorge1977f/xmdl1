\
@echo off
setlocal
cd /d "%~dp0"

if not exist "build" mkdir build

echo =====================================================
echo Gerando build onefile com Nuitka...
echo Use este modo apenas apos validar o standalone.
echo =====================================================

python -m nuitka ^
  --assume-yes-for-downloads ^
  --mode=onefile ^
  --windows-console-mode=disable ^
  --enable-plugin=pyside6 ^
  --output-dir=build ^
  --output-filename=XMLDownloader.exe ^
  --include-data-dir=app/resources=app/resources ^
  --include-data-files=data/municipios_ibge.json=data/municipios_ibge.json ^
  main.py

if errorlevel 1 (
    echo.
    echo ERRO na compilacao.
    pause
    exit /b 1
)

echo.
echo Build concluido.
echo Saida esperada: build\XMLDownloader.exe
pause
