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
# Techo por mapa del cliente objetivo 1.27b.
MAX_MAP_MB="${WC3_MAX_MAP_MB:-128}"

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

# Sin 0/O ni 1/l/I: el token se lee de la consola y se tipea en el navegador,
# y una "l" minuscula tecleada como "1" da un 404 que no se entiende.
TOKEN="$(head -c 512 /dev/urandom | LC_ALL=C tr -dc 'abcdefghjkmnpqrstuvwxyz23456789' | cut -c1-12)"

# --- galeria de previews -----------------------------------------------------
# Los .png quedan en el servidor, donde no se pueden mirar. Los exportamos y la
# misma pagina los muestra abajo de la zona de subida. Si falta alguna
# dependencia no pasa nada: la pagina sale sin galeria.
GALERIA="$(mktemp -d)"
shopt -s nullglob
existentes=("${DEST}"/*.w3x /opt/wc3/maps/*.w3x)
if [[ "${#existentes[@]}" -gt 0 ]] && command -v smpq >/dev/null; then
    log "exportando las previews que ya traen los mapas"
    "${PY}" "${REPO_DIR}/scripts/brand-map.py" "${existentes[@]}" \
        --report --dump-previews "${GALERIA}" >/dev/null 2>&1 || true
fi

# Un solo trap para todo: dos `trap ... EXIT` seguidos se pisan y el segundo
# gana, que es justo como se filtra un directorio temporal sin que nadie note.
limpiar() {
    log "cerrando el puerto ${PORT} en ufw"
    ufw delete allow "${PORT}/tcp" >/dev/null 2>&1 || true
    rm -rf "${GALERIA}"
}
trap limpiar EXIT

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

# Si ya hay un kit armado se ofrece para descargar en la misma pagina: es la
# unica forma comoda de sacarlo del servidor y llevarlo a Windows, y es el
# link que despues se les pasa a los amigos.
KIT_ARGS=()
KIT=""
for z in "${REPO_DIR}"/dist/*.zip; do
    [[ -f "${z}" ]] || continue
    [[ -z "${KIT}" || "${z}" -nt "${KIT}" ]] && KIT="${z}"
done
if [[ -n "${KIT}" ]]; then
    log "ofreciendo para descarga: $(basename "${KIT}")"
    KIT_ARGS=(--offer "${KIT}")
fi

"${PY}" "${REPO_DIR}/scripts/upload-maps.py" \
    --dest "${DEST}" --port "${PORT}" --minutes "${MINUTES}" \
    --realm "${REALM}" --token "${TOKEN}" --gallery "${GALERIA}" \
    --banner-dest "${REPO_DIR}/config/pvpgn/banner.png" \
    --max-map-mb "${MAX_MAP_MB}" \
    "${KIT_ARGS[@]}" || true

echo
if [[ -f "${REPO_DIR}/config/pvpgn/banner.png" ]]; then
    log "hay un banner propio en config/pvpgn/banner.png"
    log "  aplicalo con: sudo make render-config && sudo systemctl restart pvpgn"
fi

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
