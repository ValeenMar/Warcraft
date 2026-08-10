@echo off
setlocal EnableDelayedExpansion
title ${WC3_REALM_NAME} - Instalar WFE (teclas LoL + mapas grandes)
color 0B

:: El binario de WFE NO viaja dentro del kit a proposito (se inyecta en el
:: juego y los antivirus lo marcan; meterlo haria sospechoso al kit entero).
:: Este script lo baja de su sitio OFICIAL, en una version fija, y verifica
:: el SHA-256 del zip antes de tocar nada: si alguien lo cambio en el camino,
:: se corta aca.
set WFE_URL=https://github.com/UnryzeC/WFE-Release/releases/download/v3.1.13.85/WFE.zip
set WFE_SHA256=1f76e78cacb30e3460116e0cf1ef136de7d91a0ea937ffdcb3d63ec4b9cd52af

echo.
echo   ================================================
echo      ${WC3_REALM_NAME} - Instalar WFE
echo   ================================================
echo.
echo   WFE agrega, si vos queres: teclas QWER estilo LoL,
echo   smartcast, barras de vida siempre visibles, y permite
echo   cargar los mapas GRANDES del server (los de mas de 8 MB).
echo.
echo   Se baja de su sitio oficial (github.com/UnryzeC/WFE-Release)
echo   y queda adentro de tu carpeta de Warcraft III, con el perfil
echo   del server ya configurado. Es 100%% opcional y se saca
echo   borrando la carpeta WFE.
echo.
pause

:: ---------------------------------------------------------------
:: 1. Encontrar la carpeta de Warcraft III (igual que INSTALAR.bat)
:: ---------------------------------------------------------------
set WC3DIR=
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if not defined WC3DIR for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if not defined WC3DIR if exist "%ProgramFiles(x86)%\Warcraft III\war3.exe" set WC3DIR=%ProgramFiles(x86)%\Warcraft III
if not defined WC3DIR if exist "%ProgramFiles%\Warcraft III\war3.exe" set WC3DIR=%ProgramFiles%\Warcraft III
if not defined WC3DIR (
    echo.
    set /p WC3DIR=  Pega aca la ruta de tu carpeta Warcraft III:
)
if not exist "!WC3DIR!\war3.exe" (
    echo.
    echo   ERROR: en "!WC3DIR!" no hay un war3.exe
    pause
    exit /b 1
)
echo         OK: !WC3DIR!

:: ---------------------------------------------------------------
:: 2. Bajar el zip oficial (a .part, y se renombra recien al final)
:: ---------------------------------------------------------------
set DL=%TEMP%\wc3-revival-wfe
if not exist "%DL%" mkdir "%DL%"
echo.
echo   [1/3] Bajando WFE del sitio oficial...
if not exist "%DL%\WFE.zip" (
    curl.exe -fL -o "%DL%\WFE.zip.part" "%WFE_URL%"
    if errorlevel 1 goto :fallo_descarga
    move /Y "%DL%\WFE.zip.part" "%DL%\WFE.zip" >nul
) else (
    echo         ya estaba bajado, sigo
)

:: ---------------------------------------------------------------
:: 3. Verificar que el zip sea EXACTAMENTE el esperado (SHA-256)
:: ---------------------------------------------------------------
echo.
echo   [2/3] Verificando la descarga...
set HASH_OK=
for /f "skip=1 tokens=1" %%h in ('certutil -hashfile "%DL%\WFE.zip" SHA256') do (
    if /i "%%h"=="%WFE_SHA256%" set HASH_OK=1
    goto :hash_listo
)
:hash_listo
if not defined HASH_OK (
    echo.
    echo   ERROR: el archivo bajado NO coincide con el esperado.
    echo   Puede ser una descarga cortada; borra esta carpeta y proba de nuevo:
    echo       %DL%
    echo   Si sigue fallando, avisale al admin (puede ser algo peor que
    echo   una descarga cortada, y mejor que lo mire).
    del "%DL%\WFE.zip" >nul 2>nul
    pause
    exit /b 1
)
echo         OK: verificado

:: ---------------------------------------------------------------
:: 4. Instalar en <Warcraft III>\WFE + perfil del server
::    (tar viene con Windows 10+ y sabe abrir .zip)
:: ---------------------------------------------------------------
echo.
echo   [3/3] Instalando en !WC3DIR!\WFE ...
if not exist "!WC3DIR!\WFE" mkdir "!WC3DIR!\WFE"
tar -xf "%DL%\WFE.zip" -C "!WC3DIR!\WFE"
if errorlevel 1 (
    echo.
    echo   ERROR: no pude descomprimir. Descomprimi a mano %DL%\WFE.zip
    echo   adentro de "!WC3DIR!\WFE" y copia WC3Revival.ini a su carpeta
    echo   Profiles.
    pause
    exit /b 1
)
if not exist "!WC3DIR!\WFE\Profiles" mkdir "!WC3DIR!\WFE\Profiles"
copy /Y "%~dp0WC3Revival.ini" "!WC3DIR!\WFE\Profiles\" >nul

echo.
echo   ================================================
echo      LISTO
echo   ================================================
echo.
echo   Para activarlo (una sola vez):
echo     1) Abri !WC3DIR!\WFE\WFEApp.exe
echo     2) En Profile elegi "WC3Revival"
echo     3) Verifica que el Process Name sea war3.exe
echo     4) Activa "Auto Injector"
echo   Despues jugas como siempre (acceso directo del escritorio).
echo   El detalle completo esta en TECLAS-LOL.txt.
echo.
echo   OJO: tu antivirus puede quejarse de WFE. Es un falso
echo   positivo conocido (se inyecta en el juego, y eso les huele
echo   mal). El proyecto es publico: github.com/UnryzeC/WFE-Release
echo.
pause
exit /b 0

:fallo_descarga
echo.
echo   ERROR: no se pudo bajar WFE.
echo   Proba de nuevo mas tarde, o bajalo a mano desde:
echo     %WFE_URL%
echo   y descomprimilo adentro de "!WC3DIR!\WFE" (copiando ademas
echo   WC3Revival.ini a su carpeta Profiles).
echo.
pause
exit /b 1
