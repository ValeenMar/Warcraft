"""Tests del dashboard: auth y subida de mapas, contra el servidor real
levantado en un puerto efimero (mismo enfoque que test_upload_maps.py).

Las lecturas de sistema (systemctl, /proc, journal) no se testean: dependen
de la maquina. Lo que si se clava aca es lo que da miedo romper: que sin
contraseña no pasa nadie, y que la subida rechaza lo que hay que rechazar.
"""

import importlib.util
import os
import threading
import unittest
import urllib.error
import urllib.request
from base64 import b64encode
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

_SPEC = importlib.util.spec_from_file_location(
    "dashboard", Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
)
dashboard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dashboard)

PASSWORD = "clave-de-prueba"


def _auth(clave: str = PASSWORD) -> dict:
    token = b64encode(f"admin:{clave}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class TestDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.incoming = Path(cls.tmp.name) / "incoming"
        cls.incoming.mkdir()
        dashboard.INCOMING_DIR = cls.incoming
        dashboard.MAPS_DIR = Path(cls.tmp.name) / "maps"
        dashboard.BACKUPS_DIR = Path(cls.tmp.name) / "backups"
        dashboard.INSTANCES_DIR = Path(cls.tmp.name) / "instances"
        os.environ["WC3_DASH_PASSWORD"] = PASSWORD

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def _url(self, ruta: str) -> str:
        return f"http://127.0.0.1:{self.port}{ruta}"

    def _put(self, ruta: str, cuerpo: bytes, headers: dict):
        req = urllib.request.Request(
            self._url(ruta), data=cuerpo, method="PUT", headers=headers
        )
        return urllib.request.urlopen(req, timeout=10)

    # --- auth ---------------------------------------------------------------
    def test_sin_contrasena_401(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self._url("/"), timeout=10)
        self.assertEqual(ctx.exception.code, 401)

    def test_contrasena_incorrecta_401(self):
        req = urllib.request.Request(self._url("/"), headers=_auth("otra"))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 401)

    def test_con_contrasena_carga_la_pagina(self):
        req = urllib.request.Request(self._url("/"), headers=_auth())
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("dashboard", resp.read().decode())

    # --- subida --------------------------------------------------------------
    def test_subida_ok(self):
        cuerpo = b"HM3W" + b"\x00" * 700
        with self._put("/subir/Mi%20Mapa.w3x", cuerpo, _auth()) as resp:
            self.assertEqual(resp.status, 200)
        destino = self.incoming / "Mi Mapa.w3x"
        self.assertTrue(destino.is_file())
        self.assertEqual(destino.read_bytes()[:4], b"HM3W")

    def test_subida_sin_auth_401(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._put("/subir/x.w3x", b"HM3W" + b"\x00" * 10, {})
        self.assertEqual(ctx.exception.code, 401)

    def test_traversal_se_reduce_a_basename(self):
        cuerpo = b"HM3W" + b"\x00" * 10
        with self._put("/subir/..%2Fafuera.w3x", cuerpo, _auth()) as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue((self.incoming / "afuera.w3x").is_file())
        self.assertFalse((self.incoming.parent / "afuera.w3x").exists())

    def test_rechaza_extension_rara(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._put("/subir/nota.txt", b"HM3W", _auth())
        self.assertEqual(ctx.exception.code, 400)

    def test_rechaza_contenido_falso(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._put("/subir/trucho.w3x", b"PK\x03\x04" + b"\x00" * 64, _auth())
        self.assertEqual(ctx.exception.code, 400)
        self.assertFalse((self.incoming / "trucho.w3x").exists())

    def test_rechaza_gigante(self):
        req = urllib.request.Request(
            self._url("/subir/gordo.w3x"), data=b"", method="PUT", headers=_auth()
        )
        req.add_unredirected_header("Content-Length", str(dashboard.MAX_MAP_BYTES + 1))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
