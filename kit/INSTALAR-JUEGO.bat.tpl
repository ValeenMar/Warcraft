@echo off
setlocal EnableDelayedExpansion
title ${WC3_REALM_NAME} - Instalar Warcraft III 1.27b
color 0B

set DL=%TEMP%\wc3-revival-instaladores
set PATCH=%DL%\War3TFT_127b_Castellano.exe
set PATCH_URL=http://ftp.blizzard.com/pub/war3x/patches/pc/War3TFT_127b_Castellano.exe

echo.
echo   ================================================
echo      ${WC3_REALM_NAME} - Warcraft III 1.27b
echo   ================================================
echo.
echo   Sirve tanto para una instalacion nueva como para
echo   actualizar un Warcraft III 1.27a existente.
echo.
echo   Instalacion nueva:
echo     1) Baja los instaladores oficiales Legacy de Blizzard.
echo     2) Te pide TUS CD keys de Reign of Chaos y Frozen Throne.
echo     3) Aplica el parche oficial 1.27b de Blizzard.
echo     4) Instala el loader, el gateway y los mapas del kit.
echo.
echo   Si ya tenes 1.27a, salta directo al paso 3.
echo   No necesitas una cuenta oficial de Battle.net.
echo.
pause

call :buscar_juego
if not defined WC3DIR goto :instalar_base
if not exist "!WC3DIR!\war3.exe" goto :instalar_base

for %%f in ("!WC3DIR!\war3.exe") do set WC3SIZE=%%~zf
if "!WC3SIZE!"=="515048" (
    echo.
    echo   Ya tenes Warcraft III 1.27b en: !WC3DIR!
    goto :configurar_servidor
)
if "!WC3SIZE!"=="514536" (
    echo.
    echo   Encontre Warcraft III 1.27a en: !WC3DIR!
    echo   Lo voy a actualizar a 1.27b.
    goto :elegir_idioma
)

echo.
echo   ERROR: encontre Warcraft III, pero war3.exe pesa
echo   !WC3SIZE! bytes. No es 1.27a ni 1.27b.
echo.
echo   No voy a parchearlo a ciegas. Usa una instalacion limpia
echo   o consulta LEEME.txt.
echo.
pause
exit /b 1

:instalar_base
if not exist "%DL%" mkdir "%DL%"

:: Se baja a un .part y recien al terminar se renombra: si la descarga se
:: corta a la mitad, el proximo intento NO va a encontrar un .exe truncado
:: y decir "ya estaba bajado" (eso daba instaladores rotos indescifrables).
echo.
echo   [1/5] Bajando Reign of Chaos oficial...
if not exist "%DL%\roc-instalador.exe" (
    curl.exe -fL --retry 3 -o "%DL%\roc-instalador.exe.part" "https://us.battle.net/download/getLegacy?product=WAR3&locale=esES&os=WIN"
    if errorlevel 1 goto :fallo_descarga
    move /Y "%DL%\roc-instalador.exe.part" "%DL%\roc-instalador.exe" >nul
) else (
    echo         ya estaba bajado, sigo
)

echo.
echo   [2/5] Bajando The Frozen Throne oficial...
if not exist "%DL%\tft-instalador.exe" (
    curl.exe -fL --retry 3 -o "%DL%\tft-instalador.exe.part" "https://us.battle.net/download/getLegacy?product=W3XP&locale=esES&os=WIN"
    if errorlevel 1 goto :fallo_descarga
    move /Y "%DL%\tft-instalador.exe.part" "%DL%\tft-instalador.exe" >nul
) else (
    echo         ya estaba bajado, sigo
)

echo.
echo   [3/5] Instalando Reign of Chaos.
echo         Escribi TU CD key cuando la pida.
echo.
start "" /wait "%DL%\roc-instalador.exe"

echo.
echo   [4/5] Instalando The Frozen Throne.
echo         Escribi TU CD key de la expansion.
echo.
start "" /wait "%DL%\tft-instalador.exe"

