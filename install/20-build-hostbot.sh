#!/usr/bin/env bash
# ============================================================================
# 20-build-hostbot.sh — clona, parchea, compila e instala Aura en /opt/wc3/hostbot
# Correr con sudo. Idempotente.
#
# Validado en sandbox Ubuntu 24.04 + GCC 13.3 el 2026-08-08 (ver DECISIONES.md):
# compila OK agregando #include <cstdint> a los headers que usan uint*_t
# (libstdc++ 13 dejo de incluirlo transitivamente). StormLib y bncsutil vienen
# vendored en el mismo repo y se compilan primero.
# ============================================================================
set -euo pipefail

AURA_REPO="${WC3_AURA_REPO:-https://github.com/Josko/aura-bot.git}"
# Commit validado en sandbox (ultimo del upstream, 2018-09-09).
AURA_REF="${WC3_AURA_REF:-1e5df425fd325e9b0e6aa8fa5eed35f0c61f3114}"
DEST=/opt/wc3/hostbot
SRC_DIR=/opt/wc3/src/aura-bot

log() { printf '[build-hostbot] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo (instala en ${DEST})." >&2
    exit 1
fi

# --- Fuente ------------------------------------------------------------------
install -d /opt/wc3/src
if [[ -d "${SRC_DIR}/.git" ]]; then
    log "repo ya clonado, actualizando"
    git -C "${SRC_DIR}" fetch --all --tags
else
    log "clonando ${AURA_REPO}"
    git clone "${AURA_REPO}" "${SRC_DIR}"
fi
git -C "${SRC_DIR}" checkout --force "${AURA_REF}"

# --- Parche: autohost (no existe en el upstream) ------------------------------
# Aura no tiene autohost y solo admite UN lobby a la vez (m_CurrentGame es un
# puntero unico), asi que cuando una partida arranca el bot deja de publicar
# nada hasta que alguien escriba !pub. Este parche hace que recree el lobby
# solo. Con eso, y una instancia por mapa, la lista de partidas queda siempre
# poblada; y como al arrancar una partida Aura libera el nombre en Battle.net
# (QueueGameUncreate), el lobby nuevo puede usar el mismo nombre — o sea que
# un mapa "ocupado" vuelve a estar disponible enseguida.
# Compilado y verificado en sandbox el 2026-08-09.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log "aplicando parche de autohost"
if git -C "${SRC_DIR}" apply --check "${REPO_DIR}/patches/aura-autohost.patch" 2>/dev/null; then
    git -C "${SRC_DIR}" apply "${REPO_DIR}/patches/aura-autohost.patch"
else
    log "  ya estaba aplicado, sigo"
fi

# --- Parche: arranque automatico por !ready (no existe en el upstream) --------
# Aura no tiene ningun sistema de "listo": la partida solo arranca cuando un
# admin escribe !start. Este parche agrega el comando !ready para cualquier
# jugador; cuando TODOS los del lobby estan listos (y son al menos 2) se lanza
# una cuenta regresiva de 30 segundos y la partida arranca sola, sin admin. Si
# ademas alguien escribe !start estando todos listos, arranca en el acto.
# Compilado y verificado en sandbox junto al resto de los parches.
log "aplicando parche de arranque por !ready"
if git -C "${SRC_DIR}" apply --check "${REPO_DIR}/patches/aura-readycheck.patch" 2>/dev/null; then
    git -C "${SRC_DIR}" apply "${REPO_DIR}/patches/aura-readycheck.patch"
else
    log "  ya estaba aplicado, sigo"
fi

# --- Parche cstdint (GCC/libstdc++ >= 13) ------------------------------------
# Varios headers usan uint8_t/uint32_t sin incluir <cstdint>; con toolchains
# viejos entraba transitivamente, con GCC 13 el build corta. Insertamos el
# include al principio de cada header afectado (idempotente por el grep -L).
log "aplicando parche cstdint a headers que lo necesiten"
for h in "${SRC_DIR}"/src/*.h; do
    if grep -qE 'u?int(8|16|32|64)_t' "$h" && ! grep -q '<cstdint>' "$h"; then
        sed -i '0,/^#include/s//#include <cstdint>\n#include/' "$h"
        log "  parcheado: $(basename "$h")"
    fi
done

# --- Parche: abrir War3Patch.mpq en SOLO LECTURA -----------------------------
# Aura llama a SFileOpenArchive sin MPQ_OPEN_READ_ONLY, asi que StormLib abre
# el MPQ en lectura-escritura. Como los archivos del juego son de root y la
# unidad de systemd monta /opt/wc3/mpq con ReadOnlyPaths, el open falla con
# error 13 (EACCES) y el bot no puede extraer common.j/blizzard.j, que son los
# que necesita para calcular los CRC de los mapas. Descubierto en el VPS real
# el 2026-08-08. El MPQ solo se lee, nunca se escribe: el flag es correcto.
if grep -q 'MPQ_OPEN_FORCE_MPQ_V1, &MPQ' "${SRC_DIR}/src/aura.cpp"; then
    log "aplicando parche de apertura del MPQ en solo lectura"
    sed -i 's/MPQ_OPEN_FORCE_MPQ_V1, &MPQ/MPQ_OPEN_FORCE_MPQ_V1 | MPQ_OPEN_READ_ONLY, \&MPQ/g' \
        "${SRC_DIR}/src/aura.cpp"
fi

# --- Parche CRITICO: volver a 12 jugadores (clientes 1.24-1.28) --------------
# El commit 2de4fc0 del upstream ("Add preliminary 24 player support", era
# 1.29) rompe a los clientes clasicos de 12 jugadores: el statstring del
# anuncio de partida pasa a declarar 23 slots libres (byte 110 = 'n') donde
# un cliente 1.27 espera como maximo 11 (byte 98 = 'b') — el comentario del
# propio codigo avisa que ese byte es la cantidad de PIDs que el cliente va
# a reservar. Resultado: el cliente ve la partida en la lista pero la
# descarta sin intentar conectarse al lobby. Confirmado por el issue
# uakfdotb/ghostpp#31, cuyo workaround oficial es exactamente este revert.
# Verificado compilando y revisando todos los usos en sandbox el 2026-08-09
# (los demas sitios usan aritmetica sobre MAX_SLOTS y vuelven solos a la
# semantica 12/11/10; el 110 de bnetprotocol.cpp:567 es 'enUS', no tocarlo).
log "aplicando parche de 12 jugadores (clientes 1.24-1.28)"
cd "${SRC_DIR}"
if grep -q 'constexpr int MAX_SLOTS = 24;' src/gameslot.h; then
    sed -i 's/^constexpr int MAX_SLOTS = 24;$/constexpr int MAX_SLOTS = 12;/' src/gameslot.h
fi
if grep -q 'packet\.push_back(110);' src/bnetprotocol.cpp; then
    sed -i "s|packet\.push_back(110);                                 // Slots Free (ascii 110 = char 'n' = 23 slots free)|packet.push_back(98);                                  // Slots Free (ascii 98 = char 'b' = 11 slots free)|" src/bnetprotocol.cpp
fi
grep -q 'constexpr int MAX_SLOTS = 12;' src/gameslot.h
grep -q 'packet\.push_back(98);' src/bnetprotocol.cpp
cd - >/dev/null

# --- Limpiar objetos de builds anteriores ------------------------------------
# El Makefile de Aura no rastrea dependencias de headers: tras parchear
# gameslot.h, un make incremental NO recompila las unidades que lo incluyen y
# el binario queda mezclado. En re-ejecuciones de este script hay que partir
# de cero. (El primer build no tiene .o y esto es un no-op.)
rm -f "${SRC_DIR}"/src/*.o "${SRC_DIR}/aura++"

# --- StormLib (vendored) -----------------------------------------------------
log "compilando StormLib"
cmake -S "${SRC_DIR}/StormLib" -B "${SRC_DIR}/StormLib/build" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_DYNAMIC_MODULE=1
cmake --build "${SRC_DIR}/StormLib/build" -j "$(nproc)"
cmake --install "${SRC_DIR}/StormLib/build"

# --- bncsutil (vendored) -----------------------------------------------------
log "compilando bncsutil"
make -C "${SRC_DIR}/bncsutil/src/bncsutil"
make -C "${SRC_DIR}/bncsutil/src/bncsutil" install
ldconfig

# --- Aura --------------------------------------------------------------------
log "compilando aura++ (el link con LTO tarda)"
make -C "${SRC_DIR}"

# --- Instalar ----------------------------------------------------------------
log "instalando en ${DEST}"
install -d -o wc3 -g wc3 "${DEST}" "${DEST}/mapcfgs" "${DEST}/instances"
install -m 755 "${SRC_DIR}/aura++" "${DEST}/aura++"
# ip-to-country: Aura lo busca en su directorio de trabajo; lo copiamos a cada
# instancia en 40-render-configs.sh. Guardamos el original aca.
install -m 644 "${SRC_DIR}/ip-to-country.csv" "${DEST}/ip-to-country.csv"
chown -R wc3:wc3 "${DEST}"

# --- Unidad systemd ----------------------------------------------------------
log "instalando unidad systemd wc3-hostbot@.service"
install -m 644 "${REPO_DIR}/systemd/wc3-hostbot@.service" /etc/systemd/system/wc3-hostbot@.service
systemctl daemon-reload

log "OK. Binario: ${DEST}/aura++"
log "Proximo paso: install/30-setup-mysql.sh"
