# El dashboard de admin

Una página web que queda **siempre prendida** en el VPS y muestra **en vivo**
(se actualiza sola, sin recargar), sin tocar una terminal:

- si PvPGN y cada bot están vivos (verde/rojo), con el log de cada uno en un
  desplegable — y **quiénes están adentro de cada lobby/partida**, con nombre
  (se reconstruye del log del bot; los equipos no se ven porque el bot no los
  publica);
- **el chat del canal en vivo**: el panel entra al canal con su propia cuenta
  de PvPGN, ves quién está y lo que se dice, y podés escribir (los
  `/comandos` de PvPGN también valen);
- cuánta gente hay conectada y jugando, los mapas, los backups (con alerta
  roja si el último es viejo), el disco y la RAM;
- subir mapas **arrastrándolos al navegador**, y **botones** para lo demás:
  iniciar una partida, instalar mapas, hacer backup, reparar servicios caídos
  y reiniciar PvPGN o un bot puntual. Cada botón pide confirmación y muestra
  el resultado.

## Prenderlo (una sola vez)

```bash
cd /opt/wc3-repo

# 1. ponerle contraseña: editar .env y completar WC3_DASH_PASSWORD
openssl rand -base64 18     # <- genera una; copiala en el .env
nano .env

# 2. instalar y prender
sudo make dashboard
```

La forma recomendada es `WC3_DASH_BIND=127.0.0.1`: el panel no queda expuesto
a Internet y se abre desde Windows con `ABRIR-PANEL-WC3.bat`, que crea un
túnel SSH seguro y abre `http://127.0.0.1:18322/`. Usuario **admin**, con la
contraseña de `WC3_DASH_PASSWORD`; el navegador puede recordarla. El lanzador
también reinicia el dashboard si lo encuentra caído.

Dejar `WC3_DASH_BIND=0.0.0.0` conserva el acceso público anterior, pero HTTP
Basic viaja sin cifrado y no se recomienda sin HTTPS delante.

**Para el chat** faltan dos pasos de una sola vez:

1. Crear la cuenta `panel` desde el cliente del juego, con "New Account"
   (usuario `panel`, contraseña la de `WC3_BOT_PASSWORD` — o la que definas
   en `WC3_DASH_CHAT_PASSWORD`).
2. Correr `sudo make dashboard` de nuevo: además de reinstalar, le otorga a
   esa cuenta el **permiso de bot** que PvPGN exige para conexiones de chat
   (sin eso, el server la rechaza con "no bot access" aunque exista), y te
   dice si falta reiniciar PvPGN para que lo tome (botón del panel).

Hasta entonces, la sección de chat te va diciendo exactamente qué falta; el
resto del panel anda igual.

Para que el botón **Iniciar** controle los bots, la cuenta del panel también
debe figurar en `WC3_BOT_ROOTADMINS`, por ejemplo:
`WC3_BOT_ROOTADMINS="LoboGriz panel"`.

## Dónde está cada botón

- **Instalar mapas subidos** y **Hacer backup ahora**: en la barra de arriba,
  justo debajo de los números (y repetidos en sus secciones).
- **Iniciar**: al lado de cada lobby; manda `/w hostbotN !start` usando la
  cuenta autenticada del panel.
- **Reparar caídos**: levanta PvPGN o bots detenidos sin reiniciar los que ya
  están sanos, por lo que no corta partidas activas.
- **Reiniciar PvPGN**: en el recuadro "PvPGN" de los números de arriba.
  También reinicia los bots activos porque Aura no republica un lobby después
  de perder la conexión al servidor. La confirmación avisa que cae cualquier
  partida activa.
- **Reiniciar un bot**: al final de su fila en la tabla de bots.

Al instalar el panel también queda habilitado `wc3-backup.timer`: hace un
backup verificado todos los días a las 04:15 y conserva los últimos 14.

## Subir un mapa, ahora todo desde la página

1. Arrastrá el `.w3x` a la zona de subida.
2. Tocá **"Instalar ahora"**: les mete la preview, los deja en la carpeta
   del bot y archiva los originales.
3. Si el mapa **reemplaza** uno que ya se hostea, tocá "reiniciar" en el bot
   de ese mapa y listo. Si es **nuevo**, falta darle su bot (eso sí es por
   SSH): `./scripts/make-instances.py --maps-dir /opt/wc3/maps` te dice todo.

Mapas de **más de 8 MB**: el techo se levanta una sola vez con
`WC3_MAX_MAP_MB=64` en el `.env` + `sudo make dashboard`; el detalle (y lo
que necesitan los jugadores para poder cargarlos) está en
`docs/mapas-grandes.md`.

## Cómo hacen los botones para tocar el sistema (y por qué es seguro)

La página corre como el usuario `wc3`, que **no puede** reiniciar servicios
ni escribir en las carpetas del server. Cuando tocás un botón, la página
deja un *pedido* por escrito y un ayudante de root (otro servicio de
systemd) lo lee y ejecuta **solo si está en su lista blanca fija**:
instalar-mapas, backup, reparar-caidos, reiniciar-pvpgn, reiniciar-bot N.
Nada más. Aunque
alguien robara la contraseña del panel, no puede mandarle comandos propios
al servidor: como mucho aprieta esos mismos botones.

## Por qué NO hay una terminal

Una terminal de verdad en el navegador sería una shell de root viajando por
HTTP sin candado: cualquiera espiando la red se queda con el servidor
entero. Los botones cubren lo que se hacía por terminal en el día a día; para
lo demás está SSH (desde el celular, una app como Termius funciona bien).

## Si algo no anda

```bash
systemctl status wc3-dashboard          # ¿está corriendo el panel?
journalctl -u wc3-dashboard -n 30       # ¿qué dice su log?
journalctl -u wc3-dashboard-acciones -n 30   # ¿y el ayudante de los botones?
systemctl status wc3-backup.timer       # ¿está agendado el backup diario?
sudo make dashboard                     # reinstala/reinicia con la config del .env
```
