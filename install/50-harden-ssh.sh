#!/usr/bin/env bash
# ============================================================================
# 50-harden-ssh.sh — deshabilita el login por contraseña y el root por SSH
#
#   sudo ./install/50-harden-ssh.sh [usuario_admin]
#
# CORRER SOLO DESPUES de haber comprobado que entras por clave:
#   ssh usuario@IP     -> tiene que entrar SIN pedirte contraseña
#
# Este paso esta separado del bootstrap a proposito. En la primera puesta en
# marcha real (2026-08-08) hacerlo automatico dejo el VPS inaccesible: el
# archivo de config quedo con prioridad mas baja que el de cloud-init, asi que
# se aplico el bloqueo de root pero NO el de contraseñas, y el usuario admin
# no tenia contraseña ni clave. Puerta cerrada por los dos lados.
#
# Salvaguardas de este script:
#  - se niega a correr si el usuario admin no tiene authorized_keys
#  - usa prefijo 01- para ganarle a 50-cloud-init.conf (sshd usa el PRIMER
#    valor que encuentra, leyendo los .conf en orden alfabetico)
#  - deja PermitRootLogin en prohibit-password, no en no: root por clave sigue
#    disponible como red de contencion
#  - valida la config con sshd -t ANTES de recargar
# ============================================================================
set -euo pipefail

ADMIN_USER="${1:-wc3admin}"

log() { printf '[harden-ssh] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Correr con sudo." >&2
    exit 1
fi

if ! id "${ADMIN_USER}" &>/dev/null; then
    echo "El usuario ${ADMIN_USER} no existe. Pasá el nombre correcto como argumento." >&2
    exit 1
fi

KEYS="/home/${ADMIN_USER}/.ssh/authorized_keys"
if [[ ! -s "${KEYS}" ]]; then
    echo "ABORTADO: ${KEYS} no existe o esta vacio." >&2
    echo "Sin clave publica cargada, endurecer SSH te deja afuera del servidor." >&2
    exit 1
fi
log "clave publica encontrada para ${ADMIN_USER} ($(wc -l < "${KEYS}") linea/s)"

cat <<EOF

  ATENCION: antes de seguir, abri OTRA terminal y comproba que esto entra
  sin pedirte contraseña:

      ssh ${ADMIN_USER}@<IP-del-servidor>

  Si no entra, cancela con Ctrl+C y resolve eso primero.

EOF
read -r -p "Ya lo comprobaste y entra por clave? (escribi SI) " answer
if [[ "${answer}" != "SI" ]]; then
    echo "Cancelado. Nada fue modificado." >&2
    exit 1
fi

install -d /etc/ssh/sshd_config.d
# Prefijo 01: sshd usa el PRIMER valor que encuentra y lee los .conf en orden
# alfabetico, asi que este tiene que ir ANTES que 50-cloud-init.conf.
CONF=/etc/ssh/sshd_config.d/01-wc3-hardening.conf
cat > "${CONF}" <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
# prohibit-password (no "no"): root por clave queda como red de contencion
PermitRootLogin prohibit-password
X11Forwarding no
EOF
log "escrito ${CONF}"

if ! sshd -t; then
    log "la config de sshd NO valida: revirtiendo"
    rm -f "${CONF}"
    exit 1
fi
log "config validada con sshd -t"

systemctl reload ssh
log "sshd recargado."
log "NO cierres esta sesion hasta confirmar en otra terminal que seguis entrando."
