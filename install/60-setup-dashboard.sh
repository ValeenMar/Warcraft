#!/usr/bin/env bash
# ============================================================================
# 60-setup-dashboard.sh — instala y prende el dashboard web de admin
# Correr con sudo. Idempotente: re-correrlo actualiza el script y la config.
#
#   sudo ./install/60-setup-dashboard.sh      (o: sudo make dashboard)
#
# Que hace: copia scripts/dashboard.py a /opt/wc3/dashboard/, arma
# /opt/wc3/dashboard.env con la contraseña y el puerto del .env, agrega el
# usuario wc3 al grupo systemd-journal (para que la pagina muestre los logs),
# abre el puerto en ufw e instala/prende la unidad systemd.
#
# Despues de esto el dashboard queda SIEMPRE prendido en
#   http://IP-del-VPS:PUERTO/   (usuario: admin, contraseña: WC3_DASH_PASSWORD)
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env"

log() { printf '[dashboard] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo." >&2
    exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Falta ${ENV_FILE}. Copia .env.example a .env y completalo." >&2
    exit 1
fi
chmod 600 "${ENV_FILE}"
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

DASH_PORT="${WC3_DASH_PORT:-8322}"
if [[ -z "${WC3_DASH_PASSWORD:-}" || "${WC3_DASH_PASSWORD}" == "CAMBIAME" ]]; then
    echo "WC3_DASH_PASSWORD falta o sigue en CAMBIAME en .env." >&2
    echo "La contraseña es lo UNICO que separa el dashboard de internet." >&2
    echo "Genera una con: openssl rand -base64 18" >&2
    exit 1
fi

# --- Archivos -----------------------------------------------------------------
log "instalando dashboard.py en /opt/wc3/dashboard/"
install -d -o root -g wc3 -m 750 /opt/wc3/dashboard
install -m 644 "${REPO_DIR}/scripts/dashboard.py" /opt/wc3/dashboard/dashboard.py
install -d -o wc3 -g wc3 /opt/wc3/incoming

log "escribiendo /opt/wc3/dashboard.env (la contraseña vive ahi, 640 root:wc3)"
cat > /opt/wc3/dashboard.env <<EOF
WC3_DASH_PASSWORD=${WC3_DASH_PASSWORD}
WC3_DASH_PORT=${DASH_PORT}
WC3_REALM_NAME=${WC3_REALM_NAME:-WC3}
WC3_MAX_MAP_MB=${WC3_MAX_MAP_MB:-8}
EOF
chown root:wc3 /opt/wc3/dashboard.env
chmod 640 /opt/wc3/dashboard.env

# --- Journal ------------------------------------------------------------------
# Para que la pagina pueda mostrar las ultimas lineas de pvpgn y de cada bot.
if ! id -nG wc3 | grep -qw systemd-journal; then
    log "agregando wc3 al grupo systemd-journal (lectura de logs)"
    usermod -aG systemd-journal wc3
fi

# --- Firewall -----------------------------------------------------------------
log "abriendo el puerto ${DASH_PORT}/tcp en ufw (permanente)"
ufw allow "${DASH_PORT}/tcp" comment 'dashboard admin wc3' >/dev/null

# --- Unidad -------------------------------------------------------------------
log "instalando y prendiendo wc3-dashboard.service"
install -m 644 "${REPO_DIR}/systemd/wc3-dashboard.service" \
    /etc/systemd/system/wc3-dashboard.service
systemctl daemon-reload
systemctl enable --now wc3-dashboard
# Si ya estaba corriendo, reiniciar para tomar script/config nuevos
systemctl restart wc3-dashboard

sleep 1
if ! systemctl is-active --quiet wc3-dashboard; then
    echo "El dashboard NO quedo corriendo. Ver el motivo con:" >&2
    echo "    journalctl -u wc3-dashboard -n 20" >&2
    exit 1
fi

IP="${WC3_PUBLIC_IP:-$(hostname -I | awk '{print $1}')}"
log "listo. El dashboard quedo prendido para siempre en:"
log ""
log "    http://${IP}:${DASH_PORT}/"
log ""
log "  usuario: admin   contraseña: la de WC3_DASH_PASSWORD en .env"
log "  (guardala en el navegador y ya queda un clic)"
