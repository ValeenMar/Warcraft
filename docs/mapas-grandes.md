# Mapas de más de 8 MiB (FOCS y compañía)

Algunos clásicos —Fight of Characters sobre todo— pesan 15-18 MB, muy por
encima del techo de 8 MiB del cliente 1.27a. **Se pueden jugar igual**, pero
con un costo que hay que entender antes de meterse.

## Qué es el límite, y qué no

El tope de **8.388.608 bytes (8 MiB)** es del **cliente** (`game.dll`), no del
servidor:

- **Aura (el bot) NO tiene límite.** Verificado en `src/map.cpp`: calcula el
  tamaño real del `.w3x` y lo hostea. Puede servir un mapa de 15 MB sin
  problema.
- **El `game.dll` de cada jugador rechaza los mapas > 8 MiB** al cargarlos o
  al unirse. Ese es el muro.

O sea: el server puede ofrecer FOCS; el problema está en cada PC.

## Cómo se levanta el límite del cliente

Dos caminos, verificados en foros (ENT Gaming, Hive) el 2026-08-09:

1. **Parche 1.27b** — Blizzard sacó el límite de fábrica en 1.27**b**. Pero
   este servidor es 1.27**a**: migrar es rehacer el versioncheck de PvPGN, el
   loader, y que todos reinstalen. Un proyecto aparte, no lo cubre esto.

2. **WFE → "Unlock Map Size"** — la misma herramienta de las teclas estilo
   LoL (`docs/presentacion.md`) quita el tope. Su texto: *"removes 4 MB and
   8 MB map limit from Online Hosting"*. El perfil `WC3Revival` que arma
   `scripts/make-wfe-profile.py` ya trae `REMOVEMAPSIZELIMIT = yes`, así que
   **cualquiera que active WFE con ese perfil ya lo tiene habilitado**. Es el
   camino de este proyecto. OJO: WFE **no viene en el kit** (decisión del
   2026-08-10: inyecta en el proceso del juego y los antivirus lo marcan, y
   eso hacía desconfiar de todo el kit) — cada jugador lo baja del sitio
   oficial (github.com/UnryzeC/WFE-Release) y el admin le pasa el perfil.

## El costo, sin vueltas

**Para un mapa grande, WFE deja de ser opcional: lo necesitan TODOS.** El que
no tenga WFE con Unlock Map Size activo no puede cargar el mapa — le va a
fallar al entrar al lobby. Los 8 mapas que están abajo de 8 MiB no dependen de
esto; solo los grandes.

**El mapa va SÍ o SÍ en el kit.** 15 MB por el lobby, a la velocidad de
transferencia de WC3, es una espera insoportable. Hay que repartir el archivo
para que todos lo tengan en el disco antes de entrar (`build-kit.sh` ya mete
en el kit todo lo que esté en `/opt/wc3/maps`).

**Es más frágil.** Depende de una inyección en el proceso del juego que el
antivirus marca (ver la nota de WFE). Un mapa chico "anda y ya"; uno grande
arrastra toda esa cadena.

## Cómo meter uno, paso a paso

En el servidor, con el techo de subida levantado a propósito:

```bash
# 1. recibir el .w3x grande (subi el techo para esta sesion)
sudo WC3_MAX_MAP_MB=64 make recibir

# 2. brandear permitiendo el tamano grande, e instalar en /opt/wc3/maps
sudo /opt/wc3/venv/bin/python scripts/brand-map.py \
    "/opt/wc3/incoming/FOCS...w3x" --out-dir /opt/wc3/maps --allow-large

# 3. instancia + cuenta del bot + arranque (igual que cualquier mapa)
sudo /opt/wc3/venv/bin/python scripts/make-instances.py --maps-dir /opt/wc3/maps
sudo make render-config
#   crear la cuenta hostbotN en el cliente, y:
sudo systemctl enable --now wc3-hostbot@N

# 4. rearmar el kit para que el mapa grande viaje adentro
make kit
```

`--allow-large` es opt-in a propósito: sin él, `brand-map.py` sigue abortando
a los 8 MiB, así que un mapa grande subido por error no pasa en silencio.

## Antes de bajar una versión

Da lo mismo lo que diga "Game Version" en EpicWar: mirá el **Size**. Si dice
más de 8 MB, hace falta todo lo de arriba. Si una versión más vieja del mismo
mapa entra abajo de 8 MB, es muchísimo menos lío — no necesita WFE, ni que el
mapa vaya obligatoriamente en el kit, ni nada de esto. Conviene chequear las
versiones viejas primero.
