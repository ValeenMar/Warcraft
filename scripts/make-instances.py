#!/usr/bin/env python3
"""make-instances.py — arma una instancia de bot por mapa, para autohost.

Que problema resuelve
---------------------
Aura solo admite UN lobby a la vez (`m_CurrentGame` es un puntero unico), asi
que un bot no puede tener publicados varios mapas. Para que la lista de
partidas muestre todos los mapas al mismo tiempo hace falta una instancia por
mapa. Este script las genera.

Combinado con patches/aura-autohost.patch, cada instancia mantiene su lobby
abierto sola, y cuando la partida arranca vuelve a publicar el mismo mapa
enseguida — o sea que un mapa "ocupado" sigue estando disponible.

Que genera
----------
1. Un cfg de mapa por cada .w3x, en el directorio de mapcfgs. Hace falta
   porque `bot_defaultmap` NO acepta un .w3x: Aura le agrega ".cfg" y lo busca
   en bot_mapcfgpath (aura.cpp:346-351). El cfg minimo son dos claves; el CRC,
   el SHA1 y los slots los calcula Aura sola leyendo el archivo.
2. Un config/hostbot/instance-N.env por mapa, con su usuario, sus puertos y su
   nombre de autohost.

Lo que NO hace, a proposito: crear las cuentas de los bots en PvPGN (Battle.net
no deja la misma cuenta conectada dos veces, asi que cada bot necesita la suya
y se crean desde el cliente del juego con "New Account") ni prender las
unidades de systemd. Las dos cosas quedan impresas al final como pasos.

Uso:
    ./scripts/make-instances.py --maps-dir /opt/wc3/maps
    ./scripts/make-instances.py --maps-dir /opt/wc3/maps --limit 3
    ./scripts/make-instances.py --maps-dir /opt/wc3/maps --dry-run
"""

import argparse
import fnmatch
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
LOBBIES_YAML = REPO_DIR / "maps" / "lobbies.yaml"
ENV_DIR = REPO_DIR / "config" / "hostbot"

# Rango de puertos: tiene que caer dentro de WC3_BOT_PORT_RANGE (6113:6140),
# que es lo que abre ufw en install/00-bootstrap-vps.sh.
PUERTO_HOST_BASE = 6113
PUERTO_RECONNECT_BASE = 6133
MAX_INSTANCIAS = 20  # 6113+20 = 6133, que es donde arrancan los de reconnect

LIMITE_NOMBRE = 31  # aura.cpp:879
LIMITE_VIRTUALHOST = 15


def cargar_lobbies() -> list:
    import yaml

    data = yaml.safe_load(LOBBIES_YAML.read_text(encoding="utf-8")) or {}
    return data.get("lobbies", []) or []


def elegir_entry(lobbies: list, nombre_archivo: str) -> "dict | None":
    """Mismo criterio que brand-map.py: gana el primer patron que matchea."""
    for entry in lobbies:
        if entry.get("id") == "default":
            continue
        for patron in entry.get("match", []) or []:
            if fnmatch.fnmatch(nombre_archivo.lower(), patron.lower()):
                return entry
    return None


def cfg_de_mapa(nombre_archivo: str) -> str:
    """Contenido del .cfg que Aura necesita para poder cargar el mapa.

    Es lo mismo que arma `!map` en memoria (bnet.cpp): con map_path y
    map_localpath alcanza, porque CMap abre el .w3x de verdad y calcula solo el
    CRC, el SHA1, el tamano y los slots. La ruta de map_path es la que ve el
    CLIENTE, con backslashes de Windows.
    """
    lineas = [
        "# Generado por scripts/make-instances.py. Se puede regenerar.",
        "# Con estas dos claves alcanza: Aura abre el .w3x y calcula el resto",
        "# (CRC, SHA1, tamano, slots) por su cuenta.",
        f"map_path = Maps\\Download\\{nombre_archivo}",
        f"map_localpath = {nombre_archivo}",
    ]
    # DotA tiene modos (-ap, -ar...) que Aura pasa por el sistema HCL; sin
    # map_type no los reconoce. Es la unica excepcion que hace el propio Aura.
    if "dota" in nombre_archivo.lower():
        lineas.append("map_type = dota")
    return "\n".join(lineas) + "\n"


