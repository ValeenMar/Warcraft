#!/usr/bin/env bash
# ============================================================================
# backup.sh — dump de MySQL + configs a un tar fechado en /opt/wc3/backups
# Correr con sudo en el VPS (necesita leer las configs y el socket de MySQL).
#
#   sudo ./scripts/backup.sh
#
# Guarda: dump de la base de PvPGN, etc/pvpgn completo, aura.cfg y aura.dbs
# (los admins/bans que cada bot cargo con !addadmin/!ban) de cada instancia y
# el registry de mapas. NO incluye los .w3x (pesan y se reconstruyen desde el
# map pack) ni los MPQ del juego.
# Retencion: se conservan los ultimos 14 backups.
# El procedimiento de RESTORE esta en RUNBOOK.md (seccion "Restaurar un backup").
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env"
BACKUP_ROOT=/opt/wc3/backups
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

log() { printf '[backup] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo." >&2
    exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Falta ${ENV_FILE} (necesito las credenciales de la base)." >&2
    exit 1
fi
env_mode="$(stat -c '%a' "${ENV_FILE}")"
if [[ "${env_mode}" != "600" ]]; then
    echo "${ENV_FILE} debe tener modo 600 (tiene ${env_mode}); no lo corrijo en silencio." >&2
    exit 1
fi
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

# Guards con mensaje claro: bajo cron, un "unbound variable" de un .env viejo
# corta los backups en silencio y nadie se entera hasta el dia del desastre.
: "${WC3_DB_NAME:?falta WC3_DB_NAME en .env}"
: "${WC3_DB_USER:?falta WC3_DB_USER en .env}"
: "${WC3_DB_PASS:?falta WC3_DB_PASS en .env}"
: "${WC3_DB_HOST:?falta WC3_DB_HOST en .env}"

install -d "${WORK}/dump" "${WORK}/configs"

log "dump de MySQL (${WC3_DB_NAME})"
# MYSQL_PWD y no --password=: lo segundo queda visible en ps/proc mientras corre
MYSQL_PWD="${WC3_DB_PASS}" mysqldump --user="${WC3_DB_USER}" \
    --host="${WC3_DB_HOST}" --single-transaction --routines --no-tablespaces \
    "${WC3_DB_NAME}" > "${WORK}/dump/${WC3_DB_NAME}.sql"
if [[ ! -s "${WORK}/dump/${WC3_DB_NAME}.sql" ]]; then
    echo "El dump de MySQL quedo vacio; no creo un backup falso." >&2
    exit 1
fi

log "copiando configs y secretos de recuperacion"
install -m 600 "${ENV_FILE}" "${WORK}/configs/repo.env"
if [[ -f /opt/wc3/discord-avisos.env ]]; then
    install -m 600 /opt/wc3/discord-avisos.env "${WORK}/configs/discord-avisos.env"
fi
cp -a /opt/wc3/pvpgn/etc/pvpgn "${WORK}/configs/pvpgn"
if compgen -G '/opt/wc3/hostbot/instances/*/aura.cfg' >/dev/null; then
    for cfg in /opt/wc3/hostbot/instances/*/aura.cfg; do
        n="$(basename "$(dirname "${cfg}")")"
        install -D "${cfg}" "${WORK}/configs/hostbot/instance-${n}/aura.cfg"
        # aura.dbs es el sqlite del bot: ahi viven los admins y bans que se
        # cargaron con !addadmin/!ban. Sin esto, un restore los pierde todos.
        dbs="$(dirname "${cfg}")/aura.dbs"
        if [[ -f "${dbs}" ]]; then
            install -D "${dbs}" "${WORK}/configs/hostbot/instance-${n}/aura.dbs"
        fi
    done
fi
cp -a "${REPO_DIR}/maps/registry.yaml" "${WORK}/configs/registry.yaml"

install -d "${BACKUP_ROOT}"
TARBALL="${BACKUP_ROOT}/wc3-backup-${STAMP}.tar.gz"
tar -czf "${TARBALL}" -C "${WORK}" dump configs
chmod 600 "${TARBALL}"
tar -tzf "${TARBALL}" >/dev/null
log "backup escrito: ${TARBALL} ($(du -h "${TARBALL}" | cut -f1))"

# --- Retencion: dejar los 14 mas nuevos --------------------------------------
mapfile -t old < <(find "${BACKUP_ROOT}" -maxdepth 1 -name 'wc3-backup-*.tar.gz' \
    -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2- | tail -n +15)
if [[ "${#old[@]}" -gt 0 ]]; then
    log "borrando ${#old[@]} backups viejos"
    rm -f "${old[@]}"
fi
