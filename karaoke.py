#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Punto de entrada y menús del Karaoke inteligente."""

# os comprueba archivos y limpia la pantalla según el sistema operativo.
import os
# sys da acceso al intérprete y permite cerrar el programa con un código de salida.
import sys
# textwrap ajusta y recorta letras para que quepan en la terminal.
import textwrap
# Importa las funciones de datos que usa la interfaz para catálogo, búsquedas y letras.
from canciones_db import (
    agregar_cancion,
    alimentar_manual,
    buscar_por_palabras,
    cargar_desde_texto,
    conectar,
    guardar_letra,
    norm,
    obtener_letra,
    obtener_nombre,
    resolver_cancion,
)

# ===================== CONFIGURACIÓN =====================
# Archivo opcional con los nombres de las canciones en el orden previsto.
PROGRAMA_ARCHIVO = "PROGRAMA.txt"
# Ancho máximo aproximado para mostrar cada línea de letra en pantalla.
CARACTERES_POR_LINEA = 80        # caracteres promedio por línea; también es el ancho
                                 # al que se ajusta el texto en pantalla. Si las
                                 # letras tienen líneas más largas o cortas, cambie
                                 # este valor (la pantalla las parte automáticamente).
# Número de canciones o líneas que se muestran en cada página de resultados.
TAMANO_PAGINA = 10

# Los parámetros del modo automático (modelo Whisper, umbrales, tiempos) están
# al inicio de automatico.py.
# =======================================================================

# Obtiene la carpeta del archivo actual para no depender de desde dónde se ejecute Python.
BASE = os.path.dirname(os.path.abspath(__file__))
# Construye la ruta absoluta de la lista de canciones.
PROGRAMA_RUTA = os.path.join(BASE, PROGRAMA_ARCHIVO)


# ----------------------------- utilidades -----------------------------
def limpiar_pantalla():
    """Limpia la terminal usando el comando adecuado para Windows u otros sistemas."""
    # Windows entiende cls; macOS/Linux y Termux usan clear.
    os.system("cls" if os.name == "nt" else "clear")


def pausa(msg="\nEnter para continuar..."):
    """Espera a que la persona pulse Enter antes de seguir."""
    # input pausa el flujo y muestra el mensaje indicado.
    input(msg)


def preguntar_si_no(msg):
    """Devuelve True para respuestas afirmativas comunes en español."""
    # Quita espacios, convierte a minúsculas y acepta variantes de sí.
    return input(msg + " (s/n): ").strip().lower() in ("s", "si", "sí")


# ----------------------- alimentación de la BD -----------------------
def menu_alimentacion(con):
    """Permite agregar canciones desde un archivo o escribiendo su letra."""
    # Muestra las dos formas disponibles y normaliza la opción elegida.
    op = input("(t) desde archivo de texto  |  (e) escribir manualmente  >> ").strip().lower()
    # La opción t delega la lectura y el guardado al módulo de datos.
    if op == "t":
        cargar_desde_texto(con)
    # La opción e pide el nombre y la letra por consola.
    elif op == "e":
        alimentar_manual(con)
    # Avisa si se eligió una tecla que no existe en este menú.
    else:
        print("Opción no válida.")
    # Mantiene el resultado visible hasta que la persona continúe.
    pausa()


