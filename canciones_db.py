#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acceso a SQLite y operaciones de catálogo para Karaoke inteligente."""

# os permite construir rutas y comprobar si existen archivos.
import os
# re sirve para limpiar texto y separar bloques del archivo de canciones.
import re
# sqlite3 es el motor de base de datos que viene con Python.
import sqlite3
# unicodedata permite quitar acentos sin alterar otras letras.
import unicodedata
# SequenceMatcher compara textos parecidos para la búsqueda aproximada.
from difflib import SequenceMatcher


# ===================== CONFIGURACIÓN DE DATOS =====================
# Nombre del archivo de base de datos que se guarda junto a este módulo.
DB_ARCHIVO = "CANCIONES.db"
# Cantidad orientativa de líneas que se espera tener en una canción.
LINEAS_PROMEDIO = 10
# Longitud a partir de la que se avisa sobre una línea, sin impedir guardarla.
MAX_CARACTERES_LINEA = 200
# ================================================================

# Carpeta absoluta donde está este archivo Python.
BASE = os.path.dirname(os.path.abspath(__file__))
# Ruta completa al archivo SQLite, independiente de la carpeta actual de la consola.
DB_RUTA = os.path.join(BASE, DB_ARCHIVO)


def norm(texto):
    """Normaliza texto para buscarlo sin distinguir mayúsculas, acentos o signos."""
    # Separa las letras de sus marcas de acento y pasa todo a minúsculas.
    t = unicodedata.normalize("NFD", texto.lower())
    # Elimina únicamente los caracteres Unicode que son marcas diacríticas.
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    # Cambia puntuación y símbolos por espacios para separar las palabras.
    t = re.sub(r"[^a-z0-9ñ\s]", " ", t)
    # Reduce espacios repetidos y quita los espacios del principio y del final.
    return re.sub(r"\s+", " ", t).strip()


def conectar():
    """Abre la base, crea las tablas que falten y devuelve la conexión."""
    # Guarda si la base ya existía para mostrar un mensaje apropiado al final.
    existia = os.path.exists(DB_RUTA)
    # Abre o crea el archivo SQLite usando la ruta calculada al cargar el módulo.
    con = sqlite3.connect(DB_RUTA)
    # Hace que SQLite aplique las relaciones y borrados en cascada declarados.
    con.execute("PRAGMA foreign_keys = ON")
    # Crea las tablas e índice si aún no existen; no reemplaza datos existentes.
    con.executescript("""
        CREATE TABLE IF NOT EXISTS NOMBRES (
            codigo INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_cancion TEXT NOT NULL,
            nombre_norm TEXT
        );
        CREATE TABLE IF NOT EXISTS LETRAS (
            codigo INTEGER NOT NULL,
            numero_linea INTEGER NOT NULL,
            linea TEXT NOT NULL,
            linea_norm TEXT,
            PRIMARY KEY (codigo, numero_linea),
            FOREIGN KEY (codigo) REFERENCES NOMBRES(codigo) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS TEMP_NOMBRES (
            id_temp INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_cancion TEXT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS TEMP_LETRAS (
            id_temp INTEGER NOT NULL,
            numero_linea INTEGER NOT NULL,
            linea TEXT NOT NULL,
            PRIMARY KEY (id_temp, numero_linea),
            FOREIGN KEY (id_temp) REFERENCES TEMP_NOMBRES(id_temp) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_letras_norm ON LETRAS(linea_norm);
    """)
    # Confirma los cambios del esquema antes de entregar la conexión.
    con.commit()
    # Informa si se abrió una base existente o se creó una nueva.
    print("Base de datos", "encontrada y lista." if existia else "no existía: creada con todas sus tablas.")
    # Devuelve la conexión para que la use la interfaz del programa.
    return con


