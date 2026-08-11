#!/usr/bin/env bash
# Limita logs persistentes y rota el log propio de PvPGN.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '[maintenance] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr como root." >&2
    exit 1
fi

log "instalando limite de journald (256 MiB, 14 dias)"
install -d -m 755 /etc/systemd/journald.conf.d
install -m 644 "${REPO_DIR}/config/journald/60-wc3-limit.conf" \
    /etc/systemd/journald.conf.d/60-wc3-limit.conf

log "instalando rotacion de bnetd.log"
install -m 644 "${REPO_DIR}/config/logrotate/wc3-pvpgn" \
    /etc/logrotate.d/wc3-pvpgn
logrotate --debug /etc/logrotate.d/wc3-pvpgn >/dev/null

systemctl restart systemd-journald
journalctl --disk-usage
log "OK: mantenimiento de logs activo"
