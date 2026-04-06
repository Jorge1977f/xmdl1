@echo off
cd /d "%~dp0"
echo Instalando dependencias do backend local...
python -m pip install -r requirements.txt
echo.
echo Se nao apareceu erro, pode seguir para o arquivo 2_INICIAR_BACKEND_LOCAL.bat
pause