def agregar_cancion(con, nombre, lineas):
    """Guarda el nombre y las líneas; devuelve el código, o None si faltan datos."""
    # Quita espacios exteriores y descarta líneas vacías.
    lineas = [l.strip() for l in lineas if l.strip()]
    # No crea una canción sin nombre ni texto que guardar.
    if not nombre.strip() or not lineas:
        return None
    # Inserta el nombre con una versión normalizada usada para búsquedas.
    cur = con.execute("INSERT INTO NOMBRES(nombre_cancion, nombre_norm) VALUES (?,?)",
                      (nombre.strip(), norm(nombre)))
    # Recupera el identificador que SQLite acaba de asignar.
    codigo = cur.lastrowid
    # Inserta las líneas numeradas y su forma normalizada en una sola operación.
    con.executemany("INSERT INTO LETRAS VALUES (?,?,?,?)",
                    [(codigo, i, l, norm(l)) for i, l in enumerate(lineas, 1)])
    # Confirma juntos el nombre y todos sus versos.
    con.commit()
    # Advierte si la canción es mucho más larga que el promedio configurado.
    if len(lineas) > LINEAS_PROMEDIO * 3:
        print(f"  Aviso: '{nombre}' tiene {len(lineas)} líneas (promedio configurado: {LINEAS_PROMEDIO}).")
    # Reúne las líneas largas para dar un único aviso informativo.
    largas = [l for l in lineas if len(l) > MAX_CARACTERES_LINEA]
    # Informa cuántas líneas superan el umbral; no las elimina ni las trunca.
    if largas:
        print(f"  Aviso: {len(largas)} línea(s) superan {MAX_CARACTERES_LINEA} caracteres.")
    # Devuelve el código asignado para mostrarlo o referir la canción después.
    return codigo


def obtener_letra(con, codigo):
    """Devuelve las líneas de una canción en el orden guardado."""
    # Consulta las líneas por código y las ordena por su número de línea.
    return [r[0] for r in con.execute(
        "SELECT linea FROM LETRAS WHERE codigo=? ORDER BY numero_linea", (codigo,))]


def obtener_nombre(con, codigo):
    """Devuelve el nombre de una canción; retorna None si el código no existe."""
    # Busca un solo nombre asociado al código indicado.
    r = con.execute("SELECT nombre_cancion FROM NOMBRES WHERE codigo=?", (codigo,)).fetchone()
    # Una consulta sin coincidencias da None; si existe, el nombre está en la primera columna.
    return r[0] if r else None


def elegir(filas, titulo):
    """Muestra opciones numeradas y devuelve el código elegido o None."""
    # Imprime el encabezado del selector.
    print(titulo + ":")
    # Enumera las canciones empezando por 1 para que sea fácil elegirlas.
    for i, (cod, nom) in enumerate(filas, 1):
        print(f"  {i}) [{cod}] {nom}")
    # Pide la posición; Enter permite cancelar.
    op = input("Número (Enter = cancelar): ").strip()
    # Acepta solo un número que corresponda a una opción mostrada.
    if op.isdigit() and 1 <= int(op) <= len(filas):
        # Devuelve el código guardado en la primera columna de esa fila.
        return filas[int(op) - 1][0]
    # Cualquier entrada vacía o inválida cancela la selección.
    return None


def resolver_cancion(con, texto):
    """Busca por código o nombre parcial y devuelve el código, o None."""
    # Quita espacios exteriores antes de interpretar el dato.
    texto = texto.strip()
    # Si parece un código existente, lo devuelve sin hacer una búsqueda de nombre.
    if texto.isdigit() and obtener_nombre(con, int(texto)):
        return int(texto)
    # Busca nombres que contengan el texto normalizado; los signos no afectan.
    filas = con.execute("SELECT codigo, nombre_cancion FROM NOMBRES WHERE nombre_norm LIKE ?",
                        ("%" + norm(texto) + "%",)).fetchall()
    # Si no hay resultados, informa al llamador mediante None.
    if not filas:
        return None
    # Si la búsqueda es única, no hace falta mostrar el selector.
    if len(filas) == 1:
        return filas[0][0]
    # Si hay varias, deja que la persona elija cuál quería.
    return elegir(filas, "Varias coincidencias")


def buscar_por_palabras(con, texto, maximo=5):
    """Compara palabras con cada línea y devuelve las mejores coincidencias."""
    # Normaliza la consulta y la divide en palabras individuales.
    palabras = norm(texto).split()
    # Una consulta vacía no puede producir coincidencias.
    if not palabras:
        return []
    # Recupera letras y nombres para puntuar cada línea en Python.
    filas = con.execute("""SELECT l.codigo, n.nombre_cancion, l.numero_linea, l.linea, l.linea_norm
                           FROM LETRAS l JOIN NOMBRES n ON n.codigo = l.codigo""").fetchall()
    # Conserva la consulta en forma de frase para buscar coincidencias exactas.
    consulta = " ".join(palabras)
    # Guarda la mejor línea encontrada para cada canción.
    mejores = {}
    # Revisa cada línea almacenada junto al nombre de su canción.
    for cod, nom, nro, lin, lnorm in filas:
        # Cuenta cuántas palabras buscadas aparecen literalmente en la línea normalizada.
        aciertos = sum(1 for p in palabras if p in lnorm)
        # La primera parte del puntaje es la proporción de palabras encontradas.
        score = aciertos / len(palabras)
        # Una frase completa incluida en la línea recibe un aumento de puntaje.
        if consulta in lnorm:
            score += 1.0
        # Añade un aporte de similitud aproximada para tolerar errores pequeños.
        score += 0.3 * SequenceMatcher(None, consulta, lnorm[:len(consulta) + 15]).ratio()
        # Solo conserva esta línea si supera la mejor línea previa de su canción.
        if score > mejores.get(cod, (0,))[0]:
            mejores[cod] = (score, cod, nom, nro, lin)
    # Ordena las canciones por puntaje descendente.
    res = sorted(mejores.values(), reverse=True)
    # Filtra coincidencias débiles y limita cuántos resultados se devuelven.
    return [r for r in res if r[0] >= 0.8][:maximo]


