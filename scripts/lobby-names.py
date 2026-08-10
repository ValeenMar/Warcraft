#!/usr/bin/env python3
"""lobby-names.py — imprime los nombres de partida listos para copiar y pegar.

El autohost (patches/aura-autohost.patch) publica cada mapa solo, con el
nombre que make-instances.py saco de maps/lobbies.yaml. Este script sirve para
lo demas: hostear A MANO un mapa distinto del que la instancia publica
(`!pub <nombre>` / `!priv <nombre>`), con los nombres listos para pegar con
Ctrl+V en el chat.

Salen SIN codigos de color, porque el 2026-08-09 se verifico contra un cliente
1.27a real que la lista de partidas no los pinta: se los come sin mostrarlos,
asi que los 10 bytes que gasta cada codigo se tiran a la basura. Con --color
se imprimen igual, por si alguna vez se prueba otro cliente.

Valida ademas el limite duro de 31 bytes de aura.cpp:879 — mas largo que eso
y el bot contesta "The game name is too long".

Uso:
    lobby-names.py                 # los nombres que hay que usar
    lobby-names.py --color         # la version con codigos de color (no pinta)
    lobby-names.py --priv          # usar !priv en vez de !pub
    lobby-names.py --out chuleta.txt
"""

import argparse
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
LOBBIES_YAML = REPO_DIR / "maps" / "lobbies.yaml"
LIMIT = 31


def build(lobbies: list, plain: bool, command: str) -> "tuple[str, int]":
    lines = []
    problems = 0
    lines.append("Nombres de partida listos para pegar en el chat de Battle.net")
    lines.append("(susurrale al bot: /w <nombre-del-bot> <comando>)")
    lines.append("")
    for entry in lobbies:
        name = entry.get("plain_name") if plain else entry.get("display_name")
        if not name:
            continue
        size = len(name.encode("utf-8"))
        flag = ""
        if size > LIMIT:
            flag = f"  <-- SE PASA: {size} bytes, el maximo es {LIMIT}"
            problems += 1
        lines.append(f"{entry.get('id', '?'):<22} !{command} {name}{flag}")
    lines.append("")
    if plain:
        lines.append(
            "Sin codigos de color a proposito: el cliente 1.27a no los pinta en la\n"
            "lista de partidas (verificado). Como cada codigo gasta 10 de los 31\n"
            "bytes que permite el nombre, sacarlos deja lugar para nombres mas\n"
            "descriptivos, que es lo que se ve arriba."
        )
    else:
        lines.append(
            "OJO: estos NO se ven de colores en la lista de partidas del 1.27a.\n"
            "El cliente se come los codigos sin pintarlos. Quedan por si alguna\n"
            "vez se prueba con otro cliente."
        )
    return "\n".join(lines) + "\n", problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chuleta de nombres de partida")
    ap.add_argument("--color", action="store_true",
                    help="con codigos de color (verificado: el cliente no los pinta)")
    ap.add_argument("--priv", action="store_true", help="usar !priv en vez de !pub")
    ap.add_argument("--out", type=Path, help="escribir a un archivo en vez de la pantalla")
    ap.add_argument("--lobbies", type=Path, default=LOBBIES_YAML)
    args = ap.parse_args(argv)

    try:
        import yaml
    except ImportError:
        print("Falta PyYAML (apt install python3-yaml).", file=sys.stderr)
        return 3

    data = yaml.safe_load(args.lobbies.read_text(encoding="utf-8")) or {}
    text, problems = build(
        data.get("lobbies", []) or [], not args.color, "priv" if args.priv else "pub"
    )

    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"OK: {args.out}")
    else:
        print(text, end="")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
