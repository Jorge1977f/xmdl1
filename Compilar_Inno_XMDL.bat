@echo off
setlocal
cd /d "%~dp0"

set "ISCC1=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "ISCC2=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%ISCC1%" (
  "%ISCC1%" "XMDL_Setup.iss"
  goto :end
)

if exist "%ISCC2%" (
  "%ISCC2%" "XMDL_Setup.iss"
  goto :end
)

echo Inno Setup 6 nao foi encontrado.
echo Instale o Inno Setup 6 e rode este arquivo novamente.
pause
exit /b 1

:end
echo.
echo Instalador gerado em build\inno
pause
