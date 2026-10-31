# Karaoke inteligente

Aplicación de karaoke en Python que guarda letras en una base de datos local y ayuda
a seguirlas mientras cantas. Puedes buscar una canción escribiendo palabras de la
letra o activar el seguimiento automático por voz. El programa no reproduce música ni
descarga canciones o letras: tú agregas y administras el contenido.

Funciona desde una terminal en Windows, Linux y macOS. También puede ejecutarse en
Android mediante Termux; no es una aplicación con pantallas propias.

## Funciones principales

- **Modo manual:** encuentra canciones por palabras, muestra la letra y permite
  avanzar, retroceder o elegir otra línea.
- **Modo automático:** compara lo que oye con las letras guardadas y sigue el avance
  de la canción. En PC usa el micrófono y Whisper; en Android usa Termux:API.
- **Catálogo editable:** importa letras desde un archivo de texto o escríbelas en el
  programa. También puedes buscar, corregir y borrar canciones.
- **Lista tentativa:** `PROGRAMA.txt` permite preparar un orden de canciones para la
  sesión.
- **Pruebas sin micrófono:** el modo automático puede procesar frases de un archivo,
  por ejemplo `prueba.txt`.
- **Almacenamiento local:** las canciones se guardan en `CANCIONES.db`, una base
  SQLite que el programa crea al iniciarse si aún no existe.

## Requisitos

- Python 3.10 o posterior.
- Para el modo manual, no hacen falta paquetes externos.
- Para el modo automático con micrófono en PC, instala los paquetes de
  `requirements.txt`. La primera ejecución descarga el modelo de Whisper configurado
  en `automatico.py`, por lo que requiere conexión a Internet y espacio libre.
- En Android, instala Termux y Termux:API. No instales `requirements.txt` para usar el
  reconocimiento de voz en el teléfono.

## Instalación y ejecución

Clona o descarga este repositorio y abre una terminal en la carpeta del proyecto.
Para iniciar el programa:

```sh
python karaoke.py
```

En Windows también puedes usar `py karaoke.py` si el comando `python` no está
disponible.

Para habilitar el modo automático con micrófono en PC, instala sus dependencias:

```sh
python -m pip install -r requirements.txt
```

Permite el acceso al micrófono para Python en la configuración del sistema. En el
menú principal, selecciona **(a)** y luego **(m)** para usar el micrófono del PC.
Selecciona **(t)** para probar con un archivo que tenga una frase por línea.

### Android con Termux

Instala Termux y Termux:API desde el mismo proveedor, instala `python` y `termux-api`
en Termux y concede el permiso del micrófono. Copia a una misma carpeta del teléfono
`karaoke.py`, `automatico.py` y `canciones_db.py`, además de `CANCIONES.db` si quieres
conservar un catálogo existente. Ejecuta `python karaoke.py` y selecciona **(a)** y
luego **(a)** para usar el reconocedor de voz del teléfono.

La precisión del reconocimiento depende del micrófono, el ruido, la música y el
servicio de voz disponible; puede ser menor al cantar que al hablar.

## Archivos del proyecto

| Archivo | Propósito |
|---|---|
| `karaoke.py` | Interfaz de consola, menús y modo manual. |
| `automatico.py` | Seguimiento automático y fuentes de audio de PC, Android y simulación. |
| `canciones_db.py` | Catálogo, búsquedas y almacenamiento SQLite. |
| `requirements.txt` | Dependencias del modo automático con micrófono en PC. |
| `canciones_ejemplo.txt` | Ejemplo de letras para importar. |
| `PROGRAMA.txt` | Lista tentativa de canciones, una por línea. |
| `prueba.txt` | Frases de ejemplo para probar el modo automático sin micrófono. |
| `CANCIONES.db` | Base de datos local, creada al iniciar el programa. |

Mantén juntos los tres módulos Python principales. La base de datos se crea junto a
`karaoke.py`, independientemente de la carpeta desde la que abras la terminal.

## Documentación

- [Guía de uso](docs/Manual_Usuario.md): instalación paso a paso, menús, importación de
  letras y solución de problemas.
- [Guía técnica](docs/Manual_Tecnico.md): módulos, motor de seguimiento, fuentes de
  audio y esquema de la base de datos.
