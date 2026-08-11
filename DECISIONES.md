# DECISIONES

Registro de decisiones tomadas sin consultar, con sus alternativas y los
resultados reales de compilación. Convención de estados de verificación:

- **validado en seco**: chequeado con linters/tests sin VPS ni juego
- **compilado y probado**: compilado de verdad y ejecutado en sandbox
- **requiere prueba con el juego real**: solo se confirma con clientes 1.26a

---

## 1. Resultados de compilación (sandbox Ubuntu 24.04.4, GCC 13.3, 2026-08-08)

El sandbox donde se desarrolló este repo es exactamente el toolchain destino
(Ubuntu 24.04 LTS, GCC 13.3.0, CMake 3.28.3), así que estos resultados son
representativos del VPS.

### PvPGN (github.com/pvpgn/pvpgn-server, commit `9cd173f`, HEAD 2026-08-08)

**Estado: compilado y probado.**

- Configuración: `cmake -DWITH_MYSQL=ON -DWITH_D2CS=OFF -DWITH_D2DBS=OFF -DWITH_LUA=OFF`.
- **Falló al primer intento**: `src/bnetd/sql_mysql.cpp` usa `my_bool`, un
  typedef que MySQL eliminó del cliente en 8.0.1. Ubuntu 24.04 trae
  libmysqlclient 8.0.46 → `error: 'my_bool' was not declared in this scope`.
- **Parche**: `sed -i 's/\bmy_bool\b/bool/g' src/bnetd/sql_mysql.cpp` (en
  MySQL >= 8.0 `my_bool` era exactamente `bool`; reemplazo directo, sin
  cambio semántico). Automatizado en `install/10-build-pvpgn.sh`.
- Con el parche compila limpio y linkea. `bnetd -v` → `PvPGN 1.99.7.2.1-PRO`.
- **Smoke test**: `bnetd -f` con la config default (storage file) arranca,
  suelta privilegios de root, y escucha en `0.0.0.0:6112` (bnet) y
  `0.0.0.0:6200` (w3route). No se probó el backend MySQL en runtime (no hay
  mysqld en el sandbox): **requiere prueba en el VPS**, aunque el driver
  compiló y PvPGN crea las tablas solo (ver decisión 6).
- Dependencias usadas: `default-libmysqlclient-dev` 1.1.0 (→ libmysqlclient
  8.0.46), zlib1g-dev.
- Dato útil: el `versioncheck.json` que instala upstream **ya trae la entrada
  de TFT 1.26a** (`"Warcraft III - TFT (Expansion) 1.26a"`, version
  `1.26.0.1`, hash `0xf2e7cec2`, tag `W3XP_126A`). No hay que fabricar
  entradas de versioncheck.

**Segundo parche, descubierto en el VPS real (2026-08-08)**: `RANK` es
palabra reservada en MySQL desde 8.0.2 (se la quedaron las funciones de
ventana), y PvPGN tiene una columna llamada `rank` en la tabla
`arrangedteam`, usada sin comillas en tres queries de `sql_common.cpp`
(SELECT/INSERT/UPDATE) y en `sql_DB_layout.conf.in`. Resultado: un
`[error] sql_load_teams: error query db` en cada arranque.

- **Alcance real: nulo para este proyecto.** Los "arranged teams" son el
  ladder por equipos armados de Battle.net; acá se juegan partidas custom
  hosteadas por el bot. Ninguna otra tabla usa esa palabra.
- Igual se parchea (escapando con backticks) en
  `install/10-build-pvpgn.sh`, porque un `[error]` permanente en cada
  arranque envenena el log: cuando algo real falle, ya nadie lo va a mirar.
- El parche toca solo los literales SQL; `team->rank`, que es C++ válido,
  queda intacto (verificado).
- No es urgente: si PvPGN ya está compilado y andando, el error es cosmético
  y el parche se aplica en la próxima recompilación.

También aparece un `WARNING: MYSQL_OPT_RECONNECT is deprecated` al arrancar.
Es solo un aviso de deprecación de libmysqlclient 8; no rompe nada.

### Aura-bot (github.com/Josko/aura-bot, commit `1e5df42`, último del upstream, 2018-09-09)

**Estado: compilado y probado.**

- **Falló al primer intento**: ~8 headers (`bnetprotocol.h`, `gameslot.h`,
  `map.h`, `socket.h`, etc.) usan `uint8_t/uint32_t` sin incluir `<cstdint>`.
  Con libstdc++ de GCC <= 12 entraba transitivamente; GCC 13 lo dejó de
  arrastrar → cascada de `'uint8_t' was not declared in this scope`.
- **Parche**: insertar `#include <cstdint>` al inicio de cada header que usa
  `u?int(8|16|32|64)_t` y no lo incluye. Automatizado (e idempotente) en
  `install/20-build-hostbot.sh`.
- StormLib y bncsutil vienen *vendored* dentro del repo de Aura y compilaron
  sin tocar nada (StormLib vía CMake, bncsutil vía make; dependencias: libgmp,
  libbz2, zlib, m4). Se instalan en /usr/local + ldconfig, como documenta el
  README del upstream.
- El link final de `aura++` usa `-flto` y tarda varios minutos en 4 vCPU; es
  normal, no está colgado.
- **Smoke test**: `aura++` arranca, lee `aura.cfg`, abre su sqlite `aura.dbs`
  y queda corriendo. La conexión a un PvPGN con clientes 1.26a **requiere
  prueba con el juego real**.

---

## 2. Aura y no GHost++ como hostbot

**Decisión**: Aura-bot (fork moderno de GHost++, C++14, sqlite integrado).

- A favor: base de código mucho más chica y sana que GHost++, compila casi
  limpio en toolchains modernos (solo el parche cstdint), sin dependencias
  muertas (GHost++ clásico requiere Boost viejo y MySQL antiguos).
- En contra / riesgo: el upstream apunta a parches 1.28+ (su sample trae
  `war3version = 29`). Para 1.26a seteamos `WC3_WAR3_VERSION=26`.
  **TODO(verificar) crítico**: que este build acepte clientes 1.26a y calcule
  bien `exeversion/exeversionhash` contra los MPQ de 1.26a. Si no funciona,
  el plan B documentado es GHost++ clásico (ghostplusplus), que es de la era
  1.26 — a costa de pelearse con su build.
