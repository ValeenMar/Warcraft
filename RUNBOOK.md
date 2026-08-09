# RUNBOOK — de cero a servidor con web, en cuatro fases

Cada fase tiene un criterio de "listo" verificable. No arrancar una fase sin
cerrar la anterior. Antes de todo: `./scripts/validate.sh` en verde en tu
máquina.

---

## Fase 0 (previa): lo que hay que conseguir

- [ ] **VPS: Vultr, región Santiago de Chile (`scl`)** — decidido con ping
      medido, ver docs/vps.md. Plan `vc2-1c-2gb` (1 vCPU / 2 GB, USD 10/mes)
      alcanza y sobra; `vc2-2c-4gb` (USD 20) si querés margen. Imagen
      **Ubuntu 24.04 LTS x64**. Facturación por hora, así que probarlo sale
      centavos. Al crearla: subí tu clave SSH en el paso "SSH Keys" y NO
      habilites el firewall de Vultr (lo maneja `ufw` desde el bootstrap).
- [ ] Instalación de W3 TFT **1.27a** (build `1.27.0.52240`): de ella salen
      `war3.exe`, `Storm.dll`, `Game.dll` y `War3Patch.mpq` para
      `/opt/wc3/mpq/`. Verificación rápida de que es genuina: `war3.exe` tiene
      que pesar **514.536 bytes**. El paso a paso y los errores típicos están
      en **docs/conseguir-el-juego.md**.
- [ ] Los primeros 3 mapas (sugeridos: DotA 6.83d, Footmen Frenzy, Sheep Tag
      — los tres `verde` en el registry).
- [ ] Dos personas con el juego instalado para la prueba de sincronía.

---

## Fase 1: PvPGN + 1 bot + 3 mapas, probado con dos clientes reales

### 1.a — Crear el VPS en Vultr

Precios verificados contra `api.vultr.com/v2/plans` el 2026-08-08.

| Campo del formulario | Qué elegir |
|---|---|
| Type | **Cloud Compute – Shared CPU** |
| CPU & Storage Technology | **Regular Performance** (Intel; es la familia `vc2`) |
| Location | **Santiago, Chile** |
| Image | **Ubuntu 24.04 LTS x64** |
| Plan | **`vc2-1c-2gb` — USD 10/mes**: 1 vCPU, 2 GB RAM, 55 GB NVMe, 2 TB |
| Auto Backups | **Off** (cuesta extra; ya tenemos `scripts/backup.sh`) |
| Cloud Firewall | **NO habilitarlo** — el firewall lo maneja `ufw` desde el bootstrap |
| SSH Keys | agregar la clave pública propia (ver abajo) |
| Hostname / Label | `wc3-revival` |

Si más adelante hace falta margen, `vc2-2c-4gb` son USD 20/mes y se
redimensiona sin reinstalar.

**Generar la clave SSH en Windows** (PowerShell, el OpenSSH ya viene incluido):

```powershell
ssh-keygen -t ed25519 -C "wc3"
type $env:USERPROFILE\.ssh\id_ed25519.pub    # esto es lo que se pega en Vultr
```

### 1.b — Acceso al repositorio desde el VPS

El repositorio es **privado**, así que el VPS necesita permiso para clonarlo.
Dos caminos:

- **Hacerlo público** (lo más simple). El repo está diseñado para no contener
  nada sensible: los secretos viven solo en `.env`, que está en `.gitignore`,
  y `validate.sh` verifica que no haya material del juego commiteado.
- **Deploy key** (si se prefiere mantenerlo privado): generar una clave en el
  VPS con `ssh-keygen -t ed25519 -f ~/.ssh/deploy -N ""`, pegar
  `~/.ssh/deploy.pub` en GitHub → Settings del repo → Deploy keys (solo
  lectura), y clonar por SSH con `git@github.com:ValeenMar/Warcraft.git`.

### 1.c — Instalación

**Antes de nada, comprobá que entrás por clave.** En el formulario de Vultr
tenés que haber cargado tu clave SSH; verificá que `ssh root@<IP>` entra sin
pedirte contraseña. Si te pide contraseña, la clave no quedó: resolvelo ahora,
antes de instalar nada.

```bash
# --- Como root, en el VPS recién creado -----------------------------------
apt-get update && apt-get install -y git
git clone https://github.com/ValeenMar/Warcraft.git /opt/wc3-repo
cd /opt/wc3-repo
./install/00-bootstrap-vps.sh valen     # usuario, ufw, fail2ban, swap, deps
```

El bootstrap **ya no toca la configuración de SSH**: el endurecimiento quedó
en `install/50-harden-ssh.sh`, que se corre a mano al final de la fase 1,
cuando ya está confirmado que el acceso por clave funciona. Aprendido a los
golpes: hacerlo automático dejó un VPS inaccesible (ver DECISIONES.md).

```bash
# --- Reconectado como el usuario nuevo -------------------------------------
ssh valen@<IP-del-VPS>

sudo chown -R valen:valen /opt/wc3-repo
cd /opt/wc3-repo

cp .env.example .env
openssl rand -base64 24                 # generar la password de MySQL
nano .env                               # WC3_PUBLIC_IP, WC3_DB_PASS, WC3_BOT_PASSWORD

make build                              # compila PvPGN y Aura (~10 min)
sudo ./install/30-setup-mysql.sh        # base + usuario
make render-config                      # configs finales
```

Lo mínimo a completar en `.env`: `WC3_PUBLIC_IP` (la IP que asignó Vultr),
`WC3_DB_PASS` y `WC3_BOT_PASSWORD`. El resto tiene defaults razonables.

### Archivos del juego

