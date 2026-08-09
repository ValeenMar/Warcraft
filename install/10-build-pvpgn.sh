#!/usr/bin/env bash
# ============================================================================
# 10-build-pvpgn.sh — clona, parchea, compila e instala PvPGN en /opt/wc3/pvpgn
# Correr con sudo. Idempotente: re-correrlo recompila e instala de nuevo.
#
# Validado en sandbox Ubuntu 24.04 + GCC 13.3 el 2026-08-08 (ver DECISIONES.md):
# compila OK con un solo parche (my_bool, removido en libmysqlclient 8.0).
# ============================================================================
set -euo pipefail

PVPGN_REPO="${WC3_PVPGN_REPO:-https://github.com/pvpgn/pvpgn-server.git}"
# Commit validado en sandbox; actualizar a conciencia, no a ciegas.
PVPGN_REF="${WC3_PVPGN_REF:-9cd173f4e02ba3d9f8f15a67ca308b5eb78723e4}"
PREFIX=/opt/wc3/pvpgn
SRC_DIR=/opt/wc3/src/pvpgn-server

log() { printf '[build-pvpgn] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo (instala en ${PREFIX})." >&2
    exit 1
fi

# --- Fuente ------------------------------------------------------------------
install -d /opt/wc3/src
if [[ -d "${SRC_DIR}/.git" ]]; then
    log "repo ya clonado, actualizando"
    git -C "${SRC_DIR}" fetch --all --tags
else
    log "clonando ${PVPGN_REPO}"
    git clone "${PVPGN_REPO}" "${SRC_DIR}"
fi
git -C "${SRC_DIR}" checkout --force "${PVPGN_REF}"

# --- Parche my_bool (MySQL >= 8.0.1 elimino el typedef) ----------------------
# Upstream sigue usando my_bool en sql_mysql.cpp; con libmysqlclient 8.x de
# Ubuntu 24.04 el build corta. bool es un reemplazo directo.
if grep -q '\bmy_bool\b' "${SRC_DIR}/src/bnetd/sql_mysql.cpp"; then
    log "aplicando parche my_bool -> bool en sql_mysql.cpp"
    sed -i 's/\bmy_bool\b/bool/g' "${SRC_DIR}/src/bnetd/sql_mysql.cpp"
fi

# --- Parche `rank` (palabra reservada en MySQL >= 8.0.2) ---------------------
# La tabla arrangedteam tiene una columna llamada "rank", que MySQL 8 reservo
# para las funciones de ventana. Las tres queries que la tocan (SELECT/INSERT/
# UPDATE en sql_common.cpp) y su definicion en sql_DB_layout.conf.in la usan
# sin comillas, asi que fallan con error de sintaxis. Solo afecta a los
# "arranged teams" (ladder por equipos de Battle.net), que este proyecto no
# usa, pero deja un [error] en cada arranque. Se escapa con backticks.
# Cuidado: NO tocar "team->rank", que es C++ y esta bien.
SQL_COMMON="${SRC_DIR}/src/bnetd/sql_common.cpp"
if grep -q ', rank FROM %sarrangedteam' "${SQL_COMMON}"; then
    log "aplicando parche de la palabra reservada rank en sql_common.cpp"
    # shellcheck disable=SC2016  # los backticks son de SQL, no de shell
    sed -i \
        -e 's/, rank FROM %sarrangedteam/, `rank` FROM %sarrangedteam/' \
        -e 's/level, rank) VALUES/level, `rank`) VALUES/' \
        -e "s/level='%d', rank='%d' WHERE/level='%d', \`rank\`='%d' WHERE/" \
        "${SQL_COMMON}"
fi
DB_LAYOUT="${SRC_DIR}/conf/sql_DB_layout.conf.in"
if grep -q '^"rank int"' "${DB_LAYOUT}"; then
    log "aplicando parche de la palabra reservada rank en sql_DB_layout.conf.in"
    # shellcheck disable=SC2016  # los backticks son de SQL, no de shell
    sed -i 's/^"rank int"/"`rank` int"/' "${DB_LAYOUT}"
fi

# --- Compilar ----------------------------------------------------------------
log "configurando cmake (MySQL ON, Diablo2 OFF)"
cmake -S "${SRC_DIR}" -B "${SRC_DIR}/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DWITH_MYSQL=ON \
    -DWITH_D2CS=OFF \
    -DWITH_D2DBS=OFF \
    -DWITH_LUA=OFF \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}"
log "compilando (esto tarda unos minutos)"
cmake --build "${SRC_DIR}/build" -j "$(nproc)"

# --- Instalar ----------------------------------------------------------------
# make install NO pisa los .conf existentes si ya fueron editados? Si los pisa:
# por eso las configs reales se generan con 40-render-configs.sh que hace
# backup fechado antes de escribir. Aca instalamos binarios + samples.
log "instalando en ${PREFIX}"
cmake --install "${SRC_DIR}/build"
chown -R wc3:wc3 "${PREFIX}/var"

# --- Unidad systemd ----------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log "instalando unidad systemd pvpgn.service"
install -m 644 "${REPO_DIR}/systemd/pvpgn.service" /etc/systemd/system/pvpgn.service
systemctl daemon-reload

log "OK. Binario: ${PREFIX}/sbin/bnetd ($("${PREFIX}/sbin/bnetd" -v | head -1))"
log "Proximo paso: install/20-build-hostbot.sh"
