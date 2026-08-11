# Presentación: nombres de lobby y previews propias

Dos cosas distintas que el jugador ve antes de entrar a una partida, y que se
resuelven por caminos totalmente distintos:

| Lo que se ve | De dónde sale | Se cambia con |
|---|---|---|
| El **nombre** en la lista de partidas personalizadas | Lo escribe el que hostea (`!pub <nombre>`) | `maps/lobbies.yaml` + `scripts/lobby-names.py` |
| La **imagen** de preview al seleccionar la partida y en el lobby | `war3mapPreview.tga`, **adentro del archivo del mapa** | `scripts/brand-map.py` |

---

## 1. El nombre en la lista de partidas

Warcraft III pinta el texto con `|cAARRGGBB` y corta el color con `|r`. Por
ejemplo `|cFF00CCFFDotA` sale en celeste.

**El límite es 31 bytes contando los códigos de color.** No es una convención
nuestra: está en `aura.cpp:879`, y si te pasás el bot contesta *"The game name
is too long (the maximum is 31 characters)"*. Cada `|cAARRGGBB` gasta 10 bytes
y cada `|r` gasta 2, así que en la práctica entran unos 19 caracteres visibles
con un color, o unos 15 con dos. Los tests
(`tests/test_brand_map.py::TestLobbyNames`) fallan si algún nombre de
`maps/lobbies.yaml` se pasa.

Para sacar la chuleta lista para pegar:

```bash
python3 scripts/lobby-names.py
```

```
dota                   !pub DotA Allstars 6.83d
pudge-wars             !pub Pudge Wars 1.26 - 2 equipos
naruto-ninpou          !pub Naruto Ninpou Storm 0.9
...
```

Se pega con **Ctrl+V** en el chat de Battle.net, susurrándole al bot:

```
/w <nombre-del-bot> !map dota
/w <nombre-del-bot> !pub DotA Allstars 6.83d
```

> **Verificado el 2026-08-09 contra un cliente 1.27a real: no funcionan.** La
> lista de partidas personalizadas **no pinta** los códigos de color. Tampoco
> los muestra literales: se los come. `|cFF77DD44PUDGE |cFFFF3355WARS` se ve
> como `PUDGE WARS` en blanco, y los 20 bytes de los dos códigos se gastaron
> para nada.
>
> Por eso `scripts/lobby-names.py` ahora imprime los nombres **sin** color por
> defecto (`--color` sigue dando la versión vieja). El lado bueno: sin códigos
> quedan los 31 bytes enteros para el nombre, así que en vez de `DotA 6.83d`
> entra `DotA Allstars 6.83d`, y en vez de `PUDGE WARS`, `Pudge Wars 1.26 -
> 2 equipos`. Se perdió el color y se ganó claridad.

Desde el 2026-08-09 Aura **sí tiene autohost** — se lo agregamos nosotros
(`patches/aura-autohost.patch`, `DECISIONES.md`): cada instancia mantiene su
lobby abierto con el nombre de `maps/lobbies.yaml` y lo recrea sola cuando la
partida arranca. La chuleta de `lobby-names.py` queda para hostear **a mano**
un mapa distinto del que la instancia publica sola.

---

## 2. Previews propias

Al seleccionar una partida en la lista, y después en el lobby, el cliente
dibuja el **minimapa** del mapa. Salvo que el mapa tenga adentro un archivo
llamado exactamente `war3mapPreview.tga`: en ese caso dibuja esa imagen. Es el
mecanismo que usan DotA y compañía para mostrar una tapa en vez del terreno.

**Antes de generar nada, mirá qué trae el mapa.** Muchos mapas custom —los de
anime en particular— ya vienen con una `war3mapPreview.tga` hecha por el autor,
con arte de verdad. Pisarla con un dibujo generado es un downgrade, así que el
script por defecto **no la toca** y te avisa:

```bash
python3 scripts/brand-map.py /opt/wc3/maps/*.w3x --report --dump-previews /tmp/previews
```

```
=== DBZ Tribute Ultra.w3x
  tamano:  5778070 B (techo 8388608 B)
  estado:  PROTEGIDO (nombres ofuscados o sin listfile)
  preview: YA TIENE una, de 196652 B
  exportada a: /tmp/previews/DBZ Tribute Ultra.png
```

Con `--dump-previews` te las exporta a PNG para mirarlas todas juntas y decidir
cuáles vale la pena reemplazar. Para pisar una que ya existe hace falta
`--force`.

`scripts/brand-map.py` genera la imagen y la mete adentro del `.w3x` con
StormLib (vía el comando `smpq`):

```bash
# deja los mapas modificados en ./branded/, sin tocar los originales
python3 scripts/brand-map.py "DotA v6.83d.w3x" "Pudge Wars 1.26.w3x"

# o directo al directorio de mapas del server
sudo -u wc3 /opt/wc3/venv/bin/python scripts/brand-map.py \
    /opt/wc3/incoming/*.w3x --out-dir /opt/wc3/maps
```

