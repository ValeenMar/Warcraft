"""Tests de upload-maps.py — la pagina temporal para subir mapas.

Levanta el servidor en un puerto libre, le manda archivos y verifica tanto que
lo bueno entre como que lo malo NO entre: es un servicio que queda expuesto en
internet un rato, asi que los rechazos importan tanto como las aceptaciones.

Correr con:  python3 -m unittest discover tests
"""

import importlib.util
import socket
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_inspect_map import build_hm3w  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO_DIR / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


upload = _load("upload_maps", "upload-maps.py")

TOKEN = "token-de-prueba"
MAPA = build_hm3w("Mapa de prueba", 12) + b"\x00" * 256


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestSafeName(unittest.TestCase):
    def test_acepta_nombres_de_mapa_normales(self):
        for n in ["DotA v6.83d.w3x", "Anime Fight Arena0.1.w3x", "Pudge Wars 1.26.w3x",
                  "Naruto Ninpou Storm 0.9ZZZ.w3x", "Bleach vs One Piece v2.08b.w3x"]:
            with self.subTest(n):
                self.assertEqual(upload.safe_name(n), n)

    def test_se_queda_solo_con_el_basename(self):
        # Venga como venga la ruta, solo sobrevive el ultimo tramo.
        self.assertEqual(upload.safe_name("/etc/cron.d/x.w3x"), "x.w3x")
        self.assertEqual(upload.safe_name("C:\\Users\\Valen\\mapa.w3x"), "mapa.w3x")
        self.assertIsNone(upload.safe_name("../../../etc/shadow"))

    def test_rechaza_lo_que_no_es_mapa(self):
        for n in ["programa.exe", "libreria.dll", "script.sh", "nota.txt", "", ".oculto.w3x"]:
            with self.subTest(n):
                self.assertIsNone(upload.safe_name(n))


class TestAlfabetoDelToken(unittest.TestCase):
    """El token se lee de una consola y se tipea en un navegador. Si trae
    caracteres que se confunden entre si, el resultado es un 404 inexplicable
    (paso de verdad: una 'l' minuscula tecleada como '1')."""

    def test_sin_caracteres_ambiguos(self):
        for c in "01lIoO":
            self.assertNotIn(c, upload.ALFABETO, f"'{c}' se confunde al tipear")

    def test_largo_suficiente(self):
        # 12 caracteres de un alfabeto de 31 son ~59 bits: de sobra para una
        # ventana de media hora, y todavia tipeable.
        self.assertGreaterEqual(upload.LARGO_TOKEN * len(upload.ALFABETO).bit_length(), 55)


class TestServidor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name)
        upload.Handler.token = TOKEN
        upload.Handler.dest = self.dest
        upload.Handler.realm = "test"
        upload.Handler.owner = None
        self.port = puerto_libre()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), upload.Handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()
        self.base = f"http://127.0.0.1:{self.port}/{TOKEN}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.hilo.join(timeout=5)
        self.tmp.cleanup()

    def put(self, nombre: str, cuerpo: bytes) -> int:
        req = urllib.request.Request(
            f"{self.base}/subir/{urllib.parse.quote(nombre)}", data=cuerpo, method="PUT"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_la_pagina_carga_con_token(self):
        with urllib.request.urlopen(self.base, timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("Subir mapas", r.read().decode("utf-8"))

    def test_sin_el_token_no_hay_nada(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/loquesea")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_sube_un_mapa(self):
        self.assertEqual(self.put("DotA v6.83d.w3x", MAPA), 200)
        destino = self.dest / "DotA v6.83d.w3x"
        self.assertTrue(destino.exists())
        self.assertEqual(destino.read_bytes(), MAPA)

    def test_rechaza_lo_que_no_es_un_w3x(self):
        # Extension permitida pero contenido que no es un mapa: sin header HM3W
        # no entra, para que no quede basura que despues rompa al bot.
        self.assertEqual(self.put("falso.w3x", b"esto no es un mapa"), 400)
        self.assertFalse((self.dest / "falso.w3x").exists())

    def test_rechaza_extensiones_ajenas(self):
        self.assertEqual(self.put("cualquiera.txt", MAPA), 400)
        self.assertEqual(len(list(self.dest.iterdir())), 0)

    def test_no_escribe_fuera_del_destino(self):
        # No se rechaza: se le saca la ruta y se guarda adentro con el nombre
        # pelado. Lo que importa es que NO aparezca nada un nivel mas arriba.
        self.assertEqual(self.put("../afuera.w3x", MAPA), 200)
        self.assertFalse((self.dest.parent / "afuera.w3x").exists())
        self.assertTrue((self.dest / "afuera.w3x").exists())

    def test_rechaza_lo_que_pasa_el_techo_de_8_mib(self):
        grande = MAPA + b"\x00" * upload.MAX_BYTES
        try:
            code = self.put("gigante.w3x", grande)
        except urllib.error.URLError:
            # El servidor contesta 413 y cierra sin leer el cuerpo, asi que el
            # cliente puede llegar a ver la conexion cortada en vez del codigo.
            # Por eso la pagina ademas chequea el tamano antes de mandar nada.
            code = 413
        self.assertEqual(code, 413)
        self.assertFalse((self.dest / "gigante.w3x").exists())

    def test_un_handshake_tls_se_corta_sin_romper_el_servidor(self):
        # Escribir la direccion sin "http://" hace que el navegador mande TLS.
        # Antes eso llenaba el log de basura binaria; ahora se corta limpio y
        # el servidor tiene que seguir atendiendo lo siguiente.
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(b"\x16\x03\x01\x02\x00\x01\x00\x01\xfc\x03\x03" + b"\x00" * 64)
            self.assertEqual(s.recv(64), b"", "tendria que cerrar sin contestar")
        self.assertEqual(self.put("DotA v6.83d.w3x", MAPA), 200)

    def test_no_deja_archivos_a_medias(self):
        # Un rechazo no puede dejar el .parcial dando vueltas.
        self.put("falso.w3x", b"corto")
        self.assertEqual(list(self.dest.glob("*.parcial")), [])


if __name__ == "__main__":
    unittest.main()
