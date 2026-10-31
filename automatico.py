#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KARAOKE INTELIGENTE - modo automático

Arquitectura (3 piezas independientes):
  1. FUENTE de texto  -> FuenteMicrofono (Whisper local), FuenteTermux (Android) o
                         FuenteSimulada (archivo de texto).
  2. MOTOR            -> identifica la canción, sigue la línea, estima la velocidad del cantante
                         y detecta canciones nuevas. No sabe nada de audio.
  3. INTERFAZ         -> dibuja la pantalla y atiende el menú de control (Ctrl+C).
"""
# os revisa rutas de archivos usadas por la fuente de simulación.
import os
# queue permite pasar texto/audio de forma segura entre hilos.
import queue
# threading ejecuta captura y reconocimiento sin bloquear la interfaz.
import threading
# time mide pausas, duraciones y avances de línea.
import time
# SequenceMatcher compara palabras y frases con errores pequeños.
from difflib import SequenceMatcher

# ===================== CONFIGURACIÓN (editar aquí) =====================
# Nombre del modelo Whisper local que se carga en PC.
WHISPER_MODELO = "base"     # tiny < base < small. "base" = el más pequeño que rinde bien en español
# Formato de cálculo del modelo, elegido para reducir uso de memoria en CPU.
WHISPER_COMPUTE = "int8"    # int8 = rápido en CPU y poca RAM
# Idioma que Whisper debe usar para reconocer la voz.
IDIOMA = "es"
# Frecuencia de muestreo de audio usada por la fuente de micrófono en PC.
SAMPLE_RATE = 16000
# Duración de cada bloque que llega desde el micrófono.
BLOQUE_SEG = 0.25           # tamaño de cada bloque de micrófono
# Tiempo sin voz que cierra una frase capturada.
SILENCIO_CORTE = 0.7        # segundos de silencio que cierran un fragmento (fin de frase)
# Duración máxima permitida para un fragmento de voz.
SEG_MAX = 6.0               # un fragmento nunca pasa de esto (cantan sin pausa)
# Descarta fragmentos cuya parte hablada sea demasiado breve.
SEG_MIN = 1.0               # fragmentos de voz más cortos se descartan
# Multiplica el ruido ambiente para decidir qué volumen cuenta como voz.
UMBRAL_FACTOR = 3.0         # voz = volumen > ruido ambiente * este factor
# Umbral absoluto mínimo para detectar voz aunque haya poco ruido.
UMBRAL_MIN = 0.008

# Similitud necesaria para ubicar una frase en la canción actual.
UMBRAL_LINEA = 0.60         # similitud mínima para dar por oída una línea (siguiendo)
# Similitud necesaria para identificar una canción cuando aún no se sigue ninguna.
UMBRAL_IDENT = 0.65         # similitud mínima para identificar una canción (buscando)
# Puntaje suficiente para cambiar a otra canción durante el seguimiento.
UMBRAL_CAMBIO = 0.75        # similitud mínima para saltar a OTRA canción estando en una
# Frases irreconocibles consecutivas necesarias para crear un borrador de canción nueva.
FALLOS_NUEVA = 3            # frases seguidas sin identificar -> se asume canción nueva
# Frases no coincidentes antes de volver al estado de búsqueda.
FALLOS_FIN = 4              # frases seguidas sin coincidir en una canción -> vuelve a buscar
# Silencio que indica que terminó de cantarse una canción nueva.
SILENCIO_FIN_NUEVA = 15     # segundos de silencio que cierran una canción nueva
# Margen aplicado al tiempo estimado por línea antes de avanzar automáticamente.
FACTOR_AVANCE = 1.3         # avanza solo cuando pasa (velocidad estimada x 1.3)
# Límite de líneas que se pueden adelantar sin confirmación por audio.
AVANCE_AUTO_MAX = 2         # máx. avances por predicción sin confirmar con audio
# Ventaja que recibe la siguiente canción de la lista al buscar coincidencias.
PROG_BONUS_SIG = 0.10       # ventaja (0-1) al identificar la SIGUIENTE canción del PROGRAMA.txt
# Ventaja menor que reciben las demás canciones pendientes de la lista.
PROG_BONUS_OTRAS = 0.04     # ventaja menor para las demás canciones pendientes del programa
                            # (0 en ambos = el programa no influye; el orden nunca es obligatorio)
# =======================================================================

# Respuestas típicas inventadas por servicios de voz; se descartan como letras.
ALUCINACIONES = {"gracias", "gracias por ver el video", "subtitulos", "suscribete",
                 "subtitulos realizados por la comunidad de amara org", "musica"}


# ----------------------------- similitud -----------------------------
def _cobertura(a, b):
    """Calcula qué proporción de las palabras de a aparece aproximadamente en b."""
    # Una lista vacía no puede tener palabras coincidentes.
    if not a:
        return 0.0
    # Convierte el destino a conjunto para buscar palabras exactas rápidamente.
    bset = set(b)
    # Cuenta cuántas palabras se reconocen literal o aproximadamente.
    hits = 0
    # Compara cada palabra de la frase consultada.
    for w in a:
        # La coincidencia literal cuenta directamente.
        if w in bset:
            hits += 1
        # Para palabras largas, acepta una palabra parecida de longitud similar.
        elif len(w) > 3 and any(abs(len(v) - len(w)) <= 2 and
                                SequenceMatcher(None, w, v).ratio() >= 0.8 for v in b):
            hits += 1
    # Devuelve la fracción de palabras encontradas entre cero y uno.
    return hits / len(a)


def similitud(pa, pb):
    """Combina cobertura en ambos sentidos para comparar dos listas de palabras."""
    # Promedia cuánto de cada frase está cubierto por la otra.
    return 0.5 * _cobertura(pa, pb) + 0.5 * _cobertura(pb, pa)


# ------------------------------- motor -------------------------------
class Motor:
    """Mantiene la canción actual, compara frases y calcula el avance de la letra."""

    def __init__(self, con, K):
        # Guarda la conexión SQLite y el módulo de interfaz/datos que le pasó karaoke.py.
        self.con, self.K = con, K
        # Estado de búsqueda o reproducción que usa el motor y la pantalla.
        self.estado = "BUSCANDO"   # BUSCANDO | SIGUIENDO | TERMINO | NUEVA | PAUSA
        # Recuerda el estado anterior para poder salir de una pausa.
        self.estado_previo = "BUSCANDO"
        # Código y datos de la canción identificada; empiezan vacíos.
        self.cod = None
        self.c = None              # canción actual (dict)
        # Índice de la línea que debe aparecer ahora, comenzando desde cero.
        self.idx = 0               # línea que TOCA cantar ahora
        # Contadores y muestras usadas para estabilizar la identificación.
        self.fallos = 0
        self.fallidos = []
        self.marcas = []
        # Datos temporales para estimar la duración de cada línea.
        self.seg_linea = None      # segundos por línea estimados
        self.predichos = 0
        self.ultimo_avance = 0.0
        # Guarda la última actividad de voz, texto y mensaje para la interfaz.
        self.ultimo_habla = time.time()
        self.ultimo_texto = ""
        self.mensaje = "Escuchando…"
        # Identificador y líneas del borrador de una canción no catalogada.
        self.temp_id = None
        self.temp_lineas = []
        self.nueva_lista = False
        # Lista de canciones planeadas y posición actual dentro de ella.
        self.prog, self.prog_pos = [], 0   # PROGRAMA.txt: [(codigo, nombre)] y cuántas ya se cantaron
        # Carga las canciones de SQLite y la lista del cantante en memoria.
        self.recargar()

    # ---- índice en memoria ----
    def recargar(self):
        """Vuelve a cargar canciones y letras desde SQLite para las búsquedas."""
        # Reinicia el índice en memoria para no conservar datos antiguos.
        self.canciones = {}
        # Lee todas las letras con su nombre y código en orden de canción y línea.
        filas = self.con.execute("""SELECT n.codigo, n.nombre_cancion, l.linea
                                    FROM NOMBRES n JOIN LETRAS l ON l.codigo = n.codigo
                                    ORDER BY n.codigo, l.numero_linea""").fetchall()
        # Agrupa las líneas de cada código en un mismo diccionario.
        for cod, nom, lin in filas:
            # Crea la entrada de la canción solo la primera vez que aparece su código.
            d = self.canciones.setdefault(cod, {"nombre": nom, "lineas": [], "words": []})
            # Guarda el texto original para mostrarlo en pantalla.
            d["lineas"].append(lin)
            # Guarda las palabras normalizadas para comparar frases más rápido.
            d["words"].append(self.K.norm(lin).split())
        # También actualiza la lista opcional de canciones planeadas.
        self._cargar_programa()

    # ---- programa tentativo del cantante (PROGRAMA.txt) ----
    def _cargar_programa(self):
        """Lee PROGRAMA.txt con la misma función del modo manual. Conserva la posición."""
        # Reutiliza el lector de karaoke.py para que ambos modos entiendan el mismo archivo.
        try:
            self.prog = list(self.K.cargar_programa(self.con))
        # Si la lista no se puede leer, automático continúa sin programa cargado.
        except Exception:
            self.prog = []
        # Ajusta la posición para que siga dentro del tamaño de la lista actual.
        self.prog_pos = min(self.prog_pos, len(self.prog))

    def prog_siguiente(self):
        """(codigo, nombre) de la siguiente canción del programa, o None si terminó."""
        # Devuelve la entrada actual solo si aún quedan canciones.
        return self.prog[self.prog_pos] if self.prog_pos < len(self.prog) else None

    def _bonus_programa(self, cod):
        """Ventaja al identificar: la siguiente del programa pesa más; las demás pendientes, un poco."""
        # Recoge solo códigos válidos que todavía están pendientes.
        pendientes = [c for c, _ in self.prog[self.prog_pos:] if c]
        # Una canción ajena a la lista no recibe puntos extra.
        if cod not in pendientes:
            return 0.0
        # Distingue la siguiente canción de las demás pendientes.
        return PROG_BONUS_SIG if cod == pendientes[0] else PROG_BONUS_OTRAS

    def _marcar_programa(self, cod):
        """Al empezar una canción del programa, este continúa desde la siguiente a ella (igual que
        en el modo manual). Si cantan una que no está en el programa, o una ya hecha, no cambia."""
        # Busca el código desde la posición actual, sin retroceder en la lista.
        for i in range(self.prog_pos, len(self.prog)):
            # Si coincide, la siguiente posición pasa a ser la canción posterior.
            if self.prog[i][0] == cod:
                self.prog_pos = i + 1
                return

    def cargar_programada(self, ahora):
        """Tecla [p]: muestra la siguiente del programa sin esperar a oírla (la 'p' del modo manual)."""
        # Conserva los nombres de canciones sin código para informar que se saltaron.
        omitidas = []
        # Avanza sobre canciones de la lista que no existen en la base de datos.
        while self.prog_pos < len(self.prog) and not self.prog[self.prog_pos][0]:
            omitidas.append(self.prog[self.prog_pos][1])  # está en PROGRAMA.txt pero no en la BD
            self.prog_pos += 1
        # Lee la siguiente entrada válida después de saltar las ausentes.
        sig = self.prog_siguiente()
        # Avisa y no modifica la reproducción si ya no quedan canciones.
        if not sig:
            self.mensaje = "El programa ya terminó (o no hay PROGRAMA.txt)."
            return
        # Si había un borrador abierto, lo elimina antes de comenzar otra canción.
        if self.estado == "NUEVA":
            self.descartar_nueva()
        # Inicia la canción programada; -1 indica que aún no se ha oído una línea.
        self._iniciar(sig[0], -1, ahora)
        # La velocidad se empezará a estimar cuando llegue una frase reconocida.
        self.marcas = []  # la velocidad se mide desde la primera línea que se oiga
        # Muestra el nombre y añade los nombres omitidos al mensaje si los hubo.
        self.mensaje = f"Del programa: {self.c['nombre']}"
        if omitidas:
            self.mensaje += " (omitida, no está en la BD: " + ", ".join(omitidas) + ")"

    # ---- puntaje de una línea (o par de líneas) contra el texto oído ----
    def _score(self, tw, c, k):
        """Compara la frase con la línea k y, si conviene, también con la siguiente."""
        # Comienza comparando con una sola línea.
        s1, h = similitud(tw, c["words"][k]), k
        # La frase puede abarcar dos líneas; también prueba ese par si existe.
        if k + 1 < len(c["lineas"]):
            s2 = similitud(tw, c["words"][k] + c["words"][k + 1])
            # Si el par se acerca más a la frase, registra su puntaje y última línea oída.
            if s2 > s1:
                s1, h = s2, k + 1
        # Devuelve el puntaje y el índice de la última línea reconocida.
        return s1, h

    def _buscar_global(self, tw):
        """Busca en TODA la base. Devuelve (score, cod, línea_oída) o None."""
        # Usa palabras distintivas cuando hay alguna de cuatro letras o más.
        tset = {w for w in tw if len(w) >= 4} or set(tw)
        # Aún no hay una mejor canción identificada.
        mejor = None
        # Revisa cada canción guardada en memoria.
        for cod, c in self.canciones.items():
            # Recupera el número de líneas y la posible ventaja del programa.
            n = len(c["lineas"])
            bonus = self._bonus_programa(cod)
            # Prueba la frase contra cada posición de la canción.
            for k in range(n):
                # Une palabras de la línea actual y la siguiente para filtrar candidatos.
                cand = set(c["words"][k]) | (set(c["words"][k + 1]) if k + 1 < n else set())
                # Evita comparar en detalle líneas sin palabras compartidas distintivas.
                if not (cand & tset):
                    continue
                # Calcula similitud y agrega el bonus sin permitir puntajes mayores que uno.
                s, h = self._score(tw, c, k)
                s = min(1.0, s + bonus)
                # Conserva el candidato con el puntaje más alto hasta el momento.
                if mejor is None or s > mejor[0]:
                    mejor = (s, cod, h)
        # Devuelve el mejor candidato solo si supera el umbral de identificación.
        return mejor if mejor and mejor[0] >= UMBRAL_IDENT else None

    def _ventana(self, tw):
        """Busca el texto oído cerca de la línea actual. Devuelve línea oída o None."""
        # Guarda la cantidad de líneas de la canción actual.
        n = len(self.c["lineas"])
        # Aún no se ha encontrado ninguna línea suficientemente parecida.
        mejor = None
        # Limita la búsqueda a unas líneas antes y después de la posición actual.
        for k in range(max(0, self.idx - 3), min(n, self.idx + 5)):
            # Puntúa la frase contra la línea o el par de líneas.
            s, h = self._score(tw, self.c, k)
            # Solo guarda resultados que superen el umbral para seguir la canción.
            if s >= UMBRAL_LINEA:
                # Prefiere puntajes altos y, en empate, los cercanos a la línea actual.
                clave = (round(s, 2), -abs(h - (self.idx - 1)))
                # Actualiza el mejor candidato si su clave es superior.
                if mejor is None or clave > mejor[0]:
                    mejor = (clave, h)
        # Devuelve la línea detectada o None si ninguna coincide.
        return mejor[1] if mejor else None

    # ---- iniciar / seguir canción ----
    def _iniciar(self, cod, heard, ahora):
        """Configura el motor para seguir una canción a partir de la línea oída."""
        # Guarda los datos de la canción ya cargados en memoria.
        self.cod, self.c = cod, self.canciones[cod]
        # Cuenta las líneas para limitar el índice y detectar el final.
        n = len(self.c["lineas"])
        # La línea que se muestra es la posterior a la última que se oyó.
        self.idx = min(heard + 1, n - 1)
        # Si se oyó la última línea, marca la canción como terminada.
        self.estado = "TERMINO" if heard >= n - 1 else "SIGUIENDO"
        # Inicia las marcas de tiempo/línea y reinicia contadores de errores.
        self.marcas = [(ahora, heard)]
        self.seg_linea, self.predichos, self.fallos, self.fallidos = None, 0, 0, []
        # Usa el momento actual como referencia para el siguiente avance estimado.
        self.ultimo_avance = ahora
        # Mueve la lista de canciones a la entrada siguiente si la canción forma parte de ella.
        self._marcar_programa(cod)
        # Explica en pantalla si empezó el seguimiento o si la canción ya terminó.
        self.mensaje = f"Identificada: {self.c['nombre']}" if self.estado == "SIGUIENDO" else "Fin de la canción"

    def procesar(self, texto, ahora):
        """Normaliza una frase reconocida y actualiza la canción o el borrador."""
        # Durante la pausa no se procesa ni se agrega texto recibido.
        if self.estado == "PAUSA":
            return
        # Convierte el texto a forma normalizada y crea su lista de palabras.
        t = self.K.norm(texto)
        tw = t.split()
        # Ignora frases muy cortas y respuestas típicas inventadas por el reconocedor.
        if len(tw) < 2 or t in ALUCINACIONES:
            return
        # Registra el último texto válido y cuándo se recibió.
        self.ultimo_texto, self.ultimo_habla = texto, ahora

        # Si ya se sigue una canción, primero busca cerca de la posición actual.
        if self.estado == "SIGUIENDO":
            h = self._ventana(tw)
            # Una coincidencia cercana confirma la posición y termina este ciclo.
            if h is not None:
                self._confirmar(h, ahora)
                return
            # Si falló la búsqueda local, intenta encontrar otra canción en toda la base.
            r = self._buscar_global(tw)
            # Cambia de canción si es la misma o si la nueva coincidencia es muy fuerte.
            if r and (r[1] == self.cod or r[0] >= UMBRAL_CAMBIO):
                self._iniciar(r[1], r[2], ahora)
                self.mensaje = "Re-sincronizado: " + self.c["nombre"]
                return
            # Cuenta frases que no encajan con la canción actual.
            self.fallos += 1
            # Tras varios fallos, deja de seguir y vuelve a buscar desde cero.
            if self.fallos >= FALLOS_FIN:
                self.estado, self.fallos = "BUSCANDO", 0
                self.mensaje = "Perdí al cantante; escuchando de nuevo…"
            return

        # En búsqueda, canción terminada o detección de canción nueva, busca en toda la base.
        r = self._buscar_global(tw)
        # Si encuentra una canción conocida, descarta el borrador actual si lo había.
        if r:
            if self.estado == "NUEVA":
                self.descartar_nueva()
            # Inicia el seguimiento de la canción identificada.
            self._iniciar(r[1], r[2], ahora)
            return
        # Guarda la frase fallida y aumenta el contador de resultados sin coincidencia.
        self.fallos += 1
        self.fallidos.append(texto)
        # Si ya está creando un borrador, agrega la frase nueva como una posible línea.
        if self.estado == "NUEVA":
            self._agregar_temp(texto)
        # Al acumular suficientes fallos, empieza una canción nueva y crea su borrador.
        elif self.fallos >= FALLOS_NUEVA:
            self.estado = "NUEVA"
            self._crear_temp()
            # Copia también las frases que se acumularon antes de crear el borrador.
            for f in self.fallidos:
                self._agregar_temp(f)
            self.mensaje = "Canción NUEVA: transcribiendo la letra…"

    def _confirmar(self, heard, ahora):
        """Actualiza posición y velocidad aproximada tras reconocer una línea."""
        # Cuenta las líneas de la canción actual.
        n = len(self.c["lineas"])
        # Si la línea reconocida retrocedió, reinicia las muestras de velocidad.
        if self.marcas and heard < self.marcas[-1][1]:
            self.marcas = []
        # Conserva solo las seis marcas más recientes para estimar la velocidad.
        self.marcas = (self.marcas + [(ahora, heard)])[-6:]
        # Calcula cuántas líneas separan la primera y última marca guardada.
        dl = self.marcas[-1][1] - self.marcas[0][1]
        # Calcula el tiempo transcurrido entre esas mismas marcas.
        dt = self.marcas[-1][0] - self.marcas[0][0]
        # Si hubo avance y pasó tiempo, estima segundos por línea.
        if dl > 0 and dt > 0:
            self.seg_linea = dt / dl
        # Reinicia fallos y predicciones al confirmar una coincidencia real.
        self.fallos, self.predichos, self.ultimo_avance = 0, 0, ahora
        # Si se escuchó la última línea, marca el fin de la canción.
        if heard >= n - 1:
            self.idx, self.estado, self.mensaje = n - 1, "TERMINO", "Fin de la canción"
        else:
            # Muestra la línea siguiente a la última que se reconoció.
            self.idx, self.mensaje = heard + 1, "Siguiendo al cantante"

    def tick(self, ahora):
        """Llamar seguido. Devuelve True si algo cambió en pantalla."""
        # Avanza como máximo el límite configurado y solo mientras sigue una canción.
        if self.estado == "SIGUIENDO" and self.seg_linea and self.predichos < AVANCE_AUTO_MAX \
                and self.idx < len(self.c["lineas"]) - 1 \
                and ahora - self.ultimo_avance > self.seg_linea * FACTOR_AVANCE:
            # Mueve una línea y cuenta esta predicción sin confirmación por audio.
            self.idx += 1
            self.predichos += 1
            # Reinicia el reloj del siguiente avance estimado.
            self.ultimo_avance = ahora
            self.mensaje = "Avance por velocidad estimada"
            # Indica al bucle principal que debe volver a dibujar.
            return True
        # Cierra la captura de una canción nueva tras suficiente silencio.
        if self.estado == "NUEVA" and self.temp_lineas and not self.nueva_lista \
                and ahora - self.ultimo_habla > SILENCIO_FIN_NUEVA:
            self.nueva_lista = True
            return True
        # No hubo cambios visibles que requieran redibujar la pantalla.
        return False

    # ---- controles manuales (menú Ctrl+C) ----
    def avanzar(self):
        """Avanza una línea manualmente sin pasar del final de la letra."""
        # Solo puede avanzar si hay canción y todavía no se muestra su última línea.
        if self.c and self.idx < len(self.c["lineas"]) - 1:
            self.idx += 1
            # Guarda el tiempo del avance para reiniciar la predicción automática.
            self.ultimo_avance = time.time()

    def repetir(self):
        """Vuelve a mostrar la primera línea y reinicia la estimación de velocidad."""
        # No hace nada si todavía no se identificó una canción.
        if self.c:
            # Reinicia índice, estado y marcas de tiempo.
            self.idx, self.estado, self.marcas, self.seg_linea = 0, "SIGUIENDO", [], None
            # Evita que un avance predicho ocurra inmediatamente.
            self.ultimo_avance = time.time()

    def pausar(self):
        """Guarda el estado actual y deja de procesar frases."""
        # Evita sobrescribir el estado original si ya estaba en pausa.
        if self.estado != "PAUSA":
            self.estado_previo, self.estado = self.estado, "PAUSA"
            self.mensaje = "IGNORANDO (pausa)"

    def seguir(self):
        """Restaura el estado que tenía antes de pausar."""
        # Solo reanuda si la máquina de estados está pausada.
        if self.estado == "PAUSA":
            self.estado = self.estado_previo
            # Reinicia el reloj de voz para que la pausa no cierre una canción nueva.
            self.ultimo_habla = time.time()
            self.mensaje = "Escuchando…"

    def buscar_otra(self):
        """Olvida el seguimiento y vuelve a buscar una canción conocida."""
        # Reinicia los contadores de frases fallidas y actualiza el mensaje.
        self.estado, self.fallos, self.fallidos, self.mensaje = "BUSCANDO", 0, [], "Escuchando…"

    # ---- canción nueva en tablas temporales ----
    def _crear_temp(self):
        """Crea un registro temporal que contendrá las líneas de una canción nueva."""
        # Inserta un borrador sin nombre y guarda el identificador que devuelve SQLite.
        cur = self.con.execute("INSERT INTO TEMP_NOMBRES(nombre_cancion) VALUES (NULL)")
        # Reinicia las líneas en memoria y confirma la fila del borrador.
        self.temp_id, self.temp_lineas = cur.lastrowid, []
        self.con.commit()

    def _agregar_temp(self, texto):
        """Añade una frase al borrador, evitando repetir casi el mismo texto seguido."""
        # Quita espacios exteriores del resultado reconocido.
        texto = texto.strip()
        # Compara con la frase anterior para no guardar duplicados consecutivos.
        if self.temp_lineas and SequenceMatcher(
                None, self.K.norm(texto), self.K.norm(self.temp_lineas[-1])).ratio() > 0.85:
            return  # repetición de la misma frase
        # Añade la frase a la lista temporal que muestra la interfaz.
        self.temp_lineas.append(texto)
        # Persiste la nueva línea en la tabla temporal con numeración desde uno.
        self.con.execute("INSERT INTO TEMP_LETRAS VALUES (?,?,?)",
                         (self.temp_id, len(self.temp_lineas), texto))
        # Confirma cada línea para no perder el borrador si el programa se interrumpe.
        self.con.commit()

    def set_temp(self, lineas):
        """Reemplaza las líneas del borrador por las que se editaron en pantalla."""
        # Actualiza la copia en memoria.
        self.temp_lineas = list(lineas)
        # Borra las filas temporales anteriores antes de reconstruirlas.
        self.con.execute("DELETE FROM TEMP_LETRAS WHERE id_temp=?", (self.temp_id,))
        # Inserta el texto editado con números consecutivos.
        self.con.executemany("INSERT INTO TEMP_LETRAS VALUES (?,?,?)",
                             [(self.temp_id, i, l) for i, l in enumerate(lineas, 1)])
        # Guarda los cambios del borrador.
        self.con.commit()

    def descartar_nueva(self):
        """Elimina el borrador temporal y restablece los contadores de canción nueva."""
        # Borra las líneas y el registro principal solo si se creó un borrador.
        if self.temp_id is not None:
            self.con.execute("DELETE FROM TEMP_LETRAS WHERE id_temp=?", (self.temp_id,))
            self.con.execute("DELETE FROM TEMP_NOMBRES WHERE id_temp=?", (self.temp_id,))
            self.con.commit()
        # Limpia el identificador, las líneas y la marca de revisión pendiente.
        self.temp_id, self.temp_lineas, self.nueva_lista = None, [], False
        # Reinicia las frases fallidas acumuladas para la canción nueva.
        self.fallos, self.fallidos = 0, []
        # Si aún se encontraba en estado NUEVA, regresa a búsqueda.
        if self.estado == "NUEVA":
            self.estado, self.mensaje = "BUSCANDO", "Escuchando…"


# ------------------------------ fuentes ------------------------------
class FuenteSimulada:
    """Cada línea no vacía del archivo es una 'transcripción' que llega cada `pausa` segundos."""

    def __init__(self, ruta, pausa=2.5):
        # Lee frases UTF-8 y descarta filas vacías o comentarios.
        with open(ruta, encoding="utf-8-sig") as f:
            self.textos = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        # Guarda el intervalo, la cola de mensajes y el estado de fin de archivo.
        self.pausa, self.q, self.terminada = pausa, queue.Queue(), False

    def iniciar(self):
        """Inicia en segundo plano la entrega gradual de frases simuladas."""
        # El hilo separado evita bloquear la actualización de pantalla.
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        """Espera entre frases, las pone en cola y marca el final de la simulación."""
        # Entrega las frases en el orden en que aparecieron en el archivo.
        for t in self.textos:
            time.sleep(self.pausa)
            self.q.put(t)
        # Informa al bucle principal que ya no hay frases por producir.
        self.terminada = True

    def siguiente_texto(self):
        """Devuelve una frase disponible sin esperar; si no hay, devuelve None."""
        # La cola vacía significa que todavía no hay una frase lista.
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

    def pausar(self, v):
        """La fuente simulada no necesita detenerse para pausar el motor."""
        # Se conserva este método para que todas las fuentes compartan la misma interfaz.
        pass

    def detener(self):
        """No hay recursos abiertos que cerrar en una simulación desde archivo."""
        # Se conserva este método para que el cierre común funcione con cualquier fuente.
        pass


class FuenteMicrofono:
    """Micrófono -> segmentos por silencio -> limpieza -> faster-whisper -> texto."""

    def __init__(self):
        # Importa las dependencias solo si el usuario selecciona micrófono PC.
        try:
            import numpy as np
            import sounddevice as sd
            from faster_whisper import WhisperModel
        except ImportError as e:
            # Muestra el traceback original para diagnosticar el módulo que falta.
            import traceback
            traceback.print_exc()
            # Obtiene el ejecutable exacto de Python que está corriendo el programa.
            import sys as _sys
            # Da instrucciones usando ese mismo intérprete y vuelve a propagar la causa.
            raise RuntimeError(
                f"No se pudo cargar '{e.name}'. Error real: {e}\n"
                f"  Este programa se está ejecutando con: {_sys.executable}\n"
                "  Si dice 'No module named', instale las librerías PARA ESE Python con:\n"
                f'  "{_sys.executable}" -m pip install -r requirements.txt\n'
                "  Si menciona DLL, 'multiarray' o 'compiled against', es un conflicto de versiones "
                "(copie el mensaje completo de arriba).") from e
        # Guarda las bibliotecas locales a la instancia para usarlas en captura y filtros.
        self.np, self.sd = np, sd
        # Avisa que Whisper puede tardar y descargar el modelo en la primera ejecución.
        print(f"Cargando modelo Whisper '{WHISPER_MODELO}' (la primera vez se descarga; requiere internet)…")
        # Carga Whisper en CPU con el modelo y formato configurados arriba.
        self.modelo = WhisperModel(WHISPER_MODELO, device="cpu", compute_type=WHISPER_COMPUTE)
        # Crea colas independientes para audio capturado, segmentos y textos reconocidos.
        self.q_audio, self.q_seg, self.q_texto = queue.Queue(), queue.Queue(), queue.Queue()
        # Inicializa el estado de captura y la referencia al flujo de audio.
        self.activo, self.en_pausa, self.stream = False, False, None

    def iniciar(self):
        """Abre el micrófono y pone a correr los hilos de segmentación/transcripción."""
        # Activa los bucles que trabajan en segundo plano.
        self.activo = True
        # Pide silencio para estimar el ruido ambiente antes de detectar voz.
        print("Calibrando ruido ambiente: guarde SILENCIO durante 1 segundo…")
        # Abre un flujo mono de audio y define el tamaño de cada bloque capturado.
        self.stream = self.sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=int(SAMPLE_RATE * BLOQUE_SEG),
            # Copia el canal mono capturado a la cola para que lo procese otro hilo.
            callback=lambda indata, frames, t, st: self.q_audio.put(indata[:, 0].copy()))
        # Empieza a leer los bloques desde el micrófono.
        self.stream.start()
        # Un hilo detecta voz y produce segmentos; otro los convierte en texto.
        threading.Thread(target=self._segmentar, daemon=True).start()
        threading.Thread(target=self._transcribir, daemon=True).start()

    def detener(self):
        """Detiene los hilos y cierra el flujo del micrófono si estaba abierto."""
        # Las rutinas de fondo salen al comprobar esta bandera.
        self.activo = False
        # Detiene y libera el dispositivo de audio cuando se inició correctamente.
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def pausar(self, v):
        """Activa o quita la pausa de captura."""
        # Los hilos consultan esta bandera antes de procesar bloques.
        self.en_pausa = v

    def siguiente_texto(self):
        """Entrega un texto ya reconocido sin bloquear a quien lo solicita."""
        # La interfaz no espera si Whisper todavía está procesando el audio.
        try:
            return self.q_texto.get_nowait()
        except queue.Empty:
            return None

    def _segmentar(self):
        """Detecta voz por volumen y guarda bloques hasta un silencio o límite."""
        # Usa NumPy para calcular el nivel de cada bloque.
        np = self.np
        # Inicializa muestras de ruido, umbral, audio acumulado y contadores de tiempo.
        ruido, umbral, buf, hablando, silencio, dur = [], None, [], False, 0.0, 0.0
        # Sigue procesando mientras la fuente esté activa.
        while self.activo:
            # Espera como máximo medio segundo por un bloque de audio nuevo.
            try:
                b = self.q_audio.get(timeout=0.5)
            except queue.Empty:
                continue
            # En pausa vacía el segmento parcial para no mezclarlo al reanudar.
            if self.en_pausa:
                buf, hablando, silencio, dur = [], False, 0.0, 0.0
                continue
            # Calcula el volumen RMS del bloque actual.
            rms = float(np.sqrt(np.mean(b ** 2)))
            # Mientras se calibra, reúne niveles de ruido ambiente.
            if umbral is None:
                ruido.append(rms)
                # Tras aproximadamente un segundo, fija un umbral de voz mínimo.
                if len(ruido) >= int(1 / BLOQUE_SEG):
                    umbral = max(UMBRAL_MIN, UMBRAL_FACTOR * float(np.median(ruido)))
                continue
            # Un volumen superior al umbral se considera parte hablada.
            if rms > umbral:
                buf.append(b)
                hablando, silencio, dur = True, 0.0, dur + BLOQUE_SEG
            # Tras detectar voz, conserva también los bloques silenciosos de cierre.
            elif hablando:
                buf.append(b)
                silencio, dur = silencio + BLOQUE_SEG, dur + BLOQUE_SEG
            # Cierra el segmento al alcanzar el silencio requerido o la longitud máxima.
            if hablando and (silencio >= SILENCIO_CORTE or dur >= SEG_MAX):
                # Envía al reconocimiento solo la parte hablada si supera la duración mínima.
                if dur - silencio >= SEG_MIN:
                    self.q_seg.put(np.concatenate(buf))
                # Prepara el estado para detectar el siguiente fragmento de voz.
                buf, hablando, silencio, dur = [], False, 0.0, 0.0

    def _limpiar(self, audio):
        """Limpieza: quita DC, filtro pasa-altos 80 Hz, reducción de ruido, normaliza volumen."""
        # Recupera NumPy desde la instancia para evitar importarlo de nuevo.
        np = self.np
        # Resta el promedio y centra la señal alrededor de cero.
        audio = audio - float(np.mean(audio))
        # Intenta quitar frecuencias graves que suelen ser vibración o ruido de manejo.
        try:
            from scipy.signal import butter, sosfilt
            audio = sosfilt(butter(2, 80, "highpass", fs=SAMPLE_RATE, output="sos"), audio)
        except Exception:
            # El filtro es opcional; si SciPy falla, conserva el audio sin filtrar.
            pass
        # Intenta reducir ruido estacionario cuando está disponible noisereduce.
        try:
            import noisereduce as nr
            audio = nr.reduce_noise(y=audio, sr=SAMPLE_RATE, stationary=True, prop_decrease=0.8)
        except Exception:
            # La reducción de ruido es opcional; no impide continuar con la transcripción.
            pass
        # Evita dividir por cero si el segmento no tiene amplitud.
        pico = float(np.max(np.abs(audio))) or 1.0
        # Ajusta el nivel máximo a 0.9 y devuelve audio float32 para Whisper.
        return (audio / pico * 0.9).astype("float32")

    def _transcribir(self):
        """Toma segmentos de voz, los limpia y envía el texto reconocido a la cola."""
        # Sigue trabajando mientras la fuente no haya sido detenida.
        while self.activo:
            # Espera un segmento; el tiempo límite permite revisar la bandera activo.
            try:
                seg = self.q_seg.get(timeout=0.5)
            except queue.Empty:
                continue
            # Ejecuta la transcripción y deja solo fragmentos con suficiente probabilidad de voz.
            try:
                partes, _ = self.modelo.transcribe(
                    self._limpiar(seg), language=IDIOMA, beam_size=1, vad_filter=True,
                    condition_on_previous_text=False)
                # Une los fragmentos de texto reconocidos en esta sección de audio.
                texto = " ".join(p.text.strip() for p in partes if p.no_speech_prob < 0.6).strip()
                # Solo envía resultados no vacíos a la interfaz.
                if texto:
                    self.q_texto.put(texto)
            except Exception as e:
                # Un segmento defectuoso no debe detener las demás transcripciones.
                self.q_texto.put("")  # no detener el karaoke por un fragmento malo
                print("Error de transcripción:", e)


class FuenteTermux:
    """
    Android (Termux): usa el reconocedor de voz del teléfono vía Termux:API
    (comando `termux-speech-to-text`). No necesita instalar Whisper ni librerías de audio:
    el propio Android limpia y transcribe. Cada llamada devuelve una frase.
    """

    def __init__(self):
        # shutil permite comprobar que el paquete de comandos está disponible en Termux.
        import shutil
        # Avisa con instrucciones si no se instaló el comando del complemento.
        if not shutil.which("termux-speech-to-text"):
            raise RuntimeError(
                "No se encontró 'termux-speech-to-text'. En Termux ejecute:\n"
                "  pkg install termux-api\n"
                "e instale además la app 'Termux:API' (F-Droid) y conceda permiso de micrófono.")
        # Prepara la cola y los indicadores de ejecución y pausa.
        self.q_texto, self.activo, self.en_pausa = queue.Queue(), False, False

    def iniciar(self):
        """Inicia un hilo que pide frases al reconocedor del teléfono."""
        # Indica al bucle que debe seguir solicitando transcripciones.
        self.activo = True
        # El proceso de voz puede esperar interacción, por eso va en otro hilo.
        threading.Thread(target=self._escuchar, daemon=True).start()

    def detener(self):
        """Pide al hilo que deje de solicitar nuevas transcripciones."""
        # El hilo termina al revisar esta bandera tras completar la solicitud actual.
        self.activo = False

    def pausar(self, v):
        """Permite que el hilo espere sin llamar al reconocedor mientras está pausado."""
        # Guarda el estado de pausa que consulta el hilo de escucha.
        self.en_pausa = v

    def siguiente_texto(self):
        """Extrae una transcripción disponible sin esperar."""
        # Devuelve None cuando la cola aún está vacía.
        try:
            return self.q_texto.get_nowait()
        except queue.Empty:
            return None

    def _escuchar(self):
        """Invoca repetidamente Termux:API y pone las frases reconocidas en la cola."""
        # subprocess ejecuta el comando del complemento del teléfono.
        import subprocess
        # Mantiene las solicitudes mientras el modo automático siga activo.
        while self.activo:
            # Evita abrir el reconocedor cuando el usuario puso el motor en pausa.
            if self.en_pausa:
                time.sleep(0.3)
                continue
            # Ejecuta una sesión de reconocimiento de voz con tiempo máximo de espera.
            try:
                r = subprocess.run(["termux-speech-to-text"], capture_output=True,
                                   text=True, timeout=25)
                # Muestra el error reportado por el proceso y espera antes de reintentar.
                if r.returncode != 0:
                    detalle = r.stderr.strip() or f"código de salida {r.returncode}"
                    print(f"Error de Termux:API: {detalle}")
                    time.sleep(1.0)
                    continue
                # Quita espacios del texto que Termux:API imprimió.
                texto = r.stdout.strip()
                # Envía solo frases no vacías y descarta resultados si se pausó entretanto.
                if texto and not self.en_pausa:
                    self.q_texto.put(texto)
            except subprocess.TimeoutExpired:
                # Si el servicio no devuelve nada a tiempo, vuelve a solicitar reconocimiento.
                continue  # nadie habló; se vuelve a escuchar
            except OSError as e:
                # Informa fallos al iniciar el comando y espera antes de volver a intentarlo.
                print(f"No se pudo ejecutar termux-speech-to-text: {e}")
                time.sleep(1.0)


# ------------------------------ interfaz ------------------------------
def dibujar(m, K):
    """Redibuja el estado del motor, la letra actual y la lista del cantante."""
    # Limpia la salida para mostrar una pantalla actualizada.
    K.limpiar_pantalla()
    # Reutiliza el ancho elegido en la configuración de karaoke.py.
    ancho = K.CARACTERES_POR_LINEA
    # Muestra el estado general y el mensaje más reciente del motor.
    print("=" * 60)
    print(f" MODO AUTOMÁTICO   [{m.estado}]   {m.mensaje}")
    print("=" * 60)
    # Cuando hay canción identificada, muestra la línea actual y su contexto.
    if m.estado in ("SIGUIENDO", "TERMINO") and m.c:
        # Obtiene las líneas para no repetir la búsqueda al dibujar.
        l = m.c["lineas"]
        print(f"\n ♪ {m.c['nombre']}   (línea {m.idx + 1}/{len(l)})")
        # Muestra el final de la línea anterior, si existe.
        if m.idx > 0:
            print("\n  " + l[m.idx - 1][:ancho + 10])
        print("\n>>>")
        # Ajusta la línea actual al ancho de pantalla y la destaca en mayúsculas.
        import textwrap
        for p in textwrap.wrap(l[m.idx], ancho) or [""]:
            print("    " + p.upper())
        # Da una vista previa de la próxima línea cuando queda alguna.
        if m.idx + 1 < len(l):
            print("\n  siguiente: " + l[m.idx + 1][:ancho + 10])
        # Indica que ya se llegó a la última línea de la canción.
        if m.estado == "TERMINO":
            print("\n  ✔ Fin de la canción. Escuchando la siguiente…")
    # Muestra las frases guardadas mientras se arma el borrador de una canción nueva.
    elif m.estado == "NUEVA":
        print(f"\n Canción nueva ({len(m.temp_lineas)} líneas transcritas):\n")
        # Limita la vista a las últimas seis frases.
        for x in m.temp_lineas[-6:]:
            print("   " + x)
    # Aclara que el texto no se procesa en estado de pausa.
    elif m.estado == "PAUSA":
        print("\n (ignorando sonido; Ctrl+C y 's' para seguir)")
    else:
        # Mensaje inicial mientras se buscan palabras de una canción conocida.
        print("\n Escuchando… cante o diga unas palabras de la canción.")
    # Si hay lista de canciones, muestra cuál sigue o si ya terminó.
    if m.prog:
        sig = m.prog_siguiente()
        if sig:
            print(f"\n Programa {m.prog_pos}/{len(m.prog)} — siguiente: {sig[1]}"
                  + ("" if sig[0] else "  [NO ESTÁ EN LA BD]"))
        else:
            print(f"\n Programa {len(m.prog)}/{len(m.prog)} — terminado")
    # Muestra parte de la frase reconocida más recientemente.
    if m.ultimo_texto:
        print(f"\n oído: «{m.ultimo_texto[:70]}»")
    # Recuerda cómo abrir el menú de controles durante la escucha.
    print("\n Ctrl+C = menú de control")


def menu_control(m, K):
    """Devuelve 'fin' para terminar el modo automático."""
    # Presenta las acciones que se pueden usar desde el control.
    print("\n[Enter] volver  [f] finalizar modo  [c] continuar línea  [i] igual (mantener línea)  "
          "[r] repetir canción\n[g] ignorar  [s] seguir  [b] buscar otra canción  "
          "[n] guardar canción nueva  [d] descartar canción nueva\n"
          "[p] cantar la siguiente del programa (sin esperar a oírla)")
    # Ctrl+C dentro del propio menú solo lo cierra y vuelve a escuchar.
    try:
        op = input("control> ").strip().lower()
    except KeyboardInterrupt:
        return None
    # Cada opción actualiza el motor o termina el modo automático.
    if op == "f":
        return "fin"
    elif op == "c":
        m.avanzar()
    elif op == "i":
        pass
    elif op == "r":
        m.repetir()
    elif op == "g":
        m.pausar()
    elif op == "s":
        m.seguir()
    elif op == "b":
        m.buscar_otra()
    elif op == "n":
        m.nueva_lista = True
    elif op == "d":
        m.descartar_nueva()
    elif op == "p":
        m.cargar_programada(time.time())
    return None


def guardar_nueva(m, K):
    """Revisión de la canción nueva: corregir, nombrar y pasar a las tablas permanentes."""
    # Copia las líneas para editar el borrador sin cambiar la lista durante la iteración.
    lineas = list(m.temp_lineas)
    # Si no hay texto, elimina el borrador vacío y vuelve.
    if not lineas:
        m.descartar_nueva()
        return
    # Mantiene el menú de revisión abierto hasta guardar, descartar o posponer.
    while True:
        # Limpia y vuelve a dibujar el borrador con su numeración.
        K.limpiar_pantalla()
        print("CANCIÓN NUEVA DETECTADA (borrador en tablas temporales)\n")
        for i, l in enumerate(lineas, 1):
            print(f"{i:>3}. {l}")
        print("\n(g) guardar  (l) corregir línea  (e) eliminar línea  (d) descartar  (Enter) decidir después")
        # Lee la acción que se quiere hacer con las líneas transcritas.
        op = input(">> ").strip().lower()
        # g pide un título y mueve la canción del borrador a las tablas definitivas.
        if op == "g":
            # Propone como título las primeras 40 letras de la primera línea.
            sug = lineas[0][:40]
            # Permite aceptar el título sugerido o escribir uno distinto.
            nombre = input(f"Nombre de la canción [{sug}]: ").strip() or sug
            # Guarda nombre y letra con la función compartida de la base de datos.
            cod = K.agregar_cancion(m.con, nombre, lineas)
            print(f"Guardada con código {cod}.")
            # Elimina las filas temporales, recarga el catálogo y espera confirmación.
            m.descartar_nueva()
            m.recargar()
            K.pausa()
            return
        # l permite reemplazar el texto de una línea concreta.
        elif op == "l":
            n = input("Número de línea: ").strip()
            if n.isdigit() and 1 <= int(n) <= len(lineas):
                lineas[int(n) - 1] = input("Texto correcto: ").strip() or lineas[int(n) - 1]
        # e elimina una línea que no deba formar parte de la canción.
        elif op == "e":
            n = input("Número de línea: ").strip()
            if n.isdigit() and 1 <= int(n) <= len(lineas):
                lineas.pop(int(n) - 1)
        # d pide confirmación antes de borrar definitivamente el borrador.
        elif op == "d":
            if K.preguntar_si_no("¿Descartar este borrador?"):
                m.descartar_nueva()
                return
        else:
            # En otra opción (incluido Enter), conserva los cambios y pospone la revisión.
            m.set_temp(lineas)
            m.nueva_lista = False
            m.ultimo_habla = time.time()
            return


def modo_automatico(con, K):
    """Elige una fuente de texto, ejecuta el motor y atiende controles del usuario."""
    # Limpia la pantalla y presenta las fuentes disponibles.
    K.limpiar_pantalla()
    print("MODO AUTOMÁTICO")
    # m usa Whisper en PC, a usa Termux:API y t lee un archivo de prueba.
    op = input("(m) micrófono PC (Whisper)  |  (a) micrófono Android (Termux)  |  "
               "(t) simulación desde archivo de texto  |  Enter = volver  >> ").strip().lower()
    # Construye la fuente seleccionada y muestra errores de configuración esperados.
    try:
        # La fuente PC captura el audio y lo transcribe con Whisper.
        if op == "m":
            fuente = FuenteMicrofono()
        # La fuente Android solicita frases al reconocedor del teléfono.
        elif op == "a":
            fuente = FuenteTermux()
        # La fuente de prueba reproduce frases de un archivo local.
        elif op == "t":
            ruta = input(
                "Ruta del archivo con una frase por línea [prueba.txt; Enter para usarlo]: "
            ).strip().strip('"')
            if not ruta:
                ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prueba.txt")
            elif not os.path.isabs(ruta) and not os.path.exists(ruta):
                ruta_programa = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)
                if os.path.exists(ruta_programa):
                    ruta = ruta_programa
            # No intenta abrir un archivo inexistente.
            if not os.path.exists(ruta):
                print("No se encontró ese archivo. Escribe prueba.txt o una ruta completa; "
                      "las frases deben estar dentro del archivo, una por línea.")
                K.pausa()
                return
            # Permite cambiar la pausa entre frases o aceptar el valor predeterminado.
            pausa = input("Segundos entre frases [2.5]: ").strip()
            fuente = FuenteSimulada(ruta, float(pausa) if pausa else 2.5)
        else:
            # Enter o una tecla no válida vuelve al menú anterior.
            return
    except RuntimeError as e:
        # Muestra los errores previsibles de dependencias o configuración de fuente.
        print(e)
        K.pausa()
        return

    # Crea el motor que compara los textos con el catálogo de canciones.
    m = Motor(con, K)
    # Empieza a producir texto desde la fuente seleccionada.
    fuente.iniciar()
    # Este reloj se usa para cerrar la simulación un momento después de su última frase.
    fin_sim = None
    # Muestra la pantalla inicial antes de entrar al ciclo de escucha.
    dibujar(m, K)
    # El bloque finally cerrará la fuente incluso si el bucle termina con una excepción.
    try:
        while True:
            # Cada vuelta recoge frases nuevas, predice avances y actualiza la pantalla.
            try:
                cambio = False
                # Extrae el primer texto disponible sin bloquear.
                t = fuente.siguiente_texto()
                # Procesa todos los textos que estén en la cola en este momento.
                while t is not None:
                    m.procesar(t, time.time())
                    cambio = True
                    t = fuente.siguiente_texto()
                # Deja avanzar por tiempo estimado si ya hay velocidad calculada.
                if m.tick(time.time()):
                    cambio = True
                # Cuando termina una canción nueva, pausa la fuente para revisarla.
                if m.nueva_lista:
                    fuente.pausar(True)
                    guardar_nueva(m, K)
                    # Restaura la pausa según el estado del motor tras guardar o posponer.
                    fuente.pausar(m.estado == "PAUSA")
                    cambio = True
                # Solo redibuja si algo cambió en el estado o llegó texto.
                if cambio:
                    dibujar(m, K)
                # Una simulación termina cuando ya entregó todo el archivo.
                if isinstance(fuente, FuenteSimulada) and fuente.terminada and fuente.q.empty():
                    fin_sim = fin_sim or time.time()
                    # Espera brevemente para que se muestre el último resultado.
                    if time.time() - fin_sim > 1.5:
                        break
                # Evita que el bucle use toda la CPU si no hay eventos nuevos.
                time.sleep(0.2)
            except KeyboardInterrupt:
                # Ctrl+C abre el menú de control en lugar de cerrar la app de inmediato.
                if menu_control(m, K) == "fin":
                    break
                # Aplica a la fuente el estado de pausa y refresca la pantalla.
                fuente.pausar(m.estado == "PAUSA")
                dibujar(m, K)
    finally:
        # Detiene el micrófono o hilo de escucha al salir del ciclo.
        fuente.detener()
    # Ofrece revisar el borrador si el modo finalizó mientras aún quedaba texto nuevo.
    if m.estado == "NUEVA" and m.temp_lineas:
        guardar_nueva(m, K)
    # Informa que terminó el modo automático y espera antes de volver.
    print("\nModo automático finalizado.")
    K.pausa()