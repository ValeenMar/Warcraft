# Discord de Gryz WC3

La integración publica avisos en `#lobbies` y `#estado` mediante la API REST
de Discord. No modifica Aura, no usa gateway/websocket, no consulta MySQL y no
instala paquetes de Python. El proceso queda bloqueado en `journalctl --follow`:
no hace polling y su unidad limita CPU a 10% y memoria a 64 MB.

## Secreto y descubrimiento inicial

El token vive únicamente en `/opt/wc3/discord-avisos.env`, modo `640`, dueño
`root:wc3`. Nunca se agrega al repo ni se pasa como argumento. Para cargarlo
desde una terminal SSH sin mostrarlo ni guardarlo en el historial:

```bash
read -rsp 'Token: ' WC3_DISCORD_TOKEN && printf '\n' && printf 'DISCORD_BOT_TOKEN=%s\n' "$WC3_DISCORD_TOKEN" > /opt/wc3/discord-avisos.env && unset WC3_DISCORD_TOKEN && chown root:wc3 /opt/wc3/discord-avisos.env && chmod 640 /opt/wc3/discord-avisos.env
```

Después, como root:

```bash
/usr/bin/python3 /opt/wc3/discord-avisos/avisos.py discover
/opt/wc3-repo/install/65-setup-discord.sh
```

`discover` verifica el bot, elige el servidor `Gryz WIII`, descubre los IDs
de `#lobbies` y `#estado` y los deja fijos en el archivo secreto.

## Eventos y anti-spam

- Primera entrada a un lobby vacío: nombre del jugador, mapa y lugares libres.
- Inicio de partida: mapa y cantidad de jugadores.
- Fallo de PvPGN, un hostbot o el backup: `OnFailure=` de systemd.
- Backup correcto: como máximo un resumen cada siete días.
- Disco raíz en 85% o más: timer cada seis horas.

Las recreaciones horarias de los autohost se ignoran. La búsqueda de partida
tiene un cooldown persistente de diez minutos por bot. Los POST se serializan
y separan al menos tres segundos; un HTTP 429 respeta `retry_after`.

## Pruebas controladas

Mensaje directo, sin esperar eventos reales:

```bash
/usr/bin/python3 /opt/wc3/discord-avisos/avisos.py test-lobbies
/usr/bin/python3 /opt/wc3/discord-avisos/avisos.py test-estado
```

Prueba real de lobby: entrar a cualquiera de las salas activas vacías. El aviso
debe llegar en menos de 15 segundos. Para el fallo de servicio, usar el bot 9
vacío; systemd lo vuelve a levantar por `Restart=on-failure`:

```bash
systemctl kill --signal=SIGSEGV wc3-hostbot@9
```

Disco sin llenarlo: ejecutar una vez con umbral temporal 0; no modifica config:

```bash
/usr/bin/python3 /opt/wc3/discord-avisos/avisos.py disk-check 0
```

## Consumo y apagado

Medición de un minuto sobre el PID real:

```bash
pidstat -p "$(systemctl show wc3-discord-avisos.service -p MainPID --value)" 10 6
```

Para apagar daemon, timer y enlaces de fallos sin borrar el token:

```bash
/opt/wc3-repo/install/65-setup-discord.sh --disable
```
