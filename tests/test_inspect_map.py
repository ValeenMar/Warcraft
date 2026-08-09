"""Tests de inspect-map.py contra un .w3x sintetico generado aca mismo.

No requiere mapas reales ni archivos del juego: el test construye los bytes
del header HM3W y de un war3map.w3i (formato 25, TFT) segun el mismo layout
que implementa el parser. Con eso validamos parser y caminos de error; la
validacion contra mapas reales es parte de la fase 1 del RUNBOOK.

Correr con:  python3 -m unittest discover tests
"""

import importlib.util
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

# inspect-map.py tiene guion en el nombre: se importa via importlib
_SPEC = importlib.util.spec_from_file_location(
    "inspect_map", Path(__file__).resolve().parent.parent / "scripts" / "inspect-map.py"
)
inspect_map = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inspect_map)


def cstr(s: str) -> bytes:
    return s.encode("utf-8") + b"\x00"


def build_hm3w(name: str, max_players: int) -> bytes:
    """Header HM3W de 512 bytes, como el de un .w3x real."""
    body = b"HM3W" + struct.pack("<I", 0) + cstr(name) + struct.pack("<II", 0, max_players)
    return body.ljust(512, b"\x00")


def build_w3i(name="Mapa Sintetico", author="tester", slots=10, teams=2) -> bytes:
    """war3map.w3i minimo pero completo, formato 25 (TFT)."""
    b = io.BytesIO()
    b.write(struct.pack("<III", 25, 0, 6059))          # formato, saves, editor
    b.write(cstr(name) + cstr(author) + cstr("desc") + cstr("1v1"))
    b.write(struct.pack("<8f", *[0.0] * 8))            # limites de camara
    b.write(struct.pack("<4I", 0, 0, 0, 0))            # margenes
    b.write(struct.pack("<III", 64, 64, 0))            # ancho, alto, flags
    b.write(b"L")                                       # tileset
    b.write(struct.pack("<I", 0))                       # nro fondo de carga
    b.write(cstr("") + cstr("") + cstr("") + cstr(""))  # pantalla de carga
    b.write(struct.pack("<I", 0))                       # set de datos
    b.write(cstr("") + cstr("") + cstr("") + cstr(""))  # prologo
    b.write(struct.pack("<Ifff", 0, 0.0, 0.0, 0.0))     # niebla
    b.write(b"\x00" * 4)                                # color de niebla
    b.write(struct.pack("<I", 0))                       # clima
    b.write(cstr(""))                                   # ambiente de sonido
    b.write(b"L")                                       # tileset de luz
    b.write(b"\x00" * 4)                                # color de agua
    b.write(struct.pack("<I", slots))
    for i in range(slots):
        b.write(struct.pack("<IIII", i, 1, 1, 0))
        b.write(cstr(f"Player {i}"))
        b.write(struct.pack("<ffII", 0.0, 0.0, 0, 0))
    b.write(struct.pack("<I", teams))
    return b.getvalue()


class TestParseW3i(unittest.TestCase):
    def test_parse_synthetic_tft(self):
        meta = inspect_map.parse_w3i(build_w3i(slots=12, teams=3))
        self.assertEqual(meta["w3i_format"], 25)
        self.assertEqual(meta["name"], "Mapa Sintetico")
        self.assertEqual(meta["author"], "tester")
        self.assertEqual(meta["slots"], 12)
        self.assertEqual(meta["teams"], 3)

    def test_reject_unknown_format(self):
        bad = struct.pack("<I", 31) + b"\x00" * 64
        with self.assertRaises(inspect_map.InspectError):
            inspect_map.parse_w3i(bad)

    def test_truncated_w3i(self):
        with self.assertRaises(inspect_map.InspectError):
            inspect_map.parse_w3i(build_w3i()[:40])


class TestHm3wHeader(unittest.TestCase):
    def test_parse_header(self):
        meta = inspect_map.parse_hm3w_header(build_hm3w("Pudge Wars", 12))
        self.assertEqual(meta["header_name"], "Pudge Wars")
        self.assertEqual(meta["header_max_players"], 12)

    def test_reject_non_map(self):
        with self.assertRaises(inspect_map.InspectError):
            inspect_map.parse_hm3w_header(b"PK\x03\x04" + b"\x00" * 100)


class TestCliOnSyntheticW3x(unittest.TestCase):
    """Camino completo por CLI con un .w3x sintetico (header valido, MPQ no
    legible): la metadata del header sale igual y el exit code es 2 con un
    mensaje claro, sin traceback."""

    def test_protected_map_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            w3x = Path(tmp) / "synthetic.w3x"
            # header valido + un MPQ falso (magic presente, contenido basura)
            w3x.write_bytes(build_hm3w("Synthetic Arena", 8) + b"MPQ\x1a" + b"\x00" * 64)

            stdout, stderr = io.StringIO(), io.StringIO()
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = stdout, stderr
            try:
                code = inspect_map.main([str(w3x)])
            finally:
                sys.stdout, sys.stderr = old_out, old_err

            self.assertEqual(code, 2)
            self.assertIn("Synthetic Arena", stdout.getvalue())
            err = stderr.getvalue()
            self.assertTrue("protegido" in err or "mpyq no esta instalado" in err, err)


if __name__ == "__main__":
    unittest.main()


class TestWtsTrigstrs(unittest.TestCase):
    """El editor no guarda el nombre ni la descripcion en el w3i: guarda
    referencias TRIGSTR_nnn y el texto va en war3map.wts. Sin resolverlas, la
    salida es inutil para saber de que se trata un mapa."""

    WTS = """\ufeffSTRING 4
{
Anime Fight Arena AI
}

STRING 6
// comentario del editor
{
Elegi tu heroe y peleá.
Modos: -ai para activar la IA
}

STRING 7
{
autor desconocido
}
""".encode("utf-8")

    def test_parse_wts(self):
        textos = inspect_map.parse_wts(self.WTS)
        self.assertEqual(textos[4], "Anime Fight Arena AI")
        self.assertEqual(textos[7], "autor desconocido")
        self.assertIn("-ai para activar la IA", textos[6])

    def test_resolve_trigstrs(self):
        meta = {
            "name": "TRIGSTR_004",
            "author": "TRIGSTR_007",
            "description": "TRIGSTR_006",
            "players_recommended": "TRIGSTR_999",  # sin entrada: se deja como esta
        }
        inspect_map.resolve_trigstrs(meta, inspect_map.parse_wts(self.WTS))
        self.assertEqual(meta["name"], "Anime Fight Arena AI")
        self.assertEqual(meta["author"], "autor desconocido")
        self.assertIn("Modos:", meta["description"])
        self.assertEqual(meta["players_recommended"], "TRIGSTR_999")

    def test_texto_literal_no_se_toca(self):
        meta = {"name": "DotA Allstars", "author": "IceFrog"}
        inspect_map.resolve_trigstrs(meta, {4: "otra cosa"})
        self.assertEqual(meta["name"], "DotA Allstars")
        self.assertEqual(meta["author"], "IceFrog")