- Si me dijeran "compatibilidad con mapas/clientes viejos por encima de
  todo": arrancaría directamente por GHost++ 17.x o el fork ghost-one usado
  por comunidades 1.26 de la época, aceptando el dolor de build.

## 3. Instancias de Aura como directorios + unidad systemd instanciada

**Decisión**: cada bot vive en `/opt/wc3/hostbot/instances/N/` con su propio
`aura.cfg`, y `wc3-hostbot@.service` usa `WorkingDirectory=.../instances/%i`.

- Motivo (verificado en el código): `src/aura.cpp` hace `CFG.Read("aura.cfg")`
  — la ruta está **hardcodeada relativa al directorio de trabajo**, no acepta
  config por argumento. La unidad instanciada del enunciado
  (`instance-%i.cfg` plano) no es posible sin parchear Aura; el layout por
  directorios logra lo mismo (alta de bot = un `.env` nuevo + render +
  `systemctl enable --now wc3-hostbot@3`) sin tocar el código.
- Costo: cada instancia tiene su `aura.dbs` (bans/stats separados por bot).
  Para fase 1-2 es aceptable; unificar stats es parte de la fase 3.

## 4. Templates renderizados con envsubst con whitelist WC3_*

**Decisión**: los templates usan solo placeholders `${WC3_*}` y el render
pasa a `envsubst` la lista explícita de variables con ese prefijo.

- Motivo: los conf de PvPGN usan `${...}` con otro significado (p. ej.
  `${prefix}` en `sql_DB_layout.conf`); un envsubst sin whitelist los
  destrozaría en silencio.
- El render valida que no quede ningún `${WC3_` vivo y aborta si falta una
  variable. Validado en seco (validate.sh renderiza con `.env.example`).

## 5. bnetd.conf.tpl derivado del sample real, no escrito a mano

**Decisión**: `config/pvpgn/bnetd.conf.tpl` es el `bnetd.conf` que instala el
propio build de PvPGN (con las rutas /opt/wc3/pvpgn ya renderizadas por su
CMake), con exactamente 7 valores parametrizados (storage_path, servaddrs,
location, description, url, contact_name, contact_email) y `track = 0`
(server privado: no anunciarse a trackers públicos).

- Garantía: cero claves inventadas; todo lo demás queda en los defaults del
  upstream, que el smoke test cargó sin errores.
- Lo mismo para `address_translation.conf.tpl`: es el sample upstream más una
  única regla para el w3route (`0.0.0.0:6200 -> ${WC3_PUBLIC_IP}:6200`),
  siguiendo el ejemplo comentado del propio archivo.

## 6. MySQL: el script solo crea base y usuario; las tablas las crea PvPGN

**Decisión**: `30-setup-mysql.sh` crea `pvpgn`@localhost y la base, nada más.