def env_de_instancia(n: int, entry: dict, mapa: str) -> str:
    corto = entry.get("short_name") or entry["id"]
    nombre = entry.get("plain_name") or Path(mapa).stem
    return f"""# Instancia {n}: {nombre}
# Generado por scripts/make-instances.py. Pisa las variables de .env al
# renderizar el aura.cfg de /opt/wc3/hostbot/instances/{n}/.
#
# La cuenta hostbot{n} hay que crearla a mano en PvPGN desde el cliente del
# juego: Battle.net no admite la misma cuenta conectada dos veces. La
# contrasena sale de WC3_BOT_PASSWORD en .env, o sea que es la misma para
# todos los bots.
WC3_BOT_USERNAME=hostbot{n}
WC3_BOT_HOSTPORT={PUERTO_HOST_BASE + n - 1}
WC3_BOT_RECONNECTPORT={PUERTO_RECONNECT_BASE + n - 1}
WC3_BOT_VIRTUALHOST="{corto}"
WC3_BOT_DEFAULTMAP={entry['id']}
WC3_BOT_MAXGAMES=4
WC3_BOT_AUTOHOSTNAME="{nombre}"
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genera una instancia de bot por mapa")
    ap.add_argument("--maps-dir", type=Path, default=Path("/opt/wc3/maps"))
    ap.add_argument("--mapcfg-dir", type=Path, default=Path("/opt/wc3/hostbot/mapcfgs"))
    ap.add_argument("--env-dir", type=Path, default=ENV_DIR)
    ap.add_argument("--limit", type=int, help="generar solo las primeras N instancias")
    ap.add_argument("--dry-run", action="store_true", help="mostrar sin escribir nada")
    args = ap.parse_args(argv)

    if not args.maps_dir.is_dir():
        print(f"error: no existe {args.maps_dir}", file=sys.stderr)
        return 2

    try:
        lobbies = cargar_lobbies()
    except ImportError:
        print("Falta PyYAML (apt install python3-yaml).", file=sys.stderr)
        return 3

    mapas = sorted(p for p in args.maps_dir.iterdir() if p.suffix.lower() in (".w3x", ".w3m"))
    if not mapas:
        print(f"No hay mapas en {args.maps_dir}.", file=sys.stderr)
        return 1

    planificadas, sin_tema = [], []
    vistos = set()
    for mapa in mapas:
        entry = elegir_entry(lobbies, mapa.name)
        if entry is None:
            sin_tema.append(mapa.name)
            continue
        if entry["id"] in vistos:
            # Dos archivos que caen en el mismo tema (p. ej. dos versiones del
            # mismo mapa): una sola instancia, la primera.
            print(f"  aviso: {mapa.name} comparte tema con otro mapa, lo salteo")
            continue
        vistos.add(entry["id"])
        planificadas.append((entry, mapa.name))

    if args.limit:
        planificadas = planificadas[: args.limit]

    if len(planificadas) > MAX_INSTANCIAS:
        print(
            f"error: {len(planificadas)} instancias no entran en el rango de puertos "
            f"(maximo {MAX_INSTANCIAS})",
            file=sys.stderr,
        )
        return 2

    problemas = 0
    for n, (entry, mapa) in enumerate(planificadas, start=1):
        nombre = entry.get("plain_name") or Path(mapa).stem
        corto = entry.get("short_name") or entry["id"]
        if len(nombre.encode("utf-8")) > LIMITE_NOMBRE:
            print(f"  ERROR: el nombre '{nombre}' pasa los {LIMITE_NOMBRE} bytes", file=sys.stderr)
            problemas += 1
        if len(corto.encode("utf-8")) > LIMITE_VIRTUALHOST:
            print(f"  ERROR: el short_name '{corto}' pasa los {LIMITE_VIRTUALHOST} bytes",
                  file=sys.stderr)
            problemas += 1

        cfg_destino = args.mapcfg_dir / f"{entry['id']}.cfg"
        env_destino = args.env_dir / f"instance-{n}.env"
        print(f"\n=== instancia {n}: {nombre}")
        print(f"  mapa:     {mapa}")
        print(f"  usuario:  hostbot{n}")
        print(f"  puertos:  {PUERTO_HOST_BASE + n - 1} (host) / "
              f"{PUERTO_RECONNECT_BASE + n - 1} (reconnect)")
        print(f"  map cfg:  {cfg_destino}")
        print(f"  env:      {env_destino}")

        if args.dry_run:
            continue
        cfg_destino.parent.mkdir(parents=True, exist_ok=True)
        cfg_destino.write_text(cfg_de_mapa(mapa), encoding="utf-8")
        env_destino.parent.mkdir(parents=True, exist_ok=True)
        env_destino.write_text(env_de_instancia(n, entry, mapa), encoding="utf-8")

    if sin_tema:
        print(f"\nSin tema en lobbies.yaml (no se les genero instancia): {', '.join(sin_tema)}")

    if problemas:
        print(f"\n{problemas} problema(s): corregir maps/lobbies.yaml antes de seguir.",
              file=sys.stderr)
        return 1

    total = len(planificadas)
    print(f"\n{total} instancia(s) planificada(s)." + (" (dry-run, no escribi nada)"
                                                       if args.dry_run else ""))
    if args.dry_run:
        return 0

    print(f"""
Pasos que faltan, en orden:

1. Crear las cuentas de los bots en PvPGN. Desde el cliente del juego,
   "New Account", una por instancia: hostbot1 .. hostbot{total}, todas con la
   contrasena de WC3_BOT_PASSWORD. Battle.net no admite la misma cuenta
   conectada dos veces, por eso una por bot.

2. Renderizar las configs:      sudo make render-config

3. Prender las instancias:
   sudo systemctl enable --now {' '.join(f'wc3-hostbot@{i}' for i in range(1, total + 1))}

4. Mirar que entraron todas:    systemctl status 'wc3-hostbot@*' --no-pager
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
