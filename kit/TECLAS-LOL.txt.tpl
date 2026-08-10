===============================================================
  ${WC3_REALM_NAME} - Teclas estilo LoL (opcional)
===============================================================

Con doble clic a extras\WFE\INSTALAR-WFE.bat se instala el
Warcraft Feature Extender, una herramienta que le da al Warcraft
III clasico lo que no trae de fabrica. El programa se baja de su
sitio oficial (github.com/UnryzeC/WFE-Release) — no viaja dentro
del kit a proposito — y queda configurado con el perfil
"WC3Revival":

  Q W E R   las cuatro habilidades del heroe (fila de abajo)
  D F       habilidades extra (5ta y 6ta, si el mapa las tiene)
  Z X C     items 1, 2, 3
  V B N     items 4, 5, 6
  SMARTCAST en QWERDF: la habilidad se tira donde este el mouse,
            sin el clic extra, como en LoL. Los items no, para no
            tirar un teleport al suelo sin querer.
  VIDA      barras de vida siempre visibles, con color por bando:
            verde la tuya, celeste aliados, rojo enemigos. Y barra
            de mana en los heroes.

Las teclas solo aplican a HEROES: manejar aldeanos o construir
torres en un TD sigue funcionando como siempre.

Esto es 100% OPCIONAL. El juego anda perfecto sin nada de esto.


Ademas, el perfil trae prendido "Unlock Map Size": levanta el
tope de 8 MB que tiene el 1.27a para cargar mapas. Los mapas
GRANDES del server solo andan si TODOS los de la partida tienen
WFE activado con este perfil.


---------------------------------------------------------------
  COMO ACTIVARLO (una sola vez)
---------------------------------------------------------------

0. Doble clic a extras\WFE\INSTALAR-WFE.bat (baja e instala WFE
   adentro de tu carpeta de Warcraft III, con el perfil listo).

1. Abri WFE\WFEApp.exe (dentro de tu carpeta de Warcraft III).

2. En el campo Profile elegi "WC3Revival" (el perfil ya viene
   armado en la carpeta Profiles).

3. En el Injector, verifica que el Process Name sea: war3.exe
   (para la version 1.27a es ese; no hay que tocarlo)

4. Activa "Auto Injector". Con eso WFE se engancha solo cada vez
   que el juego este abierto.

5. Listo. Abri el juego como siempre (el acceso directo del
   escritorio / w3l.exe) y las teclas ya estan.

Deja WFEApp.exe abierto mientras jugas (se puede minimizar a la
bandeja). Para volver a las teclas normales: cerra WFEApp.exe.
Para sacarlo del todo: borra la carpeta WFE de tu Warcraft III.


---------------------------------------------------------------
  COSAS QUE CONVIENE SABER
---------------------------------------------------------------

EL ANTIVIRUS SE PUEDE QUEJAR. Para funcionar, WFE se inyecta en
el proceso del juego, y eso a los antivirus les huele mal. Es un
falso positivo conocido; el proyecto es publico y esta en
github.com/UnryzeC/WFE-Release. Si no te convence, no lo uses:
es opcional.

SI WFEApp.exe NO ABRE, falta el Visual C++ Redistributable de
32 bits (vc_redist.x86.exe). Se baja del sitio oficial de
Microsoft: buscar "latest supported Visual C++ downloads".

D Y F DEPENDEN DEL MAPA. Las teclas van por POSICION del boton:
QWER es la fila de abajo, que es donde casi todos los mapas ponen
las 4 habilidades. D y F son los dos botones derechos de la fila
del medio, donde suelen caer la 5ta y 6ta. Si un mapa acomodo los
botones en otro lado, alguna tecla puede caer en otra habilidad.

QWERDF PISA LAS TECLAS ORIGINALES de esas habilidades (asi lo
pide el perfil: ENFORCEHOTKEYS). Si preferis convivir con las
teclas del mapa, abri WFEApp, cambia Enforce Hotkeys a "no" y
guarda.
