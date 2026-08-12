"""Pruebas del parser liviano de journals para Discord."""

import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "discord-avisos.py"
SPEC = importlib.util.spec_from_file_location("discord_avisos", SCRIPT)
avisos = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(avisos)


class TestJournalParser(unittest.TestCase):
    def test_join_sin_exponer_ip(self):
        event = avisos.event_from_message(
            "[GAME: FOC 9.6G03 ES] player [lobogriz|190.1.2.3] joined the game"
        )
        self.assertEqual(event[0], "join")
        self.assertEqual(event[1]["player"], "lobogriz")
        self.assertNotIn("190.1.2.3", event[1]["player"])

    def test_delete(self):
        event = avisos.event_from_message(
            "[GAME: FOC] deleting player [lobogriz]: has left the game voluntarily"
        )
        self.assertEqual(event, ("delete", {"game": "FOC", "player": "lobogriz"}))

    def test_start(self):
        event = avisos.event_from_message(
            "[GAME: FOC] started loading with 7 players"
        )
        self.assertEqual(event, ("start", {"game": "FOC", "count": 7}))

    def test_rehost_no_es_evento_publicable(self):
        self.assertIsNone(
            avisos.event_from_message(
                "[AURA] creating game [Anime Fight Beta 1.39b]"
            )
        )
        self.assertEqual(
            avisos.event_from_message(
                "[GAME: Anime Fight] is over (lobby time limit hit)"
            ),
            ("expired", {}),
        )


class TestConfig(unittest.TestCase):
    def test_nombres_de_canales_decorados(self):
        self.assertEqual(avisos.canonical_channel_name("🤖┃lobbies"), "lobbies")
        self.assertEqual(avisos.canonical_channel_name("📊┃Estado"), "estado")
        self.assertEqual(avisos.canonical_channel_name("lobbies"), "lobbies")

    def test_update_env_preserva_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "avisos.env"
            path.write_text("DISCORD_BOT_TOKEN=secreto\n", encoding="utf-8")
            avisos.update_env({"DISCORD_GUILD_ID": "123"}, path)
            values = avisos.read_env(path)
            self.assertEqual(values["DISCORD_BOT_TOKEN"], "secreto")
            self.assertEqual(values["DISCORD_GUILD_ID"], "123")
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def test_descubre_instancias_aunque_haya_huecos(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number in (3, 4, 7, 9):
                (root / str(number)).mkdir()
            with mock.patch.object(avisos, "HOSTBOT_INSTANCES_DIR", root), \
                    mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("WC3_HOSTBOT_INSTANCE_NUMBERS", None)
                self.assertEqual(avisos.instance_numbers(), [3, 4, 7, 9])

    def test_instancias_pueden_declararse_por_env(self):
        with mock.patch.dict(
            os.environ, {"WC3_HOSTBOT_INSTANCE_NUMBERS": "9, 3,7"}
        ):
            self.assertEqual(avisos.instance_numbers(), [3, 7, 9])


class TestLobbyState(unittest.TestCase):
    def setUp(self):
        self.unit = "wc3-hostbot@1.service"
        self.players = {self.unit: set()}
        self.pending = {}

    def apply(self, kind, player="jugador", now=100.0):
        return avisos.apply_lobby_event(
            self.players, self.pending, self.unit, kind, {"player": player}, now
        )

    def test_primer_humano_espera_30_segundos(self):
        self.assertFalse(self.apply("join"))
        self.assertEqual(self.pending[self.unit], 130.0)
        self.assertEqual(avisos.due_first_notices(self.players, self.pending, 129.9), [])
        self.assertEqual(avisos.due_first_notices(self.players, self.pending, 130.0), [self.unit])

    def test_si_se_va_antes_se_cancela(self):
        self.apply("join")
        self.apply("delete")
        self.assertNotIn(self.unit, self.pending)

    def test_al_cruzar_tres_dispara_y_cancela_el_primero(self):
        self.apply("join", "uno")
        self.assertFalse(self.apply("join", "dos", 101.0))
        self.assertTrue(self.apply("join", "tres", 102.0))
        self.assertNotIn(self.unit, self.pending)

    def test_horario_silencioso(self):
        local = list(time.localtime())
        local[3] = 3
        local[4] = local[5] = 0
        stamp = time.mktime(tuple(local))
        self.assertTrue(avisos.quiet_hours({}, stamp))
        local[3] = 12
        stamp = time.mktime(tuple(local))
        self.assertFalse(avisos.quiet_hours({}, stamp))


class TestLobbyHealth(unittest.TestCase):
    @staticmethod
    def result(stdout):
        return avisos.subprocess.CompletedProcess([], 0, stdout=stdout)

    def test_rechaza_lobby_anterior_al_reinicio_de_pvpgn(self):
        event = '{"MESSAGE":"Creating public game [FOC]","__MONOTONIC_TIMESTAMP":"150"}\n'
        results = [self.result("200\n"), self.result("100\n"), self.result(event)]
        with mock.patch.object(avisos.subprocess, "run", side_effect=results):
            self.assertFalse(avisos.lobby_published_since_start("wc3-hostbot@9.service"))

    def test_acepta_lobby_antiguo_posterior_a_pvpgn_y_al_bot(self):
        event = '{"MESSAGE":"Creating public game [FOC]","__MONOTONIC_TIMESTAMP":"201"}\n'
        results = [self.result("200\n"), self.result("100\n"), self.result(event)]
        with mock.patch.object(avisos.subprocess, "run", side_effect=results) as run:
            self.assertTrue(avisos.lobby_published_since_start("wc3-hostbot@9.service"))
        self.assertNotIn("--since", run.call_args_list[-1].args[0])

    def test_red_sana_exige_dos_listeners_y_conexion_pvpgn(self):
        sockets = {
            ("0A", 6113, 0),
            ("0A", 6133, 0),
            ("01", 50000, 6112),
        }
        with mock.patch.object(avisos, "unit_main_pid", return_value=123), \
                mock.patch.object(avisos, "bot_ports", return_value=(6113, 6133)), \
                mock.patch.object(avisos, "tcp_sockets_for_pid", return_value=sockets):
            self.assertEqual(
                avisos.bot_network_health("wc3-hostbot@1.service", 1),
                (True, ""),
            )

    def test_red_rechaza_bot_sin_conexion_pvpgn(self):
        sockets = {("0A", 6113, 0), ("0A", 6133, 0)}
        with mock.patch.object(avisos, "unit_main_pid", return_value=123), \
                mock.patch.object(avisos, "bot_ports", return_value=(6113, 6133)), \
                mock.patch.object(avisos, "tcp_sockets_for_pid", return_value=sockets):
            healthy, reason = avisos.bot_network_health("wc3-hostbot@1.service", 1)
        self.assertFalse(healthy)
        self.assertIn("PvPGN", reason)


if __name__ == "__main__":
    unittest.main()
