"""Tests del dashboard: auth y subida de mapas, contra el servidor real
levantado en un puerto efimero (mismo enfoque que test_upload_maps.py).

Las lecturas de sistema (systemctl, /proc, journal) no se testean: dependen
de la maquina. Lo que si se clava aca es lo que da miedo romper: que sin
contraseña no pasa nadie, y que la subida rechaza lo que hay que rechazar.
"""

import importlib.util
import json
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
        cls.spool = Path(cls.tmp.name) / "spool"
        dashboard.SPOOL_DIR = cls.spool
        dashboard.RESULTADOS_DIR = Path(cls.tmp.name) / "resultados"
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

    # --- vivo: fragmento y chat ------------------------------------------------
    def test_parcial_devuelve_html(self):
        req = urllib.request.Request(self._url("/parcial"), headers=_auth())
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("Salud del VPS", resp.read().decode())

    def test_chat_estado_json(self):
        req = urllib.request.Request(self._url("/chat?desde=0"), headers=_auth())
        with urllib.request.urlopen(req, timeout=10) as resp:
            datos = json.loads(resp.read().decode())
        self.assertIn("estado", datos)
        self.assertIsInstance(datos["mensajes"], list)
        self.assertIsInstance(datos["presentes"], list)

    def test_chat_enviar_sin_conexion_503(self):
        req = urllib.request.Request(
            self._url("/chat"), data=b"hola", method="POST", headers=_auth()
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 503)

    def test_iniciar_bot_manda_whisper_autenticado(self):
        instancia = dashboard.INSTANCES_DIR / "9"
        instancia.mkdir(parents=True, exist_ok=True)
        (instancia / "aura.cfg").write_text("bnet_username = hostbot9\n")

        enviados = []
        chat_real = dashboard.CHAT

        class ChatFalso:
            estado = "conectado"

            @staticmethod
            def enviar(texto):
                enviados.append(texto)
                return True

        dashboard.CHAT = ChatFalso()
        try:
            req = urllib.request.Request(
                self._url("/bot/iniciar"), data=b"9", method="POST", headers=_auth()
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn("hostbot9", resp.read().decode())
        finally:
            dashboard.CHAT = chat_real

        self.assertEqual(enviados, ["/w hostbot9 !start"])

    def test_iniciar_bot_no_acepta_instancia_inventada(self):
        req = urllib.request.Request(
            self._url("/bot/iniciar"), data=b"99", method="POST", headers=_auth()
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)

    # --- acciones ---------------------------------------------------------------
    def test_accion_valida_encola_pedido(self):
        req = urllib.request.Request(
            self._url("/accion/backup"), data=b"", method="POST", headers=_auth()
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            datos = json.loads(resp.read().decode())
        pedido = self.spool / f"{datos['id']}.pedido"
        self.assertTrue(pedido.is_file())
        self.assertEqual(pedido.read_text().splitlines()[0], "backup")
        pedido.unlink()

    def test_reparar_caidos_encola_pedido(self):
        req = urllib.request.Request(
            self._url("/accion/reparar-caidos"), data=b"", method="POST", headers=_auth()
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            datos = json.loads(resp.read().decode())
        pedido = self.spool / f"{datos['id']}.pedido"
        self.assertTrue(pedido.is_file())
        self.assertEqual(pedido.read_text().splitlines()[0], "reparar-caidos")
        pedido.unlink()

    def test_accion_desconocida_400(self):
        req = urllib.request.Request(
            self._url("/accion/rm-rf"), data=b"", method="POST", headers=_auth()
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)

    def test_accion_bot_arg_invalido_400(self):
        req = urllib.request.Request(
            self._url("/accion/reiniciar-bot"), data=b"1; rm -rf /",
            method="POST", headers=_auth()
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)

    def test_accion_de_otro_origen_403(self):
        headers = _auth()
        headers["Sec-Fetch-Site"] = "cross-site"
        req = urllib.request.Request(
            self._url("/accion/backup"), data=b"", method="POST", headers=headers
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)

    def test_resultado_de_accion(self):
        dashboard.RESULTADOS_DIR.mkdir(exist_ok=True)
        (dashboard.RESULTADOS_DIR / "123-abcd.resultado").write_text("0\ntodo ok\n")
        req = urllib.request.Request(
            self._url("/accion/resultado?id=123-abcd"), headers=_auth()
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            datos = json.loads(resp.read().decode())
        self.assertTrue(datos["listo"])
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["salida"], "todo ok")

    def test_resultado_id_raro_no_lee_archivos(self):
        req = urllib.request.Request(
            self._url("/accion/resultado?id=../../etc/passwd"), headers=_auth()
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            datos = json.loads(resp.read().decode())
        self.assertTrue(datos["listo"])
        self.assertFalse(datos["ok"])


class TestClienteChat(unittest.TestCase):
    """El protocolo chat/telnet de bnetd, contra un PvPGN de mentira: byte
    0x03, prompts de usuario/contraseña, y lineas 'CODIGO PALABRA args'."""

    def _bnetd_falso(self, respuestas: bytes):
        """Server de un solo cliente; devuelve (puerto, lo_que_recibio)."""
        import socket as s
        recibido = []
        srv = s.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        listo = threading.Event()

        def atender():
            conn, _ = srv.accept()
            conn.settimeout(5)
            datos = b""
            try:
                # 0x03 + usuario\r\n + clave\r\n
                while datos.count(b"\r\n") < 2:
                    datos += conn.recv(1024)
                recibido.append(datos)
                conn.sendall(respuestas)
                listo.set()
                # dejar la conexion abierta para que enviar() funcione
                while True:
                    extra = conn.recv(1024)
                    if not extra:
                        break
                    recibido.append(extra)
            except OSError:
                pass
            finally:
                conn.close()
                srv.close()

        threading.Thread(target=atender, daemon=True).start()
        return srv.getsockname()[1], recibido, listo

    def test_login_canal_y_mensajes(self):
        respuestas = (b'2010 NAME panel\r\n'
                      b'1007 CHANNEL "W3"\r\n'
                      b'1001 USER pepe 0010 [W3XP]\r\n'
                      b'1005 TALK pepe 0010 "hola muchachos"\r\n'
                      b'1002 JOIN valen 0000\r\n')
        puerto, recibido, listo = self._bnetd_falso(respuestas)

        cliente = dashboard.ClienteChat()
        cliente.usuario, cliente.clave, cliente.canal = "panel", "secreta", "W3"
        viejo = dashboard.PVPGN_PORT
        dashboard.PVPGN_PORT = puerto
        try:
            hilo = threading.Thread(target=cliente._sesion, daemon=True)
            hilo.start()
            self.assertTrue(listo.wait(5))
            for _ in range(50):
                if cliente.desde(0) and "valen" in cliente.presentes:
                    break
                import time
                time.sleep(0.1)
        finally:
            dashboard.PVPGN_PORT = viejo

        self.assertTrue(cliente.estado.startswith("conectado"), cliente.estado)
        self.assertIn("pepe", cliente.presentes)
        self.assertIn("valen", cliente.presentes)
        textos = [m["texto"] for m in cliente.desde(0)]
        self.assertIn("hola muchachos", textos)
        # el login viajo como corresponde: 0x03 + usuario + clave
        self.assertTrue(recibido[0].startswith(b"\x03panel\r\n"))

    def test_login_rechazado_no_revienta(self):
        puerto, _, _ = self._bnetd_falso(b"Login failed.\r\n")
        cliente = dashboard.ClienteChat()
        cliente.usuario, cliente.clave = "panel", "mala"
        viejo = dashboard.PVPGN_PORT
        dashboard.PVPGN_PORT = puerto
        try:
            cliente._sesion()  # tiene que volver solo, sin excepcion
        finally:
            dashboard.PVPGN_PORT = viejo
        self.assertIn("rechazado", cliente.estado)


if __name__ == "__main__":
    unittest.main()