El dibujo sale de `maps/lobbies.yaml`: fondo en degradé, un motivo (espadas,
shuriken, gancho, torre, versus, orbe, rayo, estrella), el título y la versión.
El mapa se elige por patrón sobre el nombre del archivo, y gana el primer
patrón que matchea (por eso `Anime Fight Arena*` va **antes** que
`Anime Fight*`).

Si preferís una imagen de verdad en lugar del dibujo generado, `--from-image`
acepta tanto una ruta local como una **URL**, que es lo cómodo en el servidor
donde no hay navegador:

```bash
python3 scripts/brand-map.py "Pudge Wars 1.26.w3x" \
    --from-image "https://ejemplo.invalid/pudge.png"
```

Por defecto **compone**: usa la imagen como figura y le deja encima el fondo
del tema, el título y el marco. Eso importa a 128×128, donde una foto sola se
vuelve puré ilegible; con el título abajo se entiende de qué mapa es de un
vistazo. Si la imagen ya es una tapa hecha y derecha, `--raw-image` la usa tal
cual, recortada al centro.

Sale siempre como TGA sin comprimir, que es lo que el motor clásico lee sin
sorpresas.

### Qué imagen buscar

Requisitos: **cuadrada** (se recorta al centro, así que si es apaisada perdés
los costados), **256×256 o más grande** para que no se vea pixelada al
reducir, y con el motivo **centrado**. Formato cualquiera: PNG, JPG, lo que
sea — la conversión a TGA la hace el script.

Qué buscar, por orden de qué tan bien queda:

1. **El arte del propio mapa.** En la página del mapa en EpicWar o Hive
   Workshop suele estar la imagen que subió el autor. Es la que mejor
   representa el mapa porque es literalmente su tapa.
2. **"key visual" o "poster" de la serie**, si el mapa es de anime. Buscar
   `<serie> key visual` da imágenes verticales de buena calidad; `<serie>
   square icon` o `<serie> app icon`, directamente cuadradas.
3. **Un personaje icónico sobre fondo liso.** Es lo que mejor sobrevive a
   128×128: a ese tamaño, una escena con mucho detalle se convierte en puré.

Lo que **no** funciona: capturas de pantalla del juego (a 128×128 no se
entiende nada), imágenes con texto chico, y cualquier cosa apaisada tipo
wallpaper 16:9 sin recortar antes.

### Las tres cosas que hay que tener en la cabeza

**1. Cambia el hash del mapa.** Aura calcula CRC y SHA1 del `.w3x`. El que
tenga el archivo original bajado de otro lado **no va a poder entrar**: se lo
va a tener que bajar del bot en el lobby. Por eso el mapa modificado tiene que
ser el mismo en `/opt/wc3/maps` del server y en el kit que se reparte. Después
de rebrandear hay que recargar el mapa en el bot:

```
/w <nombre-del-bot> !map <nombre>
```

**2. Hay un techo de 8 MiB** (8.388.608 bytes) en los clientes 1.24-1.28. La
preview agrega alrededor de **23 KB** al archivo (medido: TGA de 128×128 pesa
49.196 B sin comprimir y queda en ~22,8 KB comprimido con zlib dentro del
MPQ). DotA 6.83d viene con apenas ~170 KB de margen, así que entra, pero por
poco. El script aborta y deja el original intacto si el resultado se pasa —
hay un test que lo verifica.

**3. Los mapas protegidos rechazan la escritura — confirmado.** Muchos mapas
populares vienen "protegidos": les rompen a propósito las estructuras internas
del MPQ para que no se puedan abrir con el editor. Probado el 2026-08-09 contra
*DBZ Tribute Ultra* (epicwar 133974, 5,7 MB, real): StormLib contesta
`Cannot create new file 'war3mapPreview.tga': Operation not permitted`, tanto
para agregar un archivo nuevo como para reemplazar uno existente. En esos mapas
la preview propia **no es posible**; queda el nombre del lobby, que no depende
del archivo.

Ojo con una trampa acá: **`smpq` devuelve código de salida 0 aunque StormLib
falle**. Imprime el error por stderr y sale bien igual. Y en un mapa protegido
el listado del MPQ tampoco sirve para verificar, porque los nombres vienen
ofuscados. Por eso la única verificación que vale, y la que hace el script, es
volver a **extraer** el archivo del mapa y comparar los bytes con lo que se
quiso escribir.