def cargar_desde_texto(con):
    """Importa bloques separados por líneas vacías; la primera línea es el nombre."""
    # Pide la ruta y quita comillas que suelen venir de copiarla desde el explorador.
    ruta = input("Ruta del archivo de texto (ej. canciones.txt): ").strip().strip('"')
    # Evita intentar abrir una ruta que no existe.
    if not os.path.exists(ruta):
        print("No se encontró el archivo.")
        return
    # Lee UTF-8 con o sin marca BOM y separa canciones en bloques vacíos.
    with open(ruta, encoding="utf-8-sig") as f:
        bloques = re.split(r"\n\s*\n", f.read().replace("\r\n", "\n").strip())
    # Cuenta cuántas canciones nuevas se importan.
    n = 0
    # Procesa por separado cada bloque que podría ser una canción.
    for b in bloques:
        # Quita líneas vacías de los bloques antes de leer nombre y letra.
        ls = [l for l in b.split("\n") if l.strip()]
        # Un bloque sin nombre y al menos una línea no representa una canción válida.
        if len(ls) < 2:
            continue
        # Permite que un nombre empiece con # y limpia espacios exteriores.
        nombre = ls[0].lstrip("#").strip()
        # Omite nombres ya guardados para no duplicar canciones al importar.
        if con.execute("SELECT 1 FROM NOMBRES WHERE nombre_norm=?", (norm(nombre),)).fetchone():
            print(f"  Ya existe, se omite: {nombre}")
            continue
        # Guarda el nombre y todas las líneas posteriores del bloque.
        cod = agregar_cancion(con, nombre, ls[1:])
        # Muestra el código y el número de líneas que se añadieron.
        print(f"  Agregada [{cod}] {nombre} ({len(ls) - 1} líneas)")
        # Aumenta el total de canciones importadas correctamente.
        n += 1
    # Resume el resultado de la importación.
    print(f"Total de canciones nuevas: {n}")


def alimentar_manual(con):
    """Pide nombre y líneas por consola, y guarda la canción al terminar."""
    # Solicita el nombre y elimina espacios exteriores.
    nombre = input("Nombre de la canción: ").strip()
    # Una entrada vacía cancela sin crear registros.
    if not nombre:
        print("Cancelado.")
        return
    # Aquí se acumulan las líneas hasta que se introduzca una línea vacía.
    lineas = []
    # Explica cómo terminar la entrada de la letra.
    print("Escriba la letra línea por línea. Línea vacía = terminar.")
    # Lee líneas hasta encontrar la entrada vacía que indica el final.
    while True:
        l = input(f"Línea {len(lineas) + 1}: ").strip()
        if not l:
            break
        lineas.append(l)
    # Reutiliza la función de guardado y validación común.
    cod = agregar_cancion(con, nombre, lineas)
    # Informa el código asignado o que los datos no alcanzaban para guardar.
    print(f"Guardada con código {cod}." if cod else "No se guardó (faltan datos).")


def guardar_letra(con, cod, lineas):
    """Reemplaza todas las líneas de una canción y recalcula sus textos normalizados."""
    # Descarta líneas vacías para que la numeración quede continua.
    lineas = [l for l in lineas if l.strip()]
    # Borra la versión anterior de la letra para reconstruirla desde el principio.
    con.execute("DELETE FROM LETRAS WHERE codigo=?", (cod,))
    # Inserta cada línea con número consecutivo y versión normalizada.
    con.executemany("INSERT INTO LETRAS VALUES (?,?,?,?)",
                    [(cod, i, l, norm(l)) for i, l in enumerate(lineas, 1)])
    # Confirma el reemplazo completo de la letra.
    con.commit()
