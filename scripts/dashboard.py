#!/usr/bin/env python3
"""dashboard.py — panel de admin permanente del servidor, por el navegador.

Que muestra (y se actualiza solo, sin recargar la pagina)
---------------------------------------------------------
- Estado de los servicios (PvPGN y cada bot), con los ultimos renglones del
  journal y QUIENES estan adentro de cada lobby/partida (parseado del log
  del bot).
- Cuanta gente hay conectada al chat y en lobbies (conexiones TCP por puerto).
- El chat del canal en vivo: el dashboard se loguea al PvPGN con su propia
  cuenta (protocolo chat/telnet de bnetd) y deja leer y escribir.
- Mapas instalados, backups (con alerta si el ultimo es viejo), disco y RAM.
- Zona para subir mapas arrastrando el .w3x, y BOTONES para las acciones
  comunes: instalar los mapas subidos, backup ya, reiniciar PvPGN o un bot.

Como ejecuta acciones sin ser root (privilegios separados)
----------------------------------------------------------
El dashboard corre como wc3 con NoNewPrivileges (no puede ni sudo). Las
acciones se piden por archivo: escribe un pedido en /opt/wc3/dashboard/spool
y un servicio systemd de root (wc3-dashboard-acciones.path + .service, ver
install/60-setup-dashboard.sh) lo procesa contra una lista BLANCA de
comandos fijos y deja el resultado en /opt/wc3/dashboard/resultados. Si
comprometen la pagina, lo maximo que pueden pedir es exactamente eso: nada
de comandos arbitrarios.

Seguridad, sin vueltas
----------------------
- La autenticacion es HTTP Basic (usuario "admin"). Con WC3_DASH_BIND en
  127.0.0.1 se usa adentro de un tunel SSH y no queda expuesta a Internet.
  En 0.0.0.0 viaja por HTTP plano y hace falta HTTPS delante.
- Los POST exigen ademas mismo-origen (Origin/Sec-Fetch-Site) para que otra
  pagina no pueda disparar acciones con la sesion del navegador.
- Subida de mapas con las defensas de upload-maps.py + cuota total.
- A proposito NO hay terminal: una shell de root sobre HTTP plano seria
  regalar el servidor. Para eso esta SSH.

Configuracion por variables de entorno (systemd las carga de
/opt/wc3/dashboard.env, que arma el instalador desde el .env del repo):
  WC3_DASH_PASSWORD       obligatoria
  WC3_DASH_PORT           default 8322
  WC3_DASH_BIND           interfaz (default 0.0.0.0; usar 127.0.0.1 con tunel SSH)
  WC3_DASH_CHAT_USER      cuenta PvPGN del panel (default: panel)
  WC3_DASH_CHAT_PASSWORD  su contraseña (el instalador usa WC3_BOT_PASSWORD
                          si no se define otra)
  WC3_BOT_CHANNEL         canal a mirar (default: W3)
  WC3_REALM_NAME          para el titulo
  WC3_MAX_MAP_MB          techo por mapa (default 8)
"""

import html
import hmac
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from base64 import b64decode
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

MAPS_DIR = Path("/opt/wc3/maps")
INCOMING_DIR = Path("/opt/wc3/incoming")
BACKUPS_DIR = Path("/opt/wc3/backups")
INSTANCES_DIR = Path("/opt/wc3/hostbot/instances")
SPOOL_DIR = Path("/opt/wc3/dashboard/spool")
RESULTADOS_DIR = Path("/opt/wc3/dashboard/resultados")
GUIAS_DIR = Path("/opt/wc3/dashboard/guias")

PVPGN_HOST = "127.0.0.1"
PVPGN_PORT = 6112
MAX_MAP_BYTES = int(os.environ.get("WC3_MAX_MAP_MB", "8")) * 1024 * 1024
# Cuota total de incoming: aunque cada mapa respete el techo, subir sin
# limite llenaria el disco del VPS (y PvPGN corre en la misma maquina).
MAX_INCOMING_TOTAL = 512 * 1024 * 1024
NOMBRE_MAPA_RE = re.compile(r"^[\w \-\.\(\)\[\]'!,&]+\.(w3x|w3m)$", re.IGNORECASE)

# Acciones permitidas: tienen que coincidir con la lista blanca de
# dashboard-acciones.sh (el que ejecuta es ese script, como root).
ACCIONES = {
    "instalar-mapas", "backup", "reparar-caidos",
    "reiniciar-pvpgn", "reiniciar-bot",
}


# ---------------------------------------------------------------------------
# Datos del sistema (todo lectura, sin privilegios)
# ---------------------------------------------------------------------------

def unidad_activa(unidad: str) -> str:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", unidad],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "desconocido"
    except (OSError, subprocess.TimeoutExpired):
        return "desconocido"


