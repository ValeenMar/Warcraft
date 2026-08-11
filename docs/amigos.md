# Guía para amigos: entrar a jugar, desde cero

Todo lo que hace falta para jugar en el servidor, empezando sin nada. Se
configura una sola vez; después, jugar es abrir `w3l.exe` y entrar. Si algo
no sale, al final hay una tabla de problemas típicos.

Los datos que se usan en toda la guía:

| Qué | Valor |
|---|---|
| IP del servidor | `64.176.24.103` |
| Versión del juego | **The Frozen Throne 1.27b** — todos la misma, sin excepción |
| Gateway en el cliente | **Northrend (Europe)** |
| Canal de encuentro | el que diga `WC3_BOT_CHANNEL` en el `.env` del servidor (por defecto `W3`) |

## 1. Conseguir el juego (TFT 1.27b, limpio)

Hace falta **Warcraft III completo: Reign of Chaos + The Frozen Throne** en
la versión **1.27b** exacta. TFT es una expansión y no instala sin RoC.
Versiones distintas no juegan entre sí: ni 1.26, ni 1.28, ni Reforged sirven
para este servidor.

El camino corto:

1. **Si tenés una CD key de 26 dígitos** (de la caja, o registrada en tu
   cuenta de Battle.net): bajá los instaladores oficiales "Legacy" de
   Blizzard, que dejan una base 1.27a. Después hace falta el parche oficial
   1.27b; el `INSTALAR.bat` del kit hace toda la cadena automáticamente:

   ```
   https://us.battle.net/download/getLegacy?product=WAR3&locale=esES&os=WIN   (Reign of Chaos)
   https://us.battle.net/download/getLegacy?product=W3XP&locale=esES&os=WIN   (Frozen Throne)
   ```

   La descarga es anónima, pero el instalador pide la key. Instalá primero
   RoC, después TFT y finalmente el parche 1.27b de tu idioma.
   En el kit alcanza con abrir `INSTALAR.bat`: si falta el juego o detecta
   1.27a, llama automáticamente al asistente `INSTALAR-JUEGO.bat`.
2. **Si no tenés nada**: comprar una copia física usada de RoC + TFT con las
   keys impresas y legibles — se consiguen baratas en el mercado de segunda
   mano por ser un juego de más de 20 años. Con la key de la caja podés usar
   los instaladores de arriba aunque no tengas lectora de CD.

**Trampas conocidas**: el cliente "Warcraft III – Legacy TFT 1.29" que
aparece en la app de Battle.net **no sirve** (es 1.29, por encima de lo que
este servidor soporta), y Reforged tampoco. El paso a paso completo, con
todas las rutas y los errores típicos al instalar o parchear, está en
[conseguir-el-juego.md](conseguir-el-juego.md).

