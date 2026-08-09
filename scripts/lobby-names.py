#!/usr/bin/env python3
"""lobby-names.py — imprime los nombres de partida listos para copiar y pegar.

Aura no tiene autohost ni saca el nombre del lobby del mapa: la partida se
crea con `!pub <nombre>` (publica) o `!priv <nombre>` (privada), asi que el
nombre lo escribe el operador. Escribir a mano un nombre con codigos de color
adentro del chat de Warcraft es un garron, asi que este script los deja
armados para pegarlos con Ctrl+V.

Valida ademas el limite duro de 31 bytes de aura.cpp:879 — mas largo que eso
y el bot contesta "The game name is too long".

Uso:
    lobby-names.py                 # tabla con los nombres con color
    lobby-names.py --plain         # los mismos sin color (plan B)
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
        lines.append(f"{entry['id']:<22} !{command} {name}{flag}")
    lines.append("")
    lines.append(
        "Los codigos |cAARRGGBB pintan el texto y |r corta el color. Si en la\n"
        "lista de partidas los ves literales en vez de pintados, corre este\n"
        "mismo script con --plain y usa esos nombres."
    )
    return "\n".join(lines) + "\n", problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chuleta de nombres de partida")
    ap.add_argument("--plain", action="store_true", help="sin codigos de color")
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
        data.get("lobbies", []) or [], args.plain, "priv" if args.priv else "pub"
    )

    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"OK: {args.out}")
    else:
        print(text, end="")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
