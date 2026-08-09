@echo off
setlocal EnableDelayedExpansion
title ${WC3_REALM_NAME} - Instalar el juego desde cero
color 0B

echo.
echo   ================================================
echo      ${WC3_REALM_NAME} - Instalar Warcraft III
echo   ================================================
echo.
echo   Esto es para el que NO tiene el juego instalado.
echo   Si ya lo tenes, cerra esto y usa INSTALAR.bat.
echo.
echo   Que va a pasar:
echo     1) Se bajan los DOS instaladores oficiales de
echo        Blizzard (Reign of Chaos y Frozen Throne),
echo        que instalan directo la version 1.27a.
echo     2) Se abre el de Reign of Chaos. Te va a pedir
echo        TU CD key de 26 digitos. Eso lo tenes que
echo        escribir vos: es tu clave, no viene aca.
echo     3) Despues el de Frozen Throne, con su key.
echo     4) Al final corre solo INSTALAR.bat, que deja
echo        el juego apuntando al servidor.
echo.
echo   La descarga es desde los servidores de Blizzard
echo   y puede tardar un buen rato.
echo.
pause

:: ---------------------------------------------------------------
:: 0. Si el juego ya esta, no hay nada que instalar
:: ---------------------------------------------------------------
set WC3DIR=
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if defined WC3DIR if exist "!WC3DIR!\war3.exe" (
    echo.
    echo   Ya tenes Warcraft III en: !WC3DIR!
    echo   No hace falta reinstalar. Corre INSTALAR.bat.
    echo.
    pause
    exit /b 0
)

:: ---------------------------------------------------------------
:: 1. Bajar los instaladores oficiales
::    Las URLs son de Blizzard (battle.net); la descarga es anonima,
::    la key se pide recien al instalar. curl viene con Windows 10+.
:: ---------------------------------------------------------------
set DL=%TEMP%\wc3-revival-instaladores
if not exist "%DL%" mkdir "%DL%"

echo.
echo   [1/4] Bajando el instalador de Reign of Chaos...
if not exist "%DL%\roc-instalador.exe" (
    curl.exe -L -o "%DL%\roc-instalador.exe" "https://us.battle.net/download/getLegacy?product=WAR3&locale=esES&os=WIN"
    if errorlevel 1 goto :fallo_descarga
) else (
    echo         ya estaba bajado, sigo
)

echo.
echo   [2/4] Bajando el instalador de The Frozen Throne...
if not exist "%DL%\tft-instalador.exe" (
    curl.exe -L -o "%DL%\tft-instalador.exe" "https://us.battle.net/download/getLegacy?product=W3XP&locale=esES&os=WIN"
    if errorlevel 1 goto :fallo_descarga
) else (
    echo         ya estaba bajado, sigo
)

:: ---------------------------------------------------------------
:: 2. Instalar, en orden: TFT es expansion y no instala sin RoC
:: ---------------------------------------------------------------
echo.
echo   [3/4] Instalando Reign of Chaos.
echo         Segui el instalador; cuando pida la CD key,
echo         escribi la TUYA de Reign of Chaos.
echo.
start "" /wait "%DL%\roc-instalador.exe"

echo.
echo   [4/4] Instalando The Frozen Throne.
echo         Ahora la key de Frozen Throne.
echo.
start "" /wait "%DL%\tft-instalador.exe"

:: ---------------------------------------------------------------
:: 3. Encadenar con el instalador del servidor
:: ---------------------------------------------------------------
if exist "%~dp0INSTALAR.bat" (
    echo.
    echo   Juego instalado. Ahora lo apunto al servidor...
    echo.
    call "%~dp0INSTALAR.bat"
) else (
    echo.
    echo   Juego instalado. Ahora corre INSTALAR.bat para
    echo   apuntarlo al servidor.
    echo.
    pause
)
exit /b 0

:fallo_descarga
echo.
echo   ERROR: no se pudo bajar el instalador.
echo.
echo   Puede ser tu conexion, o que Blizzard haya movido el
echo   enlace. Proba bajarlo a mano desde tu navegador:
echo     https://us.battle.net/download/getLegacy?product=WAR3^&locale=esES^&os=WIN
echo     https://us.battle.net/download/getLegacy?product=W3XP^&locale=esES^&os=WIN
echo   Instala primero Reign of Chaos, despues Frozen Throne,
echo   y al final corre INSTALAR.bat.
echo.
pause
exit /b 1
