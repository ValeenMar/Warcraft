# Mapas de más de 8 MiB (FOCS y compañía)

La versión objetivo del servidor es **Warcraft III 1.27b**. Blizzard elevó
en este parche el límite de mapas de **8 MiB a 128 MiB**, por lo que mapas de
15-18 MB como Fight of Characters se pueden jugar sin WFE ni modificaciones
inyectadas en `game.dll`.

## Requisitos

- Todos los jugadores deben usar **1.27b**. Un cliente 1.27a seguirá
  rechazando el mapa y tampoco es compatible con las partidas del servidor.
- El bot debe calcular los hashes usando `war3.exe`, `Storm.dll`, `Game.dll`
  y `War3Patch.mpq` de la misma instalación 1.27b.
- El archivo que tengan los jugadores debe ser exactamente el mismo que usa
  Aura. Si se cambia una preview dentro del MPQ, cambia también el hash.

Aura no impone el viejo techo de 8 MiB: lee el tamaño real del `.w3x` y puede
hostearlo. El límite relevante es el del cliente 1.27b, de 128 MiB.

## Distribución

Aunque el juego lo acepte, bajar 15 MB dentro del lobby clásico es demasiado
lento. Todo mapa grande debe viajar dentro del kit y copiarse antes de entrar
a la partida a:

```
<carpeta de Warcraft III>\Maps\Download
```

El `INSTALAR.bat` del kit ya hace esa copia.

## Cómo incorporarlo

El camino cómodo es subir el mapa desde el dashboard y pulsar **Instalar
ahora**. La alternativa por SSH es:

```bash
# 1. Abrir temporalmente la página de subida (acepta hasta 128 MiB)
sudo make recibir

# 2. Inspeccionar el mapa
sudo /opt/wc3/venv/bin/python scripts/brand-map.py \
    "/opt/wc3/incoming/FOCS...w3x" --report

# 3. Instalarlo en la biblioteca del bot; si ya trae preview se conserva
sudo /opt/wc3/venv/bin/python scripts/brand-map.py \
    "/opt/wc3/incoming/FOCS...w3x" --out-dir /opt/wc3/maps

# 4. Generar instancia/config, crear la cuenta hostbotN y arrancarla
sudo /opt/wc3/venv/bin/python scripts/make-instances.py --maps-dir /opt/wc3/maps
sudo make render-config
sudo systemctl enable --now wc3-hostbot@N

# 5. Rearmar el kit: el mapa queda incluido para los jugadores
make kit
```

Antes de publicarlo, probar una partida con dos clientes 1.27b desde redes
distintas. El techo de las herramientas del repo también es 128 MiB: un mapa
que lo supere se rechaza antes de llegar al bot.

WFE no forma parte del kit: 1.27b elimina la necesidad de inyectar una
herramienta marcada por algunos antivirus sólo para superar los 8 MiB.
