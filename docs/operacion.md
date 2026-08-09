# Operación diaria

## Servicios

```bash
systemctl status pvpgn                  # el emulador de Battle.net
systemctl status wc3-hostbot@1          # bot instancia 1 (AoS)
systemctl status wc3-hostbot@2          # bot instancia 2 (arena)

sudo systemctl restart pvpgn            # tras cambiar configs de PvPGN
sudo systemctl restart wc3-hostbot@1    # tras cambiar la instancia 1
```

## Logs

```bash
journalctl -u pvpgn -f                       # stdout del proceso
tail -f /opt/wc3/pvpgn/var/pvpgn/bnetd.log   # log de aplicacion de PvPGN (el util)
journalctl -u wc3-hostbot@1 -f               # Aura loguea todo a stdout
```

Nivel de log de PvPGN: clave `loglevels` en bnetd.conf (default
`fatal,error,warn,info,debug,trace` — bajar a `fatal,error,warn,info` cuando
el server esté estable, editando el template y re-renderizando).

## Cambiar una config

Nunca editar los archivos finales a mano (el próximo render los pisa):

1. Editar el template en `config/` (o el `.env` / `instance-N.env`).
2. `make render-config` — hace backup fechado de lo anterior en
   `/opt/wc3/backups/configs/` y valida placeholders.
3. `sudo systemctl restart pvpgn` y/o `wc3-hostbot@N`.

## Agregar un bot (instancia nueva)

1. Crear `config/hostbot/instance-3.env` copiando el 2, con **puertos únicos**
   (hostport y reconnectport dentro de `WC3_BOT_PORT_RANGE`) y su canal/mapa.
2. `make render-config`
3. `sudo systemctl enable --now wc3-hostbot@3`
4. `./scripts/validate.sh` avisa si hay puertos en colisión.

## Agregar un mapa

Procedimiento completo en docs/mapas.md. Versión corta:

```bash
# copiar el .w3x al server
scp ElMapa.w3x vps:/opt/wc3/maps/
# inspeccionar y actualizar el registry
/opt/wc3/venv/bin/python scripts/inspect-map.py /opt/wc3/maps/ElMapa.w3x --update-registry
# indexarlo en el bot (en el canal del bot, como admin)
#   !map ElMapa
# validar con dos clientes y marcar status: validado en el registry
```

## Backups

```bash
make backup        # dump MySQL + configs -> /opt/wc3/backups/wc3-backup-FECHA.tar.gz
```

- Retención automática: últimos 14.
- Sacar una copia FUERA del VPS cada tanto (scp a tu máquina); un backup que
  vive solo en el server que respalda no es un backup.
- Restaurar: descomprimir el tar, `mysql pvpgn < dump/pvpgn.sql`, copiar
  configs, `systemctl restart`.

## Cuentas

- Con `new_accounts = true` (default) cualquiera que llegue al server puede
  crearse cuenta desde el cliente. Para cerrarlo cuando el grupo esté
  completo: en `config/pvpgn/bnetd.conf.tpl` poner `new_accounts = false`,
  renderizar y reiniciar.
- Hacer admin a una cuenta (para comandos del bot): agregarla a
  `WC3_BOT_ROOTADMINS` en `.env` + render + restart del bot. Para comandos
  de PvPGN (`/admin`), ver `command_groups.conf` del upstream.

## Si quedaste afuera del servidor por SSH

Pasa, y la salida es siempre la misma: **la consola web del proveedor**
(en Vultr, la instancia → *View Console*). No pasa por SSH, así que ni el
firewall, ni `fail2ban`, ni la config de sshd la afectan.

Desde ahí, como root:

```bash
fail2ban-client status sshd                 # ¿tu IP está en "Banned IP list"?
fail2ban-client unban --all                 # desbanear
passwd valen                                # darle contraseña al usuario admin
grep -r . /etc/ssh/sshd_config.d/           # ver qué config está aplicada
sshd -T | grep -Ei 'permitrootlogin|passwordauthentication'   # config EFECTIVA
```

Ese último comando es el importante: `sshd -T` muestra la configuración
**resuelta**, después de combinar todos los archivos. Es la única forma
confiable de saber qué está aplicado, porque sshd usa el **primer** valor que
encuentra leyendo `/etc/ssh/sshd_config.d/*.conf` en orden alfabético — un
archivo `50-cloud-init.conf` le gana a uno `90-loquesea.conf`.

Para revertir el endurecimiento por completo:

```bash
rm -f /etc/ssh/sshd_config.d/01-wc3-hardening.conf
systemctl reload ssh
```

Si el teclado de la consola web te desordena los símbolos de la contraseña
(pasa seguido con teclados en español), poné una contraseña temporal simple
con `passwd`, entrá por SSH, y desde ahí cargá la clave pública.

## Salud del VPS en 30 segundos

```bash
systemctl --failed                      # nada deberia listar
free -h && df -h /                      # memoria y disco
ss -ltnp | grep -E '6112|611[3-9]'      # puertos escuchando
sudo ufw status                         # firewall arriba
```

## Chuleta del día a día

Lo mínimo para operar sin releer todo lo de arriba.

### Hostear una partida (ciclo típico)

En el canal del bot (`AoS`), como admin:

```
!map dota          <- elegir el mapa (busca por nombre parcial en /opt/wc3/maps)
!pub viernes       <- abrir un lobby público llamado "viernes"
```

Después, desde el cliente: *Custom Game* → *Play Game* → **doble clic**
sobre la partida (seleccionarla de la lista NO llena el campo del nombre;
es doble clic o escribir el nombre exacto).

### Ver qué hay hosteado

- En cualquier chat de PvPGN: `/games` — lista todas las partidas
  anunciadas, con su IP:puerto (útil para verificar que se anuncia la IP
  pública y no otra cosa).
- En el canal del bot: `!games`.

### Diagnóstico de un join que no anda

```bash
sudo ./scripts/diagnose-join.sh        # 90 segundos de captura
sudo ./scripts/diagnose-join.sh 180    # o los segundos que hagan falta
```

Graba en paralelo el tcpdump de 6112-6114 y los dos logs mientras alguien
intenta entrar, y al final resume cuántos SYN llegaron al puerto del bot:
si son 0, el cliente ni intentó conectarse (el problema está en el anuncio
de la partida, no en la red ni el firewall).

### Los tres logs útiles

```bash
tail -f /opt/wc3/pvpgn/var/pvpgn/bnetd.log   # PvPGN: logins, canales, lista de partidas
journalctl -fu wc3-hostbot@1                 # Aura: lobbies, joins, CRC de mapas
journalctl -fu pvpgn                         # stdout del proceso (errores de arranque)
```