```bash
# desde tu maquina (sacados de una instalacion 1.27a):
scp war3.exe storm.dll game.dll War3Patch.mpq vps:/tmp/
# en el VPS:
sudo mv /tmp/{war3.exe,storm.dll,game.dll,War3Patch.mpq} /opt/wc3/mpq/
sudo chown root:wc3 /opt/wc3/mpq/* && sudo chmod 640 /opt/wc3/mpq/*
```

### Arranque y cuenta del bot

```bash
sudo systemctl enable --now pvpgn
tail -f /opt/wc3/pvpgn/var/pvpgn/bnetd.log   # ver: "listening ... 6112"
#   y que el primer arranque haya creado las tablas MySQL sin errores
#   (TODO(verificar) #2 de DECISIONES.md)

# crear la cuenta del bot: conectarse con el cliente W3 al server
# (docs/clientes.md) y loguearse una vez con WC3_BOT_USERNAME/PASSWORD
# (new_accounts=true crea la cuenta al primer login)

sudo systemctl enable --now wc3-hostbot@1
journalctl -u wc3-hostbot@1 -f               # ver: login al PvPGN OK
#   (TODO(verificar) #1: si el login falla por version, ver DECISIONES.md
#    decision 2 — plan B GHost++)
```

### Validación de los 3 mapas

Para cada mapa, el protocolo completo de docs/mapas.md:

1. Cargar en Custom Game **single player en 1.27a**; anotar que carga.
2. `inspect-map.py --update-registry`: tamaño y slots al registry.
3. Copiar a `/opt/wc3/maps/`, `!map ElMapa` en el canal del bot: el bot
   calcula el hash sin quejarse.
4. `!pub prueba` y entrar con **dos clientes reales desde redes distintas**:
   ambos entran al lobby, la partida arranca, 10 minutos sin desync ni drops.
5. Registry: `status: validado`, versión probada en `versions_known`.

### Estado real (2026-08-09, primera puesta en marcha)

Verificado funcionando: bootstrap, build de PvPGN y Aura en el VPS, MySQL con
tablas creadas, PvPGN escuchando (6112/6200) con la IP pública bien anunciada,
bot logueado al PvPGN (`cd keys accepted` + `logon successful`), cliente
1.27a conectado vía loader w3l + hosts, cuentas creadas, mapa cargado con CRC
calculado, partida creada y anunciada con IP:puerto correctos.

Bloqueo restante: el cliente no entra al lobby — causa raíz diagnosticada
(commit de 24 jugadores de Aura, ver DECISIONES.md #17), fix en
`install/20-build-hostbot.sh`; requiere re-correr ese script en el VPS.

### Criterio de listo

- [ ] `systemctl status pvpgn wc3-hostbot@1` ambos `active (running)` y
      sobreviven un `sudo reboot`.
- [ ] Dos clientes reales desde afuera crearon cuenta, chatearon en un canal,
      y jugaron una partida completa hosteada por el bot en cada uno de los
      3 mapas, sin desync.
- [ ] Los 3 mapas en `status: validado` en el registry.
- [ ] `make backup` corre y el tar contiene el dump.

---

## Fase 2: biblioteca de mapas + map pack distribuible

- Conseguir y validar el resto del catálogo (los 21 del registry), en orden:
  primero los `verde`, después `amarillo`, y los `rojo` al final (con plan B
  de remakes — ver notas del registry).
- Cada mapa pasa por el protocolo de docs/mapas.md; los que pasen de
  ~2-3 MB quedan marcados "solo map pack" (el techo duro de carga son
  8 MiB).
- Armar `wc3revival-maps-v01.zip` con todos los `validado` (docs/mapas.md,
  sección map pack) y publicarlo donde el grupo lo baje.
- Segunda instancia de bot arriba (`wc3-hostbot@2`, arena) con su canal.

### Criterio de listo

- [ ] Todo el catálogo en `validado` o `descartado` con nota (cero
      `pendiente`).
- [ ] Map pack v01 publicado; un jugador nuevo con el pack entra a cualquier
      partida sin descargar nada in-lobby.
- [ ] Dos bots corriendo con catálogos distintos.

---

## Fase 3: stats en MySQL + bot de Discord que anuncia lobbies

- Volcar stats de partidas a MySQL: Aura guarda stats (DotA incluida) en el
  sqlite `aura.dbs` de cada instancia; escribir un job (cron + python) que
  los consolide a la base MySQL junto a las cuentas PvPGN.
- Bot de Discord (discord.py o similar) que:
  - anuncia lobbies abiertos (leyendo el estado de los bots) con mapa y
    cantidad de slots libres,
  - publica resultados/stats básicos por jugador.
- Nada de esto toca la ruta de juego: si el bot de Discord muere, el server
  sigue.

### Criterio de listo

- [ ] Tabla(s) de stats en MySQL alimentadas automáticamente.
- [ ] Canal de Discord recibe "se abrió lobby de X" en <30 segundos.
- [ ] Consulta de stats de un jugador funcionando (aunque sea por comando).

---

## Fase 4: sitio web con registro de cuentas

- Web mínima (estática + un backend chico) con:
  - registro de cuenta PvPGN (escribiendo el hash a la base con el mismo
    formato que usa bnetd — verificar formato de `acct_passhash1` antes),
  - instrucciones de conexión (docs/clientes.md destilado + descarga del
    `.reg` de gateway),
  - link al map pack vigente y al Discord.
- HTTPS con caddy o nginx + certbot; abrir 80/443 en ufw recién acá.

### Criterio de listo

- [ ] Un amigo sin ayuda: entra a la web, se registra, configura el gateway,
      baja el pack y juega. Cero intervención manual del admin.