def journal_de(unidad: str, lineas: int = 10) -> str:
    """Ultimos renglones del journal (wc3 esta en el grupo systemd-journal)."""
    try:
        out = subprocess.run(
            ["journalctl", "-u", unidad, "-n", str(lineas), "--no-pager",
             "-o", "short", "--no-hostname"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "(sin lineas en el journal)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(no pude leer el journal: {exc})"


JOIN_RE = re.compile(r"player \[([^\]|]+)[|\]].*joined", re.IGNORECASE)
LEAVE_RE = re.compile(r"deleting player \[([^\]|]+)", re.IGNORECASE)
RESET_RE = re.compile(r"creating game|autohost", re.IGNORECASE)


def jugadores_de(unidad: str) -> list:
    """Quienes estan en el lobby/partida de un bot, parseado de su journal.

    Aura loguea "player [Nombre|IP] joined ..." al entrar y "deleting player
    [Nombre] ..." al salir; cada vez que el autohost recrea el lobby
    ("creating game") se arranca de cero. Es una reconstruccion del log, no
    una consulta al bot (Aura no tiene API): si el bot se reinicio hace mucho
    y el journal roto, puede quedarse corto — para eso el desplegable muestra
    tambien el log crudo.
    """
    try:
        out = subprocess.run(
            ["journalctl", "-u", unidad, "-n", "400", "--no-pager",
             "-o", "cat"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    adentro: "dict[str, None]" = {}  # dict como set ordenado
    for linea in out.splitlines():
        if RESET_RE.search(linea) and "joined" not in linea:
            adentro.clear()
            continue
        m = JOIN_RE.search(linea)
        if m:
            adentro[m.group(1).strip()] = None
            continue
        m = LEAVE_RE.search(linea)
        if m:
            adentro.pop(m.group(1).strip(), None)
    return list(adentro)


def conexiones_por_puerto() -> dict:
    """Conexiones TCP ESTABLECIDAS por puerto local, de /proc/net/tcp."""
    conteo = {}
    for archivo in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lineas = Path(archivo).read_text().splitlines()[1:]
        except OSError:
            continue
        for linea in lineas:
            campos = linea.split()
            if len(campos) < 4 or campos[3] != "01":  # 01 = ESTABLISHED
                continue
            try:
                puerto = int(campos[1].rsplit(":", 1)[1], 16)
            except (ValueError, IndexError):
                continue
            conteo[puerto] = conteo.get(puerto, 0) + 1
    return conteo


def leer_cfg(ruta: Path) -> dict:
    datos = {}
    try:
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            datos[clave.strip()] = valor.strip()
    except OSError:
        pass
    return datos


def instancias() -> list:
    resultado = []
    conexiones = conexiones_por_puerto()
    if INSTANCES_DIR.is_dir():
        for d in sorted(INSTANCES_DIR.iterdir(),
                        key=lambda p: int(p.name) if p.name.isdigit() else 999):
            if not d.name.isdigit():
                continue
            cfg = leer_cfg(d / "aura.cfg")
            puerto = int(cfg.get("bot_hostport") or 0)
            unidad = f"wc3-hostbot@{d.name}"
            cuenta = cfg.get("bnet_username") or f"hostbot{d.name}"
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", cuenta):
                cuenta = f"hostbot{d.name}"
            resultado.append({
                "n": d.name,
                "unidad": unidad,
                "estado": unidad_activa(unidad),
                "nombre": cfg.get("bot_autohostname") or cfg.get("bot_defaultmap") or "?",
                "puerto": puerto,
                "jugadores": conexiones.get(puerto, 0),
                "cuenta": cuenta,
            })
    return resultado


def cuenta_de_bot(numero: str) -> str:
    """Cuenta PvPGN de una instancia, sin aceptar rutas ni texto arbitrario."""
    if not re.fullmatch(r"[0-9]{1,2}", numero or ""):
        return ""
    ruta = INSTANCES_DIR / numero / "aura.cfg"
    if not ruta.is_file():
        return ""
    cuenta = leer_cfg(ruta).get("bnet_username") or f"hostbot{numero}"
    return cuenta if re.fullmatch(r"[A-Za-z0-9_-]{1,32}", cuenta) else ""


def lista_archivos(directorio: Path, patrones=(".w3x", ".w3m")) -> list:
    out = []
    if directorio.is_dir():
        for p in sorted(directorio.iterdir()):
            if p.is_file() and p.suffix.lower() in patrones:
                out.append((p.name, p.stat().st_size, p.stat().st_mtime))
    return out


def backups() -> list:
    out = []
    if BACKUPS_DIR.is_dir():
        for p in BACKUPS_DIR.glob("wc3-backup-*.tar.gz"):
            out.append((p.name, p.stat().st_size, p.stat().st_mtime))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def salud() -> dict:
    disco = shutil.disk_usage("/")
    mem_total = mem_disp = 0
    try:
        for linea in Path("/proc/meminfo").read_text().splitlines():
            if linea.startswith("MemTotal:"):
                mem_total = int(linea.split()[1]) * 1024
            elif linea.startswith("MemAvailable:"):
                mem_disp = int(linea.split()[1]) * 1024
    except OSError:
        pass
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except OSError:
        uptime = 0.0
    return {"disco_libre": disco.free, "disco_total": disco.total,
            "mem_total": mem_total, "mem_disp": mem_disp, "uptime": uptime}


# ---------------------------------------------------------------------------
# Cliente de chat: el protocolo chat/telnet de bnetd (PvPGN)
# ---------------------------------------------------------------------------

class ClienteChat:
    """Conexion persistente al canal, como una cuenta comun de PvPGN.

    bnetd acepta clientes "chat" crudos: se abre un TCP al 6112, se manda el
    byte 0x03, y el server pide Username/Password en texto plano. Despues
    habla en lineas "CODIGO PALABRA args": 1001 USER (presentes al entrar),
    1002 JOIN, 1003 LEAVE, 1005 TALK, 1018 INFO, 1019 ERROR. Escribir es
    mandar la linea; los /comandos de bnetd tambien valen.

    La cuenta tiene que existir (se crea una vez desde el cliente del juego,
    igual que las de los bots). Si el login falla, el estado lo cuenta en la
    pagina en vez de reventar.
    """

    def __init__(self):
        self.usuario = os.environ.get("WC3_DASH_CHAT_USER", "panel")
        self.clave = os.environ.get("WC3_DASH_CHAT_PASSWORD", "")
        self.canal = os.environ.get("WC3_BOT_CHANNEL", "W3")
        self.estado = "arrancando"
        self.presentes: "dict[str, None]" = {}
        self.mensajes: deque = deque(maxlen=200)
        self._contador = 0
        self._sock = None
        self._lock = threading.Lock()

    # -- registro de mensajes -------------------------------------------------
    def _anotar(self, tipo: str, autor: str, texto: str):
        with self._lock:
            self._contador += 1
            self.mensajes.append({
                "id": self._contador, "hora": time.strftime("%H:%M"),
                "tipo": tipo, "autor": autor, "texto": texto,
            })

    def desde(self, ultimo_id: int) -> list:
        with self._lock:
            return [m for m in self.mensajes if m["id"] > ultimo_id]

    # -- envio ----------------------------------------------------------------
    def enviar(self, texto: str) -> bool:
        sock = self._sock
        if not sock or not self.estado.startswith("conectado"):
            return False
        try:
            sock.sendall(texto.encode("utf-8", "replace") + b"\r\n")
        except OSError:
            return False
        if not texto.startswith("/"):
            # bnetd no te devuelve tu propio TALK: se anota localmente
            self._anotar("talk", self.usuario, texto)
        return True

    # -- loop -----------------------------------------------------------------
    def correr(self):
        """Bucle eterno: conectar, escuchar, reconectar. Va en un hilo daemon."""
        if not self.clave:
            self.estado = "sin configurar (falta WC3_DASH_CHAT_PASSWORD)"
            return
        while True:
            try:
                self._sesion()
            except OSError as exc:
                self.estado = f"desconectado ({exc})"
            self.presentes.clear()
            time.sleep(15)

    def _sesion(self):
        self.estado = "conectando..."
        sock = socket.create_connection((PVPGN_HOST, PVPGN_PORT), timeout=10)
        sock.settimeout(300)
        try:
            sock.sendall(b"\x03")
            f = sock.makefile("rb")
            # Los prompts "Username:"/"Password:" vienen sin fin de linea:
            # se responde directo, y las lineas de verdad arrancan despues.
            sock.sendall(self.usuario.encode() + b"\r\n")
            time.sleep(0.3)
            sock.sendall(self.clave.encode() + b"\r\n")
            self._sock = sock
            logueado = False
            for cruda in f:
                linea = cruda.decode("utf-8", "replace").strip()
                if not linea:
                    continue
                # bnetd exige el permiso "botlogin" para conexiones chat
                # (default false): la cuenta puede existir y aun asi rebotar.
                # sudo make dashboard lo otorga solo (UPDATE en la base).
                if not logueado and "no bot access" in linea.lower():
                    self.estado = (f"la cuenta '{self.usuario}' existe pero le falta "
                                   "el permiso de bot: corre sudo make dashboard "
                                   "de nuevo (lo otorga solo) y reinicia PvPGN")
                    return
                if not logueado and ("failed" in linea.lower()
                                     or "incorrect" in linea.lower()):
                    self.estado = (f"login rechazado para '{self.usuario}': crear la "
                                   "cuenta desde el juego (New Account) con la "
                                   "contraseña del panel, y despues correr "
                                   "sudo make dashboard (otorga el permiso de bot)")
                    return
                partes = linea.split(" ", 2)
                if len(partes) < 2 or not partes[0].isdigit():
                    continue
                codigo, resto = partes[0], partes[1:]
                if not logueado and codigo in ("2010", "1007", "1001"):
                    logueado = True
                    self.estado = f"conectado como {self.usuario} en {self.canal}"
                    sock.sendall(f"/join {self.canal}".encode() + b"\r\n")
                self._procesar(codigo, resto)
            self.estado = "desconectado (el server corto)"
        finally:
            self._sock = None
            try:
                sock.close()
            except OSError:
                pass

    def _procesar(self, codigo: str, resto: list):
        palabra = resto[0] if resto else ""
        args = resto[1] if len(resto) > 1 else ""

        def nombre():
            return args.split(" ", 1)[0] if args else "?"

        def comillas():
            m = re.search(r'"(.*)"\s*$', args)
            return m.group(1) if m else args

        if codigo == "1001" and palabra == "USER":
            self.presentes[nombre()] = None
        elif codigo == "1002" and palabra == "JOIN":
            self.presentes[nombre()] = None
            self._anotar("evento", "", f"{nombre()} entro al canal")
        elif codigo == "1003" and palabra == "LEAVE":
            self.presentes.pop(nombre(), None)
            self._anotar("evento", "", f"{nombre()} salio del canal")
        elif codigo == "1005" and palabra == "TALK":
            self._anotar("talk", nombre(), comillas())
        elif codigo == "1004" and palabra == "WHISPER":
            self._anotar("whisper", nombre(), comillas())
        elif codigo == "1006" and palabra == "BROADCAST":
            self._anotar("info", "", comillas())
        elif codigo == "1007" and palabra == "CHANNEL":
            self.presentes.clear()
            self._anotar("evento", "", f"canal: {comillas()}")
        elif codigo in ("1018", "1019"):
            self._anotar("info" if codigo == "1018" else "error", "", comillas())


CHAT = ClienteChat()


# ---------------------------------------------------------------------------
# Acciones via spool (las ejecuta el servicio de root, lista blanca)
# ---------------------------------------------------------------------------

def pedir_accion(accion: str, arg: str = "") -> str:
    """Deja el pedido en el spool y devuelve su id. El companero de root
    (dashboard-acciones.sh, disparado por systemd .path) lo procesa."""
    pedido_id = f"{int(time.time())}-{os.urandom(4).hex()}"
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SPOOL_DIR / f".{pedido_id}.tmp"
    tmp.write_text(f"{accion}\n{arg}\n", encoding="utf-8")
    tmp.replace(SPOOL_DIR / f"{pedido_id}.pedido")
    return pedido_id


def resultado_accion(pedido_id: str) -> dict:
    if not re.fullmatch(r"[0-9]+-[0-9a-f]+", pedido_id or ""):
        return {"listo": True, "ok": False, "salida": "id invalido"}
    ruta = RESULTADOS_DIR / f"{pedido_id}.resultado"
    if not ruta.is_file():
        return {"listo": False}
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"listo": True, "ok": False, "salida": f"no pude leer el resultado: {exc}"}
    codigo, _, salida = contenido.partition("\n")
    return {"listo": True, "ok": codigo.strip() == "0", "salida": salida.strip()}


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB" if n < 1024 ** 3 else f"{n / (1024 ** 3):.1f} GB"


def hace(ts: float) -> str:
    seg = int(time.time() - ts)
    if seg < 3600:
        return f"hace {seg // 60} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    return f"hace {seg // 86400} dia(s)"


def punto(estado: str) -> str:
    color = {"active": "#3d9950", "failed": "#c0392b"}.get(estado, "#b58a1f")
    return (f'<span style="color:{color}" title="{html.escape(estado)}">&#9679;</span> '
            f"{html.escape(estado)}")


def parcial() -> str:
    """Todo lo que cambia solo. El JS lo pide cada 10 s y lo reemplaza."""
    s = salud()
    conexiones = conexiones_por_puerto()
    bots = instancias()
    en_lobbies = sum(b["jugadores"] for b in bots)
    bots_activos = sum(1 for b in bots if b["estado"] == "active")
    en_chat = max(0, conexiones.get(PVPGN_PORT, 0) - bots_activos
                  - (1 if CHAT.estado.startswith("conectado") else 0))
    pvpgn_estado = unidad_activa("pvpgn")

    filas_bots = []
    for b in bots:
        gente = jugadores_de(b["unidad"]) if b["jugadores"] else []
        detalle_gente = (
            "<br>".join(html.escape(g) for g in gente)
            if gente else
            "(nadie adentro, o el log no alcanza para reconstruirlo)"
        )
        filas_bots.append(f"""
    <tr><td>{b['n']}</td>
      <td><details><summary>{html.escape(b['nombre'])}</summary>
        <p><strong>Adentro ({b['jugadores']} conexion/es):</strong><br>{detalle_gente}</p>
        <pre>{html.escape(journal_de(b['unidad'], 12))}</pre>
      </details></td>
      <td>{punto(b['estado'])}</td><td>{b['puerto'] or '?'}</td>
      <td style='text-align:right'>{b['jugadores']}</td>
      <td class="acciones-bot">
        <button class="primario" onclick="iniciarBot('{b['n']}',this)">iniciar</button>
        <button onclick="copiar('/w {b['cuenta']} !start')">copiar !start</button>
        <button onclick="accion('reiniciar-bot','{b['n']}',this)">reiniciar</button>
      </td>
    </tr>""")
    tabla_bots = "".join(filas_bots) or \
        "<tr><td colspan=6>(no hay instancias en /opt/wc3/hostbot/instances)</td></tr>"

    mapas = lista_archivos(MAPS_DIR)
    filas_mapas = "".join(
        f"<tr><td>{html.escape(n)}</td><td style='text-align:right'>{mb(t)}</td></tr>"
        for n, t, _ in mapas
    ) or "<tr><td colspan=2>(sin mapas en /opt/wc3/maps)</td></tr>"

    instalados = {n for n, _, _ in mapas}
    pendientes = lista_archivos(INCOMING_DIR)
    seccion_pendientes = ""
    if pendientes:
        filas = "".join(
            f"<li>{html.escape(n)} ({mb(t)})"
            + (" — ya hay uno instalado con este nombre" if n in instalados else "")
            + "</li>"
            for n, t, _ in pendientes
        )
        seccion_pendientes = f"""
  <h2>Mapas subidos, esperando instalarse ({len(pendientes)})</h2>
  <ul>{filas}</ul>
  <p><button onclick="accion('instalar-mapas','',this)">Instalar ahora</button>
  &nbsp;les mete la preview, los deja en la carpeta del bot y archiva los
  originales. Si un mapa REEMPLAZA uno que ya se hostea, despues tocá
  "reiniciar" en su bot. Si es NUEVO, falta darle bot por SSH:
  <code>./scripts/make-instances.py --maps-dir /opt/wc3/maps</code></p>"""

    bks = backups()
    if bks:
        aviso_bk = ""
        if time.time() - bks[0][2] > 8 * 86400:
            aviso_bk = (' <strong style="color:#c0392b">&#9888; el ultimo backup tiene '
                        "mas de 8 dias</strong>")
        filas_bk = "".join(
            f"<tr><td>{html.escape(n)}</td><td>{hace(m)}</td>"
            f"<td style='text-align:right'>{mb(t)}</td></tr>"
            for n, t, m in bks[:5]
        )
        seccion_backups = f"<table>{filas_bk}</table><p>{len(bks)} en total.{aviso_bk}</p>"
    else:
        seccion_backups = ('<p><strong style="color:#c0392b">No hay ningun '
                           "backup.</strong></p>")

    journal_pvpgn = html.escape(journal_de("pvpgn", 12))
    todo_listo = pvpgn_estado == "active" and bool(bots) and bots_activos == len(bots)
    clase_general = "ok" if todo_listo else "alerta"
    texto_general = "Todo listo para jugar" if todo_listo else "Hay servicios que necesitan atencion"
    ultimo_backup = hace(bks[0][2]) if bks else "todavia no hay"

    return f"""
  <div class="estado-general {clase_general}">
    <div><strong>{texto_general}</strong><br>
      <small>{bots_activos}/{len(bots)} bots + PvPGN; ultimo backup: {ultimo_backup}</small></div>
    <button onclick="accion('reparar-caidos','',this)">Reparar caidos</button>
  </div>

  <div class="tiles">
    <div class="tile"><b>{en_chat}</b> conectados al chat</div>
    <div class="tile"><b>{en_lobbies}</b> en lobbies/partidas</div>
    <div class="tile"><b>{punto(pvpgn_estado)}</b> PvPGN
      <button onclick="accion('reiniciar-pvpgn','',this)">reiniciar</button></div>
    <div class="tile"><b>{bots_activos}/{len(bots)}</b> bots activos</div>
  </div>

  <p>
    <button onclick="accion('instalar-mapas','',this)">
      Instalar mapas subidos ({len(lista_archivos(INCOMING_DIR))})</button>
    &nbsp;<button onclick="accion('backup','',this)">Hacer backup ahora</button>
    &nbsp;<small style="color:#9c9c90">los "reiniciar" estan al lado de PvPGN
    (arriba) y de cada bot (tabla de abajo)</small>
  </p>

  <h2>Bots (uno por mapa) <small>— tocá el nombre para ver quien esta adentro
    y su log</small></h2>
  <table><tr><th>#</th><th>Lobby</th><th>Estado</th><th>Puerto</th>
  <th style="text-align:right">Jugadores</th><th></th></tr>{tabla_bots}</table>

  {seccion_pendientes}

  <h2>Mapas instalados ({len(mapas)})</h2>
  <table>{filas_mapas}</table>

  <h2>Backups
    <button onclick="accion('backup','',this)">hacer backup ahora</button></h2>
  {seccion_backups}

  <h2>Salud del VPS</h2>
  <div class="tiles">
    <div class="tile"><b>{mb(s['disco_libre'])}</b> disco libre de {mb(s['disco_total'])}</div>
    <div class="tile"><b>{mb(s['mem_disp'])}</b> RAM libre de {mb(s['mem_total'])}</div>
    <div class="tile"><b>{s['uptime'] / 86400:.1f} dias</b> prendido</div>
  </div>

  <h2>PvPGN — ultimas lineas</h2>
  <details><summary>journal de pvpgn</summary><pre>{journal_pvpgn}</pre></details>
"""


def pagina() -> str:
    realm = html.escape(os.environ.get("WC3_REALM_NAME", "WC3"))
    canal = html.escape(CHAT.canal)
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{realm} — dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto;
         padding: 0 1rem; background: #16181c; color: #e5e1d5; }}
  h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem;
         border-bottom: 1px solid #34373d; padding-bottom: .3rem; color: #d2ad5c; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ padding: .3rem .6rem; border-bottom: 1px solid #26292f; text-align: left; }}
  pre {{ background: #1f2227; padding: .6rem; overflow-x: auto; font-size: .82rem;
        white-space: pre-wrap; }}
  code {{ background: #1f2227; padding: .1rem .3rem; }}
  button {{ background: #2a2d33; color: #e5e1d5; border: 1px solid #4a4d55;
           border-radius: 4px; padding: .25rem .7rem; cursor: pointer; }}
  button:hover {{ border-color: #d2ad5c; }}
  button.primario {{ background: #80611f; border-color: #d2ad5c; font-weight: 700; }}
  .estado-general {{ display:flex; justify-content:space-between; align-items:center;
    gap:1rem; border-radius:8px; padding:.85rem 1rem; margin:1rem 0; }}
  .estado-general.ok {{ background:#17351f; border:1px solid #3d9950; }}
  .estado-general.alerta {{ background:#3b2716; border:1px solid #b58a1f; }}
  .estado-general strong {{ font-size:1.15rem; }}
  .guia {{ background:#1f2227; border-left:4px solid #d2ad5c; border-radius:6px;
    padding:.75rem 1rem; margin:1rem 0; }}
  .guia ol {{ margin:.4rem 0 .2rem 1.2rem; padding:0; }}
  .acciones-bot {{ white-space:nowrap; }}
  .acciones-bot button {{ margin:.1rem; }}
  .tiles {{ display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }}
  .tile {{ background: #1f2227; border-radius: 6px; padding: .7rem 1rem; min-width: 8rem; }}
  .tile b {{ display: block; font-size: 1.3rem; }}
  #zona {{ border: 2px dashed #4a4d55; border-radius: 8px; padding: 1.2rem;
          text-align: center; margin: 1rem 0; }}
  #zona.activa {{ border-color: #d2ad5c; background: #26292f; }}
  details summary {{ cursor: pointer; padding: .2rem 0; }}
  #chatlog {{ background: #1f2227; height: 16rem; overflow-y: auto; padding: .6rem;
             font-size: .9rem; border-radius: 6px 6px 0 0; }}
  #chatlog .evento {{ color: #9c9c90; }} #chatlog .error {{ color: #e08477; }}
  #chatlog .info {{ color: #8fb0c4; }} #chatlog .autor {{ color: #d2ad5c; }}
  #chatlog .hora {{ color: #6b6d75; font-size: .8rem; }}
  #chatform {{ display: flex; }}
  #chatform input {{ flex: 1; background: #26292f; color: #e5e1d5;
    border: 1px solid #4a4d55; border-radius: 0 0 0 6px; padding: .45rem; }}
  #avisos p {{ background: #26292f; border-left: 3px solid #d2ad5c;
              padding: .4rem .8rem; }}
</style></head><body>
  <h1>{realm} — dashboard <small style="color:#9c9c90;font-size:.8rem">
    en vivo, se actualiza solo</small></h1>

  <div id="avisos"></div>

  <div class="guia">
    <strong>Para mandar una partida</strong>
    <ol>
      <li>Entrá al lobby desde Warcraft y esperá unos 5 segundos.</li>
      <li>Escribí <code>!start</code> en el lobby, o tocá <b>iniciar</b> en el bot de abajo.</li>
      <li>Si el comando del juego no responde: <code>/w hostbotN sc</code> y después <code>!start</code>.</li>
    </ol>
    <p><a href="/guia/foc" target="_blank" rel="noopener"><strong>Abrir guía FOC en español:</strong>
      objetos, builds y habilidades</a></p>
  </div>

  <h2>Chat del canal {canal} <small id="chatestado" style="color:#9c9c90"></small></h2>
  <div id="chatlog"></div>
  <form id="chatform">
    <input id="chatmsg" autocomplete="off"
      placeholder="Escribir al canal (los /comandos de PvPGN tambien valen)">
    <button type="submit">Enviar</button>
  </form>
  <p style="color:#9c9c90;font-size:.85rem">En el canal ahora:
    <span id="presentes">...</span></p>

  <h2>Subir un mapa</h2>
  <div id="zona">Arrastra un .w3x aca (o toca para elegirlo).<br>
    <small>Techo: {MAX_MAP_BYTES // (1024 * 1024)} MiB. Despues aparece el boton
    de instalar.</small>
    <input type="file" id="selector" accept=".w3x,.w3m" multiple hidden>
    <div id="resultado"></div>
  </div>

  <div id="dinamico">{parcial()}</div>

<script>
// ---- refresco en vivo -------------------------------------------------------
const dinamico = document.getElementById('dinamico');
async function refrescar() {{
  try {{
    const r = await fetch('parcial');
    if (r.ok) {{
      // conservar que desplegables estaban abiertos
      const abiertos = new Set([...dinamico.querySelectorAll('details[open]')]
        .map(d => d.querySelector('summary')?.textContent));
      dinamico.innerHTML = await r.text();
      dinamico.querySelectorAll('details').forEach(d => {{
        if (abiertos.has(d.querySelector('summary')?.textContent)) d.open = true;
      }});
    }}
  }} catch (e) {{ /* sin red un ratito: se reintenta solo */ }}
}}
setInterval(refrescar, 10000);

// ---- chat -------------------------------------------------------------------
const chatlog = document.getElementById('chatlog');
let ultimoId = 0;
function lineaChat(m) {{
  const div = document.createElement('div');
  div.className = m.tipo;
  const autor = m.autor ? `<span class="autor">${{esc(m.autor)}}:</span> ` : '';
  div.innerHTML = `<span class="hora">${{m.hora}}</span> ${{autor}}${{esc(m.texto)}}`;
  return div;
}}
function esc(s) {{
  return s.replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
}}
async function pollChat() {{
  try {{
    const r = await fetch('chat?desde=' + ultimoId);
    if (!r.ok) return;
    const datos = await r.json();
    document.getElementById('chatestado').textContent = '— ' + datos.estado;
    document.getElementById('presentes').textContent =
      datos.presentes.length ? datos.presentes.join(', ') : '(nadie)';
    if (datos.mensajes.length) {{
      const abajo = chatlog.scrollTop + chatlog.clientHeight >= chatlog.scrollHeight - 30;
      for (const m of datos.mensajes) {{ chatlog.appendChild(lineaChat(m)); ultimoId = m.id; }}
      while (chatlog.children.length > 300) chatlog.removeChild(chatlog.firstChild);
      if (abajo) chatlog.scrollTop = chatlog.scrollHeight;
    }}
  }} catch (e) {{}}
}}
setInterval(pollChat, 3000); pollChat();

document.getElementById('chatform').addEventListener('submit', async e => {{
  e.preventDefault();
  const input = document.getElementById('chatmsg');
  const texto = input.value.trim();
  if (!texto) return;
  const r = await fetch('chat', {{ method: 'POST', body: texto }});
  if (r.ok) {{ input.value = ''; pollChat(); }}
  else aviso('No se pudo enviar: ' + await r.text());
}});

// ---- acciones -----------------------------------------------------------------
function aviso(texto) {{
  const p = document.createElement('p');
  p.textContent = texto;
  document.getElementById('avisos').appendChild(p);
  setTimeout(() => p.remove(), 60000);
}}
async function accion(nombre, arg, boton) {{
  const etiquetas = {{
    'instalar-mapas': 'instalar los mapas subidos',
    'backup': 'hacer un backup ahora',
    'reparar-caidos': 'levantar solamente los servicios que estan caidos',
    'reiniciar-pvpgn': 'REINICIAR PvPGN (corta el chat a todos unos segundos)',
    'reiniciar-bot': 'reiniciar el bot ' + arg + ' (si hay partida en curso, se cae)',
  }};
  if (!confirm('¿Seguro que queres ' + (etiquetas[nombre] || nombre) + '?')) return;
  if (boton) boton.disabled = true;
  aviso('Pedido: ' + (etiquetas[nombre] || nombre) + '... (puede tardar un momento)');
  try {{
    const r = await fetch('accion/' + nombre, {{ method: 'POST', body: arg }});
    if (!r.ok) {{ aviso('Error: ' + await r.text()); return; }}
    const id = (await r.json()).id;
    for (let i = 0; i < 60; i++) {{
      await new Promise(res => setTimeout(res, 2000));
      const e = await (await fetch('accion/resultado?id=' + id)).json();
      if (e.listo) {{
        aviso((e.ok ? 'Listo: ' : 'FALLO: ') + (e.salida || '(sin salida)'));
        refrescar();
        return;
      }}
    }}
    aviso('El pedido sigue corriendo; mira la seccion de nuevo en un rato.');
  }} finally {{ if (boton) boton.disabled = false; }}
}}

async function iniciarBot(numero, boton) {{
  if (!confirm('¿Iniciar ahora la partida del bot ' + numero + '?')) return;
  if (boton) boton.disabled = true;
  try {{
    const r = await fetch('bot/iniciar', {{ method: 'POST', body: numero }});
    const salida = await r.text();
    aviso(r.ok ? salida : 'No se pudo iniciar: ' + salida);
  }} finally {{ if (boton) boton.disabled = false; }}
}}

async function copiar(texto) {{
  try {{
    await navigator.clipboard.writeText(texto);
  }} catch (_) {{
    const t = document.createElement('textarea');
    t.value = texto; document.body.appendChild(t); t.select();
    document.execCommand('copy'); t.remove();
  }}
  aviso('Copiado: ' + texto);
}}

// ---- subida -------------------------------------------------------------------
const zona = document.getElementById('zona');
const selector = document.getElementById('selector');
const resultado = document.getElementById('resultado');
zona.addEventListener('click', e => {{ if (e.target === zona) selector.click(); }});
zona.addEventListener('dragover', e => {{ e.preventDefault(); zona.classList.add('activa'); }});
zona.addEventListener('dragleave', () => zona.classList.remove('activa'));
zona.addEventListener('drop', e => {{
  e.preventDefault(); zona.classList.remove('activa'); subirTodos(e.dataTransfer.files);
}});
selector.addEventListener('change', () => subirTodos(selector.files));
async function subirTodos(archivos) {{
  for (const a of archivos) await subir(a);
  refrescar();
}}
async function subir(archivo) {{
  const p = document.createElement('p');
  p.textContent = 'Subiendo ' + archivo.name + '...';
  resultado.appendChild(p);
  try {{
    const r = await fetch('subir/' + encodeURIComponent(archivo.name),
                          {{ method: 'PUT', body: archivo }});
    p.textContent = archivo.name + ': ' + await r.text();
  }} catch (err) {{
    p.textContent = archivo.name + ': fallo la subida (' + err + ')';
  }}
}}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Sin timeout, una conexion muda retiene su hilo para siempre.
    timeout = 60

    def setup(self):
        super().setup()
        self.connection.settimeout(60)

    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[dashboard] {self.address_string()} - {fmt % args}", flush=True)

    # --- auth y origen --------------------------------------------------------
    def _autorizado(self) -> bool:
        esperado = os.environ.get("WC3_DASH_PASSWORD", "")
        cabecera = self.headers.get("Authorization", "")
        if esperado and cabecera.startswith("Basic "):
            try:
                credenciales = b64decode(cabecera[6:]).decode("utf-8", "replace")
            except Exception:
                credenciales = ""
            _, _, clave = credenciales.partition(":")
            if hmac.compare_digest(clave, esperado):
                return True
        # Cerrar la conexion: si era un PUT/POST, el cuerpo quedo sin leer y
        # el keep-alive dejaria la proxima request desalineada.
        self.close_connection = True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="wc3 dashboard"')
        self._cuerpo(b"Hace falta la contrasena del dashboard.\n")
        return False

    def _mismo_origen(self) -> bool:
        """Anti-CSRF para POST/PUT: el navegador guarda la contraseña Basic,
        asi que otra pagina podria disparar pedidos con ella. Los browsers
        modernos mandan Sec-Fetch-Site y/u Origin: se exige que digan que el
        pedido nace en esta misma pagina."""
        sfs = self.headers.get("Sec-Fetch-Site")
        if sfs is not None:
            return sfs in ("same-origin", "none")
        origin = self.headers.get("Origin")
        if origin:
            return origin.split("//", 1)[-1] == self.headers.get("Host", "")
        return True  # clientes sin esas cabeceras (curl, tests)

    def _cuerpo(self, datos: bytes, tipo: str = "text/plain; charset=utf-8"):
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _json(self, obj, codigo: int = 200):
        self.send_response(codigo)
        self._cuerpo(json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _leer_cuerpo(self, maximo: int = 4096) -> str:
        try:
            largo = min(int(self.headers.get("Content-Length", "0")), maximo)
        except ValueError:
            largo = 0
        return self.rfile.read(largo).decode("utf-8", "replace") if largo > 0 else ""

    # --- rutas -----------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._autorizado():
            return
        url = urlparse(self.path)
        if url.path in ("/", ""):
            self.send_response(200)
            self._cuerpo(pagina().encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/parcial":
            self.send_response(200)
            self._cuerpo(parcial().encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/guia/foc":
            guia = GUIAS_DIR / "foc-96b03-es.html"
            try:
                datos = guia.read_bytes()
            except OSError:
                self.send_response(503)
                self._cuerpo(b"La guia FOC no esta instalada. Reinstala el dashboard.\n")
                return
            self.send_response(200)
            self._cuerpo(datos, "text/html; charset=utf-8")
        elif url.path == "/chat":
            try:
                desde = int(parse_qs(url.query).get("desde", ["0"])[0])
            except ValueError:
                desde = 0
            self._json({"estado": CHAT.estado,
                        "presentes": sorted(CHAT.presentes),
                        "mensajes": CHAT.desde(desde)})
        elif url.path == "/accion/resultado":
            pedido_id = parse_qs(url.query).get("id", [""])[0]
            self._json(resultado_accion(pedido_id))
        else:
            self.send_response(404)
            self._cuerpo(b"No hay nada aca. La pagina es /\n")

    def do_POST(self):  # noqa: N802
        if not self._autorizado():
            return
        if not self._mismo_origen():
            self.close_connection = True
            self.send_response(403)
            self._cuerpo(b"pedido de otro origen: rechazado\n")
            return
        url = urlparse(self.path)
        if url.path == "/chat":
            texto = self._leer_cuerpo(512).strip()
            texto = "".join(c for c in texto if c.isprintable())[:220]
            if not texto:
                self.send_response(400)
                self._cuerpo(b"mensaje vacio\n")
            elif CHAT.enviar(texto):
                self._json({"ok": True})
            else:
                self.send_response(503)
                self._cuerpo(f"el chat no esta conectado ({CHAT.estado})\n"
                             .encode("utf-8"))
        elif url.path == "/bot/iniciar":
            numero = self._leer_cuerpo(16).strip()
            cuenta = cuenta_de_bot(numero)
            if not cuenta:
                self.send_response(400)
                self._cuerpo(b"bot invalido\n")
            elif CHAT.enviar(f"/w {cuenta} !start"):
                print(f"[dashboard] !start enviado a {cuenta}", flush=True)
                self.send_response(200)
                self._cuerpo(f"Listo: !start enviado a {cuenta}\n".encode("utf-8"))
            else:
                self.send_response(503)
                self._cuerpo(f"el chat no esta conectado ({CHAT.estado})\n"
                             .encode("utf-8"))
        elif url.path.startswith("/accion/"):
            accion = url.path[len("/accion/"):]
            arg = self._leer_cuerpo(64).strip()
            if accion not in ACCIONES:
                self.send_response(400)
                self._cuerpo(b"accion desconocida\n")
                return
            if accion == "reiniciar-bot" and not re.fullmatch(r"[0-9]{1,2}", arg):
                self.send_response(400)
                self._cuerpo(b"numero de bot invalido\n")
                return
            try:
                pedido_id = pedir_accion(accion, arg)
            except OSError as exc:
                self.send_response(500)
                self._cuerpo(f"no pude encolar el pedido: {exc}\n".encode("utf-8"))
                return
            print(f"[dashboard] accion pedida: {accion} {arg}".strip(), flush=True)
            self._json({"id": pedido_id})
        else:
            self.send_response(404)
            self._cuerpo(b"ruta desconocida\n")

    def do_PUT(self):  # noqa: N802
        if not self._autorizado():
            return
        if not self._mismo_origen():
            self.close_connection = True
            self.send_response(403)
            self._cuerpo(b"pedido de otro origen: rechazado\n")
            return
        if not self.path.startswith("/subir/"):
            self.send_response(404)
            self._cuerpo(b"ruta desconocida\n")
            return
        # basename pelado: cualquier intento de ruta se reduce al nombre
        nombre = os.path.basename(unquote(self.path[len("/subir/"):]))
        respuesta, codigo = self._recibir_mapa(nombre)
        if codigo != 200:
            # El cuerpo pudo quedar sin leer: cortar en vez de desalinear
            self.close_connection = True
        self.send_response(codigo)
        self._cuerpo(respuesta.encode("utf-8"))

    def _recibir_mapa(self, nombre: str) -> "tuple[str, int]":
        if not NOMBRE_MAPA_RE.match(nombre or ""):
            return "solo se aceptan .w3x/.w3m con nombre normal", 400
        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            largo = 0
        if largo <= 0:
            return "subida vacia", 400
        if largo > MAX_MAP_BYTES:
            return (f"pesa {largo} B y el techo es {MAX_MAP_BYTES} B "
                    "(mapas > 8 MiB: ver docs/mapas-grandes.md)"), 413

        ocupado = sum(t for _, t, _ in lista_archivos(INCOMING_DIR))
        if ocupado + largo > MAX_INCOMING_TOTAL:
            return ("la carpeta de subidas esta llena; instala o borra los "
                    "mapas pendientes primero"), 507
        if shutil.disk_usage("/").free < largo + 1024 ** 3:
            return "queda muy poco disco en el server; no lo guardo", 507

        INCOMING_DIR.mkdir(parents=True, exist_ok=True)
        # Temporal UNICO por subida (mkstemp): dos subidas simultaneas del
        # mismo nombre no se pisan entre si; gana la que termina ultima.
        fd, tmp_ruta = tempfile.mkstemp(dir=INCOMING_DIR, suffix=".parcial")
        tmp = Path(tmp_ruta)
        try:
            recibido = 0
            with os.fdopen(fd, "wb") as fh:
                while recibido < largo:
                    trozo = self.rfile.read(min(65536, largo - recibido))
                    if not trozo:
                        return "se corto la subida, proba de nuevo", 400
                    fh.write(trozo)
                    recibido += len(trozo)
            with tmp.open("rb") as fh:
                magia = fh.read(4)
            if magia != b"HM3W":
                return "eso no es un mapa de Warcraft III (probablemente renombrado)", 400
            destino = INCOMING_DIR / nombre
            tmp.replace(destino)
            print(f"[dashboard] recibido: {nombre} -> {destino} ({largo} B)", flush=True)
            return "subido OK: quedo esperando el boton de instalar", 200
        except (OSError, socket.timeout):
            return "se corto la subida, proba de nuevo", 400
        finally:
            tmp.unlink(missing_ok=True)


def main() -> int:
    if not os.environ.get("WC3_DASH_PASSWORD"):
        print("Falta WC3_DASH_PASSWORD en el entorno; sin contraseña no arranco.",
              file=sys.stderr)
        return 1
    threading.Thread(target=CHAT.correr, daemon=True).start()
    puerto = int(os.environ.get("WC3_DASH_PORT", "8322"))
    bind = os.environ.get("WC3_DASH_BIND", "0.0.0.0")
    servidor = ThreadingHTTPServer((bind, puerto), Handler)
    servidor.daemon_threads = True
    print(f"[dashboard] escuchando en {bind}:{puerto}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