# ---------------------------- PROGRAMA ----------------------------
def cargar_programa(con):
    """Lee PROGRAMA.txt (un nombre por línea) y devuelve [(codigo, nombre)] en ese orden."""
    # Si el archivo no existe, el programa no tiene una lista predefinida.
    if not os.path.exists(PROGRAMA_RUTA):
        return []
    # Aquí se guarda cada entrada junto con su código, si se logra encontrar.
    lista = []
    # utf-8-sig acepta archivos UTF-8 normales y archivos con marca BOM.
    with open(PROGRAMA_RUTA, encoding="utf-8-sig") as f:
        # Lee los nombres en el mismo orden en que aparecen en el archivo.
        for ln in f:
            # Quita saltos de línea y espacios de cada entrada.
            ln = ln.strip()
            # Ignora líneas vacías y comentarios que empiezan con #.
            if not ln or ln.startswith("#"):
                continue
            # Empieza sin código; se llenará si se encuentra la canción en la base.
            cod = None
            # Primero intenta encontrar una coincidencia exacta del nombre normalizado.
            fila = con.execute("SELECT codigo FROM NOMBRES WHERE nombre_norm=?", (norm(ln),)).fetchone()
            # Guarda el código exacto cuando la consulta encontró una fila.
            if fila:
                cod = fila[0]
            else:
                # Si no fue exacto, busca un nombre que contenga el texto escrito.
                f2 = con.execute("SELECT codigo FROM NOMBRES WHERE nombre_norm LIKE ?",
                                 ("%" + norm(ln) + "%",)).fetchone()
                # Usa el primer código parcial encontrado, o None si no hay coincidencia.
                cod = f2[0] if f2 else None
            # Conserva también el nombre original para mostrarlo en la lista.
            lista.append((cod, ln))
    # Devuelve las entradas manteniendo el orden del archivo.
    return lista


def menu_programa(con):
    """Muestra, crea o importa el archivo de canciones planeadas."""
    # Informa dónde se guarda la lista para que sea fácil encontrarla.
    print(f"El programa se guarda en: {PROGRAMA_RUTA}")
    # Muestra las acciones del menú.
    print("(v) ver actual  |  (e) escribir nuevo por pantalla  |  (t) importar desde otro archivo")
    # Lee la opción elegida.
    op = input(">> ").strip().lower()
    # Ver la lista actual no modifica el archivo.
    if op == "v":
        # Lee las entradas y sus códigos existentes.
        prog = cargar_programa(con)
        # Informa si la lista no contiene canciones.
        if not prog:
            print("No hay programa cargado.")
        # Enumera la lista y marca las canciones que no están en la base.
        for i, (cod, nom) in enumerate(prog, 1):
            print(f"  {i}. {nom}  " + (f"[código {cod}]" if cod else "[NO ESTÁ EN LA BD]"))
    # Las opciones e y t reemplazan la lista con entradas nuevas.
    elif op in ("e", "t"):
        # Acumula temporalmente los nombres antes de escribir el archivo.
        nombres = []
        # La opción t lee nombres desde otro archivo de texto.
        if op == "t":
            # Pide la ruta y quita las comillas que quizá rodeen la ruta copiada.
            ruta = input("Ruta del archivo: ").strip().strip('"')
            # Si existe, lee cada línea no vacía como nombre de canción.
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8-sig") as f:
                    nombres = [l.strip() for l in f if l.strip()]
            # Avisa cuando la ruta indicada no existe.
            else:
                print("No se encontró el archivo.")
        else:
            # La opción e solicita nombres hasta que se envíe una línea vacía.
            print("Escriba un nombre por línea. Línea vacía = terminar.")
            while True:
                l = input(f"{len(nombres) + 1}. ").strip()
                if not l:
                    break
                nombres.append(l)
        # No reemplaza una lista válida con un archivo vacío.
        if nombres:
            # Escribe todos los nombres en UTF-8, uno por línea.
            with open(PROGRAMA_RUTA, "w", encoding="utf-8") as f:
                f.write("\n".join(nombres) + "\n")
            # Confirma cuántas canciones quedaron guardadas.
            print(f"Programa guardado con {len(nombres)} canciones.")
    # Deja tiempo para leer el resultado antes de volver al menú principal.
    pausa()


# ------------------------- consultas y edición -------------------------
def paginar(lineas, titulo=""):
    """Muestra una lista por páginas y permite salir antes de llegar al final."""
    # Recorre los elementos en grupos del tamaño configurado.
    for i in range(0, len(lineas), TAMANO_PAGINA):
        # Limpia la pantalla para que cada página se vea por separado.
        limpiar_pantalla()
        # El título es opcional; se muestra solo si el llamador lo indicó.
        if titulo:
            print(titulo)
            print("-" * 50)
        # Muestra únicamente las filas correspondientes a esta página.
        for l in lineas[i:i + TAMANO_PAGINA]:
            print(l)
        # Comprueba si el grupo actual contiene la última fila.
        fin = i + TAMANO_PAGINA >= len(lineas)
        # Solo pregunta por otra página si quedan filas por mostrar.
        if not fin:
            # q sale del listado; cualquier otra respuesta continúa.
            if input("\nEnter = siguiente página, q = salir: ").strip().lower() == "q":
                return
    # Al terminar, espera antes de volver a la pantalla anterior.
    pausa("\n-- Fin. Enter para volver --")


