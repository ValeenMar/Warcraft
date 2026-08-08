# Cómo conseguir una instalación 1.26a

Investigado y verificado en vivo el **2026-08-08**. La conclusión corta:
**Blizzard sigue publicando gratis el parche 1.26a en su propio CDN**, así que
la parte difícil está resuelta. Lo que hay que tener es el juego base.

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
