@echo off
setlocal EnableDelayedExpansion
title ${WC3_REALM_NAME} - Instalador
color 0B

set SERVER_IP=${WC3_PUBLIC_IP}
set SERVER_NAME=${WC3_REALM_NAME}
set SERVER_TZ=${WC3_KIT_GATEWAY_TZ}

echo.
echo   ================================================
echo      WC3 REVIVAL - Instalador del cliente
echo   ================================================
echo.
echo   Esto configura tu Warcraft III para entrar al
echo   servidor. No instala el juego: tenes que tenerlo
echo   ya instalado, en la version 1.27b.
echo.
echo   No modifica ningun archivo del juego. Solo copia
echo   el loader y agrega el servidor a tu lista.
echo.
pause

:: ---------------------------------------------------------------
:: 1. Encontrar la carpeta de Warcraft III
:: ---------------------------------------------------------------
echo.
echo   [1/4] Buscando tu Warcraft III...

set WC3DIR=
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if not defined WC3DIR for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if not defined WC3DIR if exist "%ProgramFiles(x86)%\Warcraft III\war3.exe" set WC3DIR=%ProgramFiles(x86)%\Warcraft III
if not defined WC3DIR if exist "%ProgramFiles%\Warcraft III\war3.exe" set WC3DIR=%ProgramFiles%\Warcraft III

if not defined WC3DIR (
    echo.
    echo   No encontre Warcraft III automaticamente.
    echo.
    set /p WC3DIR=  Pega aca la ruta de tu carpeta Warcraft III: 
)

if not exist "!WC3DIR!\war3.exe" (
    echo.
    echo   ERROR: en "!WC3DIR!" no hay un war3.exe
    echo.
    echo   Revisa que sea la carpeta correcta. Tiene que
    echo   contener war3.exe, Storm.dll y Game.dll.
    echo.
    pause
    exit /b 1
)
echo         OK: !WC3DIR!

:: ---------------------------------------------------------------
:: 2. Verificar la version (1.27b = war3.exe de 515.048 bytes)
:: ---------------------------------------------------------------
echo.
echo   [2/4] Verificando la version del juego...

for %%f in ("!WC3DIR!\war3.exe") do set WC3SIZE=%%~zf
if "!WC3SIZE!"=="515048" (
    echo         OK: 1.27b confirmado
) else (
    echo.
    echo   AVISO: tu war3.exe pesa !WC3SIZE! bytes.
    echo   El de la version 1.27b pesa 515048.
    echo.
    echo   El servidor usa 1.27b. Con otra version no vas a
    echo   poder entrar a las partidas.
    echo.
    echo   Ejecuta INSTALAR-JUEGO.bat para instalar o actualizar
    echo   el juego con tus propias CD keys.
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------
:: 3. Copiar el loader
:: ---------------------------------------------------------------
echo.
echo   [3/4] Instalando el loader...

copy /Y "%~dp0loader\w3l.exe"    "!WC3DIR!\" >nul
copy /Y "%~dp0loader\w3lh.dll"   "!WC3DIR!\" >nul
copy /Y "%~dp0loader\wl27.dll"   "!WC3DIR!\" >nul
if not exist "!WC3DIR!\latency.txt" copy /Y "%~dp0loader\latency.txt" "!WC3DIR!\" >nul
echo         OK: w3l.exe listo

:: ---------------------------------------------------------------
:: 4. Agregar el servidor a la lista de gateways
:: ---------------------------------------------------------------
echo.
echo   [4/4] Agregando el servidor a tu lista...

:: El valor del registro es un REG_MULTI_SZ con un formato propio (ver los
:: comentarios de herramientas\gateway.ps1). Lo hace PowerShell porque maneja
:: los REG_MULTI_SZ como lista de verdad; en batch hay que contar caracteres
:: a mano y es como para equivocarse.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0herramientas\gateway.ps1" ^
    -Ip "%SERVER_IP%" -Tz "%SERVER_TZ%" -Title "%SERVER_NAME%"
if errorlevel 1 (
    echo.
    echo   ERROR: no pude escribir la lista de servidores.
    echo   Se puede agregar a mano: en la pantalla de Battle.net
    echo   del juego, elegi otro gateway y editalo con %SERVER_IP%
    echo.
    pause
)

:: ---------------------------------------------------------------
:: Mapas
:: ---------------------------------------------------------------
:: OJO con la ruta: recien desde el parche 1.28 Warcraft III lee los mapas de
:: Documentos. En 1.27b, que es la version de este servidor, los busca adentro
:: de la carpeta de instalacion. Copiarlos a Documentos no rompe nada, pero el
:: juego no los ve nunca.
set MAPDIR=!WC3DIR!\Maps\Download
if exist "%~dp0mapas\*.w3x" (
    echo.
    echo   Copiando mapas...
    if not exist "!MAPDIR!" mkdir "!MAPDIR!" 2>nul
    copy /Y "%~dp0mapas\*.w3x" "!MAPDIR!\" >nul
    echo         OK: mapas en !WC3DIR!\Maps\Download
)

:: ---------------------------------------------------------------
:: Acceso directo en el escritorio
:: ---------------------------------------------------------------
echo.
echo   Creando acceso directo en el escritorio...
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\${WC3_REALM_NAME}.lnk');" ^
  "$s.TargetPath='!WC3DIR!\w3l.exe'; $s.WorkingDirectory='!WC3DIR!';" ^
  "$s.Description='Entrar al servidor ${WC3_REALM_NAME}'; $s.Save()" >nul 2>&1

echo.
echo   ================================================
echo      LISTO
echo   ================================================
echo.
echo   Para jugar: abri "${WC3_REALM_NAME}" desde el escritorio
echo   (o w3l.exe en la carpeta del juego). NUNCA abras
echo   Frozen Throne.exe para entrar al servidor: sin el
echo   loader la conexion no funciona.
echo.
echo   Adentro del juego:
echo     1) Battle.net  ^>  elegi "%SERVER_NAME%" en la lista
echo     2) Crea tu cuenta con "New Account"
echo        (cuando pida un mail, cancela: no hace falta)
echo     3) Escribi:  /join ${WC3_BOT_CHANNEL}
echo.
echo   Leelo todo en LEEME.txt si algo no sale.
echo.
pause
