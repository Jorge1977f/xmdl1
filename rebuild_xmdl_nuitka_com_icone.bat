@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo   REBUILD XMDL COM ICONE - NUITKA
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: nao encontrei o Python da venv em .venv\Scripts\python.exe
    echo Crie/ative a venv antes de usar este script.
    pause
    exit /b 1
)

if not exist "main.py" (
    echo ERRO: nao encontrei o arquivo main.py na raiz do projeto.
    echo Coloque este BAT na pasta raiz do projeto.
    pause
    exit /b 1
)

if not exist "XMDL.ico" (
    echo ERRO: nao encontrei o icone XMDL.ico na raiz do projeto.
    echo Deixe o arquivo XMDL.ico na mesma pasta deste BAT.
    pause
    exit /b 1
)

echo Limpando build antigo...
if exist "build" rmdir /s /q "build"
mkdir "build"

echo.
echo Atualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo Verificando Nuitka...
".venv\Scripts\python.exe" -m nuitka --version
if errorlevel 1 (
    echo.
    echo ERRO: Nuitka nao esta instalado na venv.
    echo Rode: .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    pause
    exit /b 1
)

echo.
echo Gerando build standalone...
".venv\Scripts\python.exe" -m nuitka ^
  --assume-yes-for-downloads ^
  --mode=standalone ^
  --windows-console-mode=disable ^
  --enable-plugin=pyside6 ^
  --windows-icon-from-ico=XMDL.ico ^
  --noinclude-pytest-mode=nofollow ^
  --noinclude-setuptools-mode=nofollow ^
  --output-dir=build ^
  --output-filename=XMLDownloader.exe ^
  --include-data-dir=app/resources=app/resources ^
  --include-data-files=data/municipios_ibge.json=data/municipios_ibge.json ^
  main.py

if errorlevel 1 (
    echo.
    echo ERRO na compilacao do Nuitka.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo BUILD CONCLUIDO COM SUCESSO
echo Saida: build\main.dist\XMLDownloader.exe
echo ==========================================
echo.
pause
