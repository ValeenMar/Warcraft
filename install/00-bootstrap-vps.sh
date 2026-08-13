#!/usr/bin/env bash
# ============================================================================
# 00-bootstrap-vps.sh — deja un Ubuntu 24.04 recien creado listo para el stack
# Correr como root (o con sudo) UNA vez; es idempotente, se puede re-correr.
#
#   sudo ./install/00-bootstrap-vps.sh [usuario_admin]
#
# Hace: usuario admin con sudo, hardening de SSH, ufw, fail2ban, timezone,
# swap si hay poca RAM, usuario de sistema wc3, arbol /opt/wc3 y dependencias
# de compilacion de PvPGN y Aura.
# ============================================================================
set -euo pipefail

ADMIN_USER="${1:-wc3admin}"
TIMEZONE="${WC3_TIMEZONE:-America/Argentina/Buenos_Aires}"
# Rango de puertos de los hostbots; mantener en sintonia con WC3_BOT_PORT_RANGE
BOT_PORT_RANGE="${WC3_BOT_PORT_RANGE:-6113:6141}"
# Algunos proveedores exponen un segundo puerto SSH dentro de la VM. Se pasa
# al bootstrap para que UFW no corte la sesion al activarse.
SSH_PORT="${WC3_SSH_PORT:-22}"

