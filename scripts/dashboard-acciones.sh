#!/usr/bin/env bash
# ============================================================================
# dashboard-acciones.sh — el companero de root del dashboard
#
# El dashboard corre como wc3 sin privilegios (NoNewPrivileges: ni sudo
# puede). Cuando el operador toca un boton, el dashboard deja un pedido en
# /opt/wc3/dashboard/spool y systemd dispara este script como root
# (wc3-dashboard-acciones.path -> .service). Aca se valida el pedido contra
# una lista BLANCA de acciones fijas y se deja el resultado donde el
# dashboard lo pueda leer. Nada de comandos arbitrarios: lo maximo que un
# atacante con la contraseña del panel puede hacer es exactamente esto.
#
# Formato del pedido (<id>.pedido): linea 1 la accion, linea 2 el argumento.
# Resultado (<id>.resultado): linea 1 el exit code, resto la salida.
# ============================================================================
set -euo pipefail

SPOOL=/opt/wc3/dashboard/spool
RESULTADOS=/opt/wc3/dashboard/resultados
# DASH_REPO_DIR viene de /opt/wc3/dashboard.env (lo escribe el instalador)
REPO="${DASH_REPO_DIR:-/opt/wc3-repo}"

log() { printf '[acciones] %s\n' "$*"; }

install -d -o root -g wc3 -m 750 "${RESULTADOS}"

PY=/opt/wc3/venv/bin/python
[[ -x "${PY}" ]] || PY=python3

# OJO con el set -e aca adentro: como ejecutar() se llama con `|| codigo=$?`,
# bash desactiva errexit dentro de la funcion. Cada comando que puede fallar
# lleva su `|| return` explicito, si no el resultado diria "exit 0" mintiendo.
ejecutar() { # ejecutar <accion> <arg> -> salida por stdout, exit code real
    local accion="$1" arg="$2"
    case "${accion}" in
        reiniciar-pvpgn)
            systemctl restart pvpgn || return 1
            echo "pvpgn reiniciado: $(systemctl is-active pvpgn)"
            ;;
        reiniciar-bot)
            [[ "${arg}" =~ ^[0-9]{1,2}$ ]] || { echo "numero de bot invalido"; return 1; }
            systemctl restart "wc3-hostbot@${arg}" || return 1
            echo "wc3-hostbot@${arg} reiniciado: $(systemctl is-active "wc3-hostbot@${arg}")"
            ;;
        backup)
            "${REPO}/scripts/backup.sh" || return 1
            ;;
        reparar-caidos)
            local unidades=(pvpgn)
            local d n unidad
            shopt -s nullglob
            for d in /opt/wc3/hostbot/instances/*; do
                [[ -d "${d}" ]] || continue
                n="$(basename "${d}")"
                [[ "${n}" =~ ^[0-9]{1,2}$ ]] || continue
                unidades+=("wc3-hostbot@${n}")
            done
            for unidad in "${unidades[@]}"; do
                if systemctl is-active --quiet "${unidad}"; then
                    echo "${unidad}: ya estaba active"
                else
                    systemctl restart "${unidad}" || return 1
                    echo "${unidad}: recuperado ($(systemctl is-active "${unidad}"))"
                fi
            done
            ;;
        instalar-mapas)
            shopt -s nullglob
            local mapas=("/opt/wc3/incoming/"*.w3x "/opt/wc3/incoming/"*.w3m)
            if [[ "${#mapas[@]}" -eq 0 ]]; then
                echo "no hay mapas esperando en /opt/wc3/incoming"
                return 0
            fi
            # Mismo camino que `make brand-maps`: preview + instalar en la
            # carpeta del bot. Si todo salio bien, los originales se archivan
            # para que no queden como "pendientes" eternos.
            # Con el techo de subida levantado (WC3_MAX_MAP_MB > 8 en el
            # dashboard.env), los mapas grandes se instalan a proposito:
            # --allow-large. Solo cargan con WFE en TODOS los clientes.
            local extra=()
            if [[ "${WC3_MAX_MAP_MB:-8}" =~ ^[0-9]+$ && "${WC3_MAX_MAP_MB:-8}" -gt 8 ]]; then
                extra+=(--allow-large)
            fi
            "${PY}" "${REPO}/scripts/brand-map.py" "${mapas[@]}" --out-dir /opt/wc3/maps \
                "${extra[@]}" || return 1
            chown wc3:wc3 /opt/wc3/maps/*.w3x /opt/wc3/maps/*.w3m 2>/dev/null || true
            install -d -o wc3 -g wc3 /opt/wc3/incoming/instalados
            mv -f "${mapas[@]}" /opt/wc3/incoming/instalados/ || return 1
            echo
            echo "${#mapas[@]} mapa(s) instalados en /opt/wc3/maps (originales"
            echo "archivados en incoming/instalados). Si alguno REEMPLAZA un mapa"
            echo "que ya se hostea, reinicia su bot para que tome el archivo nuevo."
            ;;
        *)
            echo "accion desconocida: ${accion}"
            return 1
            ;;
    esac
}

shopt -s nullglob
for pedido in "${SPOOL}"/*.pedido; do
    id="$(basename "${pedido}" .pedido)"
    # El id lo genero el dashboard: igual se valida, porque quien escribe en
    # el spool define que archivo de resultado se crea.
    if ! [[ "${id}" =~ ^[0-9]+-[0-9a-f]+$ ]]; then
        log "pedido con id invalido: ${pedido} (borrado)"
        rm -f "${pedido}"
        continue
    fi
    accion="$(sed -n '1p' "${pedido}" | tr -cd 'a-z-')"
    arg="$(sed -n '2p' "${pedido}" | tr -cd '0-9')"
    rm -f "${pedido}"

    log "ejecutando: ${accion} ${arg}"
    salida_tmp="$(mktemp)"
    codigo=0
    ejecutar "${accion}" "${arg}" >"${salida_tmp}" 2>&1 || codigo=$?

    {
        echo "${codigo}"
        tail -c 16384 "${salida_tmp}"
    } > "${RESULTADOS}/${id}.resultado.tmp"
    chown root:wc3 "${RESULTADOS}/${id}.resultado.tmp"
    chmod 640 "${RESULTADOS}/${id}.resultado.tmp"
    mv "${RESULTADOS}/${id}.resultado.tmp" "${RESULTADOS}/${id}.resultado"
    rm -f "${salida_tmp}"
    log "listo: ${accion} -> exit ${codigo}"
done

# Resultados viejos: a la basura (el dashboard los lee en segundos)
find "${RESULTADOS}" -name '*.resultado' -mmin +120 -delete 2>/dev/null || true
