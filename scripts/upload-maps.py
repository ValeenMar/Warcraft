#!/usr/bin/env python3
"""upload-maps.py — pagina web temporal para subir mapas al servidor.

Levanta un HTTP chiquito con una pagina de arrastrar-y-soltar. Los .w3x que
sueltes ahi caen en /opt/wc3/incoming, listos para scripts/brand-map.py.

Existe porque scp desde Windows es una pelea (comillas de PowerShell, claves,
contrasenas) y porque asi tus amigos tambien pueden mandarte mapas sin que les
des acceso al servidor.

Esta pensado para estar prendido un rato y apagarse solo:

  - la URL lleva un token aleatorio; sin el token todo devuelve 404, asi que
    un escaneo de puertos no encuentra nada util
  - se apaga solo a los N minutos (--minutes, 30 por defecto)
  - solo acepta .w3x y .w3m (y, si se pasa --banner-dest, un .png para el
    banner del cliente), y solo hasta 128 MiB por archivo, que es el techo del
    cliente objetivo 1.27b
  - ademas del nombre se chequea el contenido: HM3W para los mapas, la firma
    PNG para el banner. Una extension renombrada no entra
  - nunca escribe fuera del directorio de destino: del nombre que manda el
    navegador se usa unicamente el basename

Es HTTP plano, sin cifrar. Para mandar mapas a un server propio da lo mismo,
pero no le pongas nada sensible.

Uso (normalmente lo llama scripts/recibir-mapas.sh, que ademas abre el puerto
en ufw y lo vuelve a cerrar):

    sudo python3 scripts/upload-maps.py --dest /opt/wc3/incoming --port 8099
"""

import argparse
import html
import os
import re
import secrets
import shutil
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import pwd
except ImportError:  # Windows: los tests no necesitan cambiar propietario
    pwd = None

# Techo por defecto: el del cliente objetivo 1.27b.
MAX_BYTES = 128 * 1024 * 1024
ALLOWED_SUFFIXES = {".w3x", ".w3m"}
# El banner del cliente tambien se sube por aca: es la unica forma comoda de
# llevar un archivo de Windows al servidor. Se guarda aparte de los mapas.
BANNER_SUFFIXES = {".png"}
MAX_BANNER_BYTES = 4 * 1024 * 1024

