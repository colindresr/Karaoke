# Guía de uso — Karaoke inteligente

## 1. Qué hace

El programa guarda canciones en una base de datos, permite buscarlas mientras se canta
y muestra la línea que toca. Tiene modo manual y automático. Funciona en Windows y en
Android con Termux. En Android se usa desde una terminal; **no es una app con pantallas
y botones propios**.

## 2. Archivos

Deja juntos `karaoke.py`, `canciones_db.py` y `automatico.py`. El programa crea la base
de datos si todavía no existe. También puedes usar:

- `canciones_db.py`: acceso a SQLite, catálogo, búsquedas y operaciones con letras.
- `PROGRAMA.txt`: lista tentativa, con un nombre de canción por línea.
- `canciones_ejemplo.txt`: ejemplo del formato para cargar letras.
- `requirements.txt`: dependencias del modo automático con micrófono en PC.

La base de datos se crea o se abre en la misma carpeta que `karaoke.py`.

## 3. Instalación y ejecución en Windows

1. Instala Python 3.10 o posterior desde [python.org](https://www.python.org/downloads/).
   Durante la instalación, activa **Add Python to PATH**.
2. Abre PowerShell y entra a la carpeta del programa, por ejemplo:

   ```powershell
   cd C:\Karaoke
   ```

3. Para usar el modo manual no necesitas instalar paquetes adicionales. Ejecuta:

   ```powershell
   python .\karaoke.py
   ```

4. Para usar el modo automático con micrófono, instala sus dependencias en ese mismo
   Python:

   ```powershell
   python -m pip install -r .\requirements.txt
   ```

   Permite que Python use el micrófono en la configuración de privacidad de Windows.
   La primera vez, Whisper descarga el modelo indicado en `automatico.py`, así que
   necesitarás conexión a Internet y espacio libre.

Si no reconoce el comando `python`, prueba con `py` en su lugar.

## 4. Instalación y ejecución en Android

En Android, el programa se ejecuta desde la consola de **Termux**. Para pasar la voz a
texto usa el reconocedor de Android mediante Termux:API; no instala ni ejecuta Whisper
en el teléfono.

**Nota sobre el reconocimiento:** el modo de teléfono puede reconocer peor el canto
que el modo de PC, sobre todo si hay música o ruido. En Android se depende del servicio
de voz del teléfono; en PC se usa Whisper. Los resultados también cambian según el
micrófono, el ambiente y el equipo, así que ninguno garantiza una transcripción perfecta.

1. Instala **Termux** y **Termux:API** desde F-Droid. Descarga las dos desde el mismo
   lugar; no mezcles versiones de F-Droid y otras tiendas.
2. Abre Termux y ejecuta:

   ```sh
   pkg update
   pkg install python termux-api
   ```

3. Instala el complemento **Termux:API** y permite el uso del micrófono cuando Android
   lo pida. Comprueba que el comando esté disponible:

   ```sh
   command -v termux-speech-to-text
   ```

4. Copia a una carpeta accesible desde Termux los archivos `karaoke.py`,
   `canciones_db.py`, `automatico.py` y, si ya tienes canciones guardadas,
   `CANCIONES.db`. También puedes copiar los archivos de texto de ejemplo. Puedes
   pasarlos por USB, descargarlos o usar otro método. En Termux, entra a esa carpeta,
   por ejemplo:

   ```sh
   cd ~/karaoke
   ```

   Si descargaste los archivos en `Download`, primero activa el acceso compartido con
   `termux-setup-storage` y cópialos desde `~/storage/downloads`.
5. Inicia el programa:

   ```sh
   python karaoke.py
   ```

6. Elige `(a)` y luego `(a)` para usar el teléfono. Acepta los permisos de
   reconocimiento y micrófono si aparecen. Canta cerca del teléfono. Android convierte
   lo que oye en texto y el programa lo compara con las letras guardadas.

No instales `requirements.txt` en Android para esta opción. El modo Android no usa
`sounddevice`, SciPy ni Whisper. El reconocimiento depende del servicio de voz y del
idioma configurado en el teléfono; puede necesitar Internet. Deja Termux abierto y
evita que Android lo cierre para ahorrar batería.

## 5. Menú principal

- **(m) Modo manual**: escribe dos o tres palabras que escuches y elige una canción si
  aparecen varias coincidencias. También puedes usar la lista de canciones.
- **(a) Modo automático**: detecta frases transcritas por Whisper (PC), por Termux:API
  (Android) o por un archivo de simulación (pruebas). Aprovecha el `PROGRAMA.txt` si
  existe (ver sección 7).
- **(f) Alimentar base de datos**:
  - `(t)`: importa un archivo de texto con el formato descrito más abajo.
  - `(e)`: escribe el nombre y luego una línea a la vez; una línea vacía termina.
- **(p) Lista de canciones**: ver, escribir o importar una lista. Para cambiarla
  directamente, edita `PROGRAMA.txt` y pon un nombre por línea. Puedes elegir otra
  canción aunque no sea la siguiente de la lista.
- **(w) Ver catálogo**: muestra códigos y nombres en páginas de diez.
- **(x) Ver letra**: pide un código y muestra la letra en páginas de diez líneas.
- **(u) Corregir**: busca por nombre o código; permite cambiar el nombre, corregir,
  insertar, eliminar o reescribir líneas.
- **(b) Borrar**: busca por nombre o código y pide confirmación antes de borrar.
- **(q) Salir**.

### Formato para alimentar canciones desde texto

La primera línea de cada bloque es el nombre de la canción y las siguientes son partes
de la letra. Separa las canciones con una línea vacía, como en `canciones_ejemplo.txt`:

```text
Nombre de la canción
Primera línea de la letra
Segunda línea de la letra

Otra canción
Primera línea
```

Al importar, se saltan los nombres que ya están guardados. Los códigos se asignan solos.

### Primer uso recomendado

1. Iniciar el programa y elegir **(f) Alimentar base de datos**.
2. Elegir **(t) desde archivo de texto** e indicar la ruta de
   `canciones_ejemplo.txt`. Si se está en la carpeta del programa, basta con escribir
   `canciones_ejemplo.txt`.
3. Elegir **(w) Ver catálogo** y comprobar que aparezcan los nombres importados.
4. Elegir **(x) Ver letra** y abrir una canción por su código para comprobar que las
   líneas quedaron en el orden esperado.
5. Probar primero el **modo manual**. Cuando el catálogo y las letras estén correctos,
   probar el modo automático con una canción conocida.

La primera vez, el programa crea `CANCIONES.db` junto a `karaoke.py`. Las canciones
importadas se conservan allí entre ejecuciones; no hace falta volver a importarlas.
Si se importa de nuevo el mismo archivo, los nombres que ya existen se omiten.

### Cómo preparar las letras

- Mantener una línea por cada parte que se quiera mostrar en pantalla.
- Separar una canción de la siguiente con una línea vacía.
- Poner el nombre de la canción en la primera línea del bloque.
- Revisar acentos, palabras y orden antes de importar. El programa guarda el texto tal
  como aparece y lo usa para buscar coincidencias.
- Evitar incluir encabezados adicionales dentro del bloque, porque se tratarán como
  parte de la letra.

El ejemplo `canciones_ejemplo.txt` muestra varios bloques. Para una canción propia,
puede copiarse ese formato a otro archivo de texto y conservar el archivo original como
referencia.

## 6. Modo manual: controles para cantar

El modo manual sirve para avanzar a mano y también para comprobar si una canción y su
letra están bien cargadas. En el menú, se pueden escribir unas palabras de la letra
para buscar coincidencias. Si aparecen varias canciones, se muestra una lista para
elegir; si la búsqueda es clara, se abre directamente la coincidencia principal.

- **Enter** o `c`: mostrar la siguiente línea.
- `i`: quedarse en la línea actual cuando se repite.
- `r`: reiniciar la canción desde la primera línea.
- `g`: ignorar temporalmente (pausar el avance mientras se afina o se descansa).
- `s`: continuar después de ignorar.
- `b`: volver a elegir otra canción.
- `f`: terminar la sesión.

Al terminar una canción, vuelves a la selección y puedes cantar otra. En el menú manual,
`p` carga la siguiente canción de la lista, `o` deja elegir otra de esa lista y `w`
muestra el catálogo.

La lista es opcional. Para prepararla, usar **(p) Lista de canciones** desde el menú
principal y elegir si se desea escribirla en pantalla o importarla desde otro archivo.
Cada línea debe contener un nombre. Se puede editar `PROGRAMA.txt` con cualquier
editor de texto; una línea que empiece con `#` se ignora al leer el archivo.

## 7. Modo automático: controles

En automático, el programa sigue escuchando sin pedir una tecla por línea. Para abrir
los controles, pulsa **Ctrl+C una vez**. Esto abre el menú, no cierra el programa:

- Enter: volver a escuchar.
- `c`: avanzar manualmente una línea.
- `i`: mantener la línea actual.
- `r`: repetir la canción desde el inicio.
- `g`: ignorar temporalmente; `s`: reanudar.
- `b`: buscar otra canción.
- `f`: finalizar el modo automático.
- `n`: revisar/guardar una canción nueva detectada; `d`: descartar el borrador.
- `p`: cantar la siguiente canción del programa sin esperar a oírla (equivale a la `p`
  del modo manual).

**Lista de canciones en automático.** Si existe `PROGRAMA.txt`, la pantalla muestra
cuántas canciones ya se cantaron y cuál sigue. La canción siguiente tiene una pequeña
ventaja cuando el programa intenta reconocerla; las otras canciones pendientes también
tienen una ventaja menor. El orden **no** es obligatorio: se puede cantar cualquier
canción de la base, saltarse una o repetirla. Al empezar una canción de la lista, el
programa pasa a la siguiente. Si una canción de la lista no está en la base, aparece
`[NO ESTÁ EN LA BD]` y la tecla `p` la salta.

Si el programa detecta una canción que no está en la base, guarda el texto como borrador.
Después puedes corregir las líneas, ponerle nombre y guardarla, o descartarla. La
transcripción puede tener errores: revísala antes de guardarla.

### Antes de iniciar la escucha

- Comprobar que la canción está en la base y que sus líneas están completas. El modo
  automático compara la voz reconocida con esas letras; no busca canciones en Internet.
- En PC, instalar las dependencias con el mismo Python que inicia `karaoke.py`, permitir
  el micrófono y esperar a que Whisper cargue el modelo.
- En Android, probar primero `termux-speech-to-text` desde Termux. El reconocedor del
  teléfono puede mostrar su propia pantalla y depende de la configuración de voz del
  dispositivo.
- Reducir el volumen de la música que llega al micrófono y colocar el dispositivo cerca
  de quien canta. La música alta puede hacer que el reconocedor devuelva palabras de la
  canción de fondo, silencios o frases equivocadas.

El modo automático intenta ubicar la frase reconocida en la canción. Cuando no puede
confirmar una línea, el avance estimado puede ayudar, pero es aproximado. Usar `c`, `i`
o `r` desde el menú de control permite corregir la posición durante la prueba.

### Probar sin micrófono

La fuente de simulación sirve para revisar el motor antes de configurar audio. Crear un
archivo de texto, por ejemplo `prueba.txt`, con una frase reconocible por línea:

```text
La tarde deja un hilo dorado sobre el callejon
una taza espera tranquila junto al balcon
cuando la noche enciende su farol azul
```

Estas frases corresponden a `Luz en la ventana` en el archivo de ejemplo. Importar esa
canción primero y luego elegir **(a) Modo automático → (t) simulación desde archivo de
texto**. Indicar la ruta de `prueba.txt` y aceptar el intervalo sugerido. Las frases
llegan una por una; al terminar el archivo, la simulación vuelve al menú.

Esta prueba comprueba que las frases pueden compararse con el catálogo, pero no prueba
el micrófono, Whisper ni Termux:API. Para probar esas partes se debe elegir la fuente
correspondiente.

## 8. Tamaño de letra y paginación

En `karaoke.py`, al inicio del archivo:

- `CARACTERES_POR_LINEA = 80` controla el ancho de ajuste del texto en pantalla. Si
  quieres líneas más cortas, baja este valor; si la pantalla es más ancha, súbelo.

En `canciones_db.py`, al inicio del archivo:

- `MAX_CARACTERES_LINEA = 200` es un umbral de **aviso**, no un límite: las líneas
  largas se guardan y se ajustan visualmente.
- `LINEAS_PROMEDIO = 10` es una referencia informativa.

En `karaoke.py`, también al inicio:

- `TAMANO_PAGINA = 10` controla las páginas del catálogo y de las letras.

En `automatico.py`, al inicio, están los ajustes de Whisper, los segmentos de audio,
las coincidencias y el avance estimado. Cambiarlos puede afectar cómo encuentra y sigue
las canciones; prueba los cambios antes de usarlo en una presentación.

## 9. Problemas frecuentes

- **No encuentra la canción**: revisa que esté en `CANCIONES.db`. En modo manual,
  prueba otras palabras o usa `(w)` para ver el nombre.
- **Whisper no carga**: en Windows, instala `requirements.txt` con el mismo Python que
  usas para abrir `karaoke.py`. Revisa el error y la conexión a Internet si es la
  primera vez que se descarga el modelo.
- **Windows no detecta el micrófono**: revisa cuál es el micrófono predeterminado y
  permite que Windows y Python lo usen.
- **Android no pasa la voz a texto**: revisa Termux:API, el comando
  `termux-speech-to-text`, el permiso del micrófono y el servicio de voz del teléfono.
- **La transcripción sale mal**: baja el ruido, acerca el teléfono o micrófono al
  cantante y baja la música que llega al micrófono. Si estás cantando con música de
  fondo, ten en cuenta que el teléfono puede reconocer peor que el modo PC.
- **El modo manual funciona, pero el automático no**: revisar primero la fuente elegida.
  La simulación desde archivo permite comprobar el motor sin micrófono; en PC hacen falta
  las dependencias de `requirements.txt`, y en Android deben funcionar Termux:API y el
  servicio de reconocimiento de voz.
- **El catálogo aparece vacío**: confirmar que se importó el archivo correcto y que se
  ejecuta el programa desde la misma carpeta que contiene `CANCIONES.db`.
- **Una canción aparece en la lista, pero no se puede cargar**: revisar que el nombre de
  `PROGRAMA.txt` coincida con el de la base. También se puede elegir la canción desde el
  catálogo o volver a escribir el nombre en la lista.
- **Whisper tarda al iniciar**: la primera ejecución descarga el modelo configurado.
  Mantener la conexión a Internet y esperar a que termine; las ejecuciones posteriores
  usan el modelo que ya está descargado.

## 10. Copias de seguridad y traslado

`CANCIONES.db` contiene el catálogo y las letras guardadas. Para hacer una copia, cerrar
el programa y copiar ese archivo a otra ubicación. Para restaurarlo, cerrar el programa
y colocar la copia junto a `karaoke.py`. Si se reemplaza una base existente, guardar
primero una copia de la versión actual.

Para trasladar el programa a otro equipo, copiar juntos `karaoke.py`, `canciones_db.py`
y `automatico.py`. También se pueden copiar `CANCIONES.db`, `PROGRAMA.txt` y los
archivos de texto que se quieran conservar. En Windows, instalar las dependencias en el
equipo nuevo para usar el micrófono con Whisper. En Android, preparar Termux y
Termux:API en el teléfono; no es necesario instalar las dependencias de PC.