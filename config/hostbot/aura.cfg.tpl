# ============================================================================
# Template de aura.cfg para wc3-classic-revival
# ----------------------------------------------------------------------------
# Derivado del aura.cfg de ejemplo del upstream (github.com/Josko/aura-bot,
# commit 1e5df42, 2018-09-09). TODAS las claves existen en ese sample; no hay
# claves inventadas. Los placeholders WC3_* se rellenan con install/40-render-configs.sh
# a partir de .env + config/hostbot/instance-N.env.
#
# Aura lee "aura.cfg" desde su directorio de trabajo (esta hardcodeado en
# src/aura.cpp, no acepta la ruta por argumento). Por eso cada instancia del
# bot vive en /opt/wc3/hostbot/instances/N/ con su propio aura.cfg y la unidad
# systemd usa WorkingDirectory=%i.
# ============================================================================

# ---------------------------------------------------------------------------
# BOT
# ---------------------------------------------------------------------------

# Directorio con war3.exe, storm.dll y game.dll (los aporta el operador, no
# estan en el repo). Si contiene War3Patch.mpq, Aura extrae common.j y
# blizzard.j para calcular map_crc automaticamente.
bot_war3path = ${WC3_MPQ_DIR}

# Vacio = bindea a todas las interfaces. En un VPS con IP publica directa
# (sin NAT) esto es lo correcto.
bot_bindaddress =

# Puerto en el que ESTA instancia hostea partidas. Tiene que ser unico por
# instancia y estar abierto en ufw (rango WC3_BOT_PORT_RANGE del .env).
bot_hostport = ${WC3_BOT_HOSTPORT}

# Puerto para reconexiones GProxy++ (unico por instancia tambien).
bot_reconnectport = ${WC3_BOT_RECONNECTPORT}
bot_reconnectwaittime = 3

# Partidas simultaneas por instancia. En un VPS de 2 GB, conservador.
bot_maxgames = ${WC3_BOT_MAXGAMES}

bot_commandtrigger = !

# Configs de mapa (.cfg generados por el bot) y mapas .w3x compartidos entre
# todas las instancias.
bot_mapcfgpath = ${WC3_HOSTBOT_DIR}/mapcfgs
bot_mappath = ${WC3_MAPS_DIR}/

# Nombre virtual del host en el lobby (max 15 caracteres incluyendo el codigo
# de color |cFFxxxxxx).
bot_virtualhostname = ${WC3_BOT_VIRTUALHOST}

bot_autolock = 0

# 1 = los jugadores pueden bajar el mapa desde el bot (clave para mapas
# custom; el techo duro de 1.26a son 8 MiB y arriba de ~2-3 MB la
# transferencia es impracticable, ver docs/version-juego.md).
bot_allowdownloads = 1
bot_maxdownloaders = 3

# KB/s combinados para descargas in-lobby. Subilo si el VPS tiene banda.
bot_maxdownloadspeed = ${WC3_BOT_MAXDLSPEED}

bot_lcpings = 1

# Kick automatico por ping. Para publico sudamericano con server en Sao Paulo
# o Buenos Aires, 300 ms es generoso sin dejar entrar jugadores injugables.
bot_autokickping = 300

# Minutos que el bot espera a que entre el que creo la partida antes de
# cerrar el lobby solo. El default del upstream (10) es corto para un server
# de amigos, donde la gente llega de a poco: el lobby se vence y el que
# intenta entrar recibe "The game you attempted to join could not be found",
# un error que no dice nada sobre la causa real.
bot_lobbytimelimit = ${WC3_BOT_LOBBYTIMELIMIT}
bot_latency = 100
bot_synclimit = 50
bot_votekickpercentage = 70

# Mapa por defecto que hostea esta instancia (nombre del .cfg en mapcfgs, la
# extension .cfg se agrega sola).
bot_defaultmap = ${WC3_BOT_DEFAULTMAP}

# Autohost (NO es del upstream: lo agrega patches/aura-autohost.patch).
# Si bot_autohostname no esta vacio, el bot mantiene siempre un lobby abierto
# con bot_defaultmap, y lo vuelve a crear solo cuando la partida arranca. Sin
# esto Aura deja de publicar nada hasta que un admin escriba !pub, porque solo
# admite un lobby a la vez.
# Vacio = apagado, que es el comportamiento original de Aura.
bot_autohostname = ${WC3_BOT_AUTOHOSTNAME}
bot_autohostowner = ${WC3_BOT_AUTOHOSTOWNER}

