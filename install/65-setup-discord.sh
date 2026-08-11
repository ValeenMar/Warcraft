#!/usr/bin/env bash
# Instala los avisos REST a Discord. No toca ni recompila Aura.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=/opt/wc3/discord-avisos.env
APP_DIR=/opt/wc3/discord-avisos

log() { printf '[discord] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr como root." >&2
    exit 1
fi

if [[ "${1:-}" == "--disable" ]]; then
    log "apagando avisos y quitando enlaces automáticos"
    systemctl disable --now wc3-discord-avisos.service wc3-discord-disco.timer \
        wc3-discord-lobby-health.timer \
        2>/dev/null || true
    rm -f -- /etc/systemd/system/wc3-hostbot@.service.d/discord.conf \
        /etc/systemd/system/pvpgn.service.d/discord.conf \
        /etc/systemd/system/wc3-backup.service.d/discord.conf
    systemctl daemon-reload
    log "OK: integración apagada; token y archivos quedan guardados"
    exit 0
fi

log "instalando script y unidades (sin tocar Aura)"
install -d -o root -g wc3 -m 750 "${APP_DIR}"
install -o root -g wc3 -m 750 "${REPO_DIR}/scripts/discord-avisos.py" \
    "${APP_DIR}/avisos.py"

if [[ ! -e "${ENV_FILE}" ]]; then
    install -o root -g wc3 -m 640 /dev/null "${ENV_FILE}"
fi
chown root:wc3 "${ENV_FILE}"
chmod 640 "${ENV_FILE}"

for unit in wc3-discord-avisos.service wc3-discord-fallo@.service \
            wc3-discord-disco.service wc3-discord-disco.timer \
            wc3-discord-backup-ok.service wc3-discord-lobby-health.service \
            wc3-discord-lobby-health.timer; do
    install -m 644 "${REPO_DIR}/systemd/${unit}" "/etc/systemd/system/${unit}"
done

configured=1
for key in DISCORD_BOT_TOKEN DISCORD_LOBBIES_CHANNEL_ID DISCORD_ESTADO_CHANNEL_ID; do
    if ! grep -q "^${key}=.." "${ENV_FILE}"; then
        configured=0
    fi
done

if [[ "${configured}" -eq 1 ]]; then
    install -d -m 755 /etc/systemd/system/wc3-hostbot@.service.d
    install -d -m 755 /etc/systemd/system/pvpgn.service.d
    install -d -m 755 /etc/systemd/system/wc3-backup.service.d
    install -m 644 "${REPO_DIR}/systemd/discord-dropins/hostbot-onfailure.conf" \
        /etc/systemd/system/wc3-hostbot@.service.d/discord.conf
    install -m 644 "${REPO_DIR}/systemd/discord-dropins/pvpgn-onfailure.conf" \
        /etc/systemd/system/pvpgn.service.d/discord.conf
    install -m 644 "${REPO_DIR}/systemd/discord-dropins/backup.conf" \
        /etc/systemd/system/wc3-backup.service.d/discord.conf
fi

systemctl daemon-reload

if [[ "${configured}" -eq 1 ]]; then
    systemctl enable --now wc3-discord-avisos.service wc3-discord-disco.timer \
        wc3-discord-lobby-health.timer
    systemctl try-restart wc3-discord-avisos.service
    log "OK: avisos activos"
else
    log "PENDIENTE: cargar el token y ejecutar 'avisos.py discover'; no prendo nada todavia"
fi
