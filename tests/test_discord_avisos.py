"""Pruebas del parser liviano de journals para Discord."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
