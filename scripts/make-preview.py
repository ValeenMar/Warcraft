#!/usr/bin/env python3
"""make-preview.py — genera la imagen de preview de un mapa (war3mapPreview.tga).

Warcraft III clasico (1.24-1.28) muestra en la pantalla de preview —la que se
ve al seleccionar una partida en la lista de partidas personalizadas y despues
en el lobby— el archivo `war3mapPreview.tga` si el mapa lo tiene adentro del
MPQ. Si no lo tiene, dibuja el minimapa generado por el editor. Por eso, para
que se vea una imagen y no el terreno, hay que meterle ese archivo al mapa
(lo hace scripts/brand-map.py).

Requisitos del formato, segun el tutorial de world-editor-tutorials:
  - TGA, sin comprimir
  - 128x128 (recomendado, pesa menos) o 256x256
  - el nombre adentro del MPQ tiene que ser exactamente "war3mapPreview.tga"

Este script dibuja la imagen desde cero con Pillow a partir de un tema
declarado en maps/lobbies.yaml (colores + motivo + titulo), o adapta una
imagen que le pases vos con --from-image.

Uso:
    make-preview.py --theme dota --out preview.tga
    make-preview.py --from-image tapa.png --out preview.tga
    make-preview.py --theme dota --out preview.png --size 512   # para mirarla

Dependencias: Pillow y PyYAML. En el VPS viven en el venv /opt/wc3/venv.
"""

import argparse
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - depende del entorno
    print(
        "Falta Pillow. En el VPS: /opt/wc3/venv/bin/pip install pillow\n"
        "En Debian/Ubuntu tambien sirve: apt install python3-pil",
        file=sys.stderr,
    )
    raise SystemExit(3)

REPO_DIR = Path(__file__).resolve().parent.parent
LOBBIES_YAML = REPO_DIR / "maps" / "lobbies.yaml"

# Se dibuja grande y se reduce al final: el downsample hace de antialias y el
# resultado a 128x128 queda mucho mas limpio que dibujar directo en chico.
SUPERSAMPLE = 4

# Fuentes que estan en cualquier Ubuntu server (paquete fonts-dejavu-core, que
# viene por defecto). Se prueban en orden.
FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


class PreviewError(Exception):
    """Error con mensaje apto para humanos."""


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def hex_to_rgb(value: str) -> tuple:
    """Convierte '#rrggbb' (o 'rrggbb') a (r, g, b)."""
    s = value.strip().lstrip("#")
    if len(s) != 6:
        raise PreviewError(f"color invalido: {value!r} (se espera #rrggbb)")
    try:
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise PreviewError(f"color invalido: {value!r}") from exc


def load_font(size: int, bold: bool = True):
    """Devuelve una fuente TrueType del sistema al tamano pedido."""
    for path in FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    # Ultimo recurso: la bitmap de Pillow. Queda fea pero no rompe.
    return ImageFont.load_default()


