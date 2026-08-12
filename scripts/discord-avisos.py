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
import select
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
PVPGN_PORT = int(os.environ.get("WC3_PVPGN_PORT", "6112"))
HOSTBOT_INSTANCES_DIR = Path(
    os.environ.get("WC3_HOSTBOT_INSTANCES_DIR", "/opt/wc3/hostbot/instances")
)
NOTICE_COOLDOWN = 600
GLOBAL_NOTICE_COOLDOWN = 120
FAILURE_COOLDOWN = 600
POST_INTERVAL = 3.0
FIRST_NOTICE_DELAY = 30
CROWD_THRESHOLD = 3

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


def instance_numbers() -> list[int]:
    """Instancias configuradas actualmente, aun cuando haya huecos numericos.

    Los servidores viejos usaban siempre 1..9.  Después de archivar un mapa
    puede quedar, por ejemplo, 3..7 y 9; descubrir los directorios evita que
    Discord denuncie como caidos bots que fueron retirados a proposito.
    """
    configured = os.environ.get("WC3_HOSTBOT_INSTANCE_NUMBERS", "").strip()
    if configured:
        numbers: set[int] = set()
        for raw in configured.split(","):
            value = raw.strip()
            if not value.isdigit() or int(value) <= 0:
                raise RuntimeError(
                    "WC3_HOSTBOT_INSTANCE_NUMBERS debe ser una lista como 1,2,5"
                )
            numbers.add(int(value))
        return sorted(numbers)

    try:
        discovered = sorted(
            int(path.name)
            for path in HOSTBOT_INSTANCES_DIR.iterdir()
            if path.is_dir() and path.name.isdigit()
        )
    except OSError:
        discovered = []
    return discovered or list(range(1, INSTANCE_COUNT + 1))


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


def cooldowns_allow(requirements: dict[str, int]) -> bool:
    """Consume varios cooldowns de forma atomica solo si todos permiten."""
    now = time.time()
    with file_lock("state.lock"):
        state = read_state()
        cooldowns = state.setdefault("cooldowns", {})
        if any(now - float(cooldowns.get(key, 0)) < seconds
               for key, seconds in requirements.items()):
            return False
        for key in requirements:
            cooldowns[key] = now
        write_state(state)
        return True


def quiet_hours(config: dict[str, str], when: float | None = None) -> bool:
    """True durante la ventana sin avisos sociales (default 01:00-09:00)."""
    start = int(config.get("DISCORD_QUIET_START", "1")) % 24
    end = int(config.get("DISCORD_QUIET_END", "9")) % 24
    hour = time.localtime(time.time() if when is None else when).tm_hour
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


def apply_lobby_event(
    players: dict[str, set[str]],
    pending: dict[str, float],
    unit: str,
    kind: str,
    data: dict[str, Any],
    now: float,
) -> bool:
    """Actualiza estado y devuelve True al cruzar de menos de 3 a 3 humanos."""
    if kind == "join":
        before = len(players[unit])
        players[unit].add(str(data["player"]).casefold())
        after = len(players[unit])
        if before == 0 and after == 1:
            pending[unit] = now + FIRST_NOTICE_DELAY
        if before < CROWD_THRESHOLD <= after:
            pending.pop(unit, None)
            return True
    elif kind == "delete":
        players[unit].discard(str(data["player"]).casefold())
        if not players[unit]:
            pending.pop(unit, None)
    elif kind in ("start", "expired"):
        players[unit].clear()
        pending.pop(unit, None)
    return False


def due_first_notices(
    players: dict[str, set[str]], pending: dict[str, float], now: float
) -> list[str]:
    due: list[str] = []
    for unit, deadline in list(pending.items()):
        if deadline <= now:
            pending.pop(unit, None)
            if 0 < len(players[unit]) < CROWD_THRESHOLD:
                due.append(unit)
    return due


def follow() -> None:
    config = require_config(
        "DISCORD_BOT_TOKEN",
        "DISCORD_LOBBIES_CHANNEL_ID",
        "DISCORD_ESTADO_CHANNEL_ID",
    )
    numbers = instance_numbers()
    units = [f"wc3-hostbot@{number}.service" for number in numbers]
    maps = {unit: parse_instance_env(number) for number, unit in zip(numbers, units)}
    capacities = {unit: discover_capacity(unit) for unit in units}
    players: dict[str, set[str]] = {unit: set() for unit in units}
    pending: dict[str, float] = {}
    command = ["journalctl", "--follow", "--no-tail", "--output=json", "--no-pager"]
    for unit in units:
        command.extend(["--unit", unit])

    log(f"escuchando journals de {len(units)} hostbots (event-driven, sin polling)")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    def send_first(unit: str) -> None:
        if quiet_hours(config):
            log(f"aviso social de {unit} omitido por horario silencioso")
            return
        if not cooldowns_allow({
            f"lobby:{unit}": NOTICE_COOLDOWN,
            "lobby:global": GLOBAL_NOTICE_COOLDOWN,
        }):
            return
        count = len(players[unit])
        remaining = max(capacities[unit] - count, 0)
        post_message(
            "DISCORD_LOBBIES_CHANNEL_ID",
            f"🎮 Hay {count} jugador{'es' if count != 1 else ''} esperando en "
            f"**{maps[unit]}** (quedan {remaining} lugares). ¡Sumate!",
        )

    def send_crowd(unit: str) -> None:
        if quiet_hours(config):
            log(f"aviso social de {unit} omitido por horario silencioso")
            return
        if not cooldowns_allow({
            f"crowd:{unit}": NOTICE_COOLDOWN,
            "lobby:global": GLOBAL_NOTICE_COOLDOWN,
        }):
            return
        count = len(players[unit])
        post_message(
            "DISCORD_LOBBIES_CHANNEL_ID",
            f"@here 🔥 **{maps[unit]}** ya tiene {count} jugadores. ¡Se arma!",
        )

    while process.poll() is None:
        readable, _, _ = select.select([process.stdout], [], [], 1.0)
        now = time.time()
        for unit in due_first_notices(players, pending, now):
            try:
                send_first(unit)
            except RuntimeError as error:
                log(f"no pude avisar entrada: {error}")
        if not readable:
            continue
        raw = process.stdout.readline()
        if not raw:
            continue
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
        crowded = apply_lobby_event(players, pending, unit, kind, data, now)
        if crowded:
            try:
                send_crowd(unit)
            except RuntimeError as error:
                log(f"no pude avisar lobby con gente: {error}")

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