def opcion_w(con):
    """Lista las canciones guardadas, mostrando código y nombre."""
    # Recupera todas las canciones en orden de código.
    filas = con.execute("SELECT codigo, nombre_cancion FROM NOMBRES ORDER BY codigo").fetchall()
    # Informa y vuelve si la tabla está vacía.
    if not filas:
        print("La base de datos no tiene canciones.")
        pausa()
        return
    # Prepara cada fila para el paginador e indica el total del catálogo.
    paginar([f"[{c}] {n}" for c, n in filas], f"CANCIONES ({len(filas)})")


def opcion_x(con):
    """Pide el código de una canción y muestra su letra por páginas."""
    # Lee el código como texto para poder validar antes de convertirlo a número.
    t = input("Código de la canción: ").strip()
    # Rechaza códigos no numéricos y códigos numéricos que no existan.
    if not t.isdigit() or not obtener_nombre(con, int(t)):
        print(f">>> El código '{t}' NO EXISTE en la base de datos.")
        pausa()
        return
    # Convierte el código validado a entero.
    cod = int(t)
    # Obtiene la letra ordenada desde SQLite.
    letra = obtener_letra(con, cod)
    # Numera las líneas y las envía al paginador con el nombre como título.
    paginar([f"{i:>3}. {l}" for i, l in enumerate(letra, 1)], f"[{cod}] {obtener_nombre(con, cod)}")


def opcion_u(con):
    """Permite renombrar una canción y cambiar, insertar o borrar sus líneas."""
    # Busca la canción por código o nombre y pide elegir si hay varias coincidencias.
    cod = resolver_cancion(con, input("Nombre o código de la canción a corregir: "))
    # Si no se resolvió una canción válida, informa y sale.
    if not cod:
        print("No se encontró la canción.")
        pausa()
        return
    # Mantiene el menú de edición abierto hasta que se elija terminar.
    while True:
        # Vuelve a leer la letra para reflejar cualquier cambio reciente.
        letra = obtener_letra(con, cod)
        # Limpia la pantalla y muestra nombre y código de la canción seleccionada.
        limpiar_pantalla()
        print(f"[{cod}] {obtener_nombre(con, cod)}")
        # Imprime las líneas numeradas para que se puedan identificar al editar.
        for i, l in enumerate(letra, 1):
            print(f"{i:>3}. {l}")
        # Explica las acciones de edición disponibles.
        print("\n(n) cambiar nombre  (l) corregir una línea  (i) insertar línea  "
              "(e) eliminar línea  (r) reescribir toda la letra  (q) terminar")
        # Lee la opción elegida y la normaliza.
        op = input(">> ").strip().lower()
        # Salir de la edición devuelve el control al menú anterior.
        if op == "q":
            return
        # Cambiar nombre actualiza tanto el texto visible como el campo de búsqueda.
        elif op == "n":
            nn = input("Nuevo nombre: ").strip()
            if nn:
                con.execute("UPDATE NOMBRES SET nombre_cancion=?, nombre_norm=? WHERE codigo=?",
                            (nn, norm(nn), cod))
        # Estas acciones primero necesitan saber qué número de línea modificar.
        elif op in ("l", "i", "e"):
            n = input("Número de línea: ").strip()
            # Ignora entradas que no sean números.
            if not n.isdigit():
                continue
            # Convierte el número validado para usarlo como índice.
            n = int(n)
            # Reemplaza una línea existente si el número cae dentro de la letra.
            if op == "l" and 1 <= n <= len(letra):
                letra[n - 1] = input("Texto nuevo: ").strip() or letra[n - 1]
            # Inserta antes de la posición indicada, limitando el índice a la letra.
            elif op == "i":
                letra.insert(max(0, min(n - 1, len(letra))), input("Texto de la nueva línea: ").strip())
            # Elimina una línea existente si el número es válido.
            elif op == "e" and 1 <= n <= len(letra):
                letra.pop(n - 1)
            # Guarda la letra actualizada y vuelve a numerar sus líneas.
            guardar_letra(con, cod, letra)
        # La opción r recoge una letra nueva completa desde cero.
        elif op == "r":
            print("Escriba la letra nueva; línea vacía = terminar.")
            nueva = []
            while True:
                l = input(f"Línea {len(nueva) + 1}: ").strip()
                if not l:
                    break
                nueva.append(l)
            # No reemplaza la letra por una entrada completamente vacía.
            if nueva:
                guardar_letra(con, cod, nueva)
        # Confirma también los cambios de nombre, que se ejecutan directamente arriba.
        con.commit()


