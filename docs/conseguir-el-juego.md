# Cómo conseguir una instalación limpia del juego

Investigado y verificado en vivo el **2026-08-08**.

**La versión objetivo del proyecto es 1.27a** (ver docs/version-juego.md): es
la que entrega hoy el instalador oficial de Blizzard, no necesita parcheo, y
PvPGN la soporta de fábrica. Este documento cubre también 1.26a porque el
parche oficial sigue disponible y sirve si se quiere esa versión.

**Verificación rápida de una instalación 1.27a genuina**: `war3.exe` tiene que
pesar exactamente **514.536 bytes**, con fecha 05/08/2016. (Para 1.26a son
471.040 bytes, 18/03/2011.) Los tamaños salen del `versioncheck.json` del
propio PvPGN.

## Lo que cambió (y hay que saber antes de empezar)

- **21 de noviembre de 2025**: venció la posibilidad de canjear CD keys
  clásicas de RoC/TFT en una cuenta Battle.net
  ([anuncio oficial](https://news.blizzard.com/en-us/article/24241844/original-warcraft-iii-keys-expire-on-november-21)).
  Si registraste tus keys antes de esa fecha, conservás todo. Si nunca las
  registraste, ese tren se fue — pero los CDs siguen sirviendo para instalar,
  que es lo único que necesitamos acá.
- **29 de abril de 2026**: Blizzard agregó a la app de Battle.net un cliente
  clásico, **"Warcraft III – Legacy TFT 1.29"**. **No nos sirve**: es 1.29,
  declarado "offline and LAN only", y **PvPGN tiene su techo en 1.28.5**.
  Es una trampa fácil de pisar.
- **Reforged no sirve como fuente de archivos**: desde 1.30 el juego usa CASC
  en vez de MPQ. `war3.exe`, `Storm.dll`, `Game.dll` y `War3Patch.mpq`
  directamente **no existen** ahí. Comprar Reforged no te da el 1.26a.

## Los parches oficiales (verificados con HTTP 200 el 2026-08-08)

`ftp.blizzard.com` resuelve a CloudFront con backend S3 de Blizzard: es
infraestructura oficial, no un mirror. **Solo por HTTP** — el certificado TLS
no cubre ese hostname, así que `https://` falla la verificación.

| Archivo | URL | Tamaño |
|---|---|---|
| TFT 1.26a castellano | `http://ftp.blizzard.com/pub/war3x/patches/pc/War3TFT_126a_Castellano.exe` | 66.245.887 B |
| TFT 1.26a inglés | `http://ftp.blizzard.com/pub/war3x/patches/pc/War3TFT_126a_English.exe` | 58.718.061 B |
| RoC 1.26a castellano | `http://ftp.blizzard.com/pub/war3/patches/pc/War3ROC_126a_Castellano.exe` | 25.044.132 B |
| RoC 1.26a inglés | `http://ftp.blizzard.com/pub/war3/patches/pc/War3ROC_126a_English.exe` | 18.484.644 B |

Hay también 1.24b, 1.24e, 1.25b, 1.27a y 1.27b en las mismas rutas. El
listado de directorio está deshabilitado: hay que pedir el nombre exacto.

**Detalle crítico**: los parches **solo van para adelante**. El 1.26a sube
desde cualquier versión anterior, pero **se niega a instalarse sobre 1.27+**.

## Ruta A (recomendada): tenés los CDs

1. Instalar **RoC desde el CD**, después **TFT desde el CD**, con tus keys.
2. Bajar el parche 1.26a de la tabla de arriba y correrlo **como
   administrador**. Elegí el idioma que coincida con tus CDs.
3. Copiar los 4 archivos al server (ver abajo).
4. Para jugar: **solo el loader o el `.reg` de gateway** (ver docs/clientes.md).

## Ruta B: tenés la licencia en Battle.net pero no los CDs

Blizzard mantiene "Legacy Downloaders" oficiales (verificados HTTP 200):

```
https://us.battle.net/download/getLegacy?product=WAR3&locale=esES&os=WIN   (Reign of Chaos)
https://us.battle.net/download/getLegacy?product=W3XP&locale=esES&os=WIN   (Frozen Throne)
```

La descarga es anónima pero **el instalador pide la CD key de 26 dígitos**
(la sacás de tu cuenta Battle.net). Te deja en **1.27a v2**.

**Acá está el escalón**: 1.27a no baja a 1.26a con el parche standalone. Dos
salidas:

- **Warcraft 3 Version Switcher** (gaming-tools.com), guardando el `.exe` del
  parche 1.26a oficial en su carpeta `wvs`. Es la ruta documentada, aunque la
  herramienta está vieja y con errores.
- **Quedarse en 1.27a**, que es prácticamente 1.26a recompilado y anda mejor
  en Windows moderno (abandonó Direct3D 8). Varios servidores PvPGN lo
  soportan. Si vas por acá, `WC3_WAR3_VERSION=27` en el `.env` y hay que
  reverificar el versioncheck de PvPGN.

## Ruta C: no tenés ni los CDs ni licencia en Battle.net

Es el caso más incómodo y conviene decirlo derecho: **no hay ningún camino
legítimo y gratis**. El canje de CD keys clásicas cerró el 21/11/2025 y
Reforged no sirve como fuente (usa CASC, no tiene los MPQ ni los ejecutables
que necesita el bot, y el cliente Legacy que habilita es 1.29, por encima del
techo de PvPGN).

Lo que sí queda, y es barato: **comprar una copia física usada**. Warcraft III
Reign of Chaos + The Frozen Throne se consiguen sin problema en el mercado de
segunda mano argentino (MercadoLibre) por ser un juego de hace más de 20 años.

Lo que hay que tener en cuenta al comprar:

- **Hacen falta los DOS**: Reign of Chaos *y* The Frozen Throne. TFT es una
  expansión y no instala sin el juego base. Muchas publicaciones venden el
  combo.
- **Comprar la caja física con la CD key impresa**, no publicaciones
  "digitales". Las que ofrecen el juego "en formato digital" suelen ser keys
  compartidas, keys ya canjeadas (que desde noviembre de 2025 ya no se pueden
  canjear de nuevo) o directamente copias piratas.
- Verificar con el vendedor que **la clave de 26 dígitos esté presente y
  legible** — es lo único realmente imprescindible.

Con la caja en la mano hay dos formas de instalar:

1. **Desde los discos**, si tenés lectora óptica.
2. **Sin lectora**: bajar el instalador oficial con los Legacy Downloaders de
   la Ruta B y meterle la clave impresa en la caja. El instalador clásico
   valida la clave localmente (por algoritmo), no contra un servidor de
   Blizzard, así que sirve aunque la clave haya estado registrada antes en
   otra cuenta. Esta ruta te deja en 1.27a sin parchear nada.

Comprar una caja que traiga **discos y clave** deja las dos puertas abiertas.

## Los 4 archivos que necesita el hostbot

En una instalación 1.26a están **planos en la raíz** (no hay subcarpetas ni
CASC), típicamente en `C:\Program Files (x86)\Warcraft III\`:

```
war3.exe          <- ejecutable de RoC (NO "Frozen Throne.exe")
Storm.dll
Game.dll
War3Patch.mpq     <- de acá salen Scripts\common.j y Scripts\blizzard.j
```

Van a `/opt/wc3/mpq/` en el VPS (ver RUNBOOK fase 1). El bot **no ejecuta el
juego**: solo lee estos archivos para calcular hashes de mapas.

**Regla de oro**: los 4 archivos tienen que ser de la **misma versión que
usan los jugadores**. Si el server es 1.26a, archivos de 1.26a. Mezclar
versiones rompe los hashes y nadie puede entrar a las partidas.

## Lo que NO hay que bajar

Los servidores PvPGN grandes (Eurobattle y la mayoría de los latinos)
ofrecen "el cliente completo" para descargar. Eso es **redistribución del
juego sin licencia**, y además **no hace falta**: siendo dueño del juego,
de todo ese ecosistema lo único que se usa es el **loader** o el archivo
`.reg` de gateway. Tampoco hacen falta ISOs crackeados ni cracks de CD key —
la ruta oficial da un resultado mejor, porque el parche 1.26a lo sigue
regalando Blizzard.

## Compatibilidad con Windows moderno

1.26a es anterior al soporte oficial de Windows 7+ (que llegó en 1.27a) y
todavía usa Direct3D 8, que Windows moderno emula. Anda, pero:

| Problema | Solución que usa la comunidad |
|---|---|
| Crashes en **Windows 11 24H2** (reportado por iCCup, 05/2025) | [DDrawCompat](https://github.com/narzoul/DDrawCompat/releases): copiar `ddraw.dll` junto al ejecutable, sin configurar nada |
| Colores/gamma raros | DDrawCompat o dgVoodoo2 |
| 4:3 y tope 1280x1024 | [WFE](https://github.com/UnryzeC/WFE-Release) (soporta 1.26a) o RenderEdge Widescreen Fix |
| Alt-tab roto en fullscreen | correr con `-window` + Fullscreenizer |

**Linux con Wine**: anda bien (hay scripts de Lutris). Punto débil conocido:
los cinemáticos fallan con DXVK activo — se desactiva DXVK y se usa OpenGL
en modo ventana.

## Errores frecuentes al aplicar el parche

### `ERROR: Wrong language patch file - game: enUS - patch: esES`

El juego instalado está en **inglés** y el parche que bajaste es el
**castellano** (o al revés). Los parches de Blizzard son por idioma y no se
mezclan. Solución: bajar el que coincida.

| Juego en… | TFT | RoC |
|---|---|---|
| inglés (`enUS`) | `War3TFT_126a_English.exe` | `War3ROC_126a_English.exe` |
| castellano (`esES`) | `War3TFT_126a_Castellano.exe` | `War3ROC_126a_Castellano.exe` |

El propio mensaje de error te dice cuál es cuál: `game: enUS` es el idioma de
tu instalación, `patch: esES` el del archivo que corriste.

### `ERROR: unable to create file C:\...\BNUpdate.exe` / "no puede encontrar la ruta"

El parche no está escribiendo en tu carpeta de Descargas: escribe en la
carpeta de instalación del juego, que lee del registro de Windows
(`HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\Warcraft III\InstallPath`).
El error significa que esa ruta **no existe**. Pasa cuando la carpeta del
juego se movió, se renombró o se copió a mano en vez de instalarla.

Soluciones, en orden:

1. Verificar dónde está realmente `war3.exe` (suele ser
   `C:\Program Files (x86)\Warcraft III\`, no `C:\Program Files\`).
2. Si la ruta del registro apunta a otro lado, corregirla ahí, o reinstalar
   el juego desde el CD/instalador para que quede bien registrada.
3. Correr el parche **como administrador** (necesario para escribir en
   `Program Files`).

### `ERROR: unable to apply patch to file '...\shadowstrike.mdx'` / "no corresponde con la suma de comprobación"

El parche aplica deltas binarios sobre los archivos que están adentro de los
MPQ, así que necesita que esos archivos estén exactamente en el estado que
espera. Un checksum que no coincide significa que no lo están. Dos causas, en
orden de frecuencia:

1. **Estás intentando BAJAR de versión** — es de lejos la más común. Si el
   juego ya está en 1.27a y corrés el parche 1.26a, el parche encuentra
   archivos más nuevos de los que espera y falla con este error en vez de
   decirte claramente "no puedo bajar de versión". **Comprobalo primero**:
   mirá la versión en el ángulo inferior derecho del menú principal antes de
   suponer nada.
2. **La instalación no es limpia**: carpeta copiada de otra máquina, repack,
   MPQ modificados, mods, o un parcheo anterior a medias.

`shadowstrike.mdx` (un modelo de Night Elf dentro de `war3.mpq`) es el
archivo donde falla clásicamente, pero el archivo puntual da igual: es el
primero que el parche toca y encuentra distinto.

**Señal delatora**: si el juego está en `C:\Program Files\Warcraft III` en un
Windows de 64 bits, la instalación fue **copiada, no instalada**. El
instalador de Blizzard es de 32 bits y siempre cae en
`C:\Program Files (x86)\Warcraft III`.

No se arregla parcheando de nuevo, ni con permisos de administrador, ni
bajando el parche otra vez. La única salida es **partir de una instalación
limpia**: desde los CDs, o desde los Legacy Downloaders oficiales de la
Ruta B (que además ya vienen en 1.27a y no necesitan parche).

### El parche se niega a instalarse

Los parches **solo van hacia adelante**. Si ya tenés 1.27a, 1.28 o superior,
el 1.26a no se aplica: hay que usar la Version Switcher o reinstalar desde
una base más vieja. Ver la sección "Ruta B" más arriba.

### Cómo saber qué versión e idioma tenés

- **Versión**: abrí el juego y mirá el **ángulo inferior derecho** del menú
  principal (dice `v1.26.0.1` o similar). Sin abrirlo: clic derecho en
  `war3.exe` → Propiedades → pestaña Detalles → *Versión del archivo*.
- **Idioma**: si los menús del juego están en inglés, es `enUS`. También lo
  dice el propio mensaje de error del parche.