def fit_font(draw, text: str, max_width: int, start_size: int, bold: bool = True):
    """Baja el cuerpo de la fuente hasta que el texto entre en max_width."""
    size = start_size
    while size > 8:
        font = load_font(size, bold)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= max(1, size // 20)
    return load_font(8, bold)


def draw_text_outlined(draw, xy, text, font, fill, outline=(0, 0, 0), width=0):
    """Texto con contorno oscuro, para que se lea sobre cualquier fondo."""
    x, y = xy
    if width <= 0:
        width = max(1, font.size // 12)
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill, anchor="mm")


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> "Image.Image":
    """Degrade vertical de top a bottom."""
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((size, size), Image.BICUBIC)


def radial_glow(size: int, color: tuple, center=(0.5, 0.45), radius=0.55) -> "Image.Image":
    """Mascara de brillo radial, para dar volumen al fondo."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    cx, cy = center[0] * size, center[1] * size
    steps = 24
    for i in range(steps, 0, -1):
        r = radius * size * i / steps
        alpha = int(180 * (1 - i / steps) ** 1.6)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(size / 40))
    layer = Image.new("RGB", (size, size), color)
    return mask, layer


# --------------------------------------------------------------------------
# Motivos (el dibujo del centro). Todos reciben un lienzo RGBA size x size.
# --------------------------------------------------------------------------
def _poly(d, pts, size, fill, outline=None, w=0):
    scaled = [(x * size, y * size) for x, y in pts]
    d.polygon(scaled, fill=fill, outline=outline, width=w or max(1, size // 128))


def motif_swords(d, size, accent, dark):
    """Dos espadas cruzadas (AoS / arena)."""
    for flip in (1, -1):
        cx = 0.5
        # hoja + guarda + empunadura, de la punta (arriba) al pomo (abajo)
        pts = [
            (cx, 0.12),
            (cx + 0.05, 0.20),
            (cx + 0.05, 0.52),
            (cx + 0.13, 0.56),
            (cx + 0.13, 0.61),
            (cx + 0.03, 0.61),
            (cx + 0.03, 0.76),
            (cx - 0.03, 0.76),
            (cx - 0.03, 0.61),
            (cx - 0.13, 0.61),
            (cx - 0.13, 0.56),
            (cx - 0.05, 0.52),
            (cx - 0.05, 0.20),
        ]
        rot = [
            (
                0.5 + (x - 0.5) * math.cos(0.62 * flip) - (y - 0.44) * math.sin(0.62 * flip),
                0.44 + (x - 0.5) * math.sin(0.62 * flip) + (y - 0.44) * math.cos(0.62 * flip),
            )
            for x, y in pts
        ]
        _poly(d, rot, size, fill=accent, outline=dark)


def motif_shuriken(d, size, accent, dark):
    """Shuriken de cuatro puntas (ninja / Naruto)."""
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i
        r = 0.30 if i % 2 == 0 else 0.11
        pts.append((0.5 + r * math.cos(ang), 0.44 + r * math.sin(ang)))
    _poly(d, pts, size, fill=accent, outline=dark)
    r = 0.05
    d.ellipse(
        [(0.5 - r) * size, (0.44 - r) * size, (0.5 + r) * size, (0.44 + r) * size],
        fill=dark,
    )


def motif_hook(d, size, accent, dark):
    """Gancho con cadena (Pudge Wars)."""
    w = max(2, size // 22)
    for i in range(6):
        x = 0.20 + i * 0.055
        d.ellipse(
            [x * size, (0.22 + i * 0.03) * size, (x + 0.05) * size, (0.27 + i * 0.03) * size],
            outline=dark,
            width=w,
        )
    d.arc(
        [0.44 * size, 0.42 * size, 0.80 * size, 0.78 * size],
        start=250,
        end=140,
        fill=accent,
        width=w * 2,
    )
    _poly(d, [(0.60, 0.44), (0.72, 0.50), (0.60, 0.56)], size, fill=accent, outline=dark)


def motif_clash(d, size, accent, dark):
    """Choque de dos bandos (crossover / versus)."""
    _poly(d, [(0.10, 0.12), (0.48, 0.12), (0.38, 0.58), (0.10, 0.58)], size, fill=accent)
    _poly(d, [(0.52, 0.12), (0.90, 0.12), (0.90, 0.58), (0.62, 0.58)], size, fill=dark)
    f = load_font(int(size * 0.26))
    draw_text_outlined(d, (0.5 * size, 0.35 * size), "VS", f, (255, 255, 255), dark)


def motif_orb(d, size, accent, dark):
    """Orbe con anillo (magia / heroes)."""
    r = 0.26
    d.ellipse(
        [(0.5 - r) * size, (0.44 - r) * size, (0.5 + r) * size, (0.44 + r) * size],
        fill=accent,
        outline=dark,
        width=max(2, size // 60),
    )
    rr = 0.34
    d.arc(
        [(0.5 - rr) * size, (0.44 - rr * 0.45) * size, (0.5 + rr) * size, (0.44 + rr * 0.45) * size],
        start=0,
        end=360,
        fill=dark,
        width=max(2, size // 55),
    )


def motif_bolt(d, size, accent, dark):
    """Rayo (velocidad / accion)."""
    _poly(
        d,
        [(0.56, 0.12), (0.30, 0.50), (0.46, 0.50), (0.38, 0.78), (0.68, 0.38), (0.50, 0.38)],
        size,
        fill=accent,
        outline=dark,
    )


def motif_tower(d, size, accent, dark):
    """Torre (tower defense)."""
    _poly(d, [(0.36, 0.72), (0.64, 0.72), (0.60, 0.34), (0.40, 0.34)], size, fill=accent, outline=dark)
    _poly(
        d,
        [(0.34, 0.34), (0.66, 0.34), (0.66, 0.26), (0.58, 0.26), (0.58, 0.30),
         (0.54, 0.30), (0.54, 0.26), (0.46, 0.26), (0.46, 0.30), (0.42, 0.30),
         (0.42, 0.26), (0.34, 0.26)],
        size,
        fill=dark,
    )


def motif_star(d, size, accent, dark):
    """Estrella (generico)."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + math.pi / 5 * i
        r = 0.30 if i % 2 == 0 else 0.13
        pts.append((0.5 + r * math.cos(ang), 0.44 + r * math.sin(ang)))
    _poly(d, pts, size, fill=accent, outline=dark)


MOTIFS = {
    "swords": motif_swords,
    "shuriken": motif_shuriken,
    "hook": motif_hook,
    "clash": motif_clash,
    "orb": motif_orb,
    "bolt": motif_bolt,
    "tower": motif_tower,
    "star": motif_star,
    "none": lambda *_: None,
}


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
def paste_subject(base: "Image.Image", subject: "Image.Image") -> None:
    """Pega una imagen (idealmente con fondo transparente) sobre el fondo.

    Se escala conservando la proporcion y se apoya un poco por debajo del
    centro, de manera que la parte de abajo quede tapada por la banda oscura
    del titulo. Asi la figura "sale" del cuadro en vez de flotar.
    """
    big = base.size[0]
    max_w, max_h = int(big * 0.92), int(big * 0.68)
    escala = min(max_w / subject.width, max_h / subject.height)
    nuevo = subject.resize(
        (max(1, round(subject.width * escala)), max(1, round(subject.height * escala))),
        Image.LANCZOS,
    )
    x = (big - nuevo.width) // 2
    y = int(big * 0.70) - nuevo.height
    base.paste(nuevo, (x, max(0, y)), nuevo if nuevo.mode == "RGBA" else None)


def render(theme: dict, size: int = 128, subject: "Image.Image | None" = None) -> "Image.Image":
    """Dibuja la preview del tema al tamano pedido.

    Si se pasa `subject`, esa imagen reemplaza al motivo dibujado: sirve para
    usar arte de verdad (un render, una tapa) manteniendo el fondo, el titulo y
    el marco, que son los que hacen que se lea a 128x128.
    """
    big = size * SUPERSAMPLE
    top = hex_to_rgb(theme.get("bg_top", "#101828"))
    bottom = hex_to_rgb(theme.get("bg_bottom", "#050810"))
    accent = hex_to_rgb(theme.get("accent", "#ffcc00"))
    dark = hex_to_rgb(theme.get("shadow", "#000000"))

    img = vertical_gradient(big, top, bottom)
    mask, layer = radial_glow(big, accent)
    img = Image.composite(Image.blend(img, layer, 0.35), img, mask)

    d = ImageDraw.Draw(img, "RGBA")

    # Bandas diagonales tenues, para que el fondo no quede plano
    for i in range(-2, 8):
        x = i * big / 6
        d.polygon(
            [(x, big), (x + big / 14, big), (x + big / 14 + big * 0.5, 0), (x + big * 0.5, 0)],
            fill=(255, 255, 255, 10),
        )

    if subject is not None:
        paste_subject(img, subject.resize(
            (subject.width * SUPERSAMPLE, subject.height * SUPERSAMPLE), Image.LANCZOS
        ) if max(subject.size) * SUPERSAMPLE < big else subject)
        d = ImageDraw.Draw(img, "RGBA")
    else:
        motif = MOTIFS.get(theme.get("motif", "star"))
        if motif is None:
            raise PreviewError(
                f"motivo desconocido: {theme.get('motif')!r} "
                f"(validos: {', '.join(sorted(MOTIFS))})"
            )
        motif(d, big, accent, dark)

    # Sombra de abajo para que el texto se despegue del motivo
    d.rectangle([0, big * 0.62, big, big], fill=(0, 0, 0, 130))

    title = str(theme.get("title", "")).upper()
    subtitle = str(theme.get("subtitle", "")).upper()

    if title:
        font = fit_font(d, title, int(big * 0.88), int(big * 0.20))
        draw_text_outlined(d, (big / 2, big * 0.755), title, font, accent, dark)
    if subtitle:
        font = fit_font(d, subtitle, int(big * 0.86), int(big * 0.095), bold=False)
        draw_text_outlined(d, (big / 2, big * 0.90), subtitle, font, (235, 235, 235), dark)

    # Marco
    w = max(2, big // 64)
    d.rectangle([w // 2, w // 2, big - w // 2 - 1, big - w // 2 - 1], outline=accent, width=w)

    return img.resize((size, size), Image.LANCZOS)


def from_image(path: Path, size: int = 128) -> "Image.Image":
    """Adapta una imagen cualquiera: recorte centrado cuadrado + resize.

    Es el camino "crudo": la imagen ocupa todo el cuadro, sin titulo ni marco.
    Sirve cuando la imagen ya es una tapa hecha y derecha. Para un render
    suelto conviene componerlo con el tema (ver render(subject=...)).
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    return img.resize((size, size), Image.LANCZOS)


def load_subject(path: Path) -> "Image.Image":
    """Carga una imagen para usarla como figura sobre el fondo del tema."""
    img = Image.open(path)
    return img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")


def save(img: "Image.Image", out: Path) -> None:
    """Guarda en TGA sin comprimir (o en el formato que pida la extension)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".tga":
        # RGB, sin canal alfa y sin RLE: es lo que el motor clasico lee sin
        # sorpresas. Pillow escribe TGA sin comprimir por defecto.
        img.convert("RGB").save(out, format="TGA")
    else:
        img.save(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def load_themes(path: Path) -> dict:
    import yaml  # import tardio: solo hace falta con --theme

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for entry in data.get("lobbies", []):
        key = entry.get("id")
        if key:
            out[key] = entry.get("preview", {})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genera war3mapPreview.tga para un mapa")
    ap.add_argument("--theme", help="id de un entry de maps/lobbies.yaml")
    ap.add_argument("--from-image", type=Path,
                    help="imagen a usar como figura; con --theme se compone sobre el fondo")
    ap.add_argument("--out", type=Path, required=True, help="archivo de salida (.tga o .png)")
    ap.add_argument("--raw-image", action="store_true",
                    help="con --from-image: usar la imagen tal cual, sin titulo ni marco")
    ap.add_argument("--size", type=int, default=128, choices=[128, 256, 512],
                    help="lado en pixeles; 128 es lo recomendado (512 solo para mirarla)")
    ap.add_argument("--lobbies", type=Path, default=LOBBIES_YAML)
    args = ap.parse_args(argv)
    if not args.theme and not args.from_image:
        ap.error("hace falta --theme, --from-image, o los dos juntos")
    if args.raw_image and not args.from_image:
        ap.error("--raw-image solo tiene sentido junto con --from-image")

    try:
        if args.from_image and args.raw_image:
            img = from_image(args.from_image, args.size)
        else:
            themes = load_themes(args.lobbies)
            if args.theme not in themes:
                print(
                    f"No hay un tema '{args.theme}' en {args.lobbies}.\n"
                    f"Disponibles: {', '.join(sorted(themes)) or '(ninguno)'}",
                    file=sys.stderr,
                )
                return 2
            subject = load_subject(args.from_image) if args.from_image else None
            img = render(themes[args.theme], args.size, subject)
        save(img, args.out)
    except PreviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"OK: {args.out} ({args.size}x{args.size}, {args.out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
