#!/usr/bin/env python3
"""dashboard.py — panel de admin permanente del servidor, por el navegador.

Que muestra
-----------
- Estado de los servicios (PvPGN y cada bot), con los ultimos renglones del
  journal de cada uno.
- Cuanta gente hay conectada: conexiones TCP establecidas al 6112 (chat) y a
  cada puerto de bot (jugadores en lobby/partida).
- Los mapas instalados, los backups (y hace cuanto fue el ultimo) y la salud
  del VPS (disco, RAM, uptime).
- Zona para subir mapas arrastrando el .w3x: quedan en /opt/wc3/incoming y la
  pagina te dice el comando que falta correr para instalarlos.

Seguridad, sin vueltas
----------------------
- Corre como el usuario wc3 (sin privilegios), instalado por
  install/60-setup-dashboard.sh como servicio systemd endurecido.
- Toda la proteccion es la contraseña (HTTP Basic, usuario "admin"). Viaja
  por HTTP plano, el mismo tradeoff asumido que el token de recibir-mapas:
  aceptable para un server de amigos, no para nada serio.
- Solo lee; lo unico que escribe son los .w3x subidos a /opt/wc3/incoming,
  con las mismas defensas que upload-maps.py (extension, magic HM3W, techo
  de tamano, basename pelado) mas una cuota total para no llenar el disco.

Configuracion por variables de entorno (systemd las carga de
/opt/wc3/dashboard.env, que arma el instalador desde el .env del repo):
  WC3_DASH_PASSWORD  obligatoria
  WC3_DASH_PORT      default 8322
  WC3_REALM_NAME     para el titulo
  WC3_MAX_MAP_MB     techo por mapa (default 8)
"""

import html
import hmac
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from base64 import b64decode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

MAPS_DIR = Path("/opt/wc3/maps")
INCOMING_DIR = Path("/opt/wc3/incoming")
BACKUPS_DIR = Path("/opt/wc3/backups")
INSTANCES_DIR = Path("/opt/wc3/hostbot/instances")

