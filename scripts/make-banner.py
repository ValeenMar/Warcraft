#!/usr/bin/env python3
"""make-banner.py — genera el banner que el cliente muestra arriba del chat.

El cliente clasico de Warcraft III muestra, en la parte superior de la
pantalla de Battle.net, un banner publicitario que le sirve el servidor. En
PvPGN el sistema es asi (verificado en el codigo el 2026-08-09, contra el
mismo commit que corre en el VPS):

  - los banners se declaran en ad.json (clave `adfile` de bnetd.conf)
  - el archivo de imagen vive en el directorio de `filedir`
    (/opt/wc3/pvpgn/var/pvpgn/files) y el cliente lo baja por BNFTP
  - para Warcraft III sirve un PNG comun: adbanner.cpp mapea la extension
    .png a EXTENSIONTAG_MNG, que es lo que el cliente 1.2x entiende
  - el que instala PvPGN de fabrica (el logo de pvpgn.pro) mide 468x60;
    esa es la medida del hueco en la interfaz del cliente
  - al hacerle clic, el cliente abre la URL declarada en ad.json

Este script dibuja un banner de 468x60 con el estilo del resto del proyecto
(mismos helpers que make-preview.py). Reemplazar el archivo + ad.json es
trabajo de install/40-render-configs.sh.

Uso:
    make-banner.py --title "WC3 Revival" --subtitle "8 mapas - 22 ms" --out ad000001.png
    make-banner.py --from-image mi-logo.png --title "WC3 Revival" \
        --subtitle "CLASICOS - ANIME - 24/7" --out ad000001.png
    make-banner.py --title "WC3 Revival" --out banner.png --preview banner-grande.png

Si preferis dibujarlo vos: PNG de 468x60, RGB, sin transparencia. El script
lo adapta igual si se lo pasas en otra medida (recorta al centro).

Dependencias: Pillow (en el VPS vive en /opt/wc3/venv).
"""

import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Medida del banner que instala PvPGN de fabrica y que el cliente muestra
# entero. Otra medida no rompe (el cliente escala), pero se ve deformada.
ANCHO, ALTO = 468, 60
SUPERSAMPLE = 4


