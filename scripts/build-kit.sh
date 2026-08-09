#!/usr/bin/env bash
# ============================================================================
# build-kit.sh — arma el kit que se le pasa a los amigos
#
#   ./scripts/build-kit.sh [directorio_de_salida]
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
    curl -fsSL -o "${W3L_ZIP}" "${W3L_URL}" \
        || die "no pude bajar el loader. Bajalo a mano a ${W3L_ZIP} desde https://pvpgn.pro/w3l.html"
else
    log "loader ya cacheado en ${W3L_ZIP}"
fi

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

# --- WFE: teclas estilo LoL (opcional, mejor esfuerzo) -----------------------
# El binario vive en los releases de GitHub (el repo git trae solo configs),
# asi que la URL del asset se descubre por la API en el momento del build. Si
# no hay internet o la API cambia, el kit sale sin extras y se avisa: WFE es
# opcional, no vale la pena frenar el build por el.
WFE_ZIP="${CACHE_DIR}/wfe.zip"
if [[ ! -s "${WFE_ZIP}" ]]; then
    log "buscando el ultimo release de WFE (teclas QWER + vida visible)"
    wfe_url="$(curl -fsSL --max-time 30 \
        https://api.github.com/repos/UnryzeC/WFE-Release/releases/latest 2>/dev/null \
        | grep -oE '"browser_download_url" *: *"[^"]*\.zip"' \
        | head -1 | grep -oE 'https[^"]*')" || true
    if [[ -n "${wfe_url:-}" ]]; then
        log "bajando ${wfe_url}"
        curl -fsSL -o "${WFE_ZIP}" "${wfe_url}" || rm -f "${WFE_ZIP}"
    fi
fi
if [[ -s "${WFE_ZIP}" ]]; then
    install -d "${KIT}/extras/WFE"
    if unzip -qq -o "${WFE_ZIP}" -d "${KIT}/extras/WFE"; then
        # Si el zip venia con una unica carpeta arriba (p. ej. WFE/), se aplana
        # para que la ruta sea extras\WFE\WFEApp.exe, como dice TECLAS-LOL.txt.
        mapfile -t _tope < <(find "${KIT}/extras/WFE" -mindepth 1 -maxdepth 1)
        if [[ "${#_tope[@]}" -eq 1 && -d "${_tope[0]}" ]]; then
            mv "${_tope[0]}"/* "${KIT}/extras/WFE/"
            rmdir "${_tope[0]}"
        fi
        # El perfil QWER+DF se genera contra el WFEConfigBase.ini que vino en
        # ESTE zip: si WFE renombro claves, make-wfe-profile.py aborta y el
        # kit sale sin el perfil antes que con uno a medias.
        wfe_base="$(find "${KIT}/extras/WFE" -iname 'WFEConfigBase.ini' -print -quit)"
        wfe_root="$(find "${KIT}/extras/WFE" -iname 'WFEApp.exe' -printf '%h\n' -quit)"
        [[ -n "${wfe_root}" ]] || wfe_root="${KIT}/extras/WFE"
        if [[ -n "${wfe_base}" ]] && python3 "${REPO_DIR}/scripts/make-wfe-profile.py" \
                "${wfe_base}" --out "${wfe_root}/Profiles/WC3Revival.ini"; then
            envsubst "${subst}" < "${REPO_DIR}/kit/TECLAS-LOL.txt.tpl" > "${KIT}/TECLAS-LOL.txt"
            log "WFE listo con el perfil WC3Revival (ver TECLAS-LOL.txt)"
        else
            log "AVISO: no pude generar el perfil de WFE; el kit sale sin extras"
            rm -rf "${KIT}/extras"
        fi
    else
        log "AVISO: el zip de WFE no se pudo extraer; el kit sale sin extras"
        rm -rf "${KIT}/extras" "${WFE_ZIP}"
    fi
else
    log "AVISO: sin release de WFE a mano; el kit sale sin las teclas estilo LoL"
fi

# --- finales de linea CRLF ---------------------------------------------------
# Windows los quiere asi; el .bat en particular se porta raro sin ellos. Se
# excluye loader/ a proposito: esos archivos son de terceros (latency.txt es
# data del loader, no texto nuestro) y no se tocan.
log "pasando .bat/.txt/.ps1 a CRLF"
while IFS= read -r -d '' f; do
    tmp="${f}.crlf"
    sed 's/$/\r/' "${f}" > "${tmp}" && mv "${tmp}" "${f}"
done < <(find "${KIT}" \( -path "${KIT}/loader" -o -path "${KIT}/extras" \) -prune -o \
    \( -name '*.bat' -o -name '*.txt' -o -name '*.ps1' \) -type f -print0)

# --- empaquetar --------------------------------------------------------------
install -d "${OUT_DIR}"
ZIP="${OUT_DIR}/${KIT_NAME}.zip"
rm -f "${ZIP}"
( cd "${STAGE}" && zip -rq "${ZIP}" "${KIT_NAME}" )

log "OK: ${ZIP} ($(du -h "${ZIP}" | cut -f1))"
log "Se lo pasas a los amigos tal cual; lo unico que tienen que hacer es"
log "descomprimirlo y darle doble clic a INSTALAR.bat."
