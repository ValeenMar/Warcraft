# El dashboard de admin

Una página web que queda **siempre prendida** en el VPS y muestra, de un
vistazo y sin tocar una terminal:

- si PvPGN y cada bot están vivos (verde/rojo), y las últimas líneas del log
  de cada uno por si algo está en rojo;
- cuánta gente hay conectada al chat y cuántos están en lobbies/partidas;
- los mapas instalados, los backups (y te avisa en rojo si el último tiene
  más de 8 días), el disco y la RAM que quedan;
- una zona para **subir mapas arrastrándolos al navegador**, que reemplaza a
  `make recibir` para el uso diario (ya no hay que abrir la ventana temporal
  ni copiar tokens).

La página se actualiza sola cada 60 segundos.

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
es la que pusiste en `WC3_DASH_PASSWORD`. Guardala en el navegador y queda
a un clic. Sobrevive reinicios del VPS solo.

## Subir un mapa desde el dashboard

1. Arrastrá el `.w3x` a la zona de subida. Queda guardado en el server, en
   una carpeta de espera (`/opt/wc3/incoming`).
2. La página te muestra los mapas en espera y el comando exacto para
   instalarlos. Es el único paso que sigue necesitando SSH, porque escribir
   en la carpeta de mapas del bot requiere permisos que la página, a
   propósito, no tiene:

   ```bash
   cd /opt/wc3-repo && sudo make brand-maps
   ```

3. Si el mapa **reemplaza** uno que ya se hostea, con eso alcanza (más un
   `sudo systemctl restart wc3-hostbot@N` del bot afectado). Si es **nuevo**,
   el paso siguiente es darle su bot: `./scripts/make-instances.py
   --maps-dir /opt/wc3/maps` te dice todo lo que falta.

## Seguridad, para entenderla en una

- El dashboard corre como el usuario `wc3`, que no puede tocar nada del
  sistema: aunque alguien encontrara un agujero, no puede reiniciar
  servicios, ni borrar mapas, ni leer contraseñas.
- Lo único que lo separa de internet es la contraseña, y viaja por HTTP
  plano (sin candado). Es el mismo criterio asumido en el resto del
  proyecto: suficiente para un server de amigos. No reutilices ahí una
  contraseña que uses en otro lado.
- Si algún día molesta, se apaga con `sudo systemctl disable --now
  wc3-dashboard` y se cierra el puerto con `sudo ufw delete allow 8322/tcp`.

## Si algo no anda

```bash
systemctl status wc3-dashboard          # ¿está corriendo?
journalctl -u wc3-dashboard -n 30       # ¿qué dice el log?
sudo make dashboard                     # reinstala/reinicia con la config del .env
```