**Verificación de que quedó bien**: `war3.exe`, en la carpeta del juego
(típicamente `C:\Program Files (x86)\Warcraft III\`), tiene que pesar
**exactamente 515.048 bytes**, con fecha 09/12/2016. Si pesa otra cosa, no
es un 1.27b genuino y no vas a poder entrar.

## 2. Apuntar el juego a nuestro servidor

### El camino corto: el kit

Hay un kit (`WC3-Revival-Kit.zip`) que hace todo desde un único doble clic:
`INSTALAR.bat` instala la base si falta, actualiza 1.27a a 1.27b si hace falta,
copia el loader y **agrega el servidor a la lista de gateways del juego**,
sin tocar ningún archivo del juego y sin romper nada más. Pedíselo al admin.

Es el camino recomendado, y no solo por comodidad: agrega el servidor **al
lado** de los de Blizzard en vez de secuestrar el DNS de uno de ellos, así
que no tiene el efecto colateral sobre la app de Battle.net que sí tiene el
método manual de acá abajo.

El detalle de dónde vive esa lista está en la cabecera de
`herramientas/gateway.ps1` dentro del kit: es un `REG_MULTI_SZ` en
`HKCU\Software\Blizzard Entertainment\Warcraft III`, con el formato que usa
el instalador oficial de gateways de PvPGN.

### A mano: secuestrar `europe.battle.net`

El cliente trae grabadas las direcciones de los Battle.net oficiales. El
truco es hacer que una de ellas (`europe.battle.net`, la que usa el gateway
"Northrend") resuelva a la IP de nuestro servidor.

Abrí **PowerShell como administrador** (menú Inicio → escribir `powershell`
→ clic derecho → *Ejecutar como administrador*) y pegá:

```powershell
Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" -Value "64.176.24.103 europe.battle.net"
ipconfig /flushdns
```

Desde ahora, en la pantalla de login de Battle.net del juego hay que tener
elegido el gateway **Northrend (Europe)** (botón *Change Gateway*).

**Efecto colateral, para que no te agarre por sorpresa**: esa línea rompe la
**app de escritorio de Battle.net**, que se queda colgada en "Security
Check" (intenta hablar HTTPS con ese dominio, que ahora apunta a nuestro
server). El W3 clásico no usa esa app para nada. Si algún día la necesitás,
se revierte sacando la línea:

```powershell
# PowerShell como administrador
(Get-Content "$env:SystemRoot\System32\drivers\etc\hosts") |
    Where-Object { $_ -notmatch "europe\.battle\.net" } |
    Set-Content "$env:SystemRoot\System32\drivers\etc\hosts"
ipconfig /flushdns
```

## 3. El loader (obligatorio, no opcional)

El cliente de W3 verifica una firma criptográfica de Blizzard antes de
dejarte loguear, y un servidor privado no puede producirla. **Sin loader no
hay forma de conectar**: el juego tira `Unable to connect to Battle.net...`
aunque todo lo demás esté perfecto.

Si usaste el kit del paso 2, esto ya está hecho y podés saltear la sección.
A mano:

1. Bajá el **Warcraft 3 Loader (w3l)** de https://pvpgn.pro/w3l.html — el
   paquete cubre de 1.22a a 1.28f, así que 1.27b entra.
2. El zip tiene contraseña: **`pvpgn`**.
3. Copiá **`w3l.exe`**, **`w3lh.dll`** y **`wl27.dll`** (la DLL de la
   versión 1.27) a la carpeta del juego, al lado de `Frozen Throne.exe`.
4. De ahora en más el juego se abre **SIEMPRE con `w3l.exe`** (conviene
   hacerse un acceso directo). Abierto con `Frozen Throne.exe`, no conecta.

## 4. Crear tu cuenta

1. Abrí `w3l.exe` → *Battle.net* → gateway **Northrend (Europe)**.
2. Botón **New Account**: elegí usuario y contraseña.
3. No pide mail. Si aparece una pantalla pidiendo un mail, **cancelala**:
   no se usa para nada.
4. **No hay recuperación de contraseña.** Si la perdés, la cuenta se pierde
   (queda pedirle al admin que la borre y crear otra). Anotala en algún lado.

## 5. Jugar

Después de loguearte caés a un canal de chat. Los bots que hostean las
partidas viven todos en el mismo canal, **`W3`**: entrá con `/join W3`.

Ahí no tenés que pedir nada. Cada mapa tiene su propio bot y cada bot
**mantiene su lobby siempre abierto**: los vas a ver todos juntos en
*Custom Game → Play Game*. Y cuando una partida arranca, ese mismo bot
publica un lobby nuevo del mismo mapa en menos de un minuto, así que un mapa
que se está jugando sigue estando disponible.

El canal sirve para chatear y para susurrarle a un bot si hace falta
(`!getgames` por susurro le pregunta a cada bot por su lobby).

**Para entrar a una partida**: menú *Custom Game* → *Play Game*. En la lista
va a aparecer la partida. **Doble clic sobre ella.** Ojo con esta trampa del
cliente: seleccionar la partida en la lista **NO llena el campo del
nombre**, así que apretar *Join* con la partida apenas seleccionada no hace
nada. Es doble clic, o escribir el nombre exacto en el campo y recién ahí
*Join*.

### Comandos dentro del lobby (el bot te ignora hasta que te verifiques)

Adentro del lobby, el bot **ignora en silencio** los comandos de cualquiera
que no haya verificado su identidad — cualquiera podría entrar con el nombre
de un admin, así que no se fía del chat del lobby. La verificación es un
susurro por Battle.net (donde tu identidad sí está autenticada por el login):

```
/w hostbotN sc
```

Una sola vez por partida, y de ahí en más tus comandos en el lobby andan.
El atajo equivalente es mandar el comando directamente por susurro, por
ejemplo `/w hostbotN !start` (solo admins). La `N` es el número del bot que
hostea esa partida: se ve en el lobby, en el nombre del jugador virtual. Si no sos admin no te hace falta
nada de esto: entrás al lobby y esperás que arranque.

### Arrancar la partida sin admin: `!ready`

No hace falta que haya un admin para empezar. Cualquiera puede escribir
**`!ready`** en el chat del lobby (esto **no** necesita verificación). Cuando
**todos** los que están en el lobby pusieron `!ready` —y son al menos 2— el bot
avisa y arranca **solo en 30 segundos**. Si querés saltarte la espera, con
todos listos alguien escribe **`!start`** y arranca en el acto. `!notready`
saca tu "listo" si te arrepentís (y frena la cuenta regresiva). Si alguien se
va o alguien deja de estar listo, la cuenta se cancela.

### Mapas

- Los mapas livianos **te los manda el bot solo** en el lobby (se ve la
  barra de descarga). No hay que hacer nada.
- Los pesados harían la espera del lobby eterna, así que se reparten aparte
  dentro del kit: los `.w3x` van descomprimidos en
  **`<carpeta del juego>\Maps\Download`** — típicamente
  `C:\Program Files (x86)\Warcraft III\Maps\Download`. **No** es la carpeta
  Documentos: Warcraft III empezó a usar Documentos recién en el parche 1.28,
  y este servidor es 1.27b. El `INSTALAR.bat` del kit los pone donde va.

## Si algo no anda

| Síntoma | Causa y solución |
|---|---|
| `Unable to connect to Battle.net...` | O el juego se abrió sin el loader (usá `w3l.exe`, paso 3), o el gateway elegido no es el nuestro. Con el kit: que arriba diga **WC3 Revival**. A mano: que diga **Northrend (Europe)** y que la línea del `hosts` esté puesta (paso 2). |
| Veo la partida en la lista pero no puedo entrar | Versión distinta del juego (los 515.048 bytes del paso 1) o versión distinta del mapa. Los mapas del servidor llevan una preview propia inyectada, así que el archivo tiene que ser exactamente el nuestro: borrá el que tengas y dejá que te lo mande el bot. |
| Al entrar a una partida, `...could not be found` o vuelve a la lista | Ese lobby ya no existe (la partida arrancó, o venció por tiempo). Esperá su recreación automática y verificá por susurro con `!getgames`. |
| El juego crashea (típico en Windows 11 24H2) | [DDrawCompat](https://github.com/narzoul/DDrawCompat/releases): copiar su `ddraw.dll` a la carpeta del juego, junto al ejecutable. No hay que configurar nada. |
| La app de Battle.net cuelga en "Security Check" | Es la línea del `hosts` (paso 2). Esperable; revertila solo si necesitás la app. |

Si nada de esto lo destraba, avisá con la **hora exacta** del intento: del
lado del servidor queda registro de todo y se puede diagnosticar
(`scripts/diagnose-join.sh`).
