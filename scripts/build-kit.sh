#!/usr/bin/env bash
# ============================================================================
# build-kit.sh — arma el kit que se le pasa a los amigos
#
#   ./scripts/build-kit.sh [--maps DIR] [--out DIR]
#
# Junta en un .zip:
#   - INSTALAR.bat y LEEME.txt, renderizados con los valores de .env
#   - herramientas/gateway.ps1 (agrega el server a la lista de Battle.net)
#   - loader/  con w3l, que se BAJA de pvpgn.pro (nunca vive en este repo:
#     ver la regla de copyright del README)
#   - mapas/   con los .w3x que le pases con --maps (opcional)
#
# Los .txt/.bat/.ps1 salen con finales de linea CRLF, que es lo que espera
# Windows.
#
# No necesita el VPS ni los archivos del juego, pero si necesita internet
# para bajar el loader la primera vez (despues queda cacheado).
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_DIR}/dist"
MAPS_DIR=""

# w3l 1.5.1.1, el loader oficial de PvPGN. El zip trae contrasena.
W3L_URL="${WC3_W3L_URL:-http://cdn.pvpgn.pro/w3l/w3l_1_5_1_1_by_Keres.zip}"
W3L_ZIP_PASSWORD="pvpgn"
# SHA-256 del zip: el loader se baja por HTTP plano (el CDN no sirve bien por
# HTTPS) y se REDISTRIBUYE a los amigos, que lo ejecutan; sin esto, cualquiera
# en el medio de la red podria cambiar el binario y el kit lo repartiria igual.
# Calculado el 2026-08-10 sobre el zip del CDN. Si cambias WC3_W3L_URL a otra
# version, pasa el hash nuevo en WC3_W3L_SHA256 (sacalo con sha256sum).
W3L_SHA256="${WC3_W3L_SHA256:-6c6b39d5f32bfa700b7d14cf76e35d53fda3c405673173dc508b82aeb66688b7}"
CACHE_DIR="${REPO_DIR}/.cache"

log() { printf '[build-kit] %s\n' "$*"; }
die() { printf '[build-kit] ERROR: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --maps) MAPS_DIR="${2:?--maps necesita un directorio}"; shift 2 ;;
        --out)  OUT_DIR="${2:?--out necesita un directorio}"; shift 2 ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "argumento desconocido: $1" ;;
    esac
done

command -v unzip >/dev/null || die "falta unzip (apt install unzip)"
command -v curl  >/dev/null || die "falta curl"
command -v zip   >/dev/null || die "falta zip (apt install zip)"

# --- .env --------------------------------------------------------------------
[[ -f "${REPO_DIR}/.env" ]] || die "no existe ${REPO_DIR}/.env (copiar de .env.example)"
set -a
# shellcheck disable=SC1091  # .env se genera a partir de .env.example
source "${REPO_DIR}/.env"
set +a
: "${WC3_PUBLIC_IP:?falta WC3_PUBLIC_IP en .env}"
: "${WC3_REALM_NAME:?falta WC3_REALM_NAME en .env}"
: "${WC3_BOT_CHANNEL:?falta WC3_BOT_CHANNEL en .env}"
# Huso horario que se le declara al cliente en la lista de gateways. Es
# cosmetico (el juego lo muestra al lado del nombre del server), asi que en vez
# de exigirlo se usa el de Argentina y se avisa: quien tenga un .env viejo, de
# antes de que existiera la variable, no tiene por que quedarse sin kit.
if [[ -z "${WC3_KIT_GATEWAY_TZ:-}" ]]; then
    WC3_KIT_GATEWAY_TZ=-3
    log "WC3_KIT_GATEWAY_TZ no esta en .env: uso -3 (Argentina)"
fi
export WC3_KIT_GATEWAY_TZ

KIT_NAME="$(printf '%s' "${WC3_REALM_NAME}" | tr ' ' '-')-Kit"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
KIT="${STAGE}/${KIT_NAME}"
install -d "${KIT}" "${KIT}/loader" "${KIT}/mapas" "${KIT}/herramientas"

# --- loader ------------------------------------------------------------------
# Se cachea para no golpear el CDN en cada build. .cache esta en .gitignore.
install -d "${CACHE_DIR}"
W3L_ZIP="${CACHE_DIR}/w3l.zip"
if [[ ! -s "${W3L_ZIP}" ]]; then
    log "bajando el loader de ${W3L_URL}"
    # HTTP a secas: el CDN de pvpgn.pro no sirve bien por HTTPS (curl 60).
    # La integridad la garantiza el chequeo de SHA-256 de abajo, no el canal.
    curl -fsSL -o "${W3L_ZIP}" "${W3L_URL}" \
        || die "no pude bajar el loader. Bajalo a mano a ${W3L_ZIP} desde https://pvpgn.pro/w3l.html"
else
    log "loader ya cacheado en ${W3L_ZIP}"
fi

