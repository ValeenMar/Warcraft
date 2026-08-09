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
  - solo acepta .w3x y .w3m, y solo hasta 8 MiB por archivo, que es el techo
    que soportan los clientes 1.24-1.28 igual
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
import pwd
import re
import secrets
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024  # mismo techo que el cliente 1.24-1.28
ALLOWED_SUFFIXES = {".w3x", ".w3m"}

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
Máximo 8 MiB por mapa.</p>
<div id="zona"><b>Soltá los mapas acá</b><span>o clic para buscarlos</span></div>
<input type="file" id="picker" multiple accept=".w3x,.w3m">
<ul id="lista"></ul>
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
  const TECHO = 8 * 1024 * 1024;
  if (file.size > TECHO) {{
    li.className = 'mal';
    est.textContent = 'pesa ' + (file.size / 1048576).toFixed(1) + ' MB, el máximo es 8';
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


def safe_name(raw: str) -> "str | None":
    """Devuelve un nombre de archivo seguro, o None si no sirve.

    Del nombre que manda el navegador se usa solo el basename, asi que no hay
    forma de escribir fuera del destino ni con ../ ni con rutas absolutas.
    """
    name = os.path.basename(raw.replace("\\", "/")).strip()
    if not name or name.startswith("."):
        return None
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
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
    realm = "el servidor"
    owner = None

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("[upload] %s - %s\n" % (self.address_string(), fmt % args))

    def _txt(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/" + self.token:
            self._txt(404, "no existe\n")
            return
        page = PAGE.format(realm=html.escape(self.realm), base="/" + self.token)
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

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._txt(400, "largo invalido")
            return
        if length <= 0:
            self._txt(400, "archivo vacio")
            return
        if length > MAX_BYTES:
            self._txt(413, f"pesa {length // 1024} KB y el techo son 8 MiB")
            return

        # Se escribe a un temporal y recien al final se renombra: si la subida
        # se corta, no queda un .w3x a medias que despues rompa al bot.
        self.dest.mkdir(parents=True, exist_ok=True)
        tmp = self.dest / (name + ".parcial")
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
            if tmp.read_bytes()[:4] != b"HM3W":
                tmp.unlink(missing_ok=True)
                self._txt(400, "no parece un mapa de Warcraft III")
                return
            destino = self.dest / name
            tmp.replace(destino)
            if self.owner is not None:
                os.chown(destino, self.owner.pw_uid, self.owner.pw_gid)
            destino.chmod(0o644)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            self._txt(500, f"no pude guardarlo: {exc}")
            return

        print(f"[upload] recibido: {name} ({leidos} B)", flush=True)
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
    args = ap.parse_args(argv)

    Handler.token = args.token or secrets.token_urlsafe(16)
    Handler.dest = args.dest
    Handler.realm = args.realm
    if args.chown:
        try:
            Handler.owner = pwd.getpwnam(args.chown)
        except KeyError:
            print(f"aviso: no existe el usuario {args.chown}, dejo los archivos como root",
                  file=sys.stderr)

    args.dest.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.dest).free < 200 * 1024 * 1024:
        print("aviso: queda menos de 200 MB libres en el disco", file=sys.stderr)

    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    if args.minutes:
        threading.Timer(args.minutes * 60, httpd.shutdown).start()

    print(f"[upload] escuchando en el puerto {args.port}, destino {args.dest}")
    print(f"[upload] token: {Handler.token}")
    if args.minutes:
        print(f"[upload] se apaga solo en {args.minutes} minutos (Ctrl+C para cortar antes)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[upload] cortado a mano")
    httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