def opcion_b(con):
    """Borra una canción y su letra solo después de pedir confirmación."""
    # Resuelve el código a partir del nombre o código introducido.
    cod = resolver_cancion(con, input("Nombre o código de la canción a borrar: "))
    # Sale si el nombre/código no corresponde a una canción.
    if not cod:
        print("No se encontró la canción.")
        pausa()
        return
    # Guarda el nombre para mostrar claramente qué se va a borrar.
    nom = obtener_nombre(con, cod)
    # Pide confirmación explícita antes de borrar los registros.
    if preguntar_si_no(f"¿Seguro que desea BORRAR '{nom}' [{cod}] y toda su letra?"):
        # Borra primero la letra asociada al código.
        con.execute("DELETE FROM LETRAS WHERE codigo=?", (cod,))
        # Borra el registro principal de la canción.
        con.execute("DELETE FROM NOMBRES WHERE codigo=?", (cod,))
        # Confirma el borrado en la base de datos.
        con.commit()
        print("Canción borrada.")
    else:
        # Aclara que no se modificó la base si la persona dijo que no.
        print("No se borró nada.")
    # Deja el resultado visible.
    pausa()


# ----------------------------- modo manual -----------------------------
def mostrar_linea(nombre, letra, idx, ignorando=False):
    """Dibuja en pantalla la línea actual y un poco del contexto anterior/siguiente."""
    # Borra lo anterior para que la letra actual destaque.
    limpiar_pantalla()
    # Usa el ancho configurable para ajustar el texto de la letra.
    ancho = CARACTERES_POR_LINEA
    # Dibuja el borde superior y la cabecera con canción y número de línea.
    print("=" * min(ancho, 60))
    print(f" ♪ {nombre}   (línea {idx + 1}/{len(letra)})" + ("   [PAUSADO]" if ignorando else ""))
    print("=" * min(ancho, 60))
    # Muestra una versión recortada de la línea anterior cuando existe.
    if idx > 0:
        print("\n  " + textwrap.shorten(letra[idx - 1], ancho + 10, placeholder="…"))
    # Indica el comienzo de la línea que toca cantar.
    print("\n>>>")
    # Ajusta la línea a varias filas y la convierte a mayúsculas para verla mejor.
    for parte in textwrap.wrap(letra[idx], ancho) or [""]:
        print("    " + parte.upper())
    print()
    # Muestra un adelanto de la línea siguiente si todavía hay una.
    if idx + 1 < len(letra):
        print("  siguiente: " + textwrap.shorten(letra[idx + 1], ancho + 10, placeholder="…"))
    # Recuerda los controles válidos durante la canción.
    print("\n[Enter/c] continuar  [i] igual  [r] repetir canción  [g] ignorar  [s] seguir  "
          "[b] otra canción  [f] fin")


