#!/usr/bin/env bash
# ============================================================================
# 40-render-configs.sh — templates de config/ + .env -> configs finales
# Correr con sudo. Seguro de correr en caliente: escribe a archivo temporal,
# hace backup fechado del anterior y recien ahi mueve el nuevo. Los servicios
# toman la config nueva en el proximo restart (no se reinician solos).
#
# Valida que no quede ningun ${...} sin resolver en los archivos generados.
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env"
BACKUP_DIR="/opt/wc3/backups/configs"
STAMP="$(date +%Y%m%d-%H%M%S)"

log() { printf '[render] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo (escribe en /opt/wc3 y /opt/wc3/pvpgn/etc)." >&2
    exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Falta ${ENV_FILE}. Copia .env.example a .env y completalo." >&2
    exit 1
fi

# Cargar .env exportando todo (envsubst solo ve variables exportadas)
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"

# Variables agregadas despues de que se creo el .env del servidor. Si faltan,
# el render aborta por "placeholder sin resolver" y desde el mensaje no se
# entiende que el problema es un .env viejo, asi que se les da un default
# razonable. Las criticas (IP publica, contrasenas) siguen siendo obligatorias:
# ahi un default silencioso daria un servidor que no funciona.
#
# Vacio = autohost apagado, que es el comportamiento original de Aura. Cada
# instancia define el suyo en config/hostbot/instance-N.env.
WC3_BOT_AUTOHOSTNAME="${WC3_BOT_AUTOHOSTNAME:-}"
if [[ -z "${WC3_BOT_AUTOHOSTOWNER:-}" ]]; then
    # Dueno de las partidas que crea el autohost: el primer admin de la lista.
    WC3_BOT_AUTOHOSTOWNER="${WC3_BOT_ROOTADMINS%%,*}"
    log "WC3_BOT_AUTOHOSTOWNER no esta en .env: uso '${WC3_BOT_AUTOHOSTOWNER}'"
fi
set +a

# Whitelist para envsubst: SOLO variables WC3_*. Asi un ${prefix} legitimo de
# un conf de PvPGN (p. ej. sql_DB_layout.conf) jamas se pisa por accidente.
build_subst_list() {
    local v out=""
    while IFS= read -r v; do
        out+="\${${v}} "
    done < <(compgen -v | grep '^WC3_' || true)
    printf '%s' "${out}"
}

# render <template> <destino> [vars_extra_file]
render() {
    local tpl="$1" dest="$2" extra="${3:-}"
    local tmp
    tmp="$(mktemp)"

    if [[ -n "${extra}" ]]; then
        # Sub-shell: las vars de la instancia no contaminan el resto del run
        (
            set -a
            # shellcheck source=/dev/null
            source "${extra}"
            set +a
            envsubst "$(build_subst_list)" < "${tpl}" > "${tmp}"
        )
    else
        envsubst "$(build_subst_list)" < "${tpl}" > "${tmp}"
    fi

    # Ningun placeholder WC3_ puede quedar vivo
    # shellcheck disable=SC2016  # el patron busca literalmente "${WC3_"
    if grep -n '\${WC3_' "${tmp}"; then
        echo "ERROR: quedaron placeholders sin resolver renderizando ${tpl} (ver arriba)." >&2
        echo "Definilos en .env${extra:+ o en ${extra}}." >&2
        rm -f "${tmp}"
        exit 1
    fi

    if [[ -f "${dest}" ]]; then
        install -d "${BACKUP_DIR}/${STAMP}"
        cp -a "${dest}" "${BACKUP_DIR}/${STAMP}/$(basename "${dest}")"
    fi
    install -m 640 -o wc3 -g wc3 "${tmp}" "${dest}"
    rm -f "${tmp}"
    log "renderizado: ${dest}"
}

# --- PvPGN -------------------------------------------------------------------
render "${REPO_DIR}/config/pvpgn/bnetd.conf.tpl" \
       /opt/wc3/pvpgn/etc/pvpgn/bnetd.conf
render "${REPO_DIR}/config/pvpgn/address_translation.conf.tpl" \
       /opt/wc3/pvpgn/etc/pvpgn/address_translation.conf

# --- Presentacion: banner del cliente + mensaje de bienvenida ----------------
# El cliente muestra un banner de 468x60 arriba del chat; PvPGN lo declara en
# ad.json y sirve el PNG desde su filedir por BNFTP (ver docs/presentacion.md).
render "${REPO_DIR}/config/pvpgn/ad.json.tpl" /opt/wc3/pvpgn/etc/pvpgn/ad.json

# El mensaje de bienvenida (w3motd.txt) esta repetido por idioma en i18n/;
# pisamos el base y TODAS las variantes que existan, para que de el mismo
# texto sin importar el locale del cliente (era lo que hacia aparecer el
# saludo en aleman).
for motd in /opt/wc3/pvpgn/etc/pvpgn/i18n/w3motd.txt \
            /opt/wc3/pvpgn/etc/pvpgn/i18n/*/w3motd.txt; do
    [[ -f "${motd}" ]] || continue
    render "${REPO_DIR}/config/pvpgn/w3motd.txt.tpl" "${motd}"
done

# El banner en si: lo dibuja make-banner.py (necesita Pillow, que vive en el
# venv). Si falta, no es fatal: queda el banner default de PvPGN.
BANNER_PY=/opt/wc3/venv/bin/python
if [[ -x "${BANNER_PY}" ]] && "${BANNER_PY}" -c 'import PIL' 2>/dev/null; then
    "${BANNER_PY}" "${REPO_DIR}/scripts/make-banner.py" \
        --title "${WC3_REALM_NAME}" \
        --subtitle "${WC3_BANNER_SUBTITLE:-${WC3_SERVER_DESCRIPTION}}" \
        --out /opt/wc3/pvpgn/var/pvpgn/files/ad000001.png
    chown wc3:wc3 /opt/wc3/pvpgn/var/pvpgn/files/ad000001.png
    log "banner regenerado (el cliente lo cachea: puede tardar una reconexion en verse)"
else
    log "Pillow no disponible en /opt/wc3/venv: dejo el banner que este"
fi

# --- Hostbots: una instancia por config/hostbot/instance-N.env ---------------
shopt -s nullglob
found_instance=0
for inst_env in "${REPO_DIR}"/config/hostbot/instance-*.env; do
    found_instance=1
    n="$(basename "${inst_env}" | sed -E 's/instance-([0-9]+)\.env/\1/')"
    inst_dir="/opt/wc3/hostbot/instances/${n}"
    install -d -o wc3 -g wc3 "${inst_dir}"
    # Aura busca ip-to-country.csv en su directorio de trabajo
    if [[ ! -f "${inst_dir}/ip-to-country.csv" && -f /opt/wc3/hostbot/ip-to-country.csv ]]; then
        install -m 644 -o wc3 -g wc3 \
            /opt/wc3/hostbot/ip-to-country.csv "${inst_dir}/ip-to-country.csv"
    fi
    render "${REPO_DIR}/config/hostbot/aura.cfg.tpl" "${inst_dir}/aura.cfg" "${inst_env}"
    log "instancia ${n} lista: systemctl enable --now wc3-hostbot@${n}"
done
if [[ "${found_instance}" -eq 0 ]]; then
    log "ATENCION: no hay config/hostbot/instance-*.env; no se renderizo ningun bot"
fi

log "OK. Backups de configs anteriores (si habia): ${BACKUP_DIR}/${STAMP}/"
log "Aplicar con: systemctl restart pvpgn wc3-hostbot@N"
