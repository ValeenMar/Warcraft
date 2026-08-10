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
  instalar los mapas subidos, hacer backup ya, reiniciar PvPGN o un bot
  puntual. Cada botón pide confirmación y muestra el resultado.

## Prenderlo (una sola vez)

```bash
cd /opt/wc3-repo

# 1. ponerle contraseña: editar .env y completar WC3_DASH_PASSWORD
openssl rand -base64 18     # <- genera una; copiala en el .env
nano .env

# 2. instalar y prender
sudo make dashboard
```

El comando imprime la dirección final, tipo `http://TU-IP:8322/`. Se abre
desde cualquier navegador (PC o celular): usuario **admin**, la contraseña
es la que pusiste en `WC3_DASH_PASSWORD`. Sobrevive reinicios del VPS solo.

**Para el chat** falta un paso de una sola vez: crear la cuenta `panel` en el
server, desde el cliente del juego, con "New Account" (usuario `panel`,
contraseña la de `WC3_BOT_PASSWORD` — o la que definas en
`WC3_DASH_CHAT_PASSWORD` antes de correr `make dashboard`). Hasta que exista,
la sección de chat te lo recuerda; el resto del panel anda igual.

## Subir un mapa, ahora todo desde la página

1. Arrastrá el `.w3x` a la zona de subida.
2. Tocá **"Instalar ahora"**: les mete la preview, los deja en la carpeta
   del bot y archiva los originales.
3. Si el mapa **reemplaza** uno que ya se hostea, tocá "reiniciar" en el bot
   de ese mapa y listo. Si es **nuevo**, falta darle su bot (eso sí es por
   SSH): `./scripts/make-instances.py --maps-dir /opt/wc3/maps` te dice todo.

## Cómo hacen los botones para tocar el sistema (y por qué es seguro)

La página corre como el usuario `wc3`, que **no puede** reiniciar servicios
ni escribir en las carpetas del server. Cuando tocás un botón, la página
deja un *pedido* por escrito y un ayudante de root (otro servicio de
systemd) lo lee y ejecuta **solo si está en su lista blanca fija**:
instalar-mapas, backup, reiniciar-pvpgn, reiniciar-bot N. Nada más. Aunque
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
sudo make dashboard                     # reinstala/reinicia con la config del .env
```
