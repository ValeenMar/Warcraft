#!/usr/bin/env bash
# ============================================================================
# recibir-mapas.sh — abre una ventana para recibir mapas por el navegador
#
#   sudo ./scripts/recibir-mapas.sh [minutos]
#
# Levanta scripts/upload-maps.py, abre el puerto en ufw, imprime la URL que
# hay que pegar en el navegador, y cuando termina (por tiempo o por Ctrl+C)
# vuelve a cerrar el puerto y te dice que quedo adentro.
#
# Existe para no tener que pelear con scp/claves desde Windows, y para que los
# amigos puedan mandar mapas sin acceso al servidor.
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MINUTES="${1:-30}"
PORT="${WC3_UPLOAD_PORT:-8099}"
DEST="${WC3_INCOMING_DIR:-/opt/wc3/incoming}"

log() { printf '[recibir] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo (escribe en ${DEST} y toca ufw)." >&2
    exit 1
fi

if ! [[ "${MINUTES}" =~ ^[0-9]+$ ]]; then
    echo "El primer argumento son los minutos que queda abierto (un numero)." >&2
    exit 1
fi

REALM="el servidor"
if [[ -f "${REPO_DIR}/.env" ]]; then
    # shellcheck disable=SC1091  # .env se genera a partir de .env.example
    source "${REPO_DIR}/.env"
    REALM="${WC3_REALM_NAME:-${REALM}}"
fi

PUBLIC_IP="${WC3_PUBLIC_IP:-}"
if [[ -z "${PUBLIC_IP}" ]]; then
    PUBLIC_IP="$(hostname -I | awk '{print $1}')"
fi

PY=/opt/wc3/venv/bin/python
[[ -x "${PY}" ]] || PY=python3

TOKEN="$(head -c 18 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=')"

cerrar_puerto() {
    log "cerrando el puerto ${PORT} en ufw"
    ufw delete allow "${PORT}/tcp" >/dev/null 2>&1 || true
}
trap cerrar_puerto EXIT

log "abriendo el puerto ${PORT} en ufw (temporal)"
ufw allow "${PORT}/tcp" comment 'subida temporal de mapas' >/dev/null

echo
echo "  ================================================================"
echo "   Abri esta direccion en el navegador (de tu PC, no del servidor):"
echo
echo "     http://${PUBLIC_IP}:${PORT}/${TOKEN}"
echo
echo "   Arrastra los .w3x ahi. Se apaga solo en ${MINUTES} minutos."
echo "  ================================================================"
echo

"${PY}" "${REPO_DIR}/scripts/upload-maps.py" \
    --dest "${DEST}" --port "${PORT}" --minutes "${MINUTES}" \
    --realm "${REALM}" --token "${TOKEN}" || true

echo
log "listo. Quedaron en ${DEST}:"
shopt -s nullglob
mapas=("${DEST}"/*.w3x "${DEST}"/*.w3m)
if [[ "${#mapas[@]}" -eq 0 ]]; then
    log "  (ninguno)"
else
    for m in "${mapas[@]}"; do
        printf '  %10s  %s\n' "$(du -h "${m}" | cut -f1)" "$(basename "${m}")"
    done
    echo
    log "Proximo paso, para ver que trae cada uno antes de tocarlos:"
    log "  ${PY} ${REPO_DIR}/scripts/brand-map.py ${DEST}/*.w3x --report"
fi
