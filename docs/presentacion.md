# Presentación: nombres de lobby con color y previews propias

Dos cosas distintas que el jugador ve antes de entrar a una partida, y que se
resuelven por caminos totalmente distintos:

| Lo que se ve | De dónde sale | Se cambia con |
|---|---|---|
| El **nombre** en la lista de partidas personalizadas | Lo escribe el que hostea (`!pub <nombre>`) | `maps/lobbies.yaml` + `scripts/lobby-names.py` |
| La **imagen** de preview al seleccionar la partida y en el lobby | `war3mapPreview.tga`, **adentro del archivo del mapa** | `scripts/brand-map.py` |

---

## 1. Nombres con color

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
dota                   !pub |cFF00CCFFDotA |cFFFFCC006.83d
pudge-wars             !pub |cFF77DD44PUDGE |cFFFF3355WARS
naruto-ninpou          !pub |cFFFF8800Naruto Ninpou Storm
...
```

Se pega con **Ctrl+V** en el chat de Battle.net, susurrándole al bot:

```
/w <nombre-del-bot> !map dota
/w <nombre-del-bot> !pub |cFF00CCFFDotA |cFFFFCC006.83d
```

> **Falta confirmar:** que la *lista de partidas personalizadas* del cliente
> 1.27a renderice los códigos y no los muestre literales. Que los nombres de
> cuenta de Battle.net aceptan color está documentado y probado; que la lista
> de partidas también lo haga no lo pudimos probar sin un cliente. Es un test
> de 30 segundos: hosteá una partida y mirá la lista. Si sale
> `|cFF00CCFFDotA...` en crudo, corré `scripts/lobby-names.py --plain` y usá
> esos nombres; el resto del sistema no cambia.

Aura **no tiene autohost** y no saca el nombre del mapa, así que el nombre lo
pone siempre el operador a mano. Si algún día se quiere lobby permanente sin
tocar nada, la opción es GHost++, que sí tiene `!autohost` (ver
`DECISIONES.md` #18).

---

## 2. Previews propias

Al seleccionar una partida en la lista, y después en el lobby, el cliente
dibuja el **minimapa** del mapa. Salvo que el mapa tenga adentro un archivo
llamado exactamente `war3mapPreview.tga`: en ese caso dibuja esa imagen. Es el
mecanismo que usan DotA y compañía para mostrar una tapa en vez del terreno.

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

Si preferís una imagen de verdad en lugar del dibujo generado:

```bash
python3 scripts/brand-map.py mapa.w3x --from-image tapa.png
```

Recorta al centro, la lleva a 128×128 y la guarda como TGA sin comprimir, que
es lo que el motor clásico lee sin sorpresas.

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

**3. Los mapas protegidos pueden rechazar la escritura.** Muchos mapas
populares vienen "protegidos": les rompen a propósito las estructuras internas
del MPQ para que no se puedan abrir con el editor. StormLib suele poder
escribir igual, pero no siempre. Si falla, el script lo dice y no toca nada.

Un cuarto detalle menor: si el mapa tiene prendido el flag *"Hide minimap in
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

Lo que **no** está verificado y solo se puede probar con el cliente: que la
imagen efectivamente se vea en la pantalla de preview, y que los códigos de
color se rendericen en la lista de partidas.