# Verificar SIEMPRE, tambien el cacheado: un cache envenenado una vez seria
# malware repartido para siempre.
hash_real="$(sha256sum "${W3L_ZIP}" | cut -d' ' -f1)"
if [[ "${hash_real}" != "${W3L_SHA256}" ]]; then
    rm -f "${W3L_ZIP}"
    die "el zip del loader NO coincide con el SHA-256 esperado (borre el cache).
  esperado: ${W3L_SHA256}
  obtenido: ${hash_real}
Puede ser una descarga corrupta (reintentar) o un zip adulterado. Si cambiaste
de version a proposito, defini WC3_W3L_SHA256 con el hash nuevo."
fi
log "loader verificado (sha256 OK)"

log "extrayendo el loader"
W3L_TMP="${STAGE}/w3l"
install -d "${W3L_TMP}"
unzip -qq -o -P "${W3L_ZIP_PASSWORD}" "${W3L_ZIP}" -d "${W3L_TMP}"

# wl27.dll es la DLL de 1.27; sin ella el loader no engancha esa version.
for f in w3l.exe w3lh.dll wl27.dll; do
    src="$(find "${W3L_TMP}" -iname "${f}" -type f -print -quit)"
    [[ -n "${src}" ]] || die "el zip del loader no trae ${f}"
    install -m 644 "${src}" "${KIT}/loader/${f}"
done
lat="$(find "${W3L_TMP}" -iname 'latency.txt' -type f -print -quit)"
[[ -n "${lat}" ]] && install -m 644 "${lat}" "${KIT}/loader/latency.txt"

# --- templates ---------------------------------------------------------------
# Whitelist de variables para envsubst: solo las WC3_*, para no pisar cosas
# como %USERPROFILE% ni los $s de PowerShell adentro del .bat.
subst=""
while IFS= read -r v; do subst+="\${${v}} "; done < <(compgen -v | grep '^WC3_')

log "renderizando templates"
envsubst "${subst}" < "${REPO_DIR}/kit/INSTALAR.bat.tpl" > "${KIT}/INSTALAR.bat"
envsubst "${subst}" < "${REPO_DIR}/kit/INSTALAR-JUEGO.bat.tpl" > "${KIT}/INSTALAR-JUEGO.bat"
envsubst "${subst}" < "${REPO_DIR}/kit/LEEME.txt.tpl"    > "${KIT}/LEEME.txt"
install -m 644 "${REPO_DIR}/kit/herramientas/gateway.ps1" "${KIT}/herramientas/gateway.ps1"
install -m 644 "${REPO_DIR}/kit/mapas/PONER-LOS-MAPAS-ACA.txt" "${KIT}/mapas/"

for f in "${KIT}/INSTALAR.bat" "${KIT}/INSTALAR-JUEGO.bat" "${KIT}/LEEME.txt"; do
    # shellcheck disable=SC2016  # buscamos el literal ${WC3_, sin expandirlo
    if grep -q '\${WC3_' "${f}"; then
        die "quedo un placeholder sin resolver en $(basename "${f}")"
    fi
done

# --- mapas (opcional) --------------------------------------------------------
if [[ -n "${MAPS_DIR}" ]]; then
    [[ -d "${MAPS_DIR}" ]] || die "no existe el directorio de mapas ${MAPS_DIR}"
    count=0
    for m in "${MAPS_DIR}"/*.w3x; do
        [[ -f "${m}" ]] || continue
        install -m 644 "${m}" "${KIT}/mapas/"
        count=$((count + 1))
    done
    log "mapas incluidos: ${count}"
    [[ "${count}" -gt 0 ]] || log "  (ojo: no habia ningun .w3x en ${MAPS_DIR})"
else
    log "sin mapas (usar --maps DIR para incluirlos)"
fi

# --- finales de linea CRLF ---------------------------------------------------
# Windows los quiere asi; el .bat en particular se porta raro sin ellos. Se
# excluye loader/ a proposito: esos archivos son de terceros (latency.txt es
# data del loader, no texto nuestro) y no se tocan.
log "pasando .bat/.txt/.ps1 a CRLF"
while IFS= read -r -d '' f; do
    tmp="${f}.crlf"
    sed 's/$/\r/' "${f}" > "${tmp}" && mv "${tmp}" "${f}"
done < <(find "${KIT}" -path "${KIT}/loader" -prune -o \
    \( -name '*.bat' -o -name '*.txt' -o -name '*.ps1' \) -type f -print0)

# --- empaquetar --------------------------------------------------------------
install -d "${OUT_DIR}"
ZIP="${OUT_DIR}/${KIT_NAME}.zip"
rm -f "${ZIP}"
( cd "${STAGE}" && zip -rq "${ZIP}" "${KIT_NAME}" )

log "OK: ${ZIP} ($(du -h "${ZIP}" | cut -f1))"
log "Se lo pasas a los amigos tal cual; lo unico que tienen que hacer es"
log "descomprimirlo y darle doble clic a INSTALAR.bat."