# Alfabeto del token: sin 0/O ni 1/l/I. El token se lee de una consola y se
# tipea en el navegador, y con base64 normal la primera "l" minuscula se tipea
# como "1" y da 404 sin que se entienda por que. Doce caracteres de estos son
# ~59 bits, de sobra para una ventana de media hora.
ALFABETO = "abcdefghjkmnpqrstuvwxyz23456789"
LARGO_TOKEN = 12

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Subir mapas — {realm}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         background:#11141c; color:#e8ecf4;
         font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }}
  main {{ width:min(560px,92vw); padding:2rem 0; }}
  h1 {{ font-size:1.3rem; margin:0 0 .3rem; }}
  p.sub {{ margin:0 0 1.5rem; color:#93a0b8; font-size:.9rem; }}
  #zona {{ border:2px dashed #3d4a63; border-radius:14px; padding:2.5rem 1.5rem;
          text-align:center; transition:.15s; cursor:pointer; }}
  #zona.hot {{ border-color:#5aa9ff; background:#16202f; }}
  #zona b {{ display:block; font-size:1.05rem; margin-bottom:.3rem; }}
  #zona span {{ color:#93a0b8; font-size:.88rem; }}
  h2 {{ font-size:1rem; margin:2rem 0 .8rem; color:#93a0b8; font-weight:600; }}
  a.kit {{ display:block; text-align:center; padding:1rem; border-radius:12px;
          background:#1d4ed8; color:#fff; text-decoration:none; font-weight:600; }}
  a.kit:hover {{ background:#2563eb; }}
  a.kit small {{ display:block; font-weight:400; opacity:.8; margin-top:.2rem; }}
  #galeria {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
             gap:.9rem; }}
  #galeria figure {{ margin:0; }}
  #galeria img {{ width:100%; aspect-ratio:1; object-fit:cover; border-radius:8px;
                 background:#182031; display:block; image-rendering:pixelated; }}
  #galeria figcaption {{ font-size:.78rem; color:#93a0b8; margin-top:.35rem;
                        overflow-wrap:anywhere; }}
  ul {{ list-style:none; padding:0; margin:1.2rem 0 0; }}
  li {{ display:flex; justify-content:space-between; gap:1rem; padding:.5rem .7rem;
       background:#182031; border-radius:8px; margin-bottom:.4rem; font-size:.9rem; }}
  li .est {{ color:#93a0b8; white-space:nowrap; }}
  li.ok .est {{ color:#7fd88f; }}
  li.mal .est {{ color:#ff7b7b; }}
  input[type=file] {{ display:none; }}
</style></head><body><main>
<h1>Subir mapas a {realm}</h1>
<p class="sub">Arrastrá los <code>.w3x</code> acá, o hacé clic para elegirlos.
Máximo {max_map_mb} MiB por mapa.{banner_ayuda}</p>
<div id="zona"><b>Soltá los mapas acá</b><span>o clic para buscarlos</span></div>
<input type="file" id="picker" multiple accept="{acepta}">
<ul id="lista"></ul>
{descarga}
{galeria}
<script>
const zona = document.getElementById('zona');
const picker = document.getElementById('picker');
const lista = document.getElementById('lista');

zona.onclick = () => picker.click();
picker.onchange = () => subir(picker.files);
['dragenter','dragover'].forEach(e => zona.addEventListener(e, ev => {{
  ev.preventDefault(); zona.classList.add('hot');
}}));
['dragleave','drop'].forEach(e => zona.addEventListener(e, ev => {{
  ev.preventDefault(); zona.classList.remove('hot');
}}));
zona.addEventListener('drop', ev => subir(ev.dataTransfer.files));

function subir(files) {{
  for (const f of files) uno(f);
}}

function uno(file) {{
  const li = document.createElement('li');
  li.innerHTML = '<span></span><span class="est">subiendo…</span>';
  li.firstChild.textContent = file.name;
  lista.appendChild(li);
  const est = li.querySelector('.est');

  // Se chequea acá antes de mandar nada: si el servidor corta a mitad de una
  // subida de 20 MB, el navegador muestra "falló la conexión" y no se entiende
  // por qué. Avisando de entrada, el motivo queda claro y no se gasta la subida.
  const esPng = /\\.png$/i.test(file.name);
  const TECHO = esPng ? 4 * 1024 * 1024 : {max_map_bytes};
  if (file.size > TECHO) {{
    li.className = 'mal';
    est.textContent = 'pesa ' + (file.size / 1048576).toFixed(1) + ' MB, el máximo es ' + (TECHO / 1048576);
    return;
  }}

  const xhr = new XMLHttpRequest();
  xhr.open('PUT', '{base}/subir/' + encodeURIComponent(file.name));
  xhr.upload.onprogress = ev => {{
    if (ev.lengthComputable) est.textContent = Math.round(ev.loaded / ev.total * 100) + '%';
  }};
  xhr.onload = () => {{
    if (xhr.status === 200) {{ li.className = 'ok'; est.textContent = 'listo'; }}
    else {{ li.className = 'mal'; est.textContent = xhr.responseText || ('error ' + xhr.status); }}
  }};
  xhr.onerror = () => {{ li.className = 'mal'; est.textContent = 'falló la conexión'; }};
  xhr.send(file);
}}
</script></main></body></html>
"""


def es_banner(nombre: str) -> bool:
    return Path(nombre).suffix.lower() in BANNER_SUFFIXES


def safe_name(raw: str) -> "str | None":
    """Devuelve un nombre de archivo seguro, o None si no sirve.

    Del nombre que manda el navegador se usa solo el basename, asi que no hay
    forma de escribir fuera del destino ni con ../ ni con rutas absolutas.
    """
    name = os.path.basename(raw.replace("\\", "/")).strip()
    if not name or name.startswith("."):
        return None
    if Path(name).suffix.lower() not in (ALLOWED_SUFFIXES | BANNER_SUFFIXES):
        return None
    # Nada de caracteres raros: los mapas se llaman con letras, numeros,
    # espacios, puntos, guiones y parentesis.
    if not re.fullmatch(r"[\w .()\[\]+'-]{1,120}", name, re.UNICODE):
        return None
    return name


class Handler(BaseHTTPRequestHandler):
    server_version = "wc3-upload"
    # Los inyecta main()
    token = ""
    dest = Path("/opt/wc3/incoming")
    max_map_bytes = MAX_BYTES
    realm = "el servidor"
    owner = None
    gallery = None
    offer = None
    banner_dest = None

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("[upload] %s - %s\n" % (self.address_string(), fmt % args))

    def handle_one_request(self) -> None:
        """Corta las conexiones TLS antes de intentar parsearlas como HTTP.

        Si en el navegador se escribe la direccion sin el "http://", Chrome
        asume HTTPS y manda un handshake TLS. Esto habla HTTP plano, asi que el
        parser toma los bytes del handshake como si fueran una linea de pedido
        y vomita paginas de basura binaria en el log por cada reintento. Un
        handshake TLS siempre arranca con 0x16, asi que se detecta y se corta
        con un aviso legible.
        """
        try:
            primero = self.connection.recv(1, socket.MSG_PEEK)
        except OSError:
            primero = b""
        if primero == b"\x16":
            print(
                f"[upload] {self.address_string()} intento entrar por HTTPS. "
                "La direccion es http:// (sin la s).",
                flush=True,
            )
            self.close_connection = True
            return
        super().handle_one_request()

    def _txt(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _descarga_html(self) -> str:
        """Boton para bajarse el kit, si se le paso uno con --offer."""
        if self.offer is None or not self.offer.is_file():
            return ""
        from urllib.parse import quote

        mb = self.offer.stat().st_size / 1048576
        return (
            '<h2>Kit para instalar el juego</h2>'
            '<a class="kit" href="{base}/bajar/{f}">Descargar {n}'
            "<small>{mb:.1f} MB — descomprimir y doble clic en INSTALAR.bat</small></a>"
        ).format(
            base="/" + self.token,
            f=quote(self.offer.name),
            n=html.escape(self.offer.name),
            mb=mb,
        )

    def _servir_kit(self, nombre: str) -> None:
        """Manda el archivo de --offer. Solo ese, comparando por nombre."""
        if self.offer is None or os.path.basename(nombre) != self.offer.name:
            self._txt(404, "no existe\n")
            return
        datos = self.offer.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{self.offer.name}"'
        )
        self.end_headers()
        self.wfile.write(datos)

    def _galeria_html(self) -> str:
        """Grilla con las previews que haya en el directorio de galeria."""
        if self.gallery is None or not self.gallery.is_dir():
            return ""
        imgs = sorted(p for p in self.gallery.iterdir() if p.suffix.lower() == ".png")
        if not imgs:
            return ""
        from urllib.parse import quote

        filas = "".join(
            '<figure><img src="{base}/img/{f}" alt="" loading="lazy">'
            "<figcaption>{n}</figcaption></figure>".format(
                base="/" + self.token, f=quote(p.name), n=html.escape(p.stem)
            )
            for p in imgs
        )
        return (
            "<h2>Previews que ya traen los mapas</h2>"
            f'<div id="galeria">{filas}</div>'
        )

    def _serve_image(self, nombre: str) -> None:
        """Sirve un PNG de la galeria. Solo basename, y solo .png."""
        if self.gallery is None:
            self._txt(404, "no existe\n")
            return
        name = os.path.basename(nombre.replace("\\", "/"))
        ruta = self.gallery / name
        if (
            not name
            or name.startswith(".")
            or Path(name).suffix.lower() != ".png"
            or not ruta.is_file()
        ):
            self._txt(404, "no existe\n")
            return
        data = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        from urllib.parse import unquote

        prefijo_img = "/" + self.token + "/img/"
        if self.path.startswith(prefijo_img):
            self._serve_image(unquote(self.path[len(prefijo_img):]))
            return
        prefijo_kit = "/" + self.token + "/bajar/"
        if self.path.startswith(prefijo_kit):
            self._servir_kit(unquote(self.path[len(prefijo_kit):]))
            return
        if self.path.rstrip("/") != "/" + self.token:
            self._txt(404, "no existe\n")
            return
        page = PAGE.format(
            realm=html.escape(self.realm),
            base="/" + self.token,
            acepta=".w3x,.w3m,.png" if self.banner_dest else ".w3x,.w3m",
            max_map_mb=self.max_map_bytes // (1024 * 1024),
            max_map_bytes=self.max_map_bytes,
            banner_ayuda=(" También podés soltar un <code>.png</code> de 468×60 "
                          "para usarlo como banner del servidor."
                          if self.banner_dest else ""),
            descarga=self._descarga_html(),
            galeria=self._galeria_html(),
        )
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self) -> None:  # noqa: N802
        prefijo = "/" + self.token + "/subir/"
        if not self.path.startswith(prefijo):
            self._txt(404, "no existe\n")
            return

        from urllib.parse import unquote

        name = safe_name(unquote(self.path[len(prefijo):]))
        if name is None:
            self._txt(400, "solo .w3x o .w3m, y sin nombres raros")
            return

        banner = es_banner(name)
        if banner and self.banner_dest is None:
            self._txt(400, "este servidor no acepta banners")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._txt(400, "largo invalido")
            return
        if length <= 0:
            self._txt(400, "archivo vacio")
            return
        techo = MAX_BANNER_BYTES if banner else self.max_map_bytes
        if length > techo:
            self._txt(413, f"pesa {length // 1024} KB y el techo son {techo // 1048576} MiB")
            return

        # Se escribe a un temporal y recien al final se renombra: si la subida
        # se corta, no queda un .w3x a medias que despues rompa al bot.
        destino_dir = self.banner_dest.parent if banner else self.dest
        destino_dir.mkdir(parents=True, exist_ok=True)
        tmp = destino_dir / (name + ".parcial")
        leidos = 0
        try:
            with tmp.open("wb") as fh:
                while leidos < length:
                    chunk = self.rfile.read(min(1 << 16, length - leidos))
                    if not chunk:
                        break
                    fh.write(chunk)
                    leidos += len(chunk)
            if leidos != length:
                tmp.unlink(missing_ok=True)
                self._txt(400, "se corto la subida")
                return
            cabecera = tmp.read_bytes()[:8]
            if banner:
                if cabecera[:8] != b"\x89PNG\r\n\x1a\n":
                    tmp.unlink(missing_ok=True)
                    self._txt(400, "no parece un PNG")
                    return
            elif cabecera[:4] != b"HM3W":
                tmp.unlink(missing_ok=True)
                self._txt(400, "no parece un mapa de Warcraft III")
                return
            destino = self.banner_dest if banner else (self.dest / name)
            tmp.replace(destino)
            if self.owner is not None:
                os.chown(destino, self.owner.pw_uid, self.owner.pw_gid)
            destino.chmod(0o644)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            self._txt(500, f"no pude guardarlo: {exc}")
            return

        que = "banner" if banner else "mapa"
        print(f"[upload] recibido ({que}): {name} -> {destino} ({leidos} B)", flush=True)
        self._txt(200, "ok")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pagina temporal para subir mapas")
    ap.add_argument("--dest", type=Path, default=Path("/opt/wc3/incoming"))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--minutes", type=int, default=30,
                    help="apagarse solo despues de estos minutos (0 = nunca)")
    ap.add_argument("--realm", default="el servidor")
    ap.add_argument("--chown", default="wc3",
                    help="usuario dueno de los archivos subidos ('' para no cambiarlo)")
    ap.add_argument("--token", default=None, help="fijar el token en vez de sortearlo")
    ap.add_argument("--max-map-mb", type=int, default=128,
                    help="techo por mapa en MiB (128 para Warcraft III 1.27b)")
    ap.add_argument("--banner-dest", type=Path, default=None,
                    help="si se pasa, la pagina acepta un .png y lo guarda aca")
    ap.add_argument("--offer", type=Path, default=None,
                    help="archivo (el kit) que se ofrece para descargar en la pagina")
    ap.add_argument("--gallery", type=Path, default=None,
                    help="mostrar los .png de este directorio abajo de la zona de subida")
    args = ap.parse_args(argv)

    Handler.token = args.token or "".join(
        secrets.choice(ALFABETO) for _ in range(LARGO_TOKEN)
    )
    Handler.dest = args.dest
    Handler.realm = args.realm
    Handler.gallery = args.gallery
    Handler.offer = args.offer
    Handler.banner_dest = args.banner_dest
    Handler.max_map_bytes = args.max_map_mb * 1024 * 1024
    if args.chown and pwd is not None:
        try:
            Handler.owner = pwd.getpwnam(args.chown)
        except KeyError:
            print(f"aviso: no existe el usuario {args.chown}, dejo los archivos como root",
                  file=sys.stderr)
    elif args.chown:
        print("aviso: esta plataforma no permite resolver usuarios Unix; no hago chown",
              file=sys.stderr)

    args.dest.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.dest).free < 200 * 1024 * 1024:
        print("aviso: queda menos de 200 MB libres en el disco", file=sys.stderr)

    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    # daemon=True y cancel() al final: sin eso, un Ctrl+C deja al interprete
    # esperando al temporizador (hasta 30 minutos) y el segundo Ctrl+C sale
    # con un traceback feo de threading.
    apagado = None
    if args.minutes:
        apagado = threading.Timer(args.minutes * 60, httpd.shutdown)
        apagado.daemon = True
        apagado.start()

    print(f"[upload] escuchando en el puerto {args.port}, destino {args.dest}")
    print(f"[upload] token: {Handler.token}")
    if args.minutes:
        print(f"[upload] se apaga solo en {args.minutes} minutos (Ctrl+C para cortar antes)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[upload] cortado a mano")
    if apagado is not None:
        apagado.cancel()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
