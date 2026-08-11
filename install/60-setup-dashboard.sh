#!/usr/bin/env bash
# ============================================================================
# 60-setup-dashboard.sh — instala y prende el dashboard web de admin
# Correr con sudo. Idempotente: re-correrlo actualiza el script y la config.
#
#   sudo ./install/60-setup-dashboard.sh      (o: sudo make dashboard)
#
# Que hace: copia dashboard.py y su companero de acciones a /opt/wc3/dashboard/,
# arma /opt/wc3/dashboard.env con las claves del .env, agrega el usuario wc3
# al grupo systemd-journal (para que la pagina muestre los logs), abre el
# puerto en ufw solo si el bind es publico e instala/prende las unidades (panel + el par
# .path/.service que ejecuta los botones como root con lista blanca).
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
DASH_BIND="${WC3_DASH_BIND:-0.0.0.0}"
if [[ -z "${WC3_DASH_PASSWORD:-}" || "${WC3_DASH_PASSWORD}" == "CAMBIAME" ]]; then
    echo "WC3_DASH_PASSWORD falta o sigue en CAMBIAME en .env." >&2
    echo "La contraseña es lo UNICO que separa el dashboard de internet." >&2
    echo "Genera una con: openssl rand -base64 18" >&2
    exit 1
fi

# La cuenta PvPGN con la que el panel entra al chat. Se crea UNA vez desde el
# cliente del juego (New Account) con este usuario y esta contraseña; si no
# existe, el panel anda igual pero la seccion de chat dice que falta crearla.
CHAT_USER="${WC3_DASH_CHAT_USER:-panel}"
CHAT_PASS="${WC3_DASH_CHAT_PASSWORD:-${WC3_BOT_PASSWORD:-}}"

# --- Archivos -----------------------------------------------------------------
log "instalando dashboard.py y acciones.sh en /opt/wc3/dashboard/"
install -d -o root -g wc3 -m 750 /opt/wc3/dashboard
install -m 644 "${REPO_DIR}/scripts/dashboard.py" /opt/wc3/dashboard/dashboard.py
install -m 755 "${REPO_DIR}/scripts/dashboard-acciones.sh" /opt/wc3/dashboard/acciones.sh
install -d -o root -g wc3 -m 750 /opt/wc3/dashboard/guias
install -m 644 "${REPO_DIR}/docs/guias/foc-96b03-es.html" \
    /opt/wc3/dashboard/guias/foc-96b03-es.html
install -d -o wc3 -g wc3 /opt/wc3/incoming
install -d -o root -g wc3 -m 750 /opt/wc3/backups
# spool: wc3 escribe los pedidos; resultados: root escribe, wc3 lee
install -d -o wc3 -g wc3 -m 750 /opt/wc3/dashboard/spool
install -d -o root -g wc3 -m 750 /opt/wc3/dashboard/resultados

log "escribiendo /opt/wc3/dashboard.env (las claves viven ahi, 640 root:wc3)"
cat > /opt/wc3/dashboard.env <<EOF
WC3_DASH_PASSWORD=${WC3_DASH_PASSWORD}
WC3_DASH_PORT=${DASH_PORT}
WC3_DASH_BIND=${DASH_BIND}
WC3_DASH_CHAT_USER=${CHAT_USER}
WC3_DASH_CHAT_PASSWORD=${CHAT_PASS}
WC3_BOT_CHANNEL=${WC3_BOT_CHANNEL:-W3}
WC3_REALM_NAME=${WC3_REALM_NAME:-WC3}
WC3_MAX_MAP_MB=${WC3_MAX_MAP_MB:-8}
DASH_REPO_DIR=${REPO_DIR}
EOF
chown root:wc3 /opt/wc3/dashboard.env
chmod 640 /opt/wc3/dashboard.env

