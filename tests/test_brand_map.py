"""Tests de brand-map.py / make-preview.py contra un .w3x sintetico.

No requiere mapas reales ni archivos del juego: arma un .w3x valido (header
HM3W de 512 bytes + MPQ v1 con war3map.w3i adentro) usando el mismo builder
que test_inspect_map.py, y despues le inyecta la preview.

Los tests que necesitan smpq o Pillow se saltean solos si no estan instalados,
asi que `make validate` no se rompe en una maquina pelada.

Correr con:  python3 -m unittest discover tests
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_DIR / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_inspect_map import build_hm3w, build_w3i  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HAS_SMPQ = shutil.which("smpq") is not None
try:
    import PIL  # noqa: F401

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
try:
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def build_w3x(path: Path, extra_bytes: int = 0) -> Path:
    """Arma un .w3x sintetico: header HM3W + MPQ v1 con war3map.w3i."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "war3map.w3i").write_bytes(build_w3i())
        if extra_bytes:
            # Relleno realmente incompresible (zlib no lo achica) para acercar
            # el mapa al techo de 8 MiB.
            (tmp / "war3map.j").write_bytes(os.urandom(extra_bytes))
        files = [f.name for f in sorted(tmp.iterdir())]
        mpq = tmp / "inner.mpq"
        subprocess.run(
            ["smpq", "--create", "--mpq-version", "1", str(mpq), *files],
            cwd=tmp,
            check=True,
            capture_output=True,
        )
        path.write_bytes(build_hm3w("Mapa Sintetico", 12) + mpq.read_bytes())
    return path


def mpq_names(path: Path) -> list:
    out = subprocess.run(
        ["smpq", "--list", str(path)], capture_output=True, text=True, check=True
    ).stdout
    return [line.split(None, 3)[3] for line in out.splitlines() if len(line.split(None, 3)) == 4]


@unittest.skipUnless(HAS_YAML, "PyYAML no instalado")
class TestLobbyNames(unittest.TestCase):
    """El limite de 31 bytes de aura.cpp:879 es duro: si se pasa, el bot
    rechaza la partida con 'The game name is too long'."""

    LIMIT = 31

    def setUp(self):
        import yaml

        data = yaml.safe_load((REPO_DIR / "maps" / "lobbies.yaml").read_text(encoding="utf-8"))
        self.lobbies = data["lobbies"]

    def test_display_names_entran_en_el_limite(self):
        for entry in self.lobbies:
            name = entry.get("display_name")
            if not name:
                continue
            with self.subTest(entry["id"]):
                self.assertLessEqual(
                    len(name.encode("utf-8")),
                    self.LIMIT,
                    f"'{name}' mide {len(name.encode('utf-8'))} bytes",
                )

    def test_plain_names_entran_en_el_limite(self):
        for entry in self.lobbies:
            name = entry.get("plain_name")
            if not name:
                continue
            with self.subTest(entry["id"]):
                self.assertLessEqual(len(name.encode("utf-8")), self.LIMIT)

    def test_ids_unicos_y_default_al_final(self):
        ids = [e["id"] for e in self.lobbies]
        self.assertEqual(len(ids), len(set(ids)), "hay ids repetidos")
        self.assertEqual(ids[-1], "default", "el entry comodin tiene que ir ultimo")

    def test_el_patron_especifico_gana_al_generico(self):
        brand = _load("brand_map", "brand-map.py")
        elegido = brand.pick_theme(self.lobbies, Path("Anime Fight Arena0.1.w3x"), None)
        self.assertEqual(elegido["id"], "anime-fight-arena")
        elegido = brand.pick_theme(self.lobbies, Path("Anime Fight Beta 1.39b.w3x"), None)
        self.assertEqual(elegido["id"], "anime-fight")


@unittest.skipUnless(HAS_PIL, "Pillow no instalado")
class TestMakePreview(unittest.TestCase):
    def test_render_tga_128(self):
        preview = _load("make_preview", "make-preview.py")
        img = preview.render({"title": "Test", "subtitle": "v1", "motif": "swords"}, 128)
        self.assertEqual(img.size, (128, 128))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "war3mapPreview.tga"
            preview.save(img, out)
            head = out.read_bytes()[:3]
            # TGA sin comprimir, truecolor: tipo de imagen 2 en el byte 2.
            self.assertEqual(head[2], 2, "el TGA tiene que quedar sin comprimir (RLE no)")

    def test_motivo_desconocido_falla_claro(self):
        preview = _load("make_preview", "make-preview.py")
        with self.assertRaises(preview.PreviewError):
            preview.render({"motif": "no-existe"}, 128)


@unittest.skipUnless(HAS_SMPQ and HAS_PIL and HAS_YAML, "faltan smpq/Pillow/PyYAML")
class TestBrandMap(unittest.TestCase):
    def test_inyecta_y_deja_el_w3x_sano(self):
        brand = _load("brand_map", "brand-map.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = build_w3x(tmp / "DotA v6.83d.w3x")
            antes = src.stat().st_size
            rc = brand.main([str(src), "--out-dir", str(tmp / "out")])
            self.assertEqual(rc, 0)
            dest = tmp / "out" / src.name
            self.assertTrue(dest.exists())
            self.assertEqual(dest.read_bytes()[:4], b"HM3W", "se rompio el header")
            self.assertIn("war3mapPreview.tga", mpq_names(dest))
            self.assertGreater(dest.stat().st_size, antes)
            # El original no se toca
            self.assertNotIn("war3mapPreview.tga", mpq_names(src))

    def test_respeta_la_preview_que_el_mapa_ya_traiga(self):
        """Muchos mapas custom ya vienen con arte propio del autor: pisarlo
        con un dibujo generado seria un downgrade. Solo con --force."""
        brand = _load("brand_map", "brand-map.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = build_w3x(tmp / "DotA v6.83d.w3x")
            out = tmp / "out"
            self.assertEqual(brand.main([str(src), "--out-dir", str(out)]), 0)
            dest = out / src.name
            primera = dest.read_bytes()

            # Segunda pasada sobre el mapa que YA tiene preview: no la toca,
            # pero SI lo copia al destino. Con --out-dir este script es tambien
            # el que instala los mapas donde el bot los busca, asi que saltear
            # la copia dejaria afuera justo a los que no hay que modificar.
            out2 = tmp / "out2"
            self.assertEqual(brand.main([str(dest), "--out-dir", str(out2)]), 0)
            copia = out2 / dest.name
            self.assertTrue(copia.exists(), "tendria que haberlo copiado igual")
            self.assertEqual(copia.read_bytes(), primera, "lo modifico en vez de copiarlo")
            self.assertEqual(dest.read_bytes(), primera, "piso la preview existente")

    def test_aborta_si_pasa_el_techo_de_8_mib(self):
        brand = _load("brand_map", "brand-map.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Relleno incompresible hasta quedar a ~20 KB del techo: la
            # preview pesa mas que eso, asi que tiene que abortar.
            src = build_w3x(tmp / "DotA borde.w3x", extra_bytes=brand.MAX_MAP_BYTES - 20480)
            self.assertLess(src.stat().st_size, brand.MAX_MAP_BYTES)
            rc = brand.main([str(src), "--out-dir", str(tmp / "out")])
            self.assertEqual(rc, 1, "tendria que haber fallado por tamano")
            self.assertFalse((tmp / "out" / src.name).exists(), "no se limpio la salida")


if __name__ == "__main__":
    unittest.main()
