"""Invariantes de los tres elementos que ve el jugador al entrar a Battle.net."""

import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TestPresentation(unittest.TestCase):
    def test_realm_no_queda_con_nombre_default(self):
        cfg = (ROOT / "config/pvpgn/bnetd.conf.tpl").read_text(encoding="utf-8")
        self.assertIn('servername = "${WC3_REALM_NAME}"', cfg)

    def test_motd_es_un_solo_evento_para_no_repetir_rank(self):
        lineas = (ROOT / "config/pvpgn/w3motd.txt.tpl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(lineas), 1)
        self.assertIn("GRYZ WC3", lineas[0])
        self.assertIn("%u", lineas[0])
        self.assertIn("%g", lineas[0])

    def test_news_es_propio_y_tiene_fecha_valida(self):
        news = (ROOT / "config/pvpgn/news.txt.tpl").read_text(encoding="utf-8")
        self.assertRegex(news, r"^\{\d{2}/\d{2}/\d{4}\}")
        self.assertIn("GRYZ WC3", news)
        self.assertNotIn("pvpgn.berlios", news.lower())

    def test_banners_son_png_rgb_468x60(self):
        for nombre in ("banner.png", "banner-alt.png"):
            with self.subTest(nombre=nombre):
                data = (ROOT / "config/pvpgn" / nombre).read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                ancho, alto, profundidad, tipo = struct.unpack(">IIBB", data[16:26])
                self.assertEqual((ancho, alto), (468, 60))
                self.assertEqual(profundidad, 8)
                self.assertEqual(tipo, 2)  # PNG truecolor RGB, sin alfa

    def test_ad_json_alterna_dos_banners_con_url_configurable(self):
        ads = (ROOT / "config/pvpgn/ad.json.tpl").read_text(encoding="utf-8")
        self.assertIn('"ad000001.png"', ads)
        self.assertIn('"ad000002.png"', ads)
        self.assertEqual(ads.count('"url": "${WC3_SERVER_URL}"'), 2)


if __name__ == "__main__":
    unittest.main()