def cantar(con, cod, linea_inicial=0):
    """Reproduce una canción. Devuelve 'fin' (terminar sesión), 'otra' o 'termino'."""
    # Recupera el nombre y la letra antes de comenzar a mostrarla.
    nombre = obtener_nombre(con, cod)
    letra = obtener_letra(con, cod)
    # Empieza en la línea indicada y, al principio, no está en pausa.
    idx, ignorando = linea_inicial, False
    # Mantiene la canción activa mientras no se elija salir o cambiarla.
    while True:
        # Redibuja la canción con la posición y estado actuales.
        mostrar_linea(nombre, letra, idx, ignorando)
        # Lee el control introducido.
        cmd = input("> ").strip().lower()
        # En pausa solo permite reanudar o terminar la sesión.
        if ignorando:
            if cmd == "s":
                ignorando = False
            elif cmd == "f":
                return "fin"
            # No procesa otros comandos mientras está pausado.
            continue
        # Enter o c avanza una línea.
        if cmd in ("", "c"):
            idx += 1
            # Al pasar la última línea, anuncia el final y devuelve el control.
            if idx >= len(letra):
                limpiar_pantalla()
                print(f"\n  ✔ Fin de '{nombre}'.")
                return "termino"
        # i no cambia el índice, así que se vuelve a mostrar la misma línea.
        elif cmd == "i":
            pass  # se queda en la misma línea
        # r vuelve a la primera línea.
        elif cmd == "r":
            idx = 0
        # g activa el estado de pausa.
        elif cmd == "g":
            ignorando = True
        # b vuelve a la selección de otra canción.
        elif cmd == "b":
            return "otra"
        # f sale del modo manual por completo.
        elif cmd == "f":
            return "fin"


def modo_manual(con):
    """Busca canciones por palabras y permite seguir sus letras manualmente."""
    # Carga la lista opcional y empieza por su primera posición.
    programa = cargar_programa(con)
    pos_prog = 0
    # Repite la búsqueda hasta que se pida terminar la sesión.
    while True:
        # Limpia la pantalla y muestra el estado del menú.
        limpiar_pantalla()
        print("MODO MANUAL")
        # Si hay lista, muestra cuántas canciones se han recorrido y cuál sigue.
        if programa:
            sig = programa[pos_prog] if pos_prog < len(programa) else None
            print(f"Programa: {pos_prog}/{len(programa)} hechas. "
                  + (f"Siguiente: {sig[1]}" if sig else "Programa terminado."))
            print("  [p] cantar la siguiente del programa  [o] elegir otra del programa por número")
        # Pide palabras o una acción especial.
        print("Escriba 2-3 palabras que escuche del cantante, o:  [f] finalizar sesión  [w] ver lista")
        txt = input("> ").strip()
        # Separa la forma normalizada para comparar las opciones de una sola letra.
        low = txt.lower()
        # Inicializa el resultado de búsqueda y la línea inicial.
        cod, linea = None, 0
        # f termina el modo manual.
        if low == "f":
            return
        # w abre el listado del catálogo y luego regresa a este menú.
        if low == "w":
            opcion_w(con)
            continue
        # p toma la siguiente canción existente de la lista.
        if programa and low == "p" and pos_prog < len(programa):
            cod = programa[pos_prog][0]
            # Avanza la posición aunque la entrada no exista en la base.
            pos_prog += 1
            # Avisa y vuelve al menú si el nombre de la lista no está guardado.
            if not cod:
                print("Esa canción del programa NO está en la base de datos. Aliméntela con (f).")
                pausa()
                continue
        # o deja elegir una posición concreta de la lista.
        elif programa and low == "o":
            # Muestra las entradas numeradas y marca las que faltan de la base.
            for i, (c, n) in enumerate(programa, 1):
                print(f"  {i}. {n}" + ("" if c else "  [NO ESTÁ EN LA BD]"))
            n = input("Número: ").strip()
            # Solo acepta una entrada numerada que tenga código válido.
            if n.isdigit() and 1 <= int(n) <= len(programa) and programa[int(n) - 1][0]:
                cod = programa[int(n) - 1][0]
                pos_prog = int(n)  # el programa continúa desde la siguiente a la elegida
            else:
                continue
        # Las demás entradas no vacías se interpretan como palabras de una letra.
        elif txt:
            # Busca coincidencias aproximadas en la base de canciones.
            res = buscar_por_palabras(con, txt)
            # Informa si ninguna línea coincide lo suficiente.
            if not res:
                print("No se encontró ninguna canción con esas palabras.")
                pausa()
                continue
            # Elige automáticamente si hay una sola coincidencia claramente mejor.
            if len(res) == 1 or res[0][0] - res[1][0] > 0.5:
                _, cod, _, nro, _ = res[0]
            else:
                # Si los resultados son parecidos, deja que la persona elija.
                for i, (s, c, n, nro, l) in enumerate(res, 1):
                    print(f"  {i}) {n}  —  «{l[:60]}»")
                op = input("Número (Enter = cancelar): ").strip()
                # Cancela si la respuesta no corresponde a un resultado.
                if not (op.isdigit() and 1 <= int(op) <= len(res)):
                    continue
                # Extrae código y número de línea de la coincidencia elegida.
                _, cod, _, nro, _ = res[int(op) - 1]
            # La línea encontrada se convierte a índice desde cero para cantar().
            linea = nro - 1  # sincroniza en la línea donde se encontraron las palabras
        else:
            # Una entrada vacía no hace una búsqueda; vuelve a mostrar el menú.
            continue
        # Sigue la letra seleccionada hasta que termine, cambie de canción o salga.
        estado = cantar(con, cod, linea)
        # fin indica que hay que terminar la sesión completa.
        if estado == "fin":
            return
        # Al terminar normalmente, espera antes de ofrecer la canción siguiente.
        if estado == "termino":
            pausa("\nEnter para elegir la siguiente canción...")


