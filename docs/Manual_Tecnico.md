# Guía técnica — Karaoke inteligente

## 1. Alcance y supuestos

El programa funciona en una consola de Python y guarda los datos en una base SQLite
local. En Windows, el modo automático captura audio y lo pasa a `faster-whisper`. En
Android, Python corre en Termux y pide el texto al reconocedor del teléfono mediante
Termux:API. No es una app Android propia: en el teléfono no instala Whisper ni captura
el audio directamente.

**Diferencia entre PC y teléfono:** el modo Android puede reconocer peor el canto,
especialmente con música o ruido, porque depende del servicio de voz instalado en el
teléfono. En PC se usa Whisper, que puede dar mejores resultados en esas condiciones,
pero tampoco garantiza una transcripción correcta. El resultado depende del equipo,
el micrófono y el ambiente.

Supuestos adoptados:

1. El usuario agrega sus canciones; el programa no descarga letras ni música.
2. El micrófono debe oír la voz por encima de la música y del público. La limpieza de
   audio puede reducir ruido constante, pero no separa por completo la voz de la música.
3. El reconocimiento puede equivocarse. Prueba el micrófono y revisa el texto antes de
   guardar una canción nueva.
4. SQLite guarda las líneas completas. Los promedios de 10 líneas y 80 caracteres son
   solo una referencia; no se corta el texto por superar esos valores.
5. En Android, el resultado depende del servicio de voz y de la conexión que este use.

## 2. Módulos y responsabilidades

### `karaoke.py`

Archivo que inicia el programa y muestra los menús en la consola. Usa la biblioteca
estándar de Python:

- Configuración de presentación, ancho visual y paginación.
- Menús principales, modo manual, edición y gestión de `PROGRAMA.txt`.
- Importa las funciones de datos y búsqueda desde `canciones_db.py`.
- Carga diferida de `automatico.py`, de forma que el modo manual no requiera
  dependencias de audio.

### `canciones_db.py`

Módulo que maneja los datos. También usa solo la biblioteca estándar de Python:

- Configuración de la ruta de `CANCIONES.db` y normalización de texto.
- Creación de tablas e índice SQLite.
- Inserción, consulta, edición y búsqueda aproximada de canciones y letras.
- Alimentación manual o desde archivo de texto.
- Funciones de datos reutilizadas por los modos manual y automático. `karaoke.py`
  importa esas funciones y las proporciona al motor automático.

### `automatico.py`

El modo automático se divide en tres partes: cómo llega el texto, cómo se sigue la
canción y cómo se muestra en pantalla:

- `FuenteMicrofono`: toma audio mono a 16 kHz, lo divide usando el volumen y los
  silencios, lo limpia y lo pasa a `faster-whisper`.
- `FuenteTermux`: ejecuta `termux-speech-to-text` en Android y entrega al motor cada
  frase que reconoce.
- `FuenteSimulada`: lee frases de un archivo para probar el motor sin micrófono. Al
  elegir `(t)`, una ruta vacía usa `prueba.txt` junto a `automatico.py`; las rutas
  relativas se buscan primero desde la carpeta actual y después junto al programa.
  Cada línea no vacía del archivo se entrega como una frase.
- `Motor`: compara el texto con las líneas guardadas, busca la canción, calcula un
  tiempo aproximado por línea y guarda borradores de canciones nuevas.
- `dibujar`, `menu_control` y `guardar_nueva`: muestran la pantalla, los controles y
  las opciones para revisar una canción nueva.

### Archivos de datos y dependencias

- `CANCIONES.db`: base SQLite; se crea junto a `karaoke.py` si no existe.
- `canciones_db.py`: módulo requerido por `karaoke.py`; debe permanecer en la misma
  carpeta que los otros módulos Python.
- `PROGRAMA.txt`: texto UTF-8 con un nombre de canción por línea.
- `canciones_ejemplo.txt`: datos de ejemplo para importar.
- `requirements.txt`: dependencias de Whisper/captura para Windows. La fuente Android
  usa Termux:API y no necesita instalar este archivo de requisitos.

## 3. Esquema SQLite

La conexión activa las claves foráneas. `conectar()` crea cualquier tabla que falte:

