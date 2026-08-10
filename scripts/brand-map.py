#!/usr/bin/env python3
"""brand-map.py — le mete al mapa una imagen de preview propia.

Warcraft III muestra, al seleccionar una partida en la lista de partidas
personalizadas y despues en el lobby, el archivo `war3mapPreview.tga` que este
adentro del MPQ del mapa. Si no esta, dibuja el minimapa. Este script genera la
imagen (scripts/make-preview.py) y la inyecta con StormLib via `smpq`.

Tres cosas que hay que tener claras antes de usarlo:

1. CAMBIA EL HASH DEL MAPA. Aura calcula CRC y SHA1 del .w3x; si vos hosteas el
   mapa modificado, los jugadores necesitan EXACTAMENTE ese archivo. El que
   tenga el original bajado de otro lado no va a poder entrar (o se lo va a
   bajar del bot en el lobby). Por eso el mapa modificado es el que va tanto en
   /opt/wc3/maps del server como en el kit de los amigos.

2. HAY UN TECHO DE 128 MiB. El cliente objetivo 1.27b levanto el limite
   anterior de 8 MiB a 128 MiB. Meter la preview agranda el archivo; el script
   aborta y deja el mapa original intacto si supera el nuevo limite.

3. LOS MAPAS PROTEGIDOS PUEDEN RECHAZAR LA ESCRITURA. Muchos mapas populares
   estan "protegidos" (les rompen a proposito las estructuras internas del MPQ
   para que no se puedan abrir con el editor). StormLib suele poder escribir
   igual, pero no siempre. Si falla, el script lo dice y no toca nada.

Nunca modifica el archivo original salvo que le pases --in-place.

Uso:
    brand-map.py "DotA v6.83d.w3x"                    # deja el resultado en ./branded/
    brand-map.py *.w3x --out-dir /opt/wc3/maps
    brand-map.py mapa.w3x --from-image tapa.png       # imagen propia en vez de dibujo
    brand-map.py mapa.w3x --theme dota --in-place

Requiere: smpq (apt install smpq) y Pillow + PyYAML (venv /opt/wc3/venv).
"""

import argparse
import fnmatch
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
LOBBIES_YAML = REPO_DIR / "maps" / "lobbies.yaml"

PREVIEW_NAME = "war3mapPreview.tga"
# Techo duro del cliente objetivo 1.27b (ver maps/registry.yaml).
MAX_MAP_BYTES = 128 * 1024 * 1024


class BrandError(Exception):
    """Error con mensaje apto para humanos."""


