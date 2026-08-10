# Versión del juego: por qué 1.27a

**Versión objetivo: Warcraft III: The Frozen Throne 1.27a** (build in-game
`1.27.0.52240`, agosto 2016).

Antes este proyecto apuntaba a 1.26a. Se cambió el 2026-08-08 por un motivo
práctico: el operador ya tiene una instalación de 1.27a funcionando, PvPGN la
soporta de fábrica, y todos los mapas del catálogo andan igual. Ver la
sección "Historia de la decisión" al final.

## Qué versiones reconoce PvPGN

Verificado leyendo el `versioncheck.json` que instala el propio build de
PvPGN (2026-08-08):

| Versión | `version` en el protocolo | Tag | `war3.exe` esperado |
|---|---|---|---|
| 1.26a | 1.26.0.1 | `W3XP_126A` | 18/03/11 20:03:55, 471.040 B |
| **1.27a** | **1.27.0.16** | **`W3XP_127A`** | **05/08/16 03:15:27, 514.536 B** |
| 1.27b | 1.27.1.173 | `W3XP_127B` | 09/12/16 06:05:09, 515.048 B |

Las mismas entradas existen para `WAR3` (Reign of Chaos). O sea que 1.26a,
1.27a y 1.27b funcionan sin tocar el versioncheck.

**Truco de verificación**: esos tamaños de `war3.exe` son exactos. Si tu
`war3.exe` pesa **514.536 bytes** y tiene fecha 05/08/2016, es el ejecutable
genuino de 1.27a. Es la forma más rápida de saber si una instalación es
legítima o un repack.

Ojo con dos numeraciones distintas que confunden: el juego muestra
`1.27.0.52240` en el ángulo inferior derecho del menú, pero el protocolo de
Battle.net usa `1.27.0.16`. Son la misma versión.

## El techo de PvPGN: 1.28.5

PvPGN **no soporta 1.29 ni superior**. Eso descarta de plano el cliente
"Warcraft III – Legacy TFT 1.29" que Blizzard agregó a Battle.net en abril de
2026, por más tentador que suene (ver docs/conseguir-el-juego.md).

O sea que el rango real de elección es **1.24 a 1.28.5**, y dentro de ese
rango:

| | A favor | En contra |
|---|---|---|
| **1.26a** | Estándar de facto de los servidores latinos de DotA | Usa Direct3D 8: crashea en Windows 11 24H2 sin DDrawCompat. Conseguirlo limpio hoy es más difícil |
| **1.27a** ← elegido | Soporte oficial de Windows 7-10, abandonó D3D8. Es el que entrega el instalador oficial de Blizzard hoy. Descrito por la comunidad como "1.26a recompilado" | Menos usado que 1.26a en la escena latina |
| **1.28.5** | Techo de PvPGN, mejor compatibilidad moderna, mapas más grandes | No hay parche standalone oficial arriba de 1.27b en el FTP de Blizzard: es el más difícil de conseguir |

## El return bug de JASS (sigue siendo el filtro clave)

Esto **no cambia** al pasar de 1.26a a 1.27a, porque el corte está en 1.24 y
las dos versiones están por encima.

Hasta el parche 1.23, JASS permitía un exploit conocido como **return bug**:
una función podía devolver un tipo reinterpretado como otro (típicamente
`return H2I(handle)`), lo que permitía convertir handles en enteros y
viceversa. Era un bug de type-checking, pero se volvió LA base de los
sistemas avanzados de la época: handle vars de vJASS, sistemas de attachment,
"memoria extendida".

**El parche 1.24 (agosto 2009) lo eliminó** e introdujo los hashtables como
reemplazo. Consecuencia:

- Mapa que usaba el return bug y nunca se actualizó → **no carga o crashea**
  en 1.24 en adelante, o sea también en 1.26a y en 1.27a. Es el caso de
  muchos mods chicos de 2005-2008.
- Mapa mantenido → sacó versión "1.24 compatible" y funciona. El ejemplo
  canónico: **DotA 6.61b** fue la primera versión compatible con 1.24;
  cualquier DotA anterior no carga.