# --- Permiso de bot para la cuenta del chat -------------------------------------
# El login chat/telnet de bnetd exige auth\botlogin=true en la cuenta
# (handle_telnet.cpp: "Account has no bot access", default false). La cuenta
# se crea desde el juego; el permiso se otorga aca, directo en MySQL (tabla
# pvpgn_BNET, columna auth_botlogin). Mejor-esfuerzo: sin esto el panel anda
# igual, solo que sin chat.
if [[ "${CHAT_USER}" =~ ^[A-Za-z0-9_-]+$ ]] \
   && [[ -n "${WC3_DB_NAME:-}" && -n "${WC3_DB_USER:-}" && -n "${WC3_DB_PASS:-}" ]] \
   && command -v mysql >/dev/null; then
    existe="$(MYSQL_PWD="${WC3_DB_PASS}" mysql --user="${WC3_DB_USER}" \
        --host="${WC3_DB_HOST:-127.0.0.1}" -N -B "${WC3_DB_NAME}" -e \
        "SELECT COUNT(*) FROM pvpgn_BNET WHERE username = lower('${CHAT_USER}');" \
        2>/dev/null || echo error)"
    if [[ "${existe}" == "1" ]]; then
        MYSQL_PWD="${WC3_DB_PASS}" mysql --user="${WC3_DB_USER}" \
            --host="${WC3_DB_HOST:-127.0.0.1}" "${WC3_DB_NAME}" -e \
            "UPDATE pvpgn_BNET SET auth_botlogin='true' WHERE username = lower('${CHAT_USER}');"
        log "permiso de bot otorgado a la cuenta '${CHAT_USER}'"
        log "  (si PvPGN ya estaba corriendo, reinicialo para que lo tome:"
        log "   el boton 'reiniciar' del panel, o systemctl restart pvpgn)"
    elif [[ "${existe}" == "0" ]]; then
        log "AVISO: la cuenta '${CHAT_USER}' todavia no existe en PvPGN."
        log "  Creala desde el juego (New Account) y volve a correr: sudo make dashboard"
    else
        log "AVISO: no pude consultar MySQL para el permiso de bot (¿base sin crear?)."
    fi
else
    log "AVISO: sin credenciales de MySQL en .env; el permiso de bot del chat"
    log "  queda pendiente (la seccion de chat del panel va a avisar)."
fi

# --- Journal ------------------------------------------------------------------
# Para que la pagina pueda mostrar las ultimas lineas de pvpgn y de cada bot.
if ! id -nG wc3 | grep -qw systemd-journal; then
    log "agregando wc3 al grupo systemd-journal (lectura de logs)"
    usermod -aG systemd-journal wc3
fi

# --- Firewall -----------------------------------------------------------------
if [[ "${DASH_BIND}" == "127.0.0.1" || "${DASH_BIND}" == "::1" \
      || "${DASH_BIND}" == "localhost" ]]; then
    log "panel privado en ${DASH_BIND}: acceso por tunel SSH; no abro firewall"
else
    log "abriendo el puerto ${DASH_PORT}/tcp en ufw (permanente)"
    ufw allow "${DASH_PORT}/tcp" comment 'dashboard admin wc3' >/dev/null
fi

# --- Unidades -------------------------------------------------------------------
log "instalando y prendiendo wc3-dashboard + el companero de acciones"
install -m 644 "${REPO_DIR}/systemd/wc3-dashboard.service" \
    /etc/systemd/system/wc3-dashboard.service
install -m 644 "${REPO_DIR}/systemd/wc3-dashboard-acciones.service" \
    /etc/systemd/system/wc3-dashboard-acciones.service
install -m 644 "${REPO_DIR}/systemd/wc3-dashboard-acciones.path" \
    /etc/systemd/system/wc3-dashboard-acciones.path
install -m 644 "${REPO_DIR}/systemd/wc3-backup.service" \
    /etc/systemd/system/wc3-backup.service
install -m 644 "${REPO_DIR}/systemd/wc3-backup.timer" \
    /etc/systemd/system/wc3-backup.timer
systemctl daemon-reload
systemctl enable --now wc3-dashboard-acciones.path
systemctl enable --now wc3-backup.timer
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
log "listo. El dashboard y el backup diario quedaron prendidos para siempre."
log ""
if [[ "${DASH_BIND}" == "127.0.0.1" || "${DASH_BIND}" == "localhost" ]]; then
    log "    acceso privado: abrir con el lanzador de Windows (tunel SSH)"
    log "    direccion local: http://127.0.0.1:${DASH_PORT}/"
else
    log "    http://${IP}:${DASH_PORT}/"
fi
log ""
log "  usuario: admin   contraseña: la de WC3_DASH_PASSWORD en .env"
log "  (guardala en el navegador y ya queda un clic)"
log ""
log "Para que el CHAT del panel funcione, la cuenta '${CHAT_USER}' tiene que"
log "existir en PvPGN: se crea una unica vez desde el cliente del juego con"
log "New Account (usuario '${CHAT_USER}', la contraseña del panel de chat)."
log "Hasta entonces, la seccion de chat de la pagina avisa que falta."