**4. El mapa tiene que ser del usuario que corre el bot.** StormLib abre los
`.w3x` en lectura-**escritura**, así que un mapa de `root` en un directorio de
`wc3` hace que el bot no pueda abrirlo. En el log aparece como
`unable to load MPQ file` y el mapa queda inválido: sin partida publicada y sin
un error que se entienda. Es el mismo problema que ya había aparecido con el
`War3Patch.mpq` (`DECISIONES.md` #15). Desde el 2026-08-09 `brand-map.py` le
pone al archivo de salida el mismo dueño que su directorio, así que no depende
de acordarse del `chown`.

Un quinto detalle menor: si el mapa tiene prendido el flag *"Hide minimap in
preview screens"* del editor (bit 0 de los flags de `war3map.w3i`), el motor
puede tapar la pantalla de preview y no mostrar nada. `brand-map.py` lee ese
flag y avisa; es la primera cosa a mirar si la imagen no aparece.

### Verificado hasta acá

Contra un `.w3x` sintético (header HM3W de 512 bytes + MPQ v1), en Ubuntu
24.04 con `smpq` 1.6 / StormLib 9.21:

- StormLib abre y **escribe** dentro de un `.w3x` a pesar de los 512 bytes de
  header HM3W que preceden al MPQ, y el header queda intacto.
- `war3mapPreview.tga` aparece en el listado del MPQ después de inyectarlo.
- El corte por el techo de 8 MiB dispara y limpia la salida.

**Verificado el 2026-08-09 contra el cliente real**: se hosteó Pudge Wars con
la preview inyectada y la imagen aparece en el panel de la derecha de la lista
de partidas, en el lugar donde el cliente dibujaría el minimapa. El mecanismo
completo —generar el TGA, meterlo en el MPQ con StormLib, que Aura recalcule
el hash y que el cliente lo muestre— funciona de punta a punta.

En la misma prueba quedó descartado lo del color en los nombres (ver arriba).

---

## 3. El banner de arriba del chat y el mensaje de bienvenida

Las otras dos cosas que el jugador ve, apenas entra. Verificado contra el
código de PvPGN (el mismo commit que corre en el VPS) el 2026-08-09:

**El banner** es el sistema de publicidad del Battle.net clásico. Se declara
en `ad.json` (clave `adfile` de `bnetd.conf`), el archivo de imagen vive en el
`filedir` (`/opt/wc3/pvpgn/var/pvpgn/files/`) y el cliente lo baja por BNFTP.
Para Warcraft III sirve un **PNG común de 468×60** — `adbanner.cpp` mapea la
extensión `.png` al tag MNG que el cliente entiende, y 468×60 es la medida del
que PvPGN instala de fábrica (el logo de pvpgn.pro, que es lo que se ve hasta
que lo pisamos). Al hacerle clic, el cliente abre la URL declarada.

`scripts/make-banner.py` dibuja los nuestros y `40-render-configs.sh` instala
`banner.png` como `ad000001.png` y `banner-alt.png` como `ad000002.png`.
Warcraft III siempre informa `prev_ad_id=0`, así que PvPGN elige uno de los
dos al azar en cada pedido: la rotación se nota al reconectar o cuando el
cliente vuelve a pedir publicidad. Ambos llevan al hacer clic a
`WC3_SERVER_URL` (en producción, la invitación de Discord). Ojo: **el cliente
cachea los banners**, así que después de cambiarlos puede hacer falta cerrar el
juego y borrar/respaldar `bncache.dat` para verlos de inmediato.

**Para poner diseños propios**: dejar los archivos en
`config/pvpgn/banner.png` y `config/pvpgn/banner-alt.png`; el render los usa en
lugar de dibujar. Especificaciones completas en
`config/pvpgn/LEEME-banner.txt`; el resumen es **468×60, PNG, RGB sin
transparencia**. Si viene en otra medida, `make-banner.py --from-image` lo
recorta al centro hasta esa proporción en vez de deformarlo — pero conviene
dibujarlo directo en 468×60, porque es una franja muy apaisada (7,8 : 1) y un
logo cuadrado pierde la mitad de arriba y de abajo.

**El mensaje de bienvenida** (`w3motd.txt`) es el texto que aparece en el panel
derecho al loguearse. Warcraft antepone `Rank:` a cada evento informativo, así
que lo mantenemos en **una sola línea larga**: el cliente la envuelve según el
ancho de la pantalla y el prefijo aparece una sola vez. Los códigos de color sí
se renderizan. También acepta variables: `%s` (nombre del server), `%u`/`%g`
(jugadores/partidas ahora), `%U` (usuarios totales).

El template es `config/pvpgn/w3motd.txt.tpl`. El render pisa el archivo base
**y todas las variantes de idioma** de `i18n/` — eso es lo que mata el saludo
en alemán: PvPGN elige el archivo según el locale del cliente, y con todos los
idiomas pisados con el mismo texto, da igual con qué locale entre cada uno.

La columna grande de la izquierda sale de `news.txt`. Nuestro template es
`config/pvpgn/news.txt.tpl` y el render también pisa todas las variantes de
idioma, eliminando las noticias de fábrica de PvPGN. Cada bloque empieza con
`{MM/DD/YYYY}`; usar una fecha nueva fuerza a los clientes a recibir la entrada
nueva aunque conserven noticias viejas en `bncache.dat`.