| Tabla | Campos | Uso |
|---|---|---|
| `NOMBRES` | `codigo INTEGER PRIMARY KEY AUTOINCREMENT`, `nombre_cancion TEXT NOT NULL`, `nombre_norm TEXT` | Catálogo y código generado automáticamente. |
| `LETRAS` | `codigo`, `numero_linea`, `linea`, `linea_norm`; clave primaria compuesta `(codigo, numero_linea)` | Líneas ordenadas y su forma normalizada; `codigo` referencia `NOMBRES` con borrado en cascada. |
| `TEMP_NOMBRES` | `id_temp INTEGER PRIMARY KEY AUTOINCREMENT`, `nombre_cancion`, `fecha` | Borradores detectados automáticamente antes de revisión. |
| `TEMP_LETRAS` | `id_temp`, `numero_linea`, `linea`; clave primaria `(id_temp, numero_linea)` | Texto transcrito temporal relacionado con el borrador. |

`idx_letras_norm` es un índice auxiliar sobre `LETRAS(linea_norm)`. Las tablas
temporales guardan los borradores. Al revisar uno, el motor permite editarlo y, al
confirmarlo, guarda la canción y sus líneas en las tablas permanentes.

**Compatibilidad:** `CREATE TABLE IF NOT EXISTS` crea tablas que faltan, pero no cambia
una tabla existente si sus columnas o tipos no coinciden. Antes de cambiar una base
antigua, haz una copia de `CANCIONES.db`.

## 4. Identificación y sincronización automática

1. La fuente entrega al motor las frases que reconoció.
2. El motor normaliza el texto y descarta resultados muy cortos o errores conocidos del
   reconocedor.
3. Busca palabras en las líneas y en pares de líneas guardadas. Permite diferencias
   pequeñas para compensar errores de reconocimiento. Si existe `PROGRAMA.txt` (leído
   con `cargar_programa()` de `karaoke.py`), el puntaje de la siguiente canción pendiente
   del programa se incrementa en `PROG_BONUS_SIG` y el de las demás pendientes en
   `PROG_BONUS_OTRAS`, con tope de 1.0. No se descarta ninguna canción, por lo que el
   orden del programa no es estricto.
4. Cuando encuentra la canción, muestra la línea que sigue a la frase reconocida. Las
   frases siguientes ayudan a encontrar el lugar actual dentro de un grupo pequeño de
   líneas cercanas.
5. Guarda tiempos aproximados por línea. `tick()` puede avanzar según ese tiempo, pero
   como máximo dos líneas seguidas sin confirmación del audio. Una coincidencia nueva
   ajusta la posición.
6. Si deja de reconocer la canción, intenta encontrarla otra vez y vuelve a buscar
   después de varios fallos.
7. Si varias frases no coinciden con la base, guarda líneas como borrador en
   `TEMP_NOMBRES`/`TEMP_LETRAS`. Puedes corregir el texto, ponerle nombre y guardarlo,
   o descartarlo.

Lista de canciones: al empezar una canción que está en el programa, la posición pasa a
la entrada siguiente (`_marcar_programa`), como en el modo manual. Repetir una canción
ya cantada o cantar una que no está en la lista no cambia la posición. La tecla
`p` del menú de control (`cargar_programada`) muestra la siguiente canción del programa
desde su primera línea sin esperar a oírla, omitiendo las entradas que no están en la
base de datos. `recargar()` vuelve a leer `PROGRAMA.txt` para asociar códigos a canciones
recién guardadas.

El tiempo es aproximado: depende de cuánto duran las frases, las pausas, la velocidad
al cantar, la mezcla de música y la precisión del reconocedor. El programa no compara
sonidos ni sigue la melodía; los controles manuales permiten corregir la línea.

### Estados del motor

El motor mantiene un estado para decidir cómo interpretar la frase siguiente:

| Estado | Qué significa | Qué puede ocurrir |
|---|---|---|
| `BUSCANDO` | No hay una canción identificada en seguimiento. | Se busca una coincidencia en todo el catálogo. |
| `SIGUIENDO` | Hay una canción activa y una línea actual. | Se busca cerca de esa línea y se corrige la posición con el texto recibido. |
| `TERMINO` | La frase reconocida coincide con la última línea. | Se mantiene la última línea mientras se espera otra identificación o una acción manual. |
| `NUEVA` | Varias frases seguidas no coincidieron con el catálogo. | Se crea y actualiza un borrador que se puede revisar. |
| `PAUSA` | La fuente se mantiene, pero el motor ignora las frases recibidas. | Al reanudar, vuelve al estado anterior a la pausa. |

