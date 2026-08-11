# Versión del juego: por qué 1.27b

**Versión objetivo: Warcraft III: The Frozen Throne 1.27b** (build in-game
`1.27.1.7085`, diciembre de 2016).

El servidor empezó en 1.27a y migra a 1.27b para admitir mapas de hasta
128 MiB sin WFE. PvPGN reconoce ambas versiones de fábrica, pero los clientes
y los cuatro archivos que usa Aura deben migrar juntos.

## Qué versiones reconoce PvPGN

Verificado leyendo el `versioncheck.json` que instala el propio build de
PvPGN (2026-08-08):

| Versión | `version` en el protocolo | Tag | `war3.exe` esperado |
|---|---|---|---|
| 1.26a | 1.26.0.1 | `W3XP_126A` | 18/03/11 20:03:55, 471.040 B |
| 1.27a | 1.27.0.16 | `W3XP_127A` | 05/08/16 03:15:27, 514.536 B |
| **1.27b** | **1.27.1.173** | **`W3XP_127B`** | **09/12/16 06:05:09, 515.048 B** |

Las mismas entradas existen para `WAR3` (Reign of Chaos). O sea que 1.26a,
1.27a y 1.27b funcionan sin tocar el versioncheck.

**Truco de verificación**: esos tamaños de `war3.exe` son exactos. El cliente
objetivo debe pesar **515.048 bytes** y mostrar `1.27.1.7085`.

Ojo con dos numeraciones distintas que confunden: 1.27b muestra
`1.27.1.7085` en el juego, pero el protocolo de Battle.net usa
`1.27.1.173`. Son la misma versión.

## El techo de PvPGN: 1.28.5

PvPGN **no soporta 1.29 ni superior**. Eso descarta de plano el cliente
"Warcraft III – Legacy TFT 1.29" que Blizzard agregó a Battle.net en abril de
2026, por más tentador que suene (ver docs/conseguir-el-juego.md).

O sea que el rango real de elección es **1.24 a 1.28.5**, y dentro de ese
rango:

| | A favor | En contra |
|---|---|---|
| **1.26a** | Estándar de facto de los servidores latinos de DotA | Usa Direct3D 8: crashea en Windows 11 24H2 sin DDrawCompat. Conseguirlo limpio hoy es más difícil |
| **1.27a** | Soporte oficial de Windows 7-10, abandonó D3D8. Es la base que entrega el instalador Legacy de Blizzard | Mantiene el límite de 8 MiB |
| **1.27b** ← elegido | Último parche standalone clásico; mapas de hasta 128 MiB | Todos los clientes deben actualizarse juntos |
| **1.28.5** | Techo de PvPGN, mejor compatibilidad moderna, mapas más grandes | No hay parche standalone oficial arriba de 1.27b en el FTP de Blizzard: es el más difícil de conseguir |

## El return bug de JASS (sigue siendo el filtro clave)

Esto **no cambia** al pasar de 1.27a a 1.27b, porque el corte está en 1.24 y
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
  en 1.24 en adelante, o sea también en 1.27a y en 1.27b. Es el caso de
  muchos mods chicos de 2005-2008.
- Mapa mantenido → sacó versión "1.24 compatible" y funciona. El ejemplo
  canónico: **DotA 6.61b** fue la primera versión compatible con 1.24;
  cualquier DotA anterior no carga.

El campo `return_bug_risk` del registry clasifica exactamente este riesgo, y
la prueba de carga en single player (docs/mapas.md) es el filtro que lo
resuelve.

## Límites de tamaño de mapa

- **1.27a:** 8 MiB (8.388.608 bytes).
- **1.27b:** 128 MiB (134.217.728 bytes). Este es el techo que aplican
  `upload-maps.py` y `brand-map.py`.
- **No existe un tope duro de 4 MB para la transferencia in-lobby**, pero la
  transferencia es lentísima, así que en la práctica todo lo que pase de
  ~2-3 MB conviene repartirlo por **map pack** (fase 2) en vez de hacer
  esperar a la gente.
- Dato para tener presente: **DotA 6.83d pesa 8.218.959 B**. En 1.27a entraba
  con apenas ~166 KB de margen; en 1.27b deja de estar al borde.

## Cómo se cambia de versión

Para migrar el servidor existente de 1.27a a 1.27b:

1. `.env`: mantener `WC3_WAR3_VERSION=27` (Aura usa la familia mayor 1.27).
2. Reemplazar los archivos de `/opt/wc3/mpq/` por los de la instalación
   nueva (el bot calcula `exeversion`/`exeversionhash` desde ahí).
3. `make render-config`, reiniciar PvPGN y todas las instancias
   `wc3-hostbot@N`.
4. Verificar que el `versioncheck.json` de PvPGN tenga la entrada de esa
   versión (la tabla de arriba se genera leyendo ese archivo).
5. Reconstruir el kit, que ahora valida 515.048 bytes y aplica el parche
   oficial 1.27b después de los instaladores Legacy.
6. Redistribuir el cliente a los jugadores: **todos migran o nadie**, porque
   versiones distintas no juegan entre sí.
7. **Los tres lugares versión-dependientes que NO salen de `WC3_WAR3_VERSION`**
   (fáciles de olvidar):
   - `config/pvpgn/w3motd.txt.tpl` saluda con "1.27b";
   - `kit/INSTALAR.bat.tpl` verifica exactamente 515.048 bytes;
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

La migración a **1.27b** se decidió el 2026-08-10 para admitir mapas de hasta
128 MiB sin obligar a los jugadores a usar WFE. El instalador Legacy sigue
siendo la base 1.27a y el kit aplica encima el parche standalone firmado por
Blizzard.