def _load_preview_helpers():
    """Importa make-preview.py, que tiene las fuentes y el degrade."""
    spec = importlib.util.spec_from_file_location(
        "make_preview", SCRIPT_DIR / "make-preview.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render(title: str, subtitle: str, accent: str, bg_top: str, bg_bottom: str):
    from PIL import Image, ImageDraw

    prev = _load_preview_helpers()
    w, h = ANCHO * SUPERSAMPLE, ALTO * SUPERSAMPLE

    top = prev.hex_to_rgb(bg_top)
    bottom = prev.hex_to_rgb(bg_bottom)
    acc = prev.hex_to_rgb(accent)

    # Degrade vertical hecho a mano (el helper de preview es cuadrado)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        fila = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = fila
    d = ImageDraw.Draw(img, "RGBA")

    # Bandas diagonales tenues, como en las previews
    for i in range(-2, 16):
        x = i * w / 10
        d.polygon(
            [(x, h), (x + w / 30, h), (x + w / 30 + h * 0.8, 0), (x + h * 0.8, 0)],
            fill=(255, 255, 255, 8),
        )

    # Titulo a la izquierda, subtitulo a la derecha
    margen = int(h * 0.30)
    font_t = prev.fit_font(d, title.upper(), int(w * 0.45), int(h * 0.52))
    d.text((margen, h // 2), title.upper(), font=font_t, fill=acc, anchor="lm",
           stroke_width=max(2, h // 40), stroke_fill=(0, 0, 0))
    if subtitle:
        font_s = prev.fit_font(d, subtitle, int(w * 0.48), int(h * 0.30), bold=False)
        d.text((w - margen, h // 2), subtitle, font=font_s, fill=(235, 240, 248),
               anchor="rm", stroke_width=max(1, h // 60), stroke_fill=(0, 0, 0))

    # Filete de acento abajo, para separar del chat
    d.rectangle([0, h - h // 15, w, h], fill=acc)

    return img.resize((ANCHO, ALTO), Image.LANCZOS)


def adaptar(ruta: Path):
    """Adapta una imagen propia a los 468x60 exactos que espera el cliente.

    Si ya viene en la medida justa, solo se le saca la transparencia (el banner
    de fabrica es RGB sin alfa, y el cliente clasico no la usa). Si viene en
    otra proporcion, se recorta al centro hasta 468x60 en vez de deformarla:
    un banner estirado se nota mucho mas que uno recortado.
    """
    from PIL import Image

    img = Image.open(ruta)
    original = img.size

    # Alfa aplanado sobre negro: el formato final no lleva transparencia.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, (0, 0, 0, 255))
        img = Image.alpha_composite(fondo, img)
    img = img.convert("RGB")

    if img.size != (ANCHO, ALTO):
        objetivo = ANCHO / ALTO
        w, h = img.size
        actual = w / h
        if actual > objetivo:  # mas apaisada: sobra a los costados
            nuevo_w = round(h * objetivo)
            izq = (w - nuevo_w) // 2
            img = img.crop((izq, 0, izq + nuevo_w, h))
        elif actual < objetivo:  # mas alta: sobra arriba y abajo
            nuevo_h = round(w / objetivo)
            arriba = (h - nuevo_h) // 2
            img = img.crop((0, arriba, w, arriba + nuevo_h))
        img = img.resize((ANCHO, ALTO), Image.LANCZOS)
        print(f"    aviso: la imagen venia en {original[0]}x{original[1]}; "
              f"la recorte al centro y la lleve a {ANCHO}x{ALTO}")
    return img


def rotular(img, title: str, subtitle: str, accent: str):
    """Superpone texto exacto sobre un arte propio, con antialiasing.

    Los generadores de imagen son buenos para el fondo pero no para texto tan
    chico. El rótulo se dibuja a 4x y se reduce al final, así el nombre del
    realm queda nítido incluso en los 60 px reales del cliente clásico.
    """
    from PIL import Image, ImageDraw

    prev = _load_preview_helpers()
    w, h = ANCHO * SUPERSAMPLE, ALTO * SUPERSAMPLE
    acc = prev.hex_to_rgb(accent)
    grande = img.resize((w, h), Image.LANCZOS).convert("RGBA")
    d = ImageDraw.Draw(grande, "RGBA")

    # Placa central translúcida: conserva el arte y evita el rectángulo negro
    # macizo que se notaba demasiado al escalar el banner dentro del cliente.
    cx = w // 2
    placa_w = int(w * .49)
    d.rounded_rectangle(
        [cx - placa_w // 2, h * .08, cx + placa_w // 2, h * .91],
        radius=h // 7, fill=(2, 5, 11, 158),
        outline=(*acc, 92), width=max(2, h // 90),
    )

    titulo = title.upper()
    font_t = prev.fit_font(d, titulo, int(w * .43), int(h * .45))
    # Sombra dorada desplazada + metal claro encima.
    d.text((cx + h * .012, h * .38 + h * .018), titulo, font=font_t,
           fill=(*acc, 210), anchor="mm", stroke_width=max(3, h // 55),
           stroke_fill=(0, 0, 0, 245))
    d.text((cx, h * .38), titulo, font=font_t, fill=(235, 239, 245, 255),
           anchor="mm", stroke_width=max(3, h // 55), stroke_fill=(0, 0, 0, 255))

    if subtitle:
        font_s = prev.fit_font(d, subtitle.upper(), int(w * .42), int(h * .18), bold=False)
        d.text((cx, h * .73), subtitle.upper(), font=font_s, fill=(*acc, 255),
               anchor="mm", stroke_width=max(2, h // 90), stroke_fill=(0, 0, 0, 255))

    # Línea inferior azul -> oro, consistente con los dos bandos del arte.
    for x in range(w):
        t = x / max(1, w - 1)
        color = tuple(round((45, 169, 255)[i] * (1 - t) + acc[i] * t) for i in range(3))
        d.line((x, h - 4, x, h), fill=(*color, 255))

    return grande.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genera el banner 468x60 del cliente")
    ap.add_argument("--title", help="texto grande (nombre del server)")
    ap.add_argument("--from-image", type=Path,
                    help="usar esta imagen en vez de dibujar (se adapta a 468x60)")
    ap.add_argument("--subtitle", default="", help="texto chico a la derecha")
    ap.add_argument("--accent", default="#3fc4ff")
    ap.add_argument("--bg-top", default="#16233a")
    ap.add_argument("--bg-bottom", default="#060a14")
    ap.add_argument("--out", type=Path, required=True, help="PNG de salida (468x60)")
    ap.add_argument("--preview", type=Path,
                    help="ademas, una copia agrandada x3 para mirarla comoda")
    args = ap.parse_args(argv)
    if not args.from_image and not args.title:
        ap.error("hace falta --title (para dibujarlo) o --from-image (para usar el tuyo)")

    try:
        if args.from_image:
            img = adaptar(args.from_image)
            if args.title:
                img = rotular(img, args.title, args.subtitle, args.accent)
        else:
            img = render(args.title, args.subtitle, args.accent, args.bg_top, args.bg_bottom)
    except ImportError:
        print("Falta Pillow (en el VPS: /opt/wc3/venv/bin/pip install pillow).",
              file=sys.stderr)
        return 3

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Sin alfa (RGB), igual que el que instala PvPGN de fabrica. Pillow nunca
    # escribe PNG entrelazado, asi que no hay nada que apagar.
    img.save(args.out, format="PNG")
    print(f"OK: {args.out} ({ANCHO}x{ALTO}, {args.out.stat().st_size} B)")
    if args.preview:
        from PIL import Image

        img.resize((ANCHO * 3, ALTO * 3), Image.NEAREST).save(args.preview)
        print(f"    vista previa x3: {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
