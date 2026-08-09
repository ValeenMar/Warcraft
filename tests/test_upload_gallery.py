"""Tests de la galeria de upload-maps.py.

La galeria muestra, abajo de la zona de subida, las previews que ya traen los
mapas. Sirve archivos del disco, asi que lo que importa es que sirva solo los
.png del directorio que se le dio y nada mas.

Correr con:  python3 -m unittest discover tests
"""

import base64
import importlib.util
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "upload_maps", REPO_DIR / "scripts" / "upload-maps.py"
)
upload = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(upload)

TOKEN = "token-galeria"
# PNG valido de 1x1, para no depender de Pillow en este test.
PNG_MINIMO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestGaleria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.dest = raiz / "incoming"
        self.galeria = raiz / "galeria"
        self.dest.mkdir()
        self.galeria.mkdir()
        (self.galeria / "DotA v6.83d.png").write_bytes(PNG_MINIMO)
        # Un archivo que NO es .png en el mismo directorio: no se sirve.
        (self.galeria / "secreto.txt").write_text("no mirar")
        # Y uno afuera, para el intento de salirse del directorio.
        (raiz / "afuera.png").write_bytes(PNG_MINIMO)

        upload.Handler.token = TOKEN
        upload.Handler.dest = self.dest
        upload.Handler.realm = "test"
        upload.Handler.owner = None
        upload.Handler.gallery = self.galeria

        self.port = puerto_libre()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), upload.Handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()
        self.base = f"http://127.0.0.1:{self.port}/{TOKEN}"

    def tearDown(self):
        upload.Handler.gallery = None
        self.httpd.shutdown()
        self.httpd.server_close()
        self.hilo.join(timeout=5)
        self.tmp.cleanup()

    def get(self, ruta: str) -> int:
        try:
            with urllib.request.urlopen(self.base + ruta, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_la_pagina_lista_las_previews(self):
        with urllib.request.urlopen(self.base, timeout=10) as r:
            cuerpo = r.read().decode("utf-8")
        self.assertIn("Previews que ya traen los mapas", cuerpo)
        self.assertIn("DotA%20v6.83d.png", cuerpo)

    def test_sirve_el_png(self):
        with urllib.request.urlopen(self.base + "/img/DotA%20v6.83d.png", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertEqual(r.read(), PNG_MINIMO)

    def test_no_sirve_otra_cosa_que_no_sea_png(self):
        self.assertEqual(self.get("/img/secreto.txt"), 404)

    def test_no_sale_del_directorio_de_la_galeria(self):
        for intento in ["/img/..%2Fafuera.png", "/img/%2Fetc%2Fhostname",
                        "/img/....%2F%2Fafuera.png"]:
            with self.subTest(intento):
                self.assertEqual(self.get(intento), 404)

    def test_ofrece_el_kit_para_descargar(self):
        kit = Path(self.tmp.name) / "WC3-Revival-Kit.zip"
        kit.write_bytes(b"PK\x03\x04" + b"contenido del kit")
        upload.Handler.offer = kit
        try:
            with urllib.request.urlopen(self.base, timeout=10) as r:
                self.assertIn("Descargar WC3-Revival-Kit.zip", r.read().decode("utf-8"))
            with urllib.request.urlopen(
                self.base + "/bajar/WC3-Revival-Kit.zip", timeout=10
            ) as r:
                self.assertEqual(r.read(), kit.read_bytes())
            # Solo se sirve ESE archivo, no cualquiera que se pida
            self.assertEqual(self.get("/bajar/otra-cosa.zip"), 404)
            self.assertEqual(self.get("/bajar/..%2F..%2Fetc%2Fpasswd"), 404)
        finally:
            upload.Handler.offer = None

    def test_sin_kit_no_hay_boton_ni_ruta(self):
        self.assertEqual(self.get("/bajar/WC3-Revival-Kit.zip"), 404)
        with urllib.request.urlopen(self.base, timeout=10) as r:
            self.assertNotIn("Descargar", r.read().decode("utf-8"))

    def test_sin_galeria_la_pagina_sale_igual(self):
        upload.Handler.gallery = None
        with urllib.request.urlopen(self.base, timeout=10) as r:
            cuerpo = r.read().decode("utf-8")
        self.assertIn("Subir mapas", cuerpo)
        self.assertNotIn("Previews que ya traen", cuerpo)
        self.assertEqual(self.get("/img/DotA%20v6.83d.png"), 404)


if __name__ == "__main__":
    unittest.main()