- Motivo (verificado en fuente y en el conf): PvPGN crea las tablas en el
  primer arranque desde `etc/pvpgn/sql_DB_layout.conf` (el archivo lo dice
  textualmente: "the server will create the tables ... don't forget to create
  the DB yourself"; el código está en `src/bnetd/sql_dbcreator.cpp`).
  Duplicar el schema a mano en el repo sería inventarlo y desincronizarse.
- **Requiere prueba en el VPS**: primer arranque de bnetd contra MySQL real.

## 7. Pins de commit en los scripts de build

**Decisión**: `10-build-pvpgn.sh` y `20-build-hostbot.sh` clonan y hacen
checkout de los commits exactos validados en sandbox (`9cd173f` y `1e5df42`),
sobreescribibles por variables `WC3_PVPGN_REF` / `WC3_AURA_REF`.

- Motivo: lo único que sé con certeza es que ESTOS commits compilan con ESTOS
  parches en ESTE toolchain. Un HEAD futuro puede romper el parche o
  arreglarlo; en ambos casos quiero que sea una decisión consciente.

## 8. Sin Docker, sin CI, sin monitoreo

Pedido explícito del enunciado; la ruta de migración a contenedores y sus
trampas (NAT/bridge vs anuncio de IP en protocolo) quedan en
`docs/docker-futuro.md`.

## 9. mpyq en venv, no en el sistema

**Decisión**: `inspect-map.py` usa stdlib para el header HM3W y `mpyq` solo
si está disponible; el bootstrap crea `/opt/wc3/venv` con mpyq+pyyaml.

- Motivo (verificado en sandbox): `pip install mpyq` contra el Python del
  sistema en Ubuntu 24.04 **falla** (`AttributeError: install_layout`, el
  setup.py de 2015 de mpyq choca con el setuptools parcheado de Debian).
  Dentro de un venv limpio instala perfecto.
- Bonus del diseño: el header HM3W (nombre y max jugadores) vive FUERA del
  MPQ, así que se lee incluso en mapas protegidos y sin mpyq.
- Limitación honesta: mpyq exige el magic MPQ al inicio del archivo; los
  .w3x lo tienen en offset 512, así que el script recorta el prefijo antes de
  abrirlo. El parser de `war3map.w3i` está validado contra .w3i sintéticos
  (tests) — **la validación con mapas reales es parte de la fase 1**.

## 11. Versión objetivo: 1.27a en vez de 1.26a (cambio del 2026-08-08)

**Decisión**: el proyecto apunta a **1.27a** (build in-game `1.27.0.52240`,
`version` de protocolo `1.27.0.16`, tag `W3XP_127A`).

- Motivo principal, y es pragmático: **el operador ya tiene una instalación
  de 1.27a funcionando**, y conseguir 1.26a limpio hoy exige CDs físicos o
  comprar una copia usada (el canje de CD keys clásicas cerró el 21/11/2025).
- PvPGN lo soporta de fábrica: verificado leyendo el `versioncheck.json` que
  instala el propio build (entradas `W3XP_127A` y `WAR3_127A`).
- La gran mayoría del catálogo es formato 1.24a-1.28c (los `verde` y
  `amarillo` del registry), así que andan igual; los `rojo` pre-1.24 hay que
  probarlos en cualquiera de las dos versiones.
- 1.27a anda mejor en Windows moderno: agregó soporte oficial de Windows
  7-10 y abandonó Direct3D 8, de donde salen los crashes de 1.26a en
  Windows 11 24H2.
- Se pierde ser "el estándar latino de DotA", que en un servidor privado para
  amigos no significa nada.
- Reversible con `WC3_WAR3_VERSION=26` y archivos de 1.26a en `/opt/wc3/mpq/`.

**Corrección honesta de un diagnóstico previo**: al ver el error
`unable to apply patch to file ...shadowstrike.mdx` diagnostiqué que la
instalación estaba modificada, apoyándome en que vivía en `C:\Program Files\`
en vez de `Program Files (x86)`. La explicación más simple resultó ser otra:
se estaba intentando aplicar el parche 1.26a sobre una instalación que ya
estaba en 1.27a, y los parches no bajan de versión. El error de checksum era
la forma fea que tiene BNUpdate de decir eso.

## 13. Resultados de la primera conexión real bot ↔ PvPGN (2026-08-08)

**El TODO #1 quedó RESUELTO, y a favor.** El log de Aura contra el PvPGN real:

```
[BNET] connecting to server [127.0.0.1] on port 6112
[BNET] connected
[BNET] attempting to auth as Warcraft III: The Frozen Throne
[BNET] cd keys accepted            <-- el handshake de version PASO
[BNET] logon failed - invalid username, disconnecting
```

`cd keys accepted` significa que el `SID_AUTH_CHECK` completo (que incluye la
verificación de versión con `exeversion`/`exeversionhash` calculados por
bncsutil desde los MPQ) fue aceptado por PvPGN. O sea: **Aura de 2018 se
entiende con PvPGN hablando 1.27a**, con `war3version=27` y los campos de
`exeversion` vacíos (autocálculo). No hace falta el plan B de GHost++.

El fallo restante era solo que la cuenta del bot no existía todavía.

**Dos problemas menores encontrados en el mismo arranque:**

1. `warning - unable to load MPQ file [...War3Patch.mpq] - error code 13`.
   Error 13 es EACCES. Causa: Aura llama a `SFileOpenArchive(..., 0,
   MPQ_OPEN_FORCE_MPQ_V1, &MPQ)` **sin** `MPQ_OPEN_READ_ONLY`, así que
   StormLib abre el archivo en lectura-escritura. Con los MPQ en `640
   root:wc3` y la unidad de systemd montando `/opt/wc3/mpq` en
   `ReadOnlyPaths`, el open falla. Consecuencia: no extrae `common.j` ni
   `blizzard.j`, que son los que permiten calcular `map_crc` automáticamente.
   **Parcheado** en `install/20-build-hostbot.sh` agregando el flag; el MPQ
   solo se lee, nunca se escribe, así que es el comportamiento correcto.

2. `warning - bot_virtualhostname is longer than 15 characters`. El límite de
   15 cuenta **también el código de color**: `|cFF4080C0` ya son 10
   caracteres, así que el nombre visible puede tener 5 como máximo. Corregido
   en los `instance-N.env` y en `.env.example`.

## 14. El cliente necesita un loader sí o sí (verificado 2026-08-08)

Los clientes modernos de Warcraft III **verifican una firma criptográfica del
servidor** antes de continuar el login. PvPGN no puede generarla. Sin un
loader que desactive esa verificación, ningún cliente conecta, por más que el
gateway, el DNS y el firewall estén perfectos.

Evidencia recogida en el servidor real (`bnetd.log`): la conexión del cliente
llega, manda su `AUTH_INFO` (`platform=IX86, product=W3XP, versionid=0x1b`),
PvPGN responde con el desafío de CheckRevision, y **el cliente cierra la
conexión** (`read returned -1`). O sea: red, gateway y firewall correctos; el
corte lo decide el cliente.

- **Impacto en el proyecto**: cada jugador necesita el loader, no solo el
  operador. Eso hay que decirlo en la guía de la fase 4 (web de registro).
- El loader recomendado es [w3l](https://pvpgn.pro/w3l.html) (GPL v3), que no
  distribuye nada del juego: solo parchea en memoria. Soporta 1.22a-1.28f.
- **Corrección de este documento**: `docs/clientes.md` presentaba el loader
  como una de varias alternativas al editor de gateways. Es incorrecto: el
  editor de gateways resuelve *a dónde* conectarse, el loader resuelve *que
  te dejen*. Hacen falta los dos (o el `hosts` más el loader).

Dato secundario útil: el valor `Gateways` del registro **puede no existir**
(pasó en la instalación de prueba). En ese caso el cliente usa la lista
compilada dentro del ejecutable y editar el registro no cambia nada; el
redirect por `hosts` de `europe.battle.net` sí funcionó, porque el gateway
"Northrend (Europe)" resuelve ese nombre.

## 15. StormLib abre en lectura-escritura: choca con `ProtectSystem=strict`

Aura llama a `SFileOpenArchive` sin `MPQ_OPEN_READ_ONLY`, así que **StormLib
abre todo MPQ en lectura-escritura**, aunque solo vaya a leerlo. Eso choca de
frente con el blindaje de systemd, y afecta a **dos** directorios distintos:

1. `/opt/wc3/mpq` (los archivos del juego) → falla la extracción de
   `common.j`/`blizzard.j`, con `error code 13`.
2. `/opt/wc3/maps` (los `.w3x`) → falla la apertura de cada mapa, y el bot
   responde en el canal `Error while loading map: [invalid map_crc detected]`.

El segundo es más engañoso, porque el log muestra que el archivo **sí se leyó**
(calcula `map_size` y `map_info` correctamente) y solo falla al abrirlo como
MPQ:

```
[MAP] warning - unable to load MPQ file [/opt/wc3/maps/XXX.w3x]
[MAP] calculated map_size = 197 94 8 0
[MAP] unable to calculate map_crc/sha1 - map MPQ file not loaded
[MAP] invalid map_crc detected
```

Ojo con el diagnóstico: **no son los permisos del archivo**. Con
`ProtectSystem=strict` todo el sistema de archivos se monta de solo lectura
salvo lo listado en `ReadWritePaths`; sacar un directorio de `ReadOnlyPaths`
no alcanza, hay que **agregarlo a `ReadWritePaths`**.

**Solución adoptada, en dos capas:**

- El parche de `MPQ_OPEN_READ_ONLY` en `install/20-build-hostbot.sh` (fix de
  raíz, se aplica en la próxima recompilación de Aura).
- Mientras tanto, `/opt/wc3/maps` pasa a `ReadWritePaths` en la unidad, para
  no obligar a recompilar en medio de una puesta en marcha. Una vez que Aura
  esté recompilado con el parche, puede volver a `ReadOnlyPaths`.

## 16. El bot NO debe conectarse a PvPGN por loopback (2026-08-09)

El error más instructivo de la puesta en marcha, porque es **exactamente el
problema que motivó descartar Docker**, y me lo comí igual en la configuración
por loopback.

**Síntoma**: la partida se crea, PvPGN la lista correctamente
(`GAMELISTREPLY sent 1 of 1 games`), el cliente la encuentra al buscarla por
nombre (`specific game found`) y al intentar entrar **vuelve a la lista sin
ningún mensaje de error**. Ni el bot ni PvPGN loguean nada raro.

**Causa**, verificada en el código de PvPGN:

```c
// src/bnetd/game.cpp
game->addr = conn_get_game_addr(game->connections[i]);
// src/bnetd/connection.cpp
extern unsigned int conn_get_game_addr(t_connection const * c) {
    return c->socket.udp_addr;   // la IP DESDE LA QUE se conecto el host
}
```

PvPGN usa como dirección de la partida **la IP desde la que se conectó quien
la creó**. Con `bnet_server = 127.0.0.1` en `aura.cfg`, esa IP es el loopback,
así que PvPGN les anuncia a todos los jugadores que la partida está en
`127.0.0.1:6113`. Cada cliente intenta conectarse a sí mismo y falla en
silencio.

**Solución**: `bnet_server = ${WC3_PUBLIC_IP}`. El bot se conecta a su propio
servidor por la IP pública, PvPGN registra esa IP, y los jugadores reciben una
dirección alcanzable. El tráfico no sale a internet: Linux resuelve
localmente las conexiones a una IP propia.

Alternativa descartada: una regla por puerto en `address_translation.conf`
(PvPGN sí aplica `trans_net` a las direcciones de partida, no solo al
w3route). Se descartó porque hace falta una línea por cada puerto de bot,
mientras que cambiar `bnet_server` lo arregla para todas las instancias de
una.

**Lección**: la regla "los protocolos que anuncian direcciones adentro del
payload odian cualquier capa de traducción" no aplica solo a NAT y bridge
networking. **Aplica también al loopback.**

## 18. Plan B validado: GHost++ compilado en Ubuntu 24.04 (2026-08-09)

Mientras se verificaba el parche de Aura, se compiló **GHost++**
([uakfdotb/ghostpp](https://github.com/uakfdotb/ghostpp), commit `cf39754`)
en el sandbox Ubuntu 24.04 / GCC 13.3, como plan B ejecutable y no teórico.

**Resultado: compila fácil.** Receta completa:

- `apt install libboost-date-time-dev libboost-system-dev libboost-filesystem-dev libboost-thread-dev`
- Un solo parche de código: `my_bool` → `bool` en `ghost/ghostdbmysql.cpp`
  (mismo problema de MySQL 8 que PvPGN, decisión 1).
- Compilar la CascLib vendored (`cd CascLib && cmake && make install`); el
  StormLib y bncsutil que ya instala este proyecto linkean directo.
- Smoke test OK; soporte 1.26/1.27 confirmado en código (path clásico
  `war3.exe`+`storm.dll`+`game.dll` para `war3version <= 28`, logon
  `pvpgn` dedicado).

**Lo que GHost++ tiene y Aura no**: `!autohost <maxgames> <startplayers>
<gamename>` — partidas que se rehostean solas (lo pedido como "lobbies
siempre disponibles"). Claves: `autohost_maxgames`, `autohost_startplayers`,
`autohost_gamename`, `autohost_owner`.

**Para el futuro** también quedó identificado
[Slayer95/aura-bot](https://github.com/Slayer95/aura-bot): fork activo de
Aura (desarrollo 2024-2026), con soporte multi-versión de W3, byte de slots
version-aware y auto-rehost. Candidato natural si algún día se moderniza el
hostbot; por ahora el Aura parcheado alcanza y está probado.

## 17. Causa raíz de "no puedo entrar al lobby": el soporte de 24 jugadores de Aura (2026-08-09)

**El último bloqueo de la fase 1.** Síntoma: la partida se crea y se anuncia
con la IP y puerto correctos (verificado con `/games`: `64.176.24.103:6113`),
el puerto responde desde la PC del jugador (`Test-NetConnection` OK), el
cliente encuentra la partida por nombre (`specific game found` en bnetd.log)…
y **vuelve a la lista sin error y sin intentar conectarse al bot** (cero
conexiones nuevas en el log de Aura).

**Causa, encontrada en la historia del upstream**: el commit `2de4fc0`
("Add preliminary 24 player support", abril 2018) — incluido en el HEAD
`1e5df42` que compila este proyecto — adapta Aura al protocolo de W3 1.29+,
que amplió el juego de 12 a 24 jugadores. Dos cambios rompen a los clientes
clásicos (1.24-1.28, máximo 12 jugadores):

1. **El statstring del anuncio de partida** (`SEND_SID_STARTADVEX3`,
   `src/bnetprotocol.cpp`): `packet.push_back(98)` pasó a
   `packet.push_back(110)` — de "11 slots libres" (`'b'`) a "23 slots
   libres" (`'n'`). El comentario del propio código advierte: *"this is the
   # of PID's Warcraft III will allocate"*. Un cliente 1.27 recibe 23,
   no puede reservar esa cantidad de PIDs, da la partida por inválida y
   vuelve a la lista **sin conectarse**. Encaja con el síntoma al 100%.
2. **`MAX_SLOTS = 24`** (`src/gameslot.h`) usado en todo `game.cpp`: el
   equipo de observadores pasa de 12 a 24, colores hasta 23, etc. Valores
   ilegales para el protocolo de un cliente de 12 jugadores.

**Por qué el resto funcionaba**: el login BNCS (`cd keys accepted`) no pasa
por ese código; solo el anuncio/join de partidas usa el statstring.

**Fix**: parche quirúrgico que revierte la semántica (MAX_SLOTS=12 y el byte
98), manteniendo los 5 commits posteriores (incluyen un fix de buffer overrun
en bncsutilinterface que queremos). **Verificado en sandbox el 2026-08-09**:
se revisó el diff completo del commit 24p sitio por sitio (todos los demás
usos son aritmética sobre MAX_SLOTS y vuelven solos a 12/11/10; el `110` de
`bnetprotocol.cpp:567` es el código de idioma `enUS`, no tocarlo; el virtual
host usa el sentinel PID 255 y no necesita cambios), se compiló el árbol
parcheado sin errores, y los sed se validaron idempotentes corriendo dos
veces sobre un checkout limpio. Aplicado en `install/20-build-hostbot.sh`,
que además ahora borra los `.o` previos: el Makefile de Aura no rastrea
dependencias de headers, y un make incremental tras tocar `gameslot.h`
produciría un binario mezclado.

**Confirmación empírica final (2026-08-09)**: con el parche compilado en el
VPS, el cliente 1.27a entró al lobby al primer intento y jugó una partida
completa de Marvel TD con 23 ms de ping. Cerrado.

**Confirmación externa**: el issue
[uakfdotb/ghostpp#31](https://github.com/uakfdotb/ghostpp/issues/31)
documenta este mismo bug contra PvPGN para el parche de 24 jugadores
equivalente de GHost++, y el workaround oficial del autor es exactamente
este revert. bnetdocs (packet SID_GETADVLISTEX) confirma la posición y
semántica del byte de slots libres. El fork activo Slayer95/aura-bot lo
resolvió de raíz con un byte version-aware (`86 + maxSupportedSlots`).

**Lección**: "el último commit del upstream" no es sinónimo de "la mejor
versión para tu caso". Para un servidor de clientes clásicos, los commits de
la era 1.29+ son regresiones. El pin de commit ya era política del proyecto
(decisión 7); ahora además sabemos qué commit es la frontera: todo lo
anterior a `2de4fc0` es territorio 1.24-1.28.

## 19. Presentación de los lobbies: nombre con color y preview propia (2026-08-09)

**Qué se quería**: que en la lista de partidas personalizadas el nombre salga
lindo y con color, y que la imagen de preview muestre una tapa del mapa en vez
del minimapa.

**Son dos mecanismos distintos y conviene no mezclarlos.** El nombre lo escribe
el que hostea (`!pub <nombre>`) y viaja en el paquete de anuncio de partida; la
imagen vive **adentro del archivo del mapa**, en `war3mapPreview.tga`. Uno es
gratis, el otro tiene consecuencias.

**Decisión 1 — los nombres van en `maps/lobbies.yaml`, no hardcodeados.** Aura
no tiene autohost ni saca el nombre del mapa (no existe una clave `map_name`
en el cfg: los keys reales están en `map.cpp` y son todos técnicos), así que el
nombre es siempre manual. El límite real es **31 bytes contando los códigos de
color** (`aura.cpp:879`), lo que deja ~19 caracteres visibles con un color o
~15 con dos. Es lo bastante ajustado como para equivocarse, así que hay un test
que falla si un nombre se pasa, y `scripts/lobby-names.py` imprime la chuleta
lista para pegar con Ctrl+V.

Queda un `TODO(verificar)`: que la lista de partidas renderice los códigos de
color en vez de mostrarlos literales. Los nombres de cuenta de Battle.net sí
los aceptan (documentado y probado por terceros), pero la lista de partidas no
se pudo probar sin un cliente. Por eso cada entry lleva también `plain_name`:
si sale literal, se cambia de plan en 5 segundos sin tocar código.

**Decisión 2 — la preview se inyecta en una COPIA del mapa, nunca en el
original.** Meter `war3mapPreview.tga` adentro del `.w3x` cambia el CRC y el
SHA1 que Aura calcula, y eso tiene un costo real: el que tenga el mapa original
bajado de otro lado no puede entrar, se lo tiene que bajar del bot en el lobby.
Se acepta el costo porque es un servidor privado donde el mapa lo repartimos
nosotros (server + kit de amigos), y a cambio la lista de partidas deja de ser
una grilla de minimapas grises. Pero el original queda intacto por defecto:
`--in-place` es opt-in y aun así deja un `.orig`.

**Decisión 3 — el techo de 8 MiB se chequea en el script, no en la cabeza del
operador.** La preview agrega ~23 KB (TGA de 128×128 = 49.196 B sin comprimir,
~22,8 KB ya comprimido con zlib dentro del MPQ). DotA 6.83d tiene ~170 KB de
margen: entra, pero es el caso apretado y el que va a crecer si algún día se
sube a 256×256. `brand-map.py` aborta y limpia la salida si el resultado se
pasa, y hay un test con relleno incompresible que lo verifica.

**Herramienta elegida: `smpq`** (paquete de Ubuntu, frontend de StormLib
9.21) en vez de escribir bindings o usar mpyq. Motivo: mpyq es solo lectura, y
StormLib ya es la biblioteca que usa Aura, así que escribimos el MPQ con
exactamente el mismo código que después lo va a leer.

**Verificado contra el cliente real el 2026-08-09.** Las dos mitades, con
resultados opuestos:

- **La preview funciona.** Se hosteó Pudge Wars con la imagen inyectada y
  aparece en el panel derecho de la lista de partidas, donde el cliente
  dibujaría el minimapa. La cadena completa —generar el TGA, meterlo en el MPQ
  con StormLib, que Aura recalcule CRC y SHA1, que el cliente lo muestre— anda
  de punta a punta.
- **El color en los nombres no.** La lista de partidas **no pinta** los
  códigos: se los come sin mostrarlos. `|cFF77DD44PUDGE |cFFFF3355WARS` se ve
  `PUDGE WARS` en blanco. Los 20 bytes de los dos códigos se gastaban para
  nada, así que `lobby-names.py` pasó a imprimir nombres planos por defecto y
  esos 20 bytes se reinvirtieron en nombres más descriptivos (`Pudge Wars 1.26
  - 2 equipos` en vez de `PUDGE WARS`). La hipótesis de la que se partió —que
  si los nombres de cuenta de Battle.net aceptan color, la lista también—
  resultó falsa; menos mal que cada entry ya traía su `plain_name`.

**También quedó confirmado el riesgo de los mapas protegidos**, que era una
hipótesis: probado contra *DBZ Tribute Ultra* (epicwar 133974, 5,7 MB),
StormLib contesta `Cannot create new file: Operation not permitted` tanto para
agregar como para reemplazar. Y de yapa apareció una trampa: **`smpq` sale con
código 0 aunque StormLib falle**, y en un mapa protegido el listado del MPQ
viene ofuscado, así que la verificación por listado se salteaba sola y el
script daba por buena una inyección que nunca ocurrió. Ahora se verifica
extrayendo el archivo y comparando los bytes.

**El dato que cambió el plan**: de los seis mapas del catálogo real, **cinco ya
traían su propia `war3mapPreview.tga`** con arte del autor. El default pasó a
ser no tocarla. El único que faltaba, Pudge Wars, se resolvió componiendo un
render del personaje sobre el fondo del tema — y `--from-image` acepta una URL,
porque el servidor no tiene navegador para bajar la imagen a mano.

## 20. Marca propia: banner del cliente y mensaje de bienvenida (2026-08-09)

**Qué se quería**: que el banner de arriba del chat (que mostraba el logo de
pvpgn.pro) y el saludo de login (que salía en alemán) sean nuestros.

**Verificado en el código de PvPGN** (mismo commit que corre en el VPS):

- El banner se declara en `ad.json` (clave `adfile`), el archivo vive en el
  `filedir` y el cliente lo baja por BNFTP. Para Warcraft III sirve un **PNG
  común**: `adbanner.cpp` mapea `.png` → tag MNG. El de fábrica mide
  **468×60**, así que esa es la medida del hueco. El clic abre la URL del
  entry.
- El `w3motd.txt` admite **11 líneas** máximo, variables (`%s` server, `%u`
  jugadores, `%g` partidas, `%U` usuarios) y — a diferencia de la lista de
  partidas — **los códigos de color acá sí se renderizan** (el sample de
  fábrica viene pintado).
- El alemán venía de i18n: PvPGN elige la variante del motd según el locale
  del cliente, y los bots caían en `deDE`. La solución no es tocar locales
  sino **pisar el base y todas las variantes de idioma** con el mismo texto,
  que es lo que hace ahora `40-render-configs.sh`.

`make-banner.py` dibuja el banner con los mismos helpers que las previews;
el render lo regenera en cada corrida (si Pillow está en el venv) e instala
`ad.json` + `w3motd.txt`. Falta la mitad cliente: ver el banner y el motd
nuevos en un login real — el cliente **cachea** el banner, puede pedir una
reconexión.

## 21. El kit puede instalar el juego desde cero (2026-08-09)

`INSTALAR-JUEGO.bat` baja los dos instaladores oficiales "Legacy" de
Blizzard (las URLs `getLegacy` documentadas en conseguir-el-juego.md, que
instalan directo 1.27a), los corre en orden RoC → TFT y encadena con
`INSTALAR.bat`. Con eso el camino del amigo sin nada pasa de cinco pasos
manuales a: doble clic + tipear sus dos CD keys.

**Lo que NO se automatiza, a propósito**: el ingreso de la CD key en el
instalador oficial. No hay flag de instalación silenciosa documentado en esos
instaladores, y aunque lo hubiera, cada persona tiene que meter SU key — el
kit no trae ni traerá keys ni archivos del juego (regla de copyright del
proyecto). El instalador se queda en "lo mínimo que tiene que hacer un humano
son sus dos keys".

## 22. Teclas estilo LoL: WFE preconfigurado en el kit (2026-08-09)

**Qué se quería**: QWER para las habilidades, D/F para las extras, smartcast
y vida siempre visible — el pedido original de "que se juegue como LoL".

**Por qué no se puede con el juego solo**: el 1.27a vanilla no tiene teclas
por posición ni "always show health bars" (las dos cosas llegaron recién en
1.29+). Lo único nativo es CustomKeys.txt, que remapea por HABILIDAD, no por
botón: para mapas custom habría que conocer los códigos internos de cada
habilidad de cada mapa. Inviable para un catálogo variado.

**La herramienta es WFE** (github.com/UnryzeC/WFE-Release). Verificado contra
su repo real: soporta 1.27a explícito, convive con w3l (su README documenta
el caso EuroBattle), y su config tiene exactamente lo que hace falta —
`[KEYBINDS]` por posición de la grilla (A_XnYn para habilidades, I_XnYn para
los 6 ítems), `[SMARTCAST]` por botón, `[HEALTHBAR]`/`[MANABAR]` con color
por bando, `ENFORCEHOTKEYS` e `ISHEROONLY` (las teclas solo aplican a héroes:
construir torres en un TD no se ve afectado).

**Cambio de postura**: la decisión anterior era no incluir WFE (antivirus,
VC++, soporte). Se revierte a medias: se incluye pero PRECONFIGURADO y
opcional — el kit trae `extras/WFE` con el perfil `WC3Revival.ini` ya armado
(QWER en la fila de abajo, DF en los dos botones derechos de la fila del
medio — se evita la izquierda porque ahí vive Patrol —, ítems en ZXCVBN para
no pisar los grupos de control) y `TECLAS-LOL.txt` con los 5 pasos de
activación y las advertencias. Lo que convirtió el "no" en "sí": venir
preconfigurado elimina el 90% del soporte que motivaba excluirlo.

**Mecánica de build**: el binario vive en los releases de GitHub (el repo git
trae solo configs), así que `build-kit.sh` descubre la URL del asset por la
API en el momento del build, y `make-wfe-profile.py` genera el perfil contra
el `WFEConfigBase.ini` que vino en ESE zip — si WFE renombra claves, aborta
en vez de producir un perfil a medias. Todo mejor-esfuerzo: sin internet o
sin release, el kit sale sin extras y lo dice.

**No verificado** (necesita Windows): que el perfil funcione en una partida
real. Las claves y el formato salen del ini real del repo, pero la prueba de
fuego es de 5 minutos con el juego.

**ACTUALIZACIÓN (2026-08-10): el kit volvió a salir SIN WFE** (commit "Kit
sin WFE"). El motivo original (inyección en el proceso → falsos positivos de
antivirus → el kit entero parece un virus) pesó más que la comodidad. Lo que
queda de esta decisión: `make-wfe-profile.py` sigue generando el perfil
`WC3Revival.ini`, pero se le pasa al jugador que lo pida, y WFE se baja del
sitio oficial (github.com/UnryzeC/WFE-Release). El `LEEME.txt` del kit lo
explica así.

**ACTUALIZACIÓN 2 (2026-08-10): el término medio definitivo.** El operador
necesita los mapas > 8 MiB (decisión 23), y "que cada amigo se lo baje solo"
no escala. El kit ahora trae `extras/WFE/` con TRES archivos de texto:
`INSTALAR-WFE.bat` (baja el zip del **release oficial pinneado** v3.1.13.85
en la máquina del jugador y verifica su SHA-256 con certutil antes de tocar
nada), el perfil `WC3Revival.ini` (generado en el build contra el
`WFEConfigBase.ini` pinneado del repo de WFE; si upstream renombra claves,
`make-wfe-profile.py` aborta y el kit sale sin extras avisando) y
`TECLAS-LOL.txt` (el paso a paso). El binario sigue SIN viajar en el kit —
se respeta el motivo de la actualización anterior — pero instalarlo pasó de
"bajate esto y pedime el perfil" a un doble clic verificado.

## 23. Mapas de más de 8 MiB: se pueden, con WFE Unlock Map Size (2026-08-09)

**Pregunta**: ¿hay forma de hostear un mapa que pese más de 8 MiB (FOCS pesa
15-18 MB)? El techo de 8 MiB estaba documentado como muro duro.

**Hallazgo**: el muro es del CLIENTE, no del servidor. `src/map.cpp` de Aura
calcula el tamaño real y hostea sin límite propio; el que rechaza > 8 MiB es
el `game.dll` de cada jugador. Y ese límite se levanta de dos formas
(confirmado en ENT Gaming / Hive): el parche 1.27b lo sacó de fábrica, o WFE
con `REMOVEMAPSIZELIMIT` (su "Unlock Map Size"). El perfil `WC3Revival` de
`make-wfe-profile.py` trae `REMOVEMAPSIZELIMIT = yes` — inofensivo para los
mapas chicos, habilita los grandes. (El binario de WFE no viaja en el kit,
pero el kit trae `extras/WFE/INSTALAR-WFE.bat`, que lo baja verificado del
sitio oficial en la máquina del jugador — ver la actualización 2 de la
decisión 22.)

**Costo, y por eso queda OPT-IN**: para un mapa grande, WFE deja de ser
opcional (lo necesita TODO el que lo juegue), el mapa va sí o sí en el kit
(15 MB por el lobby es inviable), y se arrastra la fragilidad del inyectado.
No es gratis como un mapa chico. Por eso el techo de 8 MiB sigue siendo el
DEFAULT en todo el pipeline (`upload-maps.py` MAX_BYTES, `brand-map.py`
MAX_MAP_BYTES) y hay que levantarlo a propósito: `WC3_MAX_MAP_MB=64 make
recibir` para subir, `--allow-large` para brandear. Un mapa grande subido por
error no pasa en silencio.

**No verificado** (necesita Windows + varios clientes): que un mapa > 8 MiB
efectivamente cargue con el Unlock activado. El camino sale de la doc de WFE y
de foros; falta la prueba con el juego. Todo en docs/mapas-grandes.md.

## 24. Arranque automático por `!ready` (parche propio, 2026-08-10)

**Pedido**: que no dependa de un admin para empezar. Que cualquiera pueda
marcarse listo, y si están todos, la partida arranque sola en 30 s; y si están
todos y alguien pone `!start`, que arranque en el acto.

**Hallazgo**: Aura no tiene ningún sistema de "listo". La partida solo arranca
con el `!start` de un admin (`StartCountDown`, gate de admin+spoofcheck en
`EventPlayerBotCommand`). Hubo que agregarlo, como con el autohost.

**Solución** (`patches/aura-readycheck.patch`, 4 archivos):
- `CGamePlayer` gana un `m_Ready` (se crea en `false`, muere con el jugador:
  no hay que limpiar nada al salir ni hay líos con PIDs reciclados).
- `!ready` / `!notready` van en el switch de comandos NO-admin, que corre para
  todos sin spoofcheck — o sea que un jugador común los usa sin verificarse.
- `CGame::GetAllReady()` = hay ≥2 humanos y TODOS los del lobby están `ready`
  y ya bajaron el mapa (chequeo de descarga a mano, porque el arranque usa
  `force` y se saltea el chequeo normal).
- En `CGame::Update()` (solo en lobby): cuando `GetAllReady()` se arma una
  cuenta de 30 s (`m_ReadyCheckArmed`/`m_ReadyCheckStartTime`) y al vencer se
  hace `StartCountDown(true)`. Si deja de estar todo listo, se cancela.
- `!start` para no-admin: solo hace algo si `GetAllReady()`, y arranca ya. El
  `!start` de admin de siempre queda intacto (arranca sin exigir readys).

**Por qué `force`**: el arranque automático no puede depender de que un admin
haya hecho spoofcheck ni de los pings; con todos marcados `ready` la intención
es clara. El único chequeo que sí importa —que nadie esté a mitad de bajada—
se hace explícito en `GetAllReady()`.

**Verificado**: compila limpio en el sandbox junto al resto de los parches
(autohost, cstdint, MPQ read-only, 12 jugadores). **Falta prueba funcional**
con 2+ jugadores reales: que los mensajes se vean, que la cuenta de 30 s
arranque y que el auto-start no choque con el spoofcheck en un lobby real.

## 12. El hardening de SSH se separó del bootstrap (incidente del 2026-08-08)

**Qué pasó**: la primera puesta en marcha real dejó el VPS **inaccesible**.
El bootstrap aplicaba el endurecimiento de SSH automáticamente y la
combinación de dos errores cerró las dos puertas a la vez:

1. El archivo se escribía como `/etc/ssh/sshd_config.d/90-wc3-hardening.conf`.
   **sshd usa el PRIMER valor que encuentra** y lee los `.conf` en orden
   alfabético; la imagen de Ubuntu de Vultr trae `50-cloud-init.conf` con
   `PasswordAuthentication yes`, que gana por llegar antes. Resultado: el
   `PasswordAuthentication no` quedó sin efecto, pero el `PermitRootLogin no`
   sí se aplicó (cloud-init no define esa clave). **Root bloqueado.**
2. El usuario admin se crea con `adduser --disabled-password`, o sea sin
   contraseña: solo entra por clave. Como la clave pública nunca se había
   cargado bien, **el usuario admin tampoco entraba.**

La verificación que el script tenía (`authorized_keys` no vacío) no alcanzó:
comprobaba que el archivo existiera en el servidor, no que el operador
tuviera la clave privada correspondiente.

**Qué se cambió**:

- El bootstrap **ya no toca SSH**. Solo avisa.
- Se creó `install/50-harden-ssh.sh`, que se corre a mano y a conciencia,
  con cuatro salvaguardas: se niega a correr sin `authorized_keys`, exige
  confirmación explícita de que el login por clave ya fue probado en otra
  terminal, valida con `sshd -t` antes de recargar (y revierte si falla), y
  usa prefijo **`01-`** para ganarle a cloud-init.
- `PermitRootLogin` pasa a **`prohibit-password`** en vez de `no`: root por
  clave queda como red de contención si el usuario admin se rompe.
- `docs/operacion.md` suma una sección de recuperación por consola web, con
  `sshd -T` para ver la configuración **efectiva** (la única forma confiable
  de saber qué quedó aplicado).

**Lección transferible**: cualquier automatismo que pueda cortar el propio
canal de acceso tiene que ser un paso explícito y reversible, nunca un efecto
secundario de "preparar el sistema".

## 10. Las 3 decisiones más discutibles (resumen ejecutivo)

1. **Aura (2018) para un servidor 1.26a** — ver decisión 2. Es el riesgo
   funcional más grande después de los ya resueltos de compilación.
2. **Instancias por directorio en vez de `instance-%i.cfg` plano** — impuesto
   por el hardcode de Aura; cambia la forma del enunciado pero no el fondo.
3. **`track = 0` y server "privado por oscuridad"** (cuentas abiertas,
   `new_accounts = true` del default upstream) — cómodo para amigos, pero
   cualquiera que encuentre la IP puede crearse cuenta. Alternativa anotada
   en docs/operacion.md: cerrar `new_accounts` después de la fase 1.

## 25. Integración reproducible, nueve bots y objetivo 1.27b (2026-08-11)

**Reemplaza la decisión 11 como objetivo vigente y la decisión 23 como
camino para mapas grandes.** Las decisiones viejas se conservan arriba como
historial.

- La rama de integración nace de `origin/main`, para conservar los parches
  propios `aura-autohost.patch` y `aura-readycheck.patch`. Antes de cualquier
  build, `grep -c readycheck install/20-build-hostbot.sh` debe seguir dando 2.
- La versión objetivo pasa a **1.27b**. En la PC del operador se verificó
  `war3.exe` de 515.048 B, versión `1.27.1.7085`, junto a `w3l.exe`,
  `w3lh.dll` y `wl27.dll`. El loader ya fue usado para entrar al PvPGN; el
  servidor no registra la etiqueta exacta del cliente, por lo que ese detalle
  no se inventa en los reportes.
- 1.27b admite mapas de hasta 128 MiB sin WFE. WFE sale del kit: evitar un
  inyector marcado como HackTool vale más que conservar teclas estilo LoL.
- El estado real tiene **nueve** cuentas/instancias. Los puertos son 6113-6121
  para host y 6133-6141 para reconexión; firewall, generador y documentación
  deben moverse juntos.
- El checkout que había en el VPS no era reproducible: rama vieja, 47 cambios
  sin registrar y fuente sin `readycheck`, aunque el binario instalado sí lo
  contenía. Se respaldó completo antes de reemplazarlo. No se recompila Aura
  hasta validar esta integración y desplegar primero una sola instancia.
- La instancia 9 no se considera estable todavía: el proceso está activo pero
  el sandbox montó `/opt/wc3/maps` como sólo lectura y StormLib devolvió
  `invalid map_crc`. La corrección es devolver esa ruta a `ReadWritePaths`,
  no parchear Aura a ciegas.

---

## TODO(verificar) — lista completa, ordenada por qué bloquea primero

1. **Instancia 9 / FOC 9.6G03 ES**: comprobar CRC sin errores, lobby público,
   entrada con cliente 1.27b y una partida real. Hasta entonces el nombre
   lleva `PRUEBA` y no se anuncia como mapa estable.
2. **`!ready` funcional**: probar con dos jugadores que arma/cancela la cuenta
   de 30 segundos y que `!start` sólo acelera cuando todos están listos.
3. **Desincronización**: jugar desde dos redes distintas al menos diez minutos
   en FOC y en un mapa clásico ya validado.
4. **Backup fuera del VPS**: ejecutar el descargador de Windows y abrir con
   `tar -tzf` el archivo recibido. Un backup que vive sólo en el VPS no cierra
   recuperación ante pérdida completa de la máquina.
5. **Latencia**: probar `!latency 70` y `!sl 90` durante varias partidas antes
   de fijar valores nuevos en `aura.cfg.tpl`.
6. **Catálogo restante**: validar o descartar cada mapa pendiente con versión,
   hash y prueba de juego real; no inferir compatibilidad por fecha.
7. **Recursos bajo carga**: medir `MemoryCurrent` y CPU de los nueve bots con
   dos partidas simultáneas antes de bajar `MemoryMax=384M`.