def active_enter_monotonic(unit: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", unit, "-p", "ActiveEnterTimestampMonotonic", "--value"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def lobby_published_since_start(unit: str) -> bool:
    # Un lobby anterior al ultimo arranque de PvPGN ya no existe en la lista
    # del servidor aunque Aura siga active. Exigimos un Creating posterior al
    # arranque mas nuevo entre PvPGN y el propio bot. No usamos una ventana de
    # tiempo: un lobby sano puede permanecer abierto mucho mas de 30 minutos.
    threshold = max(active_enter_monotonic("pvpgn.service"),
                    active_enter_monotonic(unit))
    result = subprocess.run(
        ["journalctl", "-b", "-u", unit, "--no-pager", "-o", "json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for line in result.stdout.splitlines():
        try:
            record = json.loads(line)
            message = str(record.get("MESSAGE", ""))
            monotonic = int(record.get("__MONOTONIC_TIMESTAMP", "0"))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if monotonic >= threshold and "creating public game" in message.casefold():
            return True
    return False


def unit_main_pid(unit: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", unit, "--property=MainPID", "--value"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def bot_ports(number: int) -> tuple[int, int]:
    """Devuelve los puertos host/reconnect sin leer ni devolver credenciales."""
    values: dict[str, str] = {}
    path = HOSTBOT_INSTANCES_DIR / str(number) / "aura.cfg"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0, 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in {"bot_hostport", "bot_reconnectport"}:
            values[key] = value
    try:
        return int(values.get("bot_hostport", "0")), int(
            values.get("bot_reconnectport", "0")
        )
    except ValueError:
        return 0, 0


def tcp_sockets_for_pid(pid: int) -> set[tuple[str, int, int]]:
    """Retorna (estado, puerto local, puerto remoto) de un proceso Linux."""
    inodes: set[str] = set()
    try:
        descriptors = (Path("/proc") / str(pid) / "fd").iterdir()
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match:
                inodes.add(match.group(1))
    except OSError:
        return set()

    sockets: set[tuple[str, int, int]] = set()
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            rows = table.read_text(encoding="ascii", errors="replace").splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) < 10 or fields[9] not in inodes:
                continue
            try:
                local_port = int(fields[1].rsplit(":", 1)[1], 16)
                remote_port = int(fields[2].rsplit(":", 1)[1], 16)
            except (IndexError, ValueError):
                continue
            sockets.add((fields[3], local_port, remote_port))
    return sockets


def bot_network_health(unit: str, number: int) -> tuple[bool, str]:
    """Comprueba proceso, ambos listeners y sesion BNCS de una instancia."""
    pid = unit_main_pid(unit)
    if pid <= 0:
        return False, "no tiene proceso principal"
    host_port, reconnect_port = bot_ports(number)
    if not host_port or not reconnect_port:
        return False, "no pude leer sus puertos configurados"
    sockets = tcp_sockets_for_pid(pid)
    if ("0A", host_port, 0) not in sockets:
        return False, f"el puerto de partida {host_port} no está escuchando"
    if ("0A", reconnect_port, 0) not in sockets:
        return False, f"el puerto de reconexión {reconnect_port} no está escuchando"
    if not any(state == "01" and remote == PVPGN_PORT
               for state, _local, remote in sockets):
        return False, "no está conectado a PvPGN"
    return True, ""


def record_health(unit: str, healthy: bool) -> bool | None:
    with file_lock("state.lock"):
        state = read_state()
        health = state.setdefault("health", {})
        previous = health.get(unit)
        health[unit] = healthy
        write_state(state)
    return bool(previous) if previous is not None else None


def lobby_health() -> None:
    require_config("DISCORD_BOT_TOKEN", "DISCORD_ESTADO_CHANNEL_ID")
    for number in instance_numbers():
        unit = f"wc3-hostbot@{number}.service"
        active = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit], check=False
        ).returncode == 0
        if not active:
            healthy = False
            reason = "el servicio no está active"
        else:
            network_ok, network_reason = bot_network_health(unit, number)
            published = lobby_published_since_start(unit)
            healthy = network_ok and published
            reason = network_reason if not network_ok else (
                "no publicó un lobby después del último arranque"
            )
        previous = record_health(unit, healthy)
        if not healthy:
            allowed = cooldown_allows(f"health:{unit}", 3600)
            if previous is not False or allowed:
                post_message(
                    "DISCORD_ESTADO_CHANNEL_ID",
                    f"🚨 **{unit}** no hostea correctamente: {reason}.",
                )
        elif previous is False:
            post_message(
                "DISCORD_ESTADO_CHANNEL_ID",
                f"✅ **{unit}** volvió a publicar su lobby.",
            )
    log("healthcheck de lobbies terminado")


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
    elif mode == "lobby-health":
        lobby_health()
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
