# Cómo se conecta un jugador

## Qué necesita el jugador

1. **Warcraft III: The Frozen Throne 1.27b** instalado (RoC + TFT). Todos
   los jugadores tienen que estar en la MISMA versión: versiones distintas no
   juegan entre sí. La instalación la consigue cada uno por su lado; este
   proyecto no distribuye archivos del juego. El camino concreto está en
   **docs/conseguir-el-juego.md**.
2. La **IP (o dominio) del servidor**: la `WC3_PUBLIC_IP` del `.env`.
3. Para mapas grandes: el **map pack** descomprimido en
   `Warcraft III/Maps/Download/` (ver docs/mapas.md).

## El loader es OBLIGATORIO, no opcional

Verificado contra el servidor real el **2026-08-08**. Los clientes modernos de
Warcraft III **verifican una firma criptográfica del servidor** antes de
seguir con el login. PvPGN no puede producirla (haría falta la clave privada
de Blizzard), así que el cliente corta la conexión por su cuenta.

Sin un loader que desactive esa verificación, **no hay forma de conectar**,
por más que el gateway apunte perfecto y el firewall esté abierto.

Cómo se ve el síntoma:

- En el cliente: `Unable to connect to Battle.net. You may be trying to
  connect to an invalid Battle.net server.`
- En `bnetd.log` del servidor, la conexión llega y muere enseguida:

```
sd_accept: accepted connection from <IP-del-jugador>:60857 on 0.0.0.0:6112
handle_init_packet: client initiated bnet connection
_client_auth_info: AUTH_INFO packet { platform=IX86, product=W3XP, versionid=0x1b, ... }
_client_auth_info: selected "ver-IX86-1.mpq" "B=... C=... A=..."
sd_tcpinput: read returned -1 (closing connection)     <-- el CLIENTE corta
```

Que el `AUTH_INFO` aparezca en el log es la prueba de que la red, el gateway y
el firewall están bien: el corte es decisión del cliente.

**Solución**: [Warcraft 3 Loader (w3l)](https://pvpgn.pro/w3l.html), GPL v3.
Se baja el paquete de la versión que corresponda (soporta de 1.22a a 1.28f),
se copian `w3l.exe`, `w3lh.dll` y la DLL de la versión (para 1.27b es
`wl27.dll`) a la carpeta de Warcraft III, y se abre el juego con **`w3l.exe`**
en vez del ejecutable normal. Los zips del sitio traen contraseña: `pvpgn`.

## Redirección de gateway (apuntar el cliente a nuestro PvPGN)

El cliente de W3 trae hardcodeadas las direcciones de Battle.net oficiales
("gateways"). Para entrar a un server PvPGN hay que agregar/redirigir un
gateway. Opciones, de la más simple a la más manual:

### Opción A: loader o editor de gateways (recomendada)

Dos herramientas libres, verificadas vigentes en 2026:

- **Warcraft 3 Loader (w3l)** — https://pvpgn.pro/w3l.html — GPL v3, no
  distribuye nada del juego: parchea en memoria tu `war3.exe` para que apunte
  a un PvPGN. Soporta de 1.22a a 1.28f.
- **Warcraft Feature Extender (WFE)** — https://github.com/UnryzeC/WFE-Release
  — soporta la familia 1.27 y además suma widescreen, borderless y
  smartcast.

También sirven los editores de gateway clásicos ("BNGatewayEditor", "W3
Gateway Editor"). Datos a cargar:

- **Nombre**: WC3 Revival (o el `WC3_REALM_NAME` que quede en el .env)
- **Dirección**: la IP pública del VPS
- **Puerto**: 6112
- **Timezone**: -3 (Argentina) — solo afecta cómo se muestra la hora

### Opción B: registro de Windows a mano

Los gateways viven en el valor multi-string **`Battle.net Gateways`** de
`HKEY_CURRENT_USER\Software\Blizzard Entertainment\Warcraft III`
(ojo: el valor se llama así, con espacio; un valor `Gateways` a secas el
juego lo ignora). Esto ya lo resuelve solo el kit: `INSTALAR.bat` llama a
`herramientas/gateway.ps1`, que agrega el server a esa lista sin pisar los
gateways existentes.

### Opción C: DNS local / hosts (la más rápida para probar)

Redirigir un gateway oficial (ej. `useast.battle.net`) a nuestra IP vía
`C:\Windows\System32\drivers\etc\hosts`:

```
203.0.113.10 useast.battle.net
```

Verificado funcionando: el gateway **Northrend (Europe)** del cliente resuelve
`europe.battle.net`, así que con esa línea el juego llega al servidor propio.

En Windows moderno conviene hacerlo desde PowerShell **como administrador**,
porque abrir el archivo desde el explorador lanza un editor sin permisos:

```powershell
Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" -Value "<IP> europe.battle.net"
ipconfig /flushdns
```

Efecto colateral a saber: **rompe la app de escritorio de Battle.net**, que
se queda colgada en "Security Check" al intentar hablar HTTPS con ese dominio.
El juego clásico no la necesita (se abre directo con `Frozen Throne.exe` o con
`w3l.exe`), pero si molesta, se revierte quitando la línea.

Ojo: el valor `Battle.net Gateways` del registro **puede no existir**; en ese
caso el cliente usa la lista que trae compilada adentro del ejecutable
(`gateway.ps1` lo crea si falta). Por eso el `hosts` es más confiable para
una prueba rápida a mano.

## Flujo del jugador

1. Abrir W3 → Battle.net → elegir el gateway nuevo.
2. **Crear cuenta**: con `new_accounts = true` (default actual), alcanza con
   poner usuario/contraseña nuevos en la pantalla de login la primera vez.
3. Entrar al canal `W3` (`/join W3`), donde viven todos los bots, y usar sus
   comandos:
   `!getgames` por susurro a un bot (su lobby actual) y `!gp 0` (quién espera).
4. Entrar a la partida desde Custom Games; si el mapa es chico (hasta ~2-3 MB)
   lo baja del bot ahí mismo; si es más pesado, la descarga in-lobby es
   impracticable y hace falta el map pack.

## Qué viaja por qué puerto (para diagnóstico)

| Puerto | Quién | Qué |
|--------|-------|-----|
| 6112/tcp | PvPGN | chat, login, lista de partidas |
| 6112/udp | PvPGN | test de red del cliente |
| 6200/tcp | PvPGN (w3route) | solo partidas PG/AT de ladder (no las custom del bot) |
| 6113+/tcp | cada bot | el juego en sí: el cliente se conecta AL PUERTO DEL BOT |

El dato crítico: cuando un jugador entra a una partida del bot, el bot le
anuncia **su IP:puerto dentro del protocolo** y el cliente abre una conexión
TCP directa a ese puerto. Por eso los puertos de los bots tienen que estar
abiertos en ufw y por eso NAT/bridge rompe todo (ver docs/docker-futuro.md).