El campo `return_bug_risk` del registry clasifica exactamente este riesgo, y
la prueba de carga en single player (docs/mapas.md) es el filtro que lo
resuelve.

## Límites de tamaño de mapa

- **8 MiB (8.388.608 bytes)** es el techo real, tanto para cargar el mapa
  como para hostearlo. El famoso límite de **4 MB era PRE-1.24**: el parche
  1.24 lo subió a 8 MB.
  TODO(verificar): confirmar que 1.27a mantiene el mismo techo de 8 MiB y no
  lo subió (el salto grande a 128 MB llegó recién con 1.29).
- **No existe un tope duro de 4 MB para la transferencia in-lobby**, pero la
  transferencia es lentísima, así que en la práctica todo lo que pase de
  ~2-3 MB conviene repartirlo por **map pack** (fase 2) en vez de hacer
  esperar a la gente.
- Dato para tener presente: **DotA 6.83d pesa 8.218.959 B**, o sea que entra
  con apenas ~166 KB de margen. De 6.88 en adelante ya no entra.

## Cómo se cambia de versión

Todo lo dependiente de versión está detrás de variables. Migrar (por ejemplo
a 1.28.5) es:

1. `.env`: `WC3_WAR3_VERSION=28`.
2. Reemplazar los archivos de `/opt/wc3/mpq/` por los de la instalación
   nueva (el bot calcula `exeversion`/`exeversionhash` desde ahí).
3. `make render-config && sudo systemctl restart pvpgn wc3-hostbot@1 wc3-hostbot@2`.
4. Verificar que el `versioncheck.json` de PvPGN tenga la entrada de esa
   versión (la tabla de arriba se genera leyendo ese archivo).
5. Redistribuir el cliente a los jugadores: **todos migran o nadie**, porque
   versiones distintas no juegan entre sí.
6. **Los tres lugares versión-dependientes que NO salen de `WC3_WAR3_VERSION`**
   (fáciles de olvidar):
   - `config/pvpgn/w3motd.txt.tpl` saluda con "1.27a" hardcodeado;
   - `kit/INSTALAR.bat.tpl` verifica que `war3.exe` pese 514.536 bytes, que
     es el tamaño DE 1.27a (buscar el de la versión nueva);
   - el loader del kit usa `wl27.dll` para enganchar 1.27 (`build-kit.sh`);
     otra versión necesita su propia DLL, y 1.28+ directamente otro loader.

## Historia de la decisión

El proyecto arrancó apuntando a **1.26a**, por ser el estándar de facto de
las comunidades latinas de DotA de la era clásica. Se cambió a **1.27a** el
2026-08-08 por estos motivos, en orden de peso:

1. **Es lo que hay.** El operador ya tiene una instalación de 1.27a
   funcionando y verificada. Conseguir 1.26a limpio hoy requiere CDs físicos
   o comprar una copia usada, porque el canje de CD keys clásicas cerró el
   21/11/2025.
2. **PvPGN lo soporta de fábrica**, sin tocar el versioncheck.
3. **La gran mayoría del catálogo es formato 1.24a-1.28c** (13 de los 22
   entries confirmados `verde`, 7 `amarillo` casi seguros), así que andan
   igual en 1.27a que en 1.26a. Los 2 `rojo` (pre-1.24) hay que probarlos
   antes de publicar en cualquiera de las dos versiones — el registry es la
   fuente de verdad de esto.
4. **Anda mejor en Windows moderno**: 1.27a fue la versión que agregó soporte
   oficial de Windows 7-10 y abandonó Direct3D 8, que es de donde salen los
   crashes de 1.26a en Windows 11 24H2.
5. La ventaja de 1.26a (ser el estándar latino) **no aplica a un servidor
   privado para amigos**, donde la versión la decidimos nosotros.

Para volver a 1.26a alcanza con `WC3_WAR3_VERSION=26` y archivos de 1.26a en
`/opt/wc3/mpq/`; el resto del stack no cambia.