# --------------------------- modo automático ---------------------------
def modo_automatico(con):
    """Carga bajo demanda el módulo automático y abre su interfaz."""
    # Importar aquí permite usar el resto del programa sin cargar dependencias de audio.
    try:
        import automatico
    except ImportError:
        # Informa si falta el archivo que contiene el modo automático.
        print("No se encontró automatico.py (debe estar en la misma carpeta que karaoke.py).")
        pausa()
        return
    # Proporciona la conexión y este módulo, cuyas utilidades reutiliza automático.
    automatico.modo_automatico(con, sys.modules[__name__])


# -------------------------------- menú --------------------------------
MENU = """
==============  KARAOKE INTELIGENTE  ==============
 (m) modo manual
 (a) modo automático
 (f) alimentar base de datos (texto / manual)
 (p) programa tentativo del cantante
 (w) ver códigos y nombres de canciones
 (x) ver letra de una canción por código
 (u) corregir letra de una canción
 (b) borrar una canción
 (q) salir
===================================================
"""


def main():
    """Abre la base de datos y ejecuta el menú principal hasta salir."""
    # Conecta a SQLite y crea la base/tablas si hacen falta.
    con = conectar()
    # Relaciona cada tecla del menú con la función que atiende esa opción.
    acciones = {
        "m": modo_manual, "a": modo_automatico, "f": menu_alimentacion,
        "p": menu_programa, "w": opcion_w, "x": opcion_x, "u": opcion_u, "b": opcion_b,
    }
    # Repite el menú principal mientras no se indique salir.
    while True:
        # Muestra todas las acciones disponibles.
        print(MENU)
        # Lee y normaliza la opción elegida.
        op = input("Opción: ").strip().lower()
        # q termina el ciclo y cierra la conexión al salir.
        if op == "q":
            break
        # Ejecuta la función correspondiente cuando la tecla está registrada.
        if op in acciones:
            acciones[op](con)
        else:
            # Informa si la tecla no corresponde a ninguna opción.
            print("Opción no válida.")
    # Cierra SQLite para liberar el archivo y guardar recursos.
    con.close()


if __name__ == "__main__":
    # Este bloque se ejecuta solo al iniciar este archivo, no al importarlo.
    try:
        # Arranca el menú principal.
        main()
    # Trata Ctrl+C o el fin de entrada como una salida normal.
    except (KeyboardInterrupt, EOFError):
        print("\nSaliendo...")
        # Termina con código 0 para indicar que la salida fue intencional.
        sys.exit(0)