bot_gameoverplayernumber = 1

# ---------------------------------------------------------------------------
# LAN
# ---------------------------------------------------------------------------

# Version de W3 para el broadcast LAN. 27 = 1.27x.
# TODO(verificar): el sample del upstream trae 29 (1.29); confirmar con el
# juego real que este build de Aura acepta clientes 1.27a con este valor.
lan_war3version = ${WC3_WAR3_VERSION}

udp_broadcasttarget =
udp_dontroute = 0

# ---------------------------------------------------------------------------
# BASE DE DATOS (sqlite local por instancia: bans, stats de DotA, admins)
# ---------------------------------------------------------------------------

db_sqlite3_file = aura.dbs

# ---------------------------------------------------------------------------
# IRC (no se usa; queda vacio)
# ---------------------------------------------------------------------------

irc_server =
irc_port = 6667
irc_nickname =
irc_username =
irc_password =
irc_commandtrigger =
irc_channel =
irc_rootadmin =

# ---------------------------------------------------------------------------
# BATTLE.NET (nuestro PvPGN local)
# ---------------------------------------------------------------------------

# El bot se conecta al PvPGN del mismo VPS, pero por la IP PUBLICA, NO por
# 127.0.0.1. Motivo (verificado en el codigo de PvPGN y en el servidor real el
# 2026-08-09): al crear una partida, PvPGN registra como direccion del host
# "la IP desde la que se conecto quien la creo"
# (game->addr = conn_get_game_addr(c) -> c->socket.udp_addr).
# Con loopback, PvPGN le anuncia a los jugadores "la partida esta en
# 127.0.0.1:6113", cada cliente intenta conectarse a si mismo y no entra
# nunca. El sintoma es cruel: la partida aparece listada y al entrar el
# cliente vuelve a la lista sin ningun mensaje de error.
bnet_server = ${WC3_PUBLIC_IP}
bnet_serveralias = ${WC3_REALM_NAME}

# En PvPGN las CD keys no se validan: el sample upstream indica dejarlas asi.
bnet_cdkeyroc = FFFFFFFFFFFFFFFFFFFFFFFFFF
bnet_cdkeytft = FFFFFFFFFFFFFFFFFFFFFFFFFF

# NO usar "system": en Linux Aura cae al valor 1031 (aleman) y el servidor le
# contesta todo en ese idioma, lo que ensucia el log del bot. Verificado en el
# servidor real el 2026-08-08. 1033 = en-US. Para es-AR seria 11274.
bnet_locale = ${WC3_BOT_LOCALE}

# Cuenta del bot en el PvPGN. Crearla antes con el cliente o via bnetd
# (new_accounts = true) — ver RUNBOOK fase 1.
bnet_username = ${WC3_BOT_USERNAME}
bnet_password = ${WC3_BOT_PASSWORD}

bnet_firstchannel = ${WC3_BOT_CHANNEL}

# Admins raiz del bot (separados por espacio, cuentas del PvPGN).
bnet_rootadmins = ${WC3_BOT_ROOTADMINS}

bnet_commandtrigger = !

# --- Seccion PvPGN custom (obligatoria contra un PvPGN, no Blizzard) -------
# TODO(verificar): estos cuatro valores dependen del par cliente/servidor real
# y solo se pueden confirmar conectando el bot a un PvPGN con clientes 1.27a.
# war3version 27 = 1.27x. exeversion/exeversionhash: si se dejan vacios, Aura
# intenta calcularlos con bncsutil a partir de los archivos de bot_war3path
# (war3.exe/storm.dll/game.dll de 1.27a). passwordhashtype pvpgn es lo
# documentado para servidores PvPGN en el propio sample.
bnet_custom_war3version = ${WC3_WAR3_VERSION}
bnet_custom_exeversion =
bnet_custom_exeversionhash =
bnet_custom_passwordhashtype = pvpgn
bnet_custom_pvpgnrealmname = ${WC3_REALM_NAME}