log() { printf '[bootstrap] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Este script tiene que correr como root (sudo)." >&2
    exit 1
fi

# --- Paquetes ----------------------------------------------------------------
log "instalando paquetes base y dependencias de compilacion"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
# build-essential/cmake/git: PvPGN y Aura
# default-libmysqlclient-dev: backend MySQL de PvPGN
# libgmp-dev/libbz2-dev/zlib1g-dev/m4: bncsutil y StormLib (Aura)
# gettext-base: envsubst para render de configs
# smpq: frontend de StormLib, lo usa scripts/brand-map.py para meterle la
#       preview propia a los mapas
apt-get install -y -q \
    build-essential cmake git m4 \
    default-libmysqlclient-dev \
    libgmp-dev libbz2-dev zlib1g-dev \
    mysql-server \
    ufw fail2ban \
    gettext-base python3 python3-pip python3-venv \
    python3-yaml python3-jsonschema \
    smpq \
    curl unzip

# venv para las dependencias de inspect-map.py y brand-map.py que no estan
# empaquetadas en Ubuntu (mpyq no instala contra el setuptools parcheado de
# Debian fuera de un venv; verificado en sandbox 2026-08-08). Pillow se usa
# para dibujar las previews de los mapas (scripts/make-preview.py).
# Versiones PINNEADAS: el bootstrap se re-corre, y sin pin cada corrida
# traeria lo ultimo de PyPI al venv del servidor (irreproducible, y un
# release roto o comprometido entraria solo). Actualizar a conciencia.
if [[ ! -x /opt/wc3/venv/bin/python ]]; then
    log "creando venv /opt/wc3/venv (mpyq + pyyaml + pillow)"
    install -d /opt/wc3
    python3 -m venv /opt/wc3/venv
fi
/opt/wc3/venv/bin/pip install --quiet 'mpyq==0.2.5' 'pyyaml==6.0.2' 'pillow==11.0.0'

# --- Timezone ----------------------------------------------------------------
log "timezone -> ${TIMEZONE}"
timedatectl set-timezone "${TIMEZONE}"

# --- Usuario admin con sudo --------------------------------------------------
if ! id "${ADMIN_USER}" &>/dev/null; then
    log "creando usuario admin ${ADMIN_USER}"
    adduser --disabled-password --gecos '' "${ADMIN_USER}"
    usermod -aG sudo "${ADMIN_USER}"
    # Copiar las authorized_keys de root si existen, para no quedar afuera
    if [[ -f /root/.ssh/authorized_keys ]]; then
        install -d -m 700 -o "${ADMIN_USER}" -g "${ADMIN_USER}" "/home/${ADMIN_USER}/.ssh"
        install -m 600 -o "${ADMIN_USER}" -g "${ADMIN_USER}" \
            /root/.ssh/authorized_keys "/home/${ADMIN_USER}/.ssh/authorized_keys"
    fi
else
    log "usuario ${ADMIN_USER} ya existe, sigo"
fi
# El usuario se crea SIN contraseña (entra por clave SSH), asi que sudo no
# puede pedirle una: sin esto, estar en el grupo sudo no sirve de nada y la
# unica administracion posible queda siendo root directo.
if [[ ! -f "/etc/sudoers.d/90-${ADMIN_USER}" ]]; then
    log "sudo sin contraseña para ${ADMIN_USER} (no tiene password: entra por clave)"
    echo "${ADMIN_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-${ADMIN_USER}"
    chmod 440 "/etc/sudoers.d/90-${ADMIN_USER}"
    visudo -cf "/etc/sudoers.d/90-${ADMIN_USER}" >/dev/null
fi

# --- Hardening de SSH: NO se hace aca ---------------------------------------
# Se movio a install/50-harden-ssh.sh, que hay que correr a mano DESPUES de
# confirmar que entras por clave. Motivo (aprendido a los golpes el
# 2026-08-08): hacerlo automatico aca dejo un VPS inaccesible.
log "SSH: el endurecimiento NO se aplica automaticamente (ver 50-harden-ssh.sh)"
if [[ ! -s "/home/${ADMIN_USER}/.ssh/authorized_keys" ]]; then
    log "  ATENCION: ${ADMIN_USER} no tiene clave publica cargada todavia."
    log "  Cargala antes de intentar endurecer SSH, o vas a quedar afuera."
fi

# --- Firewall ----------------------------------------------------------------
log "configurando ufw (SSH 22/${SSH_PORT}, 6112/tcp, bots ${BOT_PORT_RANGE}/tcp)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
if [[ "${SSH_PORT}" != "22" ]]; then
    ufw allow "${SSH_PORT}/tcp" comment 'SSH alternativo'
fi
ufw allow 6112/tcp comment 'PvPGN bnetd'
# 6200/tcp: w3route de PvPGN. address_translation.conf lo anuncia a los
# clientes para las partidas PG/AT; anunciarlo con el puerto cerrado hace
# que fallen igual que sin la regla, pero mas dificil de diagnosticar.
ufw allow 6200/tcp comment 'PvPGN w3route'
ufw allow "${BOT_PORT_RANGE}/tcp" comment 'hostbots Aura'
# 6112/udp: los clientes W3 hacen un test UDP contra el server; sin esto
# funciona igual pero con latencia de deteccion. Lo abrimos por las dudas.
ufw allow 6112/udp comment 'PvPGN udptest'
ufw --force enable

# --- fail2ban ----------------------------------------------------------------
log "activando fail2ban (jail sshd por defecto)"
systemctl enable --now fail2ban

# --- Swap si hay menos de 2 GB de RAM ---------------------------------------
mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if [[ "${mem_kb}" -lt 2000000 && ! -f /swapfile ]]; then
    log "menos de 2 GB de RAM: creando swap de 2 GB"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- Usuario de sistema wc3 y arbol /opt/wc3 ---------------------------------
if ! id wc3 &>/dev/null; then
    log "creando usuario de sistema wc3 (sin shell de login)"
    useradd --system --home-dir /opt/wc3 --shell /usr/sbin/nologin wc3
fi
log "creando arbol /opt/wc3"
install -d -o wc3 -g wc3 /opt/wc3 /opt/wc3/maps /opt/wc3/logs /opt/wc3/backups
# mpq: los archivos del juego los aporta el operador; read-only para wc3
install -d -o root -g wc3 -m 750 /opt/wc3/mpq

log "bootstrap OK. Proximo paso: install/10-build-pvpgn.sh"
