#!/usr/bin/env bash
# ============================================================================
# diagnose-join.sh — captura la evidencia de UN intento de join, en el VPS
#
# Mientras el script corre, alguien intenta entrar a una partida desde su
# cliente. En paralelo se graba:
#   - tcpdump de 6112 (PvPGN) y todo el rango de los bots (6113-6140) a un .pcap
#   - el log de aplicacion de PvPGN (bnetd.log)
#   - el journal del bot de la instancia elegida
# Al final, el resumen que importa: cuantos SYN llegaron al puerto del bot.
# Si son 0, el cliente NUNCA intento conectarse: el problema esta antes (en
# el anuncio de la partida), no en la red ni en el firewall.
#
# Uso: sudo ./scripts/diagnose-join.sh [instancia] [segundos]
#      instancia: numero de bot (default 1); su puerto es 6113+(N-1)
#      segundos:  duracion de la captura (default 90)
# ============================================================================
set -euo pipefail

INSTANCE="${1:-1}"
DURATION="${2:-90}"
BNETD_LOG="/opt/wc3/pvpgn/var/pvpgn/bnetd.log"

# --- Validaciones -----------------------------------------------------------
if [[ ! "${INSTANCE}" =~ ^[1-9][0-9]?$ ]]; then
    echo "uso: sudo $0 [instancia] [segundos]   (instancia: 1-28; default 1)" >&2
    exit 1
fi
if [[ ! "${DURATION}" =~ ^[1-9][0-9]*$ ]]; then
    echo "uso: sudo $0 [instancia] [segundos]   (segundos: entero positivo; default 90)" >&2
    exit 1
fi

HOSTBOT_UNIT="wc3-hostbot@${INSTANCE}"
# Mismas bases que scripts/make-instances.py: host 6113+, reconnect 6133+
BOT_PORT=$((6113 + INSTANCE - 1))

if [[ "${EUID}" -ne 0 ]]; then
    echo "hay que correrlo con sudo: tcpdump, journalctl y bnetd.log lo necesitan" >&2
    exit 1
fi

if ! command -v tcpdump >/dev/null; then
    echo "falta tcpdump. Instalarlo con:" >&2
    echo "    sudo apt install tcpdump" >&2
    exit 1
fi

if [[ ! -r "${BNETD_LOG}" ]]; then
    echo "no se puede leer ${BNETD_LOG}" >&2
    echo "¿PvPGN esta instalado y corriendo en esta maquina?" >&2
    exit 1
fi

# --- Archivos de salida -----------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
PCAP="/tmp/join-${STAMP}.pcap"
BNETD_OUT="/tmp/join-${STAMP}-bnetd.log"
BOT_OUT="/tmp/join-${STAMP}-hostbot.log"
TCPDUMP_ERR="/tmp/join-${STAMP}-tcpdump.err"

PIDS=()

cleanup() {
    if [[ "${#PIDS[@]}" -gt 0 ]]; then
        kill "${PIDS[@]}" 2>/dev/null || true
        wait "${PIDS[@]}" 2>/dev/null || true
        PIDS=()
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# --- Captura ----------------------------------------------------------------
echo "== diagnose-join: instancia ${INSTANCE} (puerto ${BOT_PORT}), captura de ${DURATION}s =="
echo "    pcap:      ${PCAP}"
echo "    bnetd.log: ${BNETD_OUT}"
echo "    hostbot:   ${BOT_OUT}"
echo

# Todo el rango de bots (host 6113-6120 y reconnect 6133-6140, con margen):
# capturar solo el puerto elegido escondia los joins a las otras instancias.
tcpdump -i any -nn 'tcp port 6112 or tcp portrange 6113-6140' \
    -w "${PCAP}" 2>"${TCPDUMP_ERR}" &
PIDS+=("$!")

tail -n 0 -f "${BNETD_LOG}" >"${BNETD_OUT}" &
PIDS+=("$!")

journalctl -fu "${HOSTBOT_UNIT}" -n 0 --no-pager >"${BOT_OUT}" &
PIDS+=("$!")

# darle un momento a tcpdump y verificar que arranco de verdad
sleep 1
if ! kill -0 "${PIDS[0]}" 2>/dev/null; then
    echo "tcpdump no arranco:" >&2
    cat "${TCPDUMP_ERR}" >&2
    exit 1
fi

# --- Countdown --------------------------------------------------------------
echo ">>> INTENTA EL JOIN AHORA (entrar a la partida desde el cliente) <<<"
for ((s = DURATION; s > 0; s--)); do
    printf '\r    capturando... quedan %4d s ' "${s}"
    sleep 1
done
printf '\r    captura terminada.               \n\n'

cleanup

# --- Resumen ----------------------------------------------------------------
SYN_COUNT="$(tcpdump -nn -r "${PCAP}" "tcp dst port ${BOT_PORT}" 2>/dev/null \
    | grep -c 'Flags \[S\]' || true)"
SYN_COUNT="${SYN_COUNT:-0}"

echo "== resumen =="
echo "SYN entrantes al puerto ${BOT_PORT} (el bot): ${SYN_COUNT}"
if [[ "${SYN_COUNT}" -eq 0 ]]; then
    echo "    -> 0 SYN: el cliente nunca intento conectarse al bot."
    echo "       El problema esta ANTES (el anuncio de la partida que recibe"
    echo "       el cliente), no en la red ni en el firewall."
else
    echo "    -> el cliente SI llego al puerto del bot; mirar el log de Aura"
    echo "       de abajo para ver que paso con esa conexion."
fi
echo

echo "-- ultimas lineas de bnetd.log durante la captura --"
if [[ -s "${BNETD_OUT}" ]]; then
    tail -n 15 "${BNETD_OUT}"
else
    echo "    (sin lineas nuevas durante la captura)"
fi
echo

echo "-- ultimas lineas del bot (${HOSTBOT_UNIT}) durante la captura --"
if [[ -s "${BOT_OUT}" ]]; then
    tail -n 15 "${BOT_OUT}"
else
    echo "    (sin lineas nuevas durante la captura)"
fi
echo

echo "== archivos generados =="
ls -lh "${PCAP}" "${BNETD_OUT}" "${BOT_OUT}"
echo
echo "El pcap quedo en: ${PCAP}"
echo "Para inspeccionarlo: tcpdump -nn -r ${PCAP} | less"