call :buscar_juego
if not defined WC3DIR goto :fallo_instalacion
if not exist "!WC3DIR!\war3.exe" goto :fallo_instalacion
for %%f in ("!WC3DIR!\war3.exe") do set WC3SIZE=%%~zf
if not "!WC3SIZE!"=="514536" (
    echo.
    echo   ERROR: la base instalada no es la 1.27a esperada.
    echo   war3.exe pesa !WC3SIZE! bytes, no 514536.
    echo.
    pause
    exit /b 1
)
goto :parchear_127b

:elegir_idioma
echo.
echo   El parche tiene que coincidir con el idioma del juego:
echo     1) Castellano
echo     2) English
echo.
set /p "PATCH_LANG=  Elegi 1 o 2 [1]: "
if "!PATCH_LANG!"=="2" (
    set PATCH=%DL%\War3TFT_127b_English.exe
    set PATCH_URL=http://ftp.blizzard.com/pub/war3x/patches/pc/War3TFT_127b_English.exe
)
goto :parchear_127b

:parchear_127b
if not exist "%DL%" mkdir "%DL%"
echo.
echo   [5/5] Bajando el parche oficial 1.27b...
if not exist "%PATCH%" (
    curl.exe -fL --retry 3 -o "%PATCH%.part" "%PATCH_URL%"
    if errorlevel 1 goto :fallo_descarga
    move /Y "%PATCH%.part" "%PATCH%" >nul
) else (
    echo         ya estaba bajado, sigo
)

echo   Verificando la firma digital de Blizzard...
powershell -NoProfile -Command "$s=Get-AuthenticodeSignature -LiteralPath '%PATCH%'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notlike '*Blizzard Entertainment*'){exit 1}"
if errorlevel 1 goto :fallo_firma

echo   Aplicando 1.27b. Espera a que Blizzard Updater termine...
start "" /wait "%PATCH%"

call :buscar_juego
if not defined WC3DIR goto :fallo_parche
if not exist "!WC3DIR!\war3.exe" goto :fallo_parche
for %%f in ("!WC3DIR!\war3.exe") do set WC3SIZE=%%~zf
if not "!WC3SIZE!"=="515048" goto :fallo_parche
echo         OK: Warcraft III 1.27b confirmado

:configurar_servidor
if exist "%~dp0INSTALAR.bat" (
    echo.
    echo   Ahora instalo el acceso a ${WC3_REALM_NAME}...
    echo.
    call "%~dp0INSTALAR.bat"
) else (
    echo.
    echo   Juego 1.27b listo. Ahora ejecuta INSTALAR.bat para
    echo   agregar el servidor, el loader y los mapas.
    echo.
    pause
)
exit /b 0

:buscar_juego
set WC3DIR=
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
if not defined WC3DIR for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\Warcraft III" /v InstallPath 2^>nul') do set WC3DIR=%%b
exit /b 0

:fallo_descarga
del /Q "%PATCH%.part" "%DL%\roc-instalador.exe.part" "%DL%\tft-instalador.exe.part" 2>nul
echo.
echo   ERROR: no se pudo completar una descarga oficial.
echo   Revisa la conexion y vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:fallo_firma
echo.
echo   ERROR: el parche descargado no tiene una firma valida de
echo   Blizzard Entertainment. No se va a ejecutar.
echo   Borra "%PATCH%" y vuelve a intentarlo.
echo.
pause
exit /b 1

:fallo_instalacion
echo.
echo   ERROR: los instaladores no dejaron una instalacion detectable.
echo   Revisa si alguno fue cancelado y vuelve a intentarlo.
echo.
pause
exit /b 1

:fallo_parche
echo.
echo   ERROR: el parche no dejo war3.exe 1.27b de 515048 bytes.
echo   La causa mas comun es que el idioma del parche no coincida
echo   o que la instalacion haya sido modificada.
echo.
pause
exit /b 1
