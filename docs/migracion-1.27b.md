# Migración del servidor: 1.27a → 1.27b

Objetivo: aceptar mapas de hasta 128 MiB manteniendo el stack clásico
PvPGN + Aura y las cuentas existentes.

## Antes del corte

1. Probar el cliente 1.27b local: `war3.exe` debe pesar 515.048 bytes y
   mostrar `1.27.1.7085`.
2. Confirmar que abre mediante `w3l.exe` + `wl27.dll`.
3. Ejecutar `sudo make backup` en el VPS.
4. Respaldar aparte los MPQ, porque `scripts/backup.sh` no los incluye:

   ```bash
   stamp="$(date +%Y%m%d-%H%M%S)"
   sudo cp -a /opt/wc3/mpq "/opt/wc3/backups/mpq-1.27a-${stamp}"
   ```

## Archivos del bot

Copiar desde una instalación limpia 1.27b estos cuatro archivos:

```text
war3.exe
Storm.dll
Game.dll
War3Patch.mpq
```

Subirlos primero a un directorio temporal y comprobar que `war3.exe` mida
515.048 bytes. Después:

```bash
for dir in /opt/wc3/hostbot/instances/*; do
    sudo systemctl stop "wc3-hostbot@${dir##*/}.service"
done
sudo install -o root -g wc3 -m 640 /tmp/wc3-1.27b/war3.exe /opt/wc3/mpq/
sudo install -o root -g wc3 -m 640 /tmp/wc3-1.27b/Storm.dll /opt/wc3/mpq/
sudo install -o root -g wc3 -m 640 /tmp/wc3-1.27b/Game.dll /opt/wc3/mpq/
sudo install -o root -g wc3 -m 640 /tmp/wc3-1.27b/War3Patch.mpq /opt/wc3/mpq/
```

`WC3_WAR3_VERSION` queda en `27`: Aura usa el número de la familia 1.27,
no la letra del parche. PvPGN 1.99.7.2.1-PRO ya incluye `W3XP_127B` en
`versioncheck.json`.

## Aplicar y probar

```bash
cd /opt/wc3-repo
make render-config
sudo systemctl restart pvpgn
for dir in /opt/wc3/hostbot/instances/*; do
    sudo systemctl start "wc3-hostbot@${dir##*/}.service"
done
sudo systemctl --no-pager --full status pvpgn 'wc3-hostbot@*.service'
```

Revisar los logs de una instancia. Aura debe calcular `exeversion` y
`exeversionhash` desde `/opt/wc3/mpq/` y completar el login:

```bash
journalctl -u wc3-hostbot@1 -n 100 --no-pager
```

Después entrar con dos clientes 1.27b, primero a un mapa conocido y luego al
mapa de más de 8 MiB. Recién cuando ambos funcionen, reconstruir y distribuir
el kit:

```bash
make kit
```

Versiones distintas pueden aparecer conectadas al mismo PvPGN si ambas pasan
el versioncheck, pero no deben mezclarse en una partida. El corte se comunica
como obligatorio: todos migran juntos.

## Rollback

Si el bot no logra autenticarse o calcular hashes:

```bash
for dir in /opt/wc3/hostbot/instances/*; do
    sudo systemctl stop "wc3-hostbot@${dir##*/}.service"
done
sudo cp -a /opt/wc3/backups/mpq-1.27a-FECHA/. /opt/wc3/mpq/
sudo systemctl restart pvpgn
for dir in /opt/wc3/hostbot/instances/*; do
    sudo systemctl start "wc3-hostbot@${dir##*/}.service"
done
```

Volver a repartir el kit 1.27a mientras se investiga el fallo.
