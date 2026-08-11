#!/usr/bin/env python3
"""Avisos livianos de WC3 Revival hacia Discord usando solo stdlib.

Modos:
  follow                 sigue los journals de Aura y avisa lobbies/arranques
  discover               verifica el token y guarda guild/canales en el env
  failure UNIDAD         avisa que una unidad systemd fallo
  disk-check [UMBRAL]    avisa si / supera el porcentaje indicado
  backup-ok              manda como maximo un OK semanal de backup
  test-lobbies           mensaje de prueba a #lobbies
  test-estado            mensaje de prueba a #estado
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

try:  # fcntl no existe en Windows; el servicio real corre en Linux.
    import fcntl
except ImportError:  # pragma: no cover - solo facilita tests locales
    fcntl = None  # type: ignore[assignment]


CONFIG_PATH = Path(os.environ.get("WC3_DISCORD_ENV", "/opt/wc3/discord-avisos.env"))
STATE_DIR = Path(os.environ.get("WC3_DISCORD_STATE", "/var/lib/wc3-discord"))
REPO_DIR = Path(os.environ.get("WC3_REPO_DIR", "/opt/wc3-repo"))
DISCORD_API = "https://discord.com/api/v10"
INSTANCE_COUNT = 9
NOTICE_COOLDOWN = 600
FAILURE_COOLDOWN = 600
POST_INTERVAL = 3.0

JOIN_RE = re.compile(
    r"\[GAME: (?P<game>.+?)\] player \[(?P<player>[^|\]]+)(?:\|[^\]]*)?\] joined the game"
)
DELETE_RE = re.compile(
    r"\[GAME: (?P<game>.+?)\] deleting player \[(?P<player>[^\]]+)\]:"
)
START_RE = re.compile(
    r"\[GAME: (?P<game>.+?)\] started loading with (?P<count>\d+) players"
)
LOBBY_EXPIRED_RE = re.compile(r"\[GAME: .+?\] is over \(lobby time limit hit\)")
UNIT_RE = re.compile(r"wc3-hostbot@(?P<number>\d+)\.service")


def log(message: str) -> None:
    print(f"[discord-avisos] {message}", flush=True)


def read_env(path: Path = CONFIG_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            parsed = shlex.split(value, comments=False, posix=True)
            values[key] = parsed[0] if len(parsed) == 1 else value
        except ValueError:
            values[key] = value
    return values


def require_config(*keys: str) -> dict[str, str]:
    config = read_env()
    missing = [key for key in keys if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"faltan {', '.join(missing)} en {CONFIG_PATH}; el token no debe ir en el repo"
        )
    return config


def update_env(values: dict[str, str], path: Path = CONFIG_PATH) -> None:
    """Actualiza claves sin imprimir ni reescribir el token en la consola."""
    current = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    result: list[str] = []
    for line in current:
        if "=" not in line or line.lstrip().startswith("#"):
            result.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in pending:
            result.append(f"{key}={pending.pop(key)}")
        else:
            result.append(line)
    for key, value in pending.items():
        result.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(result).rstrip() + "\n")
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def discord_request(
    token: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        DISCORD_API + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "WC3-Revival-Discord/1.0",
        },
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                detail = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                detail = {}
            if error.code == 429 and attempt < 4:
                retry_after = float(detail.get("retry_after", 1.0))
                time.sleep(max(0.5, min(retry_after, 60.0)))
                continue
            message = str(detail.get("message", "respuesta sin detalle"))
            raise RuntimeError(f"Discord API HTTP {error.code}: {message}") from None
        except urllib.error.URLError as error:
            if attempt < 4:
                time.sleep(min(2**attempt, 15))
                continue
            raise RuntimeError(f"Discord API no disponible: {error.reason}") from None
    raise RuntimeError("Discord API no respondio despues de los reintentos")


@contextmanager
def file_lock(name: str) -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_DIR / name
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state() -> dict[str, Any]:
    path = STATE_DIR / "state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "state.json"
    fd, temporary = tempfile.mkstemp(prefix="state.", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def post_message(channel_key: str, content: str) -> None:
    config = require_config("DISCORD_BOT_TOKEN", channel_key)
    with file_lock("post.lock"):
        stamp_path = STATE_DIR / "last-post"
        try:
            previous = float(stamp_path.read_text(encoding="ascii"))
        except (FileNotFoundError, ValueError):
            previous = 0.0
        delay = POST_INTERVAL - (time.time() - previous)
        if delay > 0:
            time.sleep(delay)
        discord_request(
            config["DISCORD_BOT_TOKEN"],
            "POST",
            f"/channels/{config[channel_key]}/messages",
            {"content": content},
        )
        stamp_path.write_text(str(time.time()), encoding="ascii")


def canonical_channel_name(value: object) -> str:
    """Devuelve el nombre logico aunque Discord use un prefijo decorativo."""
    name = str(value).casefold().strip()
    return name.rsplit("┃", 1)[-1].strip().lstrip("#").strip()


def discover() -> None:
    config = require_config("DISCORD_BOT_TOKEN")
    token = config["DISCORD_BOT_TOKEN"]
    bot = discord_request(token, "GET", "/users/@me")
    guilds = discord_request(token, "GET", "/users/@me/guilds")
    matches = [g for g in guilds if str(g.get("name", "")).casefold() == "gryz wiii"]
    if not matches and len(guilds) == 1:
        matches = guilds
    if len(matches) != 1:
        names = ", ".join(str(g.get("name", "?")) for g in guilds) or "ninguno"
        raise RuntimeError(f"no pude elegir el servidor Gryz WIII; visibles: {names}")
    guild = matches[0]
    channels = discord_request(token, "GET", f"/guilds/{guild['id']}/channels")

    def channel_id(name: str) -> str:
        found = [
            c for c in channels
            if canonical_channel_name(c.get("name", "")) == name
            and int(c.get("type", -1)) == 0
        ]
        if len(found) != 1:
            raise RuntimeError(f"falta un unico canal de texto #{name} en {guild['name']}")
        return str(found[0]["id"])

    update_env(
        {
            "DISCORD_GUILD_ID": str(guild["id"]),
            "DISCORD_LOBBIES_CHANNEL_ID": channel_id("lobbies"),
            "DISCORD_ESTADO_CHANNEL_ID": channel_id("estado"),
            "DISCORD_INVITE_URL": "https://discord.gg/SnSSX2rReT",
            "DISCORD_DISK_THRESHOLD": "85",
        }
    )
    username = str(bot.get("username", "bot"))
    log(f"bot verificado: {username}; servidor: {guild['name']}; canales: #lobbies y #estado")


def parse_instance_env(number: int) -> str:
    path = REPO_DIR / "config" / "hostbot" / f"instance-{number}.env"
    if not path.exists():
        return f"Hostbot {number}"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("WC3_BOT_AUTOHOSTNAME="):
            value = line.split("=", 1)[1].strip()
            try:
                parsed = shlex.split(value)
                return parsed[0] if parsed else f"Hostbot {number}"
            except ValueError:
                return value.strip('"')
    return f"Hostbot {number}"


def discover_capacity(unit: str) -> int:
    result = subprocess.run(
        [
            "journalctl", "-u", unit, "-b", "--no-pager", "-o", "cat",
            "--grep", "calculated map_numplayers",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    matches = re.findall(r"calculated map_numplayers = (\d+)", result.stdout)
    return int(matches[-1]) if matches else 12


def event_from_message(message: str) -> tuple[str, dict[str, Any]] | None:
    match = JOIN_RE.search(message)
    if match:
        return "join", match.groupdict()
    match = DELETE_RE.search(message)
    if match:
        return "delete", match.groupdict()
    match = START_RE.search(message)
    if match:
        data: dict[str, Any] = match.groupdict()
        data["count"] = int(data["count"])
        return "start", data
    if LOBBY_EXPIRED_RE.search(message):
        return "expired", {}
    return None


def cooldown_allows(key: str, seconds: int) -> bool:
    now = time.time()
    with file_lock("state.lock"):
        state = read_state()
        cooldowns = state.setdefault("cooldowns", {})
        previous = float(cooldowns.get(key, 0))
        if now - previous < seconds:
            return False
        cooldowns[key] = now
        write_state(state)
        return True


def follow() -> None:
    require_config(
        "DISCORD_BOT_TOKEN",
        "DISCORD_LOBBIES_CHANNEL_ID",
        "DISCORD_ESTADO_CHANNEL_ID",
    )
    units = [f"wc3-hostbot@{number}.service" for number in range(1, INSTANCE_COUNT + 1)]
    maps = {unit: parse_instance_env(index + 1) for index, unit in enumerate(units)}
    capacities = {unit: discover_capacity(unit) for unit in units}
    players: dict[str, set[str]] = {unit: set() for unit in units}
    command = ["journalctl", "--follow", "--no-tail", "--output=json", "--no-pager"]
    for unit in units:
        command.extend(["--unit", unit])

    log("escuchando journals de 9 hostbots (event-driven, sin polling)")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for raw in process.stdout:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        unit = str(record.get("_SYSTEMD_UNIT", ""))
        if unit not in players:
            continue
        event = event_from_message(str(record.get("MESSAGE", "")))
        if event is None:
            continue
        kind, data = event
        if kind == "join":
            was_empty = not players[unit]
            player = str(data["player"])
            players[unit].add(player.casefold())
            if was_empty and cooldown_allows(f"lobby:{unit}", NOTICE_COOLDOWN):
                remaining = max(capacities[unit] - len(players[unit]), 0)
                try:
                    post_message(
                        "DISCORD_LOBBIES_CHANNEL_ID",
                        f"🎮 **{player}** entró al lobby de **{maps[unit]}** "
                        f"(quedan {remaining} lugares). ¡Sumate!",
                    )
                except RuntimeError as error:
                    log(f"no pude avisar entrada: {error}")
        elif kind == "delete":
            players[unit].discard(str(data["player"]).casefold())
        elif kind == "start":
            count = int(data["count"])
            players[unit].clear()
            try:
                post_message(
                    "DISCORD_LOBBIES_CHANNEL_ID",
                    f"⚔️ Arrancó **{maps[unit]}** con {count} jugador{'es' if count != 1 else ''}.",
                )
            except RuntimeError as error:
                log(f"no pude avisar arranque: {error}")
        elif kind == "expired":
            players[unit].clear()

    return_code = process.wait()
    raise RuntimeError(f"journalctl termino inesperadamente con codigo {return_code}")


def failure(unit: str) -> None:
    if unit.startswith("hostbot-") and unit.removeprefix("hostbot-").isdigit():
        unit = f"wc3-hostbot@{unit.removeprefix('hostbot-')}.service"
    elif unit == "pvpgn":
        unit = "pvpgn.service"
    elif unit == "backup":
        unit = "wc3-backup.service"
    unit = unit.replace("\\x40", "@").replace("%40", "@")
    if not cooldown_allows(f"failure:{unit}", FAILURE_COOLDOWN):
        log(f"fallo repetido de {unit} suprimido por 10 minutos")
        return
    post_message(
        "DISCORD_ESTADO_CHANNEL_ID",
        f"🚨 El servicio **{unit}** pasó a estado failed. Revisar el VPS.",
    )


def disk_check(threshold: int | None = None) -> None:
    config = require_config("DISCORD_BOT_TOKEN", "DISCORD_ESTADO_CHANNEL_ID")
    configured = int(config.get("DISCORD_DISK_THRESHOLD", "85"))
    limit = configured if threshold is None else threshold
    usage = shutil.disk_usage("/")
    percent = round((usage.used / usage.total) * 100)
    if percent >= limit and cooldown_allows("disk-high", 6 * 3600):
        post_message(
            "DISCORD_ESTADO_CHANNEL_ID",
            f"💽 Disco del VPS al **{percent}%** (umbral {limit}%).",
        )
    else:
        log(f"disco {percent}%: sin aviso (umbral {limit}%)")


def backup_ok() -> None:
    if cooldown_allows("backup-ok", 7 * 24 * 3600):
        post_message(
            "DISCORD_ESTADO_CHANNEL_ID",
            "✅ Resumen semanal: el backup diario de WC3 Revival está funcionando.",
        )
    else:
        log("backup OK semanal ya informado; no envio otro")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise RuntimeError("falta modo: follow, discover, failure, disk-check o test")
    mode = argv[1]
    if mode == "follow":
        follow()
    elif mode == "discover":
        discover()
    elif mode == "failure" and len(argv) == 3:
        failure(argv[2])
    elif mode == "disk-check":
        disk_check(int(argv[2]) if len(argv) == 3 else None)
    elif mode == "backup-ok":
        backup_ok()
    elif mode == "test-lobbies":
        post_message("DISCORD_LOBBIES_CHANNEL_ID", "🧪 Prueba de avisos de WC3 Revival: #lobbies conectado.")
    elif mode == "test-estado":
        post_message("DISCORD_ESTADO_CHANNEL_ID", "🧪 Prueba de avisos de WC3 Revival: #estado conectado.")
    else:
        raise RuntimeError(f"modo o argumentos invalidos: {' '.join(argv[1:])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (RuntimeError, ValueError) as error:
        log(f"ERROR: {error}")
        raise SystemExit(1)