En `SIGUIENDO`, primero se revisa una ventana pequeña alrededor de la línea actual.
Esto evita buscar cada frase en todas las canciones cuando ya se conoce la canción.
Si no hay coincidencia cercana, el motor intenta una búsqueda global para recuperarse o
detectar un cambio. Tras varios fallos vuelve a `BUSCANDO`.

### Puntaje de coincidencia

El texto reconocido y las letras se normalizan antes de compararse: se pasan a
minúsculas, se quitan acentos y puntuación, y se separan en palabras. `similitud()`
combina la cobertura de palabras en ambos sentidos; para palabras largas también acepta
parecidos aproximados. La búsqueda prueba cada línea y, cuando existe, el par formado
por esa línea y la siguiente.

Los umbrales de configuración representan decisiones distintas:

- `UMBRAL_LINEA` decide si una frase se parece lo suficiente a una línea cercana para
  confirmar el seguimiento.
- `UMBRAL_IDENT` decide si el mejor resultado de todo el catálogo basta para empezar a
  seguir una canción.
- `UMBRAL_CAMBIO` exige una coincidencia más fuerte para cambiar de canción durante el
  seguimiento.

Reducir estos valores puede ayudar cuando el reconocedor comete errores, pero también
puede aumentar las coincidencias equivocadas. Aumentarlos reduce algunos falsos
positivos, pero puede hacer que el motor no encuentre una letra.

### Fuentes de texto y coordinación

Las tres fuentes presentan la misma interfaz: `iniciar()`, `siguiente_texto()`,
`pausar()` y `detener()`. De esta forma, el motor no necesita conocer el origen de la
frase.

1. La fuente de PC recibe bloques de audio y los pone en una cola. Un hilo detecta
   fragmentos de voz y otro llama a Whisper.
2. La fuente Android ejecuta `termux-speech-to-text` en un hilo y coloca cada frase que
   devuelve en su cola.
3. La fuente simulada lee líneas de un archivo y las envía con una pausa configurable.
4. El bucle principal extrae las frases sin bloquear, llama a `Motor.procesar()` y
   actualiza la pantalla solo cuando hay cambios.

Las colas separan la captura y la transcripción del dibujo de pantalla. Por eso el
reconocimiento puede tardar sin detener por completo los controles de la interfaz. Al
salir, un bloque `finally` llama a `detener()` para cerrar la fuente activa.

## 5. Captura y limpieza de audio

En Windows, `FuenteMicrofono` usa `sounddevice` y bloques de 0.25 segundos a 16 kHz.
Durante aproximadamente un segundo mide el ruido del lugar. Luego usa RMS para notar
cuándo hay voz y cierra cada fragmento después de un silencio o al llegar al tiempo
límite.
`_limpiar()` elimina componente DC, intenta un filtro pasa-altos de 80 Hz y reducción
de ruido con `noisereduce`, y normaliza el pico antes de transcribir con Whisper en
español.

En Android, Termux:API pide una frase al reconocedor de voz del teléfono. Ese servicio
se encarga de limpiar y reconocer el audio; el programa recibe el texto, no captura ni
filtra el audio directamente.

Este método no separa por completo la voz del resto de los sonidos. Para mejorar el
resultado, acerca el micrófono al cantante, baja la música que capta y evita que el
audio se distorsione o que el público tape la voz. Haz pruebas en el lugar donde se va
a usar.

### Qué datos se guardan y cuándo

- Las canciones importadas o escritas se guardan en `NOMBRES` y `LETRAS`. El número de
  línea forma parte de la clave, por lo que las líneas de cada canción se mantienen
  ordenadas.
- La forma normalizada de los nombres y las letras se guarda para simplificar las
  búsquedas. El texto original permanece disponible para mostrarlo y editarlo.
- Las frases de una canción nueva se guardan en `TEMP_NOMBRES` y `TEMP_LETRAS`. La
  revisión puede modificar ese borrador; solo al elegir guardarlo se crea una canción
  permanente.
- Al confirmar un borrador, se guarda la canción definitiva y se eliminan sus datos
  temporales. Al descartarlo, se eliminan las filas temporales sin añadirla al catálogo.

SQLite confirma los cambios al importar, editar o eliminar letras. Cerrar el programa
normalmente permite liberar la conexión de forma ordenada. Para mover o respaldar la
base, conviene cerrar el programa y copiar `CANCIONES.db`.

## 6. Configuración de capacidad

En la sección de configuración de `karaoke.py`:

- `CARACTERES_POR_LINEA` cambia el ancho visual de ajuste. No elimina caracteres del
  texto almacenado.

