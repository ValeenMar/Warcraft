===============================================================
  ${WC3_REALM_NAME} - Kit para entrar al servidor
===============================================================

Servidor privado de Warcraft III: The Frozen Throne, con mapas
custom. Ping desde Argentina: entre 20 y 30 ms.


---------------------------------------------------------------
  QUE NECESITAS ANTES
---------------------------------------------------------------

Warcraft III completo (Reign of Chaos + The Frozen Throne) en la
version 1.27b, ya instalado.

Como saber si tenes la version correcta:
  - Entra a la carpeta del juego (normalmente
    C:\Program Files (x86)\Warcraft III)
  - Clic derecho en war3.exe -> Propiedades
  - Tiene que pesar EXACTAMENTE 515.048 bytes

Si te da otro numero, no vas a poder entrar. Ni 1.26, ni 1.28,
ni Reforged sirven: todos tenemos que tener la misma version.

NO TENES EL JUEGO, O TENES 1.27a? Usa igualmente INSTALAR.bat:
el mismo archivo llama al asistente que baja los DOS instaladores
oficiales de Blizzard (base 1.27a), descarga y aplica el parche oficial
1.27b y al final deja el juego apuntado al servidor. Lo unico que haces vos
es escribir TU CD key de 26 digitos cuando cada instalador la
pida — la key es tuya, no viene en el kit. Si no tenes keys, una
copia fisica usada de RoC + TFT con las keys legibles se consigue
barata, y con eso alcanza (no hace falta lectora de CD).

El juego NO viene en este kit y no se puede repartir.


---------------------------------------------------------------
  INSTALAR
---------------------------------------------------------------

Doble clic en INSTALAR.bat y seguir lo que dice.

Windows probablemente muestre "Windows protegio tu PC" porque el
archivo no tiene firma digital. Es esperable: es un .bat de
cuatro pasos que podes abrir con el Bloc de notas y leer entero.
Clic en "Mas informacion" -> "Ejecutar de todas formas".

Que hace, exactamente:
  1. Busca donde tenes instalado Warcraft III.
  2. Si falta, instala la base oficial; si es 1.27a, descarga y
     aplica el actualizador oficial 1.27b. Las versiones desconocidas
     se rechazan para no parchearlas a ciegas.
  3. Copia el loader (w3l.exe y dos DLLs) a la carpeta del juego.
     No pisa ni modifica ningun archivo del juego.
  4. Agrega el servidor a tu lista de Battle.net, sin borrar los
     que ya tenias, y lo deja elegido.
  Ademas: copia los mapas de la carpeta "mapas" (si hay) y te
  crea un acceso directo en el escritorio.

Para desinstalar: borra w3l.exe, w3lh.dll y wl27.dll de la
carpeta del juego. El servidor de la lista se saca desde la
propia pantalla de Battle.net del juego.


---------------------------------------------------------------
  JUGAR
---------------------------------------------------------------

1. Abri "${WC3_REALM_NAME}" desde el escritorio.

   IMPORTANTE: siempre por ahi, o por w3l.exe en la carpeta del
   juego. Si abris "Frozen Throne.exe" directo, no conecta. No
   es un capricho: el juego verifica una firma de Blizzard que
   un servidor privado no puede fabricar, y el loader es lo que
   resuelve eso.

2. Boton Battle.net. Arriba tiene que decir "${WC3_REALM_NAME}"; si
   dice otra cosa, tocá "Change Gateway" y elegilo.

3. Boton "New Account" para crear tu usuario.
   - Si te pide un mail, cancelá esa pantalla: no se usa.
   - NO HAY recuperacion de contraseña. Si la perdes, perdiste
     la cuenta. Anotala en algun lado.

4. Ya adentro, escribi:  /join ${WC3_BOT_CHANNEL}
   Ese es el canal donde vive el bot que abre las partidas.

5. Para recibir avisos cuando alguien entre a jugar, escribi una
   sola vez:  /watchall

6. Para entrar a una partida: menu Custom Game -> Play Game, y
   DOBLE CLIC sobre la partida en la lista.

   Ojo con esta: seleccionar la partida con un clic NO llena el
   campo del nombre, asi que apretar "Join" con la partida
   apenas marcada no hace nada y parece que estuviera roto. Es
   doble clic.

7. Adentro del lobby, todos escriben !ready. Cuando estan todos
   listos la partida arranca sola en 30 segundos. Tambien existen
   !notready, !checkme, !votekick y !yes.

Por susurro a cualquier bot podes usar !getgames para ver su
lobby, !gp 0 para ver quienes esperan, !stats y !status.


---------------------------------------------------------------
  SI ALGO NO SALE
---------------------------------------------------------------

"Unable to connect to Battle.net"
    Abriste el juego sin el loader. Usa el acceso directo
    "${WC3_REALM_NAME}" o w3l.exe. Si ya lo hiciste, fijate que arriba
    de la pantalla de Battle.net diga "${WC3_REALM_NAME}" y no
    "Azeroth" ni "Northrend".

Entro a la partida y me dice "could not be found", o me devuelve
a la lista
    Ese lobby ya no existe: la partida arranco, o se vencio por
    tiempo. Pedi en el canal que la vuelvan a abrir.

Veo la partida en la lista pero no puedo entrar
    Casi siempre es version distinta de Warcraft (mira los
    515.048 bytes de arriba) o que tenes una version distinta
    del mapa. Los mapas de este servidor estan modificados para
    que muestren una imagen propia en el lobby, asi que tiene
    que ser exactamente el que esta en la carpeta "mapas" o el
    que te baja el bot.

El juego crashea al abrir (tipico en Windows 11 24H2)
    Baja DDrawCompat de
    https://github.com/narzoul/DDrawCompat/releases
    y copia su ddraw.dll a la carpeta del juego. No hay que
    configurar nada.

El antivirus se queja del loader
    Es un falso positivo conocido de w3l: para poder conectar
    tiene que engancharse al proceso del juego, y eso a los
    antivirus les huele mal. Viene de pvpgn.pro, que es el
    proyecto de Battle.net emulado de toda la vida. Si no te
    convence, no lo instales.


---------------------------------------------------------------
  LOS MAPAS
---------------------------------------------------------------

Los que estan en la carpeta "mapas" los copia el instalador a la
carpeta del juego:
    <donde tengas Warcraft III>\Maps\Download

Ojo si buscas a mano: NO es la carpeta Documentos. Warcraft III
empezo a usar Documentos recien en el parche 1.28, y este
servidor es 1.27b.

Los que no tengas te los manda el bot solo cuando entras al
lobby (se ve una barra de descarga). Con los mapas grandes eso
tarda bastante, asi que conviene tener los del kit ya puestos.

1.27b admite mapas de hasta 128 MiB sin WFE. El kit no instala
inyectores ni herramientas que los antivirus marquen como HackTool.


---------------------------------------------------------------
  QUE HAY ADENTRO DEL KIT
---------------------------------------------------------------

  INSTALAR.bat            la unica entrada: instala, actualiza y configura
  INSTALAR-JUEGO.bat      asistente interno que el anterior llama solo
  LEEME.txt               esto
  loader\                 w3l 1.5.1.1, bajado de pvpgn.pro
  herramientas\           el script que agrega el servidor a la
                          lista de Battle.net
  mapas\                  mapas para copiar (puede venir vacia)

Todo es texto plano menos el loader. Se puede leer entero antes
de ejecutar nada.
