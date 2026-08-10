===============================================================
  ${WC3_REALM_NAME} - Kit para entrar al servidor
===============================================================

Servidor privado de Warcraft III: The Frozen Throne, con mapas
custom. Ping desde Argentina: entre 20 y 30 ms.


---------------------------------------------------------------
  QUE NECESITAS ANTES
---------------------------------------------------------------

Warcraft III completo (Reign of Chaos + The Frozen Throne) en la
version 1.27a, ya instalado.

Como saber si tenes la version correcta:
  - Entra a la carpeta del juego (normalmente
    C:\Program Files (x86)\Warcraft III)
  - Clic derecho en war3.exe -> Propiedades
  - Tiene que pesar EXACTAMENTE 514.536 bytes

Si te da otro numero, no vas a poder entrar. Ni 1.26, ni 1.28,
ni Reforged sirven: todos tenemos que tener la misma version.

NO TENES EL JUEGO? Usa INSTALAR-JUEGO.bat en vez de INSTALAR.bat:
baja los DOS instaladores oficiales de Blizzard (que instalan
directo la 1.27a), los corre en orden, y al final te deja el
juego ya apuntado al servidor. Lo unico que tenes que hacer vos
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
  2. Chequea que sea 1.27a y avisa si no.
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

5. Para ver que hay abierto ahora, escribi:  !games

6. Para entrar a una partida: menu Custom Game -> Play Game, y
   DOBLE CLIC sobre la partida en la lista.

   Ojo con esta: seleccionar la partida con un clic NO llena el
   campo del nombre, asi que apretar "Join" con la partida
   apenas marcada no hace nada y parece que estuviera roto. Es
   doble clic.


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
    514.536 bytes de arriba) o que tenes una version distinta
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
servidor es 1.27a.

Los que no tengas te los manda el bot solo cuando entras al
lobby (se ve una barra de descarga). Con los mapas grandes eso
tarda bastante, asi que conviene tener los del kit ya puestos.


---------------------------------------------------------------
  TECLAS ESTILO LOL (opcional, NO viene en el kit a proposito)
---------------------------------------------------------------

Se pueden tener QWER para las habilidades, smartcast y barras de
vida siempre visibles, con una herramienta que se llama WFE
(Warcraft Feature Extender). NO viene en este kit a proposito:
para funcionar se inyecta en el proceso del juego, y eso el
antivirus lo marca como amenaza (es un falso positivo, pero mete
miedo). Meterlo en el kit haria que el instalador parezca un
virus, y la idea es que sea confiable.

Si te interesa, lo bajas por tu cuenta desde el sitio oficial:
    github.com/UnryzeC/WFE-Release
y le pedis al admin el perfil ya armado (WC3Revival.ini).

Aclaracion sobre W3Champions, por si lo estabas pensando: no
sirve aca. Necesita Reforged / 1.32, y este servidor es 1.27a.


---------------------------------------------------------------
  QUE HAY ADENTRO DEL KIT
---------------------------------------------------------------

  INSTALAR.bat            el instalador (si ya tenes el juego)
  INSTALAR-JUEGO.bat      baja e instala el juego oficial + lo anterior
  LEEME.txt               esto
  loader\                 w3l 1.5.1.1, bajado de pvpgn.pro
  herramientas\           el script que agrega el servidor a la
                          lista de Battle.net
  mapas\                  mapas para copiar (puede venir vacia)

Todo es texto plano menos el loader. Se puede leer entero antes
de ejecutar nada.