En la sección de configuración de `canciones_db.py`:

- `MAX_CARACTERES_LINEA` es el umbral que genera un aviso al alimentar la base; no
  impide guardar líneas mayores.
- `LINEAS_PROMEDIO` documenta el promedio esperado y controla un aviso para canciones
  excepcionalmente largas.

En la sección de configuración de `karaoke.py`:

- `TAMANO_PAGINA` define filas por página en las consultas de catálogo y letra.

En la configuración inicial de `automatico.py`:

- `WHISPER_MODELO`, `WHISPER_COMPUTE` e `IDIOMA` determinan modelo, cómputo e idioma
  en Windows.
- `BLOQUE_SEG`, `SILENCIO_CORTE`, `SEG_MAX`, `SEG_MIN`, `UMBRAL_FACTOR` y
  `UMBRAL_MIN` controlan captura y segmentación.
- `UMBRAL_LINEA`, `UMBRAL_IDENT`, `UMBRAL_CAMBIO`, `FALLOS_NUEVA` y `FALLOS_FIN`
  controlan coincidencia y cambios de estado.
- `FACTOR_AVANCE` y `AVANCE_AUTO_MAX` limitan el avance basado en velocidad estimada.
- `PROG_BONUS_SIG` y `PROG_BONUS_OTRAS` fijan cuánta ventaja da el `PROGRAMA.txt` a la
  siguiente canción y a las demás pendientes al identificar (0 en ambos desactiva el
  efecto).

Cambia un parámetro por vez y prueba con la misma canción y en el mismo lugar. Con
umbrales bajos puede haber más coincidencias incorrectas; con umbrales altos, puede que
no encuentre la canción.

### Comprobación por etapas

Cuando una instalación no funciona como se espera, conviene separar las partes:

1. **Datos:** iniciar el programa, importar `canciones_ejemplo.txt` y revisar el
   catálogo y una letra. Esto comprueba SQLite y el formato de importación.
2. **Búsqueda manual:** escribir palabras distintivas y confirmar que se abre la canción
   esperada. Si falla aquí, revisar la letra, los acentos no son obligatorios, pero sí
   deben estar las palabras correctas.
3. **Motor sin micrófono:** usar la fuente simulada con un archivo que tenga frases
   similares a líneas del catálogo. Así se puede probar la identificación y los
   controles sin depender de un dispositivo de audio.
4. **Fuente de audio:** probar por separado el micrófono de PC o el comando de Android.
   Si la fuente produce texto incorrecto, revisar el micrófono y el servicio de voz
   antes de cambiar los umbrales del motor.

Esta separación evita ajustar el motor para compensar un problema de permisos, una
dependencia que falta o una letra incompleta.

## 7. Instalación operativa

### Windows

1. Instala Python 3.10 o posterior.
2. En la carpeta del programa, ejecuta `python -m pip install -r requirements.txt`.
3. Abre el programa con `python .\karaoke.py`.
4. Para usar el modo automático, elige `(a)` y luego `(m)`. Permite el acceso al
   micrófono. Whisper descarga el modelo la primera vez, así que necesitarás conexión y
   espacio libre.

Modo manual, base SQLite y alimentación no requieren paquetes adicionales.

### Android

1. Instala Termux y Termux:API desde F-Droid, los dos del mismo origen.
2. En Termux, ejecuta `pkg update` y `pkg install python termux-api`.
3. Permite el uso del micrófono a Termux:API y configura el servicio y el idioma de voz
   en Android.
4. Copia `karaoke.py`, `canciones_db.py`, `automatico.py` y, si quieres, `CANCIONES.db`
   a una misma carpeta del teléfono. Desde esa carpeta, ejecuta `python karaoke.py`.
5. En el programa, elige `(a)` y luego `(a)` para usar el teléfono.

No instales en Android las dependencias de audio de `requirements.txt` para este modo.
Deja Termux abierto. El reconocedor puede necesitar conexión y su disponibilidad
depende del teléfono. La guía para pasar archivos y configurar permisos está en
`MANUAL_USUARIO.md`.


## 8. Controles del modo automático

Durante escucha, `Ctrl+C` abre el menú de control. `c` avanza; `i` mantiene la línea
actual; `r` repite; `g` ignora y `s` reanuda; `b` vuelve a buscar canción; `f` termina
el modo; `n` inicia la revisión de una canción nueva y `d` la descarta; `p` carga la
siguiente canción del programa. `i` mantiene la línea actual, igual que en el modo
manual.