PVPGN_PORT = 6112
MAX_MAP_BYTES = int(os.environ.get("WC3_MAX_MAP_MB", "8")) * 1024 * 1024
# Cuota total de incoming: aunque cada mapa respete el techo, subir sin
# limite llenaria el disco del VPS (y PvPGN corre en la misma maquina).
MAX_INCOMING_TOTAL = 512 * 1024 * 1024
NOMBRE_MAPA_RE = re.compile(r"^[\w \-\.\(\)\[\]'!,&]+\.(w3x|w3m)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Datos del sistema (todo lectura, sin privilegios)
# ---------------------------------------------------------------------------

def unidad_activa(unidad: str) -> str:
    """Estado de una unidad segun systemd: active / inactive / failed / ..."""
    try:
        out = subprocess.run(
            ["systemctl", "is-active", unidad],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "desconocido"
    except (OSError, subprocess.TimeoutExpired):
        return "desconocido"


def journal_de(unidad: str, lineas: int = 10) -> str:
    """Ultimos renglones del journal. Necesita que wc3 este en el grupo
    systemd-journal (lo hace el instalador); si no puede, lo dice y ya."""
    try:
        out = subprocess.run(
            ["journalctl", "-u", unidad, "-n", str(lineas), "--no-pager",
             "-o", "short", "--no-hostname"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "(sin lineas en el journal)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(no pude leer el journal: {exc})"


def conexiones_por_puerto() -> dict:
    """Cuenta conexiones TCP ESTABLECIDAS por puerto local, de /proc/net/tcp.

    Cada jugador dentro de un lobby/partida es una conexion al puerto del
    bot; cada cliente logueado al server (incluidos los propios bots) es una
    al 6112. Es un conteo, no una lista de nombres: para los nombres esta el
    canal del juego.
    """
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
    """Lee las claves clave=valor de un aura.cfg (formato simple de Aura)."""
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
    """Una entrada por bot: numero, unidad, estado, mapa, puerto, jugadores."""
    resultado = []
    conexiones = conexiones_por_puerto()
    if INSTANCES_DIR.is_dir():
        for d in sorted(INSTANCES_DIR.iterdir(),
                        key=lambda p: int(p.name) if p.name.isdigit() else 999):
            if not d.name.isdigit():
                continue
            cfg = leer_cfg(d / "aura.cfg")
            puerto = int(cfg.get("bot_hostport") or 0)
            resultado.append({
                "n": d.name,
                "unidad": f"wc3-hostbot@{d.name}",
                "estado": unidad_activa(f"wc3-hostbot@{d.name}"),
                "nombre": cfg.get("bot_autohostname") or cfg.get("bot_defaultmap") or "?",
                "puerto": puerto,
                "jugadores": conexiones.get(puerto, 0),
            })
    return resultado


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


def pagina() -> str:
    realm = html.escape(os.environ.get("WC3_REALM_NAME", "WC3"))
    s = salud()
    conexiones = conexiones_por_puerto()
    bots = instancias()
    en_lobbies = sum(b["jugadores"] for b in bots)
    # Al 6112 tambien estan conectados los propios bots: se restan para
    # aproximar "personas", sin bajar de cero si algo quedo raro.
    bots_activos = sum(1 for b in bots if b["estado"] == "active")
    en_chat = max(0, conexiones.get(PVPGN_PORT, 0) - bots_activos)

    filas_bots = "".join(
        f"<tr><td>{b['n']}</td><td>{html.escape(b['nombre'])}</td>"
        f"<td>{punto(b['estado'])}</td><td>{b['puerto'] or '?'}</td>"
        f"<td style='text-align:right'>{b['jugadores']}</td></tr>"
        for b in bots
    ) or "<tr><td colspan=5>(no hay instancias en /opt/wc3/hostbot/instances)</td></tr>"

    mapas = lista_archivos(MAPS_DIR)
    filas_mapas = "".join(
        f"<tr><td>{html.escape(n)}</td><td style='text-align:right'>{mb(t)}</td></tr>"
        for n, t, _ in mapas
    ) or "<tr><td colspan=2>(sin mapas en /opt/wc3/maps)</td></tr>"

    pendientes = lista_archivos(INCOMING_DIR)
    seccion_pendientes = ""
    if pendientes:
        filas = "".join(f"<li>{html.escape(n)} ({mb(t)})</li>" for n, t, _ in pendientes)
        seccion_pendientes = f"""
  <h2>Mapas subidos, esperando instalarse ({len(pendientes)})</h2>
  <ul>{filas}</ul>
  <p>Para meterles la preview e instalarlos en el server, por SSH:</p>
  <pre>cd /opt/wc3-repo &amp;&amp; sudo make brand-maps</pre>
  <p>Si el mapa es NUEVO (no reemplaza uno que ya se hostea), despues:</p>
  <pre>./scripts/make-instances.py --maps-dir /opt/wc3/maps</pre>"""

    bks = backups()
    if bks:
        ultimo = bks[0]
        aviso_bk = ""
        if time.time() - ultimo[2] > 8 * 86400:
            aviso_bk = (' <strong style="color:#c0392b">&#9888; el ultimo backup tiene '
                        "mas de 8 dias: correr <code>sudo make backup</code></strong>")
        filas_bk = "".join(
            f"<tr><td>{html.escape(n)}</td><td>{hace(m)}</td>"
            f"<td style='text-align:right'>{mb(t)}</td></tr>"
            for n, t, m in bks[:5]
        )
        seccion_backups = f"<table>{filas_bk}</table><p>{len(bks)} en total.{aviso_bk}</p>"
    else:
        seccion_backups = ('<p><strong style="color:#c0392b">No hay ningun backup.</strong> '
                           "Correr <code>sudo make backup</code> en el server.</p>")

    dias_uptime = s["uptime"] / 86400
    pvpgn_estado = unidad_activa("pvpgn")

    journals = "".join(
        f"<details><summary>{html.escape(u)}</summary>"
        f"<pre>{html.escape(journal_de(u))}</pre></details>"
        for u in ["pvpgn"] + [b["unidad"] for b in bots]
    )

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>{realm} — dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto;
         padding: 0 1rem; background: #16181c; color: #e5e1d5; }}
  h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem;
         border-bottom: 1px solid #34373d; padding-bottom: .3rem; color: #d2ad5c; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ padding: .3rem .6rem; border-bottom: 1px solid #26292f; text-align: left; }}
  pre {{ background: #1f2227; padding: .6rem; overflow-x: auto; font-size: .85rem; }}
  code {{ background: #1f2227; padding: .1rem .3rem; }}
  .tiles {{ display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }}
  .tile {{ background: #1f2227; border-radius: 6px; padding: .7rem 1rem; min-width: 8rem; }}
  .tile b {{ display: block; font-size: 1.3rem; }}
  #zona {{ border: 2px dashed #4a4d55; border-radius: 8px; padding: 1.5rem;
          text-align: center; margin: 1rem 0; }}
  #zona.activa {{ border-color: #d2ad5c; background: #26292f; }}
  details summary {{ cursor: pointer; padding: .3rem 0; }}
</style></head><body>
  <h1>{realm} — dashboard <small style="color:#9c9c90;font-size:.8rem">
    se actualiza solo cada 60 s</small></h1>

  <div class="tiles">
    <div class="tile"><b>{en_chat}</b> conectados al chat</div>
    <div class="tile"><b>{en_lobbies}</b> en lobbies/partidas</div>
    <div class="tile"><b>{punto(pvpgn_estado)}</b> PvPGN</div>
    <div class="tile"><b>{bots_activos}/{len(bots)}</b> bots activos</div>
  </div>

  <h2>Bots (uno por mapa)</h2>
  <table><tr><th>#</th><th>Lobby</th><th>Estado</th><th>Puerto</th>
  <th style="text-align:right">Jugadores</th></tr>{filas_bots}</table>

  <h2>Subir un mapa</h2>
  <div id="zona">Arrastra un .w3x aca (o toca para elegirlo).<br>
    <small>Techo: {MAX_MAP_BYTES // (1024 * 1024)} MiB. Queda en el server
    esperando el paso de instalacion (te lo muestro despues de subirlo).</small>
    <input type="file" id="selector" accept=".w3x,.w3m" multiple hidden>
    <div id="resultado"></div>
  </div>
  {seccion_pendientes}

  <h2>Mapas instalados ({len(mapas)})</h2>
  <table>{filas_mapas}</table>

  <h2>Backups</h2>
  {seccion_backups}

  <h2>Salud del VPS</h2>
  <div class="tiles">
    <div class="tile"><b>{mb(s['disco_libre'])}</b> disco libre de {mb(s['disco_total'])}</div>
    <div class="tile"><b>{mb(s['mem_disp'])}</b> RAM libre de {mb(s['mem_total'])}</div>
    <div class="tile"><b>{dias_uptime:.1f} dias</b> prendido</div>
  </div>

  <h2>Ultimas lineas de cada servicio</h2>
  {journals}

<script>
const zona = document.getElementById('zona');
const selector = document.getElementById('selector');
const resultado = document.getElementById('resultado');
zona.addEventListener('click', () => selector.click());
zona.addEventListener('dragover', e => {{ e.preventDefault(); zona.classList.add('activa'); }});
zona.addEventListener('dragleave', () => zona.classList.remove('activa'));
zona.addEventListener('drop', e => {{
  e.preventDefault(); zona.classList.remove('activa'); subirTodos(e.dataTransfer.files);
}});
selector.addEventListener('change', () => subirTodos(selector.files));
async function subirTodos(archivos) {{
  for (const a of archivos) await subir(a);
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

    # --- auth ---------------------------------------------------------------
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
        # Cerrar la conexion: si era un PUT, el cuerpo quedo sin leer y el
        # keep-alive dejaria la proxima request desalineada.
        self.close_connection = True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="wc3 dashboard"')
        self._cuerpo(b"Hace falta la contrasena del dashboard.\n")
        return False

    def _cuerpo(self, datos: bytes, tipo: str = "text/plain; charset=utf-8"):
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    # --- rutas ---------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._autorizado():
            return
        if self.path in ("/", ""):
            self.send_response(200)
            self._cuerpo(pagina().encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self._cuerpo(b"No hay nada aca. La pagina es /\n")

    def do_PUT(self):  # noqa: N802
        if not self._autorizado():
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
            return ("subido OK. Para instalarlo, por SSH: "
                    "cd /opt/wc3-repo && sudo make brand-maps"), 200
        except (OSError, socket.timeout):
            return "se corto la subida, proba de nuevo", 400
        finally:
            tmp.unlink(missing_ok=True)


def main() -> int:
    if not os.environ.get("WC3_DASH_PASSWORD"):
        print("Falta WC3_DASH_PASSWORD en el entorno; sin contraseña no arranco.",
              file=sys.stderr)
        return 1
    puerto = int(os.environ.get("WC3_DASH_PORT", "8322"))
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Handler)
    servidor.daemon_threads = True
    print(f"[dashboard] escuchando en :{puerto}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