def _load_sibling(name: str, filename: str):
    """Importa un script hermano cuyo nombre tiene guiones."""
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise BrandError(f"no pude importar {filename}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def require_smpq() -> str:
    exe = shutil.which("smpq")
    if not exe:
        raise BrandError(
            "falta el comando 'smpq' (frontend de StormLib).\n"
            "  Ubuntu/Debian: sudo apt install smpq"
        )
    return exe


def heredar_dueno(destino: Path) -> None:
    """Le pone al archivo el mismo dueno que su directorio.

    Cuando esto corre con sudo, los mapas quedan de root. StormLib abre los
    .w3x en lectura-ESCRITURA, asi que un mapa de root en un directorio del
    usuario wc3 hace que el bot no pueda abrirlo: dice "unable to load MPQ
    file" y el mapa queda invalido, sin partida y sin error claro. Pasa cada
    vez que se corre el script a mano en vez de por `make brand-maps`, asi que
    en lugar de documentarlo se arregla solo.
    """
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        return  # sin privilegios no se puede cambiar el dueno, y tampoco hace falta
    try:
        st = destino.parent.stat()
        if (st.st_uid, st.st_gid) != (destino.stat().st_uid, destino.stat().st_gid):
            os.chown(destino, st.st_uid, st.st_gid)
            print(f"  dueno:   heredado del directorio (uid {st.st_uid})")
    except OSError as exc:
        print(f"  aviso: no pude ajustar el dueno de {destino.name}: {exc}", file=sys.stderr)


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lobbies(path: Path) -> list:
    import yaml

    if not path.exists():
        raise BrandError(f"no existe {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("lobbies", []) or []


def pick_theme(lobbies: list, map_path: Path, forced_id: "str | None") -> dict:
    """Elige el entry de lobbies.yaml para este archivo (gana el primero)."""
    if forced_id:
        for entry in lobbies:
            if entry.get("id") == forced_id:
                return entry
        raise BrandError(
            f"no hay un tema con id '{forced_id}'. "
            f"Disponibles: {', '.join(e.get('id', '?') for e in lobbies)}"
        )
    name = map_path.name
    for entry in lobbies:
        for pattern in entry.get("match", []) or []:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                return entry
    raise BrandError(f"ningun patron de {LOBBIES_YAML.name} matchea con '{name}'")


def mpq_list(smpq: str, archive: Path) -> list:
    """Lista los archivos del MPQ. Devuelve [] si el mapa no tiene listfile."""
    proc = subprocess.run(
        [smpq, "--list", str(archive)], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise BrandError(f"smpq no pudo abrir el archivo: {proc.stderr.strip()}")
    names = []
    for line in proc.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            names.append(parts[3])
    return names


def read_w3i_flags(smpq: str, archive: Path) -> "dict | None":
    """Extrae war3map.w3i y devuelve su metadata, o None si no se pudo."""
    inspect = _load_sibling("inspect_map", "inspect-map.py")
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [smpq, "--extract", str(archive.resolve()), "war3map.w3i"],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=False,
        )
        extracted = Path(tmp) / "war3map.w3i"
        if proc.returncode != 0 or not extracted.exists():
            return None
        try:
            return inspect.parse_w3i(extracted.read_bytes())
        except Exception:  # mapa protegido: el w3i esta adrede corrupto
            return None


def extract_file(smpq: str, archive: Path, name: str) -> "bytes | None":
    """Saca un archivo del MPQ por nombre exacto. None si no esta.

    Sirve incluso en mapas protegidos (sin listfile): StormLib busca por hash
    del nombre, no necesita el indice.
    """
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [smpq, "--extract", str(archive.resolve()), name],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=False,
        )
        out = Path(tmp) / name
        return out.read_bytes() if out.exists() else None


def resolve_image(spec: "str | None", tmp_dir: Path) -> "Path | None":
    """Acepta una ruta local o una URL http(s) y devuelve un archivo local.

    Que --from-image tome URLs ahorra el paso de bajar la imagen a mano en el
    servidor, que es donde corre esto y donde no hay navegador.
    """
    if not spec:
        return None
    if not str(spec).lower().startswith(("http://", "https://")):
        ruta = Path(spec)
        if not ruta.is_file():
            raise BrandError(f"no existe la imagen {ruta}")
        return ruta

    import urllib.error
    import urllib.request

    destino = tmp_dir / "subject_descargado"
    pedido = urllib.request.Request(
        str(spec), headers={"User-Agent": "wc3-revival/brand-map"}
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resp:
            datos = resp.read(16 * 1024 * 1024)
    except (urllib.error.URLError, OSError) as exc:
        raise BrandError(f"no pude bajar {spec}: {exc}") from exc
    if not datos:
        raise BrandError(f"la descarga de {spec} vino vacia")
    destino.write_bytes(datos)
    print(f"  imagen bajada: {len(datos)} B de {spec}")
    return destino


def inject_preview(smpq: str, archive: Path, tga: Path) -> None:
    """Mete (o reemplaza) war3mapPreview.tga adentro del MPQ del .w3x.

    OJO: smpq devuelve codigo de salida 0 aunque StormLib falle (verificado el
    2026-08-09 contra un mapa protegido real: imprime "Cannot create new file
    ... Operation not permitted" y sale 0 igual). Por eso la unica verificacion
    que vale es volver a sacar el archivo y comparar los bytes.
    """
    expected = tga.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / PREVIEW_NAME
        shutil.copyfile(tga, staged)
        # Corremos con cwd=tmp y pasamos solo el basename: smpq guarda el
        # archivo adentro del MPQ con la ruta tal cual se la damos.
        proc = subprocess.run(
            [smpq, "--append", "--overwrite", str(archive.resolve()), PREVIEW_NAME],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=False,
        )
    salida = (proc.stderr + proc.stdout).strip()
    if proc.returncode != 0:
        raise BrandError(f"StormLib no pudo escribir adentro del mapa: {salida}")

    got = extract_file(smpq, archive, PREVIEW_NAME)
    if got != expected:
        raise BrandError(
            "el mapa esta protegido: StormLib no pudo escribir adentro.\n"
            "         El MPQ no acepta archivos nuevos ni reemplazos (tabla de\n"
            "         hash llena o cerrada a proposito por el protector).\n"
            "         Para este mapa la preview propia no es posible; queda el\n"
            "         nombre con color, que no depende del archivo."
            + (f"\n         Dijo StormLib: {salida}" if salida else "")
        )


def describe(smpq: str, src: Path) -> dict:
    """Que trae el mapa hoy: preview propia, si esta protegido, tamano."""
    listing = mpq_list(smpq, src)
    # Un mapa protegido o bien no tiene listfile, o lo tiene con los nombres
    # ofuscados (File00000123.blp). El sintoma fiable es que no aparezcan los
    # archivos canonicos que todo mapa tiene.
    canonicos = {"war3map.j", "war3map.w3e", "war3map.wpm"}
    protegido = not listing or not (canonicos & {n.lower() for n in listing})
    return {
        "bytes": src.stat().st_size,
        "preview": extract_file(smpq, src, PREVIEW_NAME),
        "protegido": protegido,
    }


def report_one(smpq: str, src: Path, dump_dir: "Path | None") -> int:
    """Modo --report: no toca nada, solo cuenta que hay adentro."""
    print(f"\n=== {src.name}")
    if not src.is_file():
        print(f"  ERROR: no existe {src}", file=sys.stderr)
        return 1
    info = describe(smpq, src)
    print(f"  tamano:  {info['bytes']} B (techo {MAX_MAP_BYTES} B)")
    if info["protegido"]:
        print("  estado:  PROTEGIDO (nombres ofuscados o sin listfile)")
        print("           es probable que no acepte que le escribamos adentro")
    else:
        print("  estado:  sin proteger")
    if info["preview"] is None:
        print("  preview: NO tiene. El cliente le va a dibujar el minimapa.")
        return 0
    print(f"  preview: YA TIENE una, de {len(info['preview'])} B")
    if dump_dir:
        try:
            from PIL import Image
        except ImportError:
            print("  (instala Pillow para exportarla a PNG)")
            return 0
        dump_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tga = Path(tmp) / PREVIEW_NAME
            tga.write_bytes(info["preview"])
            out = dump_dir / (src.stem + ".png")
            Image.open(tga).convert("RGB").save(out)
        print(f"  exportada a: {out}")
    return 0


def brand_one(args, lobbies: list, smpq: str, src: Path) -> int:
    print(f"\n=== {src.name}")
    if not src.is_file():
        print(f"  ERROR: no existe {src}", file=sys.stderr)
        return 1, False

    original_bytes = src.stat().st_size
    original_sha1 = sha1_of(src)

    # --- destino ---------------------------------------------------------
    # La copia va primero, ANTES de decidir si hay que tocar el mapa: cuando
    # se usa --out-dir, este script es tambien el que instala los mapas en su
    # lugar definitivo. Si el salto por "ya tiene preview" ocurriera antes de
    # copiar, los mapas que no hay que modificar —que son la mayoria— nunca
    # llegarian al directorio del bot.
    if args.in_place:
        dest = src
        backup = src.with_suffix(src.suffix + ".orig")
        if not backup.exists():
            shutil.copyfile(src, backup)
            print(f"  respaldo: {backup.name}")
    else:
        out_dir = args.out_dir or (src.parent / "branded")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / src.name
        shutil.copyfile(src, dest)

    # --- lo que el mapa ya trae ------------------------------------------
    # Muchos mapas custom (sobre todo los de anime) YA vienen con una
    # war3mapPreview.tga hecha por el autor, con arte de verdad. Pisarla con
    # un dibujo generado es un downgrade, asi que por defecto no se toca.
    ya_tiene = extract_file(smpq, dest, PREVIEW_NAME)
    if ya_tiene is not None and not args.force:
        print(f"  ya trae una preview propia ({len(ya_tiene)} B): queda como esta.")
        if not args.in_place:
            heredar_dueno(dest)
            print(f"  copiado sin cambios a: {dest}")
        print("  (--report --dump-previews DIR para verla; --force para pisarla)")
        return 0, False

    entry = pick_theme(lobbies, src, args.theme)
    theme_id = entry.get("id", "?")
    print(f"  tema: {theme_id}")

    # --- aviso del flag "hide minimap in preview screens" -----------------
    meta = read_w3i_flags(smpq, dest)
    if meta is None:
        print("  aviso: no pude leer war3map.w3i (mapa protegido). Sigo igual.")
    elif meta.get("hide_minimap_in_preview"):
        print(
            "  AVISO: el mapa tiene prendido 'Hide minimap in preview screens'.\n"
            "         Si la imagen no aparece en el lobby, la causa es esa."
        )

    # --- imagen ----------------------------------------------------------
    preview = _load_sibling("make_preview", "make-preview.py")
    with tempfile.TemporaryDirectory() as tmp:
        imagen = resolve_image(args.from_image, Path(tmp))
        tga = Path(tmp) / PREVIEW_NAME
        if args.from_image and args.raw_image:
            img = preview.from_image(imagen, args.size)
        else:
            subject = preview.load_subject(imagen) if imagen else None
            img = preview.render(entry.get("preview", {}), args.size, subject)
        preview.save(img, tga)
        tga_bytes = tga.stat().st_size
        try:
            inject_preview(smpq, dest, tga)
        except BrandError as exc:
            if not args.in_place:
                dest.unlink(missing_ok=True)
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 1, False

    # --- verificaciones --------------------------------------------------
    new_bytes = dest.stat().st_size
    with dest.open("rb") as fh:
        head = fh.read(4)
    problems = []
    if head != b"HM3W":
        problems.append("se rompio el header HM3W del .w3x")
    if new_bytes > MAX_MAP_BYTES:
        problems.append(
            f"el mapa quedo en {new_bytes} B y el techo de 1.27b es "
            f"{MAX_MAP_BYTES} B: no lo va a cargar ningun cliente"
        )

    if problems:
        for p in problems:
            print(f"  ERROR: {p}", file=sys.stderr)
        if args.in_place:
            backup = src.with_suffix(src.suffix + ".orig")
            if backup.exists():
                shutil.copyfile(backup, src)
                print("  restaurado desde el respaldo .orig", file=sys.stderr)
        else:
            dest.unlink(missing_ok=True)
        return 1, False

    heredar_dueno(dest)

    delta = new_bytes - original_bytes
    margin = MAX_MAP_BYTES - new_bytes
    print(f"  imagen:  {args.size}x{args.size} TGA, {tga_bytes} B sin comprimir")
    print(f"  tamano:  {original_bytes} B -> {new_bytes} B ({delta:+d} B)")
    print(f"  margen:  {margin} B hasta el techo de 128 MiB")
    print(f"  sha1:    {original_sha1[:12]}... -> {sha1_of(dest)[:12]}...")
    print(f"  salida:  {dest}")
    display = entry.get("display_name") or entry.get("plain_name")
    if display:
        print(f"  hostear: !pub {display}")
    return 0, True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Inyecta una preview propia (war3mapPreview.tga) en mapas .w3x"
    )
    ap.add_argument("maps", nargs="+", type=Path, help="archivos .w3x")
    ap.add_argument("--out-dir", type=Path, help="donde dejar los mapas modificados")
    ap.add_argument("--in-place", action="store_true",
                    help="modificar el archivo original (deja un respaldo .orig)")
    ap.add_argument("--theme", help="forzar un id de maps/lobbies.yaml para todos")
    ap.add_argument("--from-image",
                    help="imagen a usar como figura: ruta local o URL http(s). "
                         "Se compone sobre el fondo y el titulo del tema")
    ap.add_argument("--raw-image", action="store_true",
                    help="con --from-image: usar la imagen tal cual, sin titulo ni marco")
    ap.add_argument("--report", action="store_true",
                    help="solo informar que trae cada mapa, sin modificar nada")
    ap.add_argument("--dump-previews", type=Path, metavar="DIR",
                    help="con --report: exportar a PNG las previews que ya tengan")
    ap.add_argument("--force", action="store_true",
                    help="pisar la preview que el mapa ya traiga (por defecto se respeta)")
    ap.add_argument("--size", type=int, default=128, choices=[128, 256],
                    help="lado de la preview (128 recomendado: pesa menos)")
    ap.add_argument("--lobbies", type=Path, default=LOBBIES_YAML)
    args = ap.parse_args(argv)

    if args.in_place and args.out_dir:
        print("error: --in-place y --out-dir son excluyentes", file=sys.stderr)
        return 2

    try:
        smpq = require_smpq()
        lobbies = load_lobbies(args.lobbies)
    except BrandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.report:
        fallos = 0
        for src in args.maps:
            fallos += report_one(smpq, src, args.dump_previews)
        return 1 if fallos else 0

    failures = 0
    modificados = 0
    for src in args.maps:
        try:
            fallo, cambio = brand_one(args, lobbies, smpq, src)
        except BrandError as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            fallo, cambio = 1, False
        failures += fallo
        modificados += int(cambio)

    print()
    total = len(args.maps)
    print(f"Listo: {total - failures}/{total} mapas procesados sin error.")
    if failures:
        return 1
    # El aviso solo tiene sentido si de verdad se toco algun mapa: si estaban
    # todos con su preview propia, ningun hash cambio y no hay nada que
    # recargar.
    if modificados:
        print(
            f"Acordate: cambio el hash de {modificados} mapa(s). En el server hay que\n"
            "volver a cargarlos en el bot (!map <nombre>) y los jugadores necesitan\n"
            "ESTOS archivos, no los que puedan tener bajados de otro lado."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
