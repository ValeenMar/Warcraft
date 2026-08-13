#!/usr/bin/env python3
"""make-wfe-profile.py — genera el perfil "estilo LoL" para WFE.

WFE (Warcraft Feature Extender, github.com/UnryzeC/WFE-Release) es la
herramienta que le da al 1.27a lo que el juego no trae de fabrica: teclas por
POSICION del boton (grilla), smartcast por boton, y barras de vida siempre
visibles. Soporta 1.27a explicitamente y convive con el loader w3l (su README
documenta el caso EuroBattle/w3l).

Este script toma el WFEConfigBase.ini que viene en el zip de WFE y produce
nuestro perfil, cambiando SOLO estas cosas (verificadas contra el ini real):

  [KEYBINDS]  la fila de abajo de la botonera -> Q W E R
              (ahi caen las habilidades de heroe en la enorme mayoria de los
              mapas), y los dos botones derechos de la fila del medio -> D F
              (donde los mapas con 5ta/6ta habilidad las suelen poner; se
              evitan los de la izquierda porque ahi vive Patrol).
              El menu de aprender habilidad (SA_) usa las mismas teclas:
              subis el skill con la misma tecla con la que despues lo usas.
              Los 6 items -> Z X C / V B N (como DotA 2; no pisan los grupos
              de control 1-9).
  [SMARTCAST] "yes" en QWERDF. En items no: un teleport con smartcast se
              dispara al suelo sin querer.
  [HOTKEYS]   ISHEROONLY = On -> las teclas solo aplican a HEROES. Manejar
              aldeanos o construir torres en un TD queda como siempre.
  ENFORCEHOTKEYS = yes -> nuestras teclas ganan sobre las del mapa.
  [HEALTHBAR] color por bando: verde propio, celeste aliados, rojo enemigos.
              (ISENABLED ya viene en yes de fabrica.)
  [MANABAR]   prendida, solo heroes.

Todo lo demas queda exactamente como el base: la regla del proyecto es no
inventar claves, y aca ni siquiera se agregan claves — solo se cambian valores
de las que ya existen. Si una clave esperada no aparece en el base (WFE nuevo
que renombro algo), el script ABORTA en vez de generar un perfil a medias.

Uso:
    make-wfe-profile.py WFEConfigBase.ini --out Profiles/GryzWC3.ini
"""

import argparse
import sys
from pathlib import Path

# (seccion, clave) -> valor nuevo. Las claves existen todas en el
# WFEConfigBase.ini de la v3.1.x (verificado 2026-08-09).
CAMBIOS = {
    # Teclas que ganan sobre las del mapa, y solo para heroes
    ("FUNCTIONS", "ENFORCEHOTKEYS"): "yes",
    # Quita el tope de 8 MB del cliente. Inofensivo para los mapas chicos, y
    # es lo unico que permite cargar mapas grandes (FOCS y compania). OJO: solo
    # sirve si TODOS los jugadores lo tienen activado. Ver docs/mapas-grandes.md.
    ("FUNCTIONS", "REMOVEMAPSIZELIMIT"): "yes",
    ("HOTKEYS", "ISHEROONLY"): "On",
    # QWER en la fila de abajo (habilidades), DF en la derecha del medio
    ("KEYBINDS", "A_X0Y2"): "Q",
    ("KEYBINDS", "A_X1Y2"): "W",
    ("KEYBINDS", "A_X2Y2"): "E",
    ("KEYBINDS", "A_X3Y2"): "R",
    ("KEYBINDS", "A_X2Y1"): "D",
    ("KEYBINDS", "A_X3Y1"): "F",
    # El menu de aprender habilidad, con las mismas teclas
    ("KEYBINDS", "SA_X0Y2"): "Q",
    ("KEYBINDS", "SA_X1Y2"): "W",
    ("KEYBINDS", "SA_X2Y2"): "E",
    ("KEYBINDS", "SA_X3Y2"): "R",
    ("KEYBINDS", "SA_X2Y1"): "D",
    ("KEYBINDS", "SA_X3Y1"): "F",
    # Items como DotA 2: no pisan los grupos de control 1-9
    ("KEYBINDS", "I_X0Y0"): "Z",
    ("KEYBINDS", "I_X1Y0"): "X",
    ("KEYBINDS", "I_X0Y1"): "C",
    ("KEYBINDS", "I_X1Y1"): "V",
    ("KEYBINDS", "I_X0Y2"): "B",
    ("KEYBINDS", "I_X1Y2"): "N",
    # Smartcast estilo LoL en las seis teclas de habilidad
    ("SMARTCAST", "A_X0Y2"): "yes",
    ("SMARTCAST", "A_X1Y2"): "yes",
    ("SMARTCAST", "A_X2Y2"): "yes",
    ("SMARTCAST", "A_X3Y2"): "yes",
    ("SMARTCAST", "A_X2Y1"): "yes",
    ("SMARTCAST", "A_X3Y1"): "yes",
    # Vida a la vista, por color de bando (LoL: propio verde, enemigo rojo)
    ("HEALTHBAR", "ISENABLED"): "yes",
    ("HEALTHBAR", "ISCOLOURENABLED"): "yes",
    ("HEALTHBAR", "YOURCOLOUR"): "0xFF00FF00",
    ("HEALTHBAR", "ALLYCOLOUR"): "0xFF00A8FF",
    ("HEALTHBAR", "ENEMYCOLOUR"): "0xFFFF2020",
    ("HEALTHBAR", "NEUTRALAGGRESSIVECOLOUR"): "0xFFFFB000",
    ("HEALTHBAR", "NEUTRALPASSIVECOLOUR"): "0xFFFFFF60",
    ("MANABAR", "ISENABLED"): "yes",
    ("MANABAR", "ISHEROONLY"): "On",
}


def generar(base: str) -> "tuple[str, set]":
    """Aplica CAMBIOS sobre el texto del ini, seccion por seccion."""
    pendientes = dict(CAMBIOS)
    salida = []
    seccion = None
    for linea in base.splitlines():
        pelada = linea.strip()
        if pelada.startswith("[") and pelada.endswith("]"):
            seccion = pelada[1:-1].upper()
            salida.append(linea)
            continue
        if "=" in pelada and not pelada.startswith(";"):
            clave = pelada.split("=", 1)[0].strip().upper()
            for scope in (seccion, None):
                if (scope, clave) in pendientes:
                    valor = pendientes.pop((scope, clave))
                    salida.append(f"{clave} = {valor}")
                    break
            else:
                salida.append(linea)
            continue
        salida.append(linea)
    # CRLF: el perfil lo lee WFE en Windows
    return "\r\n".join(salida) + "\r\n", set(pendientes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Perfil WFE estilo LoL (QWER+DF)")
    ap.add_argument("base", type=Path, help="el WFEConfigBase.ini del zip de WFE")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    if not args.base.is_file():
        print(f"error: no existe {args.base}", file=sys.stderr)
        return 2

    texto, faltantes = generar(args.base.read_text(encoding="utf-8", errors="replace"))
    if faltantes:
        # Mejor no generar nada que generar un perfil a medias: si WFE renombro
        # claves, hay que revisar este script contra el ini nuevo.
        print("error: estas claves no aparecen en el ini base (WFE cambio de formato?):",
              file=sys.stderr)
        for scope, clave in sorted(faltantes, key=str):
            print(f"  [{scope or 'global'}] {clave}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(texto, encoding="utf-8")
    print(f"OK: {args.out} ({len(CAMBIOS)} valores cambiados sobre el base)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
