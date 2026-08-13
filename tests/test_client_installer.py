import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class ClientInstallerTests(unittest.TestCase):
    def test_game_installer_upgrades_127a_to_127b(self):
        installer = (REPO / "kit" / "INSTALAR-JUEGO.bat.tpl").read_text(
            encoding="utf-8"
        )

        self.assertIn('if "!WC3SIZE!"=="514536"', installer)
        self.assertIn('if "!WC3SIZE!"=="515048"', installer)
        self.assertIn("War3TFT_127b_Castellano.exe", installer)
        self.assertIn("War3TFT_127b_English.exe", installer)
        self.assertIn("Get-AuthenticodeSignature", installer)
        self.assertIn("*Blizzard Entertainment*", installer)
        self.assertIn('start "" /wait "%PATCH%"', installer)
        self.assertIn('call "%~dp0INSTALAR.bat"', installer)

    def test_main_installer_hands_127a_to_the_automatic_updater(self):
        installer = (REPO / "kit" / "INSTALAR.bat.tpl").read_text(
            encoding="utf-8"
        )

        self.assertIn('if "!WC3SIZE!"=="515048"', installer)
        self.assertIn('else if "!WC3SIZE!"=="514536"', installer)
        self.assertIn("goto :instalar_juego", installer)
        self.assertIn('call "%~dp0INSTALAR-JUEGO.bat"', installer)
        version_block = installer.split("[2/4] Verificando la version", 1)[1].split(
            "[3/4] Instalando el loader", 1
        )[0]
        self.assertIn("No voy a parchear una version desconocida", version_block)
        self.assertIn("exit /b 1", version_block)

    def test_every_internal_batch_jump_has_a_label(self):
        for name in ("INSTALAR.bat.tpl", "INSTALAR-JUEGO.bat.tpl"):
            installer = (REPO / "kit" / name).read_text(encoding="utf-8")
            labels = set(re.findall(r"(?im)^:([a-z0-9_-]+)\s*$", installer))
            references = set(
                re.findall(r"(?i)\b(?:goto|call)\s+:([a-z0-9_-]+)", installer)
            )

            self.assertEqual(set(), references - labels, name)

    def test_ninth_instance_ports_fit_the_documented_range(self):
        env_example = (REPO / ".env.example").read_text(encoding="utf-8")
        instance = (REPO / "config" / "hostbot" / "instance-9.env").read_text(
            encoding="utf-8"
        )

        end = int(re.search(r"WC3_BOT_PORT_RANGE=\d+:(\d+)", env_example).group(1))
        host_port = int(re.search(r"WC3_BOT_HOSTPORT=(\d+)", instance).group(1))
        reconnect_port = int(
            re.search(r"WC3_BOT_RECONNECTPORT=(\d+)", instance).group(1)
        )

        self.assertLessEqual(host_port, end)
        self.assertLessEqual(reconnect_port, end)
        self.assertEqual("hostbot9", re.search(r"WC3_BOT_USERNAME=(\w+)", instance).group(1))


if __name__ == "__main__":
    unittest.main()
