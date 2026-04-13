"""
pako_fuzzy.py — Motor de comprensión semántica y fuzzy matching de PAKO.

Implementa:
  - Distancia de Levenshtein (edición mínima)
  - Distancia Jaro-Winkler (similitud de strings)
  - Corrección fonética (metáfono simplificado en español)
  - N-gramas de caracteres
  - Corrección de vocabulario conocido
  - Expansión de abreviaturas y contracciones comunes

El resultado: PAKO entiende "tomat" → "tomate", "autmatizcion" → "automatización",
"crrea" → "crea", "werflow" → "workflow", etc. EN SILENCIO, sin decirle al usuario.
"""

import re
import math
from typing import Optional


# ══════════════════════════════════════════════════════════════════
# VOCABULARIO CONOCIDO (dominio de la plataforma + español general)
# ══════════════════════════════════════════════════════════════════

VOCABULARIO_PLATAFORMA = {
    # Acciones generales
    "crear", "crear", "creame", "crea", "nuevo", "nueva", "hacer", "haz",
    "borrar", "eliminar", "borra", "elimina", "editar", "edita", "modificar",
    "mostrar", "muestra", "ver", "listar", "lista", "abrir", "abre",
    "guardar", "guarda", "exportar", "importar", "cargar",
    # Navegación
    "pagina", "página", "dashboard", "inicio", "home", "panel",
    "ajustes", "configuracion", "configuración", "perfil", "cuenta",
    "automatizaciones", "automatizacion", "flujo", "flujos", "workflow",
    "nodo", "nodos", "conexion", "conexiones", "trigger", "accion", "acción",
    # n8n / automatizaciones
    "disparador", "disparadores", "webhook", "schedule", "programar",
    "correo", "email", "notificacion", "notificación", "slack", "telegram",
    "http", "api", "base", "datos", "database", "archivo", "fichero",
    "condicion", "condición", "si", "entonces", "bucle", "loop", "repetir",
    "transformar", "filtrar", "fusionar", "dividir", "esperar", "delay",
    # IA / Pako
    "resumir", "resumen", "analizar", "análisis", "categorizar", "clasificar",
    "extraer", "detectar", "sentimiento", "traducir", "generar", "responder",
    "procesar", "entender", "interpretar",
    # Entidades comunes
    "usuario", "usuarios", "proyecto", "proyectos", "tarea", "tareas",
    "mensaje", "mensajes", "resultado", "resultados", "error", "errores",
    # Español cotidiano relacionado
    "tomate", "tomates", "producto", "productos", "nombre", "nombre",
    "precio", "fecha", "hora", "dia", "mes", "año",
}

# Abreviaturas y contracciones → expansión
ABREVIATURAS = {
    "auto":   "automatización",
    "autos":  "automatizaciones",
    "autom":  "automatización",
    "wf":     "workflow",
    "wflow":  "workflow",
    "cfg":    "configuración",
    "config": "configuración",
    "msg":    "mensaje",
    "msgs":   "mensajes",
    "notif":  "notificación",
    "notifs": "notificaciones",
    "bd":     "base de datos",
    "db":     "base de datos",
    "trig":   "trigger",
    "q":      "que",
    "xq":     "porque",
    "xk":     "porque",
    "tb":     "también",
    "tmb":    "también",
    "xa":     "para",
    "k":      "que",
    "d":      "de",
}


# ══════════════════════════════════════════════════════════════════
# LEVENSHTEIN
# ══════════════════════════════════════════════════════════════════

def levenshtein(s1: str, s2: str) -> int:
    """Distancia de edición mínima entre dos strings."""
    if s1 == s2:
        return 0
    n, m = len(s1), len(s2)
    if n == 0: return m
    if m == 0: return n

    # Optimización: si la diferencia de longitud es > umbral, descartamos antes
    if abs(n - m) > max(n, m) * 0.6:
        return abs(n - m) + 1

    # DP con una sola fila
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            curr[j] = min(curr[j-1] + 1, prev[j] + 1, prev[j-1] + cost)
        prev = curr
    return prev[m]


def similitud_levenshtein(s1: str, s2: str) -> float:
    """Similitud normalizada [0, 1] basada en Levenshtein."""
    dist = levenshtein(s1, s2)
    max_len = max(len(s1), len(s2), 1)
    return 1.0 - dist / max_len


# ══════════════════════════════════════════════════════════════════
# JARO-WINKLER
# ══════════════════════════════════════════════════════════════════

def jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    n1, n2 = len(s1), len(s2)
    if n1 == 0 or n2 == 0:
        return 0.0

    window = max(n1, n2) // 2 - 1
    if window < 0:
        window = 0

    matched1 = [False] * n1
    matched2 = [False] * n2
    matches = 0
    transpositions = 0

    for i in range(n1):
        start = max(0, i - window)
        end   = min(i + window + 1, n2)
        for j in range(start, end):
            if matched2[j] or s1[i] != s2[j]:
                continue
            matched1[i] = matched2[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(n1):
        if not matched1[i]:
            continue
        while not matched2[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (matches / n1 + matches / n2 + (matches - transpositions / 2) / matches) / 3


def jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    j = jaro(s1, s2)
    prefix = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return j + prefix * p * (1 - j)


# ══════════════════════════════════════════════════════════════════
# N-GRAMAS DE CARACTERES
# ══════════════════════════════════════════════════════════════════

def ngramas(s: str, n: int = 2) -> set:
    """Genera n-gramas de caracteres."""
    s = f"#{s}#"
    return {s[i:i+n] for i in range(len(s) - n + 1)}


def similitud_ngramas(s1: str, s2: str, n: int = 2) -> float:
    """Dice coefficient sobre n-gramas."""
    g1 = ngramas(s1, n)
    g2 = ngramas(s2, n)
    if not g1 or not g2:
        return 0.0
    interseccion = len(g1 & g2)
    return 2 * interseccion / (len(g1) + len(g2))


# ══════════════════════════════════════════════════════════════════
# SIMILITUD COMBINADA
# ══════════════════════════════════════════════════════════════════

def similitud_total(palabra: str, candidato: str) -> float:
    """
    Combina Levenshtein, Jaro-Winkler y bigramas para una similitud robusta.
    """
    if palabra == candidato:
        return 1.0

    p = palabra.lower()
    c = candidato.lower()

    # Penalizar si difieren mucho en longitud
    len_ratio = min(len(p), len(c)) / max(len(p), len(c), 1)
    if len_ratio < 0.4:
        return 0.0

    lev = similitud_levenshtein(p, c)
    jw  = jaro_winkler(p, c)
    bg  = similitud_ngramas(p, c, 2)

    # Boost si comparten prefijo
    prefix_boost = 0.0
    pref_len = min(len(p), len(c), 3)
    if pref_len > 0 and p[:pref_len] == c[:pref_len]:
        prefix_boost = 0.1

    combined = (lev * 0.35 + jw * 0.40 + bg * 0.25) + prefix_boost
    return min(combined, 1.0)


# ══════════════════════════════════════════════════════════════════
# CORRECTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoFuzzy:
    """
    Motor de comprensión tolerante a errores.
    Corrige silenciosamente palabras mal escritas usando el vocabulario
    conocido + vocabulario dinámico aprendido de la memoria.
    """

    # Umbral mínimo de similitud para considerar una corrección
    UMBRAL = 0.72

    def __init__(self):
        self._vocab_extra: set[str] = set()

    def enriquecer_vocabulario(self, palabras: list[str]) -> None:
        """Añade palabras del conocimiento de PAKO al vocabulario fuzzy."""
        for p in palabras:
            if len(p) > 3:
                self._vocab_extra.add(p.lower())

    def _vocabulario_completo(self) -> set[str]:
        return VOCABULARIO_PLATAFORMA | self._vocab_extra

    # Palabras que NUNCA se corrigen — evita falsos positivos críticos
    _NO_TOCAR = frozenset({
        # Saludos
        "hola","hey","adios","bye","chao","buenas","saludo","saludos",
        # Preguntas — crítico para no romper calculadora y búsquedas
        "busca","buscar","busco","busque",
        "cuanto","cuantos","cuanta","cuantas",
        "cuando","donde","quien","quienes","cual","cuales",
        "porque","para","sobre","entre","hasta","desde","segun",
        # Pronombres y conjunciones
        "que","como","si","no","ya","ok","bien","mal",
        "yo","tu","el","ella","nos","les","mis","sus","tus",
        "esto","eso","estos","esos","este","esta","ese","esa",
        # Verbos comunes que no se deben cambiar
        "hola","soy","eres","somos","tengo","tiene","tienes",
        "quiero","quiere","puedo","puede","hacer","haces",
        # Técnicos
        "api","sql","css","xml","json","http","git","npm",
        "pip","url","ide","sdk","jwt","csv","pdf","png",
    })

    def corregir_palabra(self, palabra: str) -> str:
        """
        Intenta corregir una palabra mal escrita.
        Retorna la palabra corregida o la original si no hay buena corrección.
        """
        p = palabra.lower().strip()

        # Lista de palabras protegidas — nunca se corrigen
        if p in self._NO_TOCAR:
            return palabra

        # Ya está en el vocabulario exacto
        if p in self._vocabulario_completo():
            return palabra

        # Abreviatura conocida
        if p in ABREVIATURAS:
            return ABREVIATURAS[p]

        # Palabras cortas (≤ 4): no corregir para evitar falsos positivos
        # "hola"→"hora", "como"→"code", etc son correcciones dañinas
        if len(p) <= 4:
            return palabra

        mejor_candidato = ""
        mejor_sim = 0.0

        for candidato in self._vocabulario_completo():
            # Optimización: saltar si la diferencia de longitud es demasiado grande
            if abs(len(p) - len(candidato)) > max(len(p), 2) * 0.65:
                continue
            sim = similitud_total(p, candidato)
            if sim > mejor_sim:
                mejor_sim = sim
                mejor_candidato = candidato

        if mejor_sim >= self.UMBRAL and mejor_candidato:
            return mejor_candidato

        return palabra

    def corregir_texto(self, texto: str) -> tuple[str, bool]:
        """
        Corrige silenciosamente un texto completo.
        Retorna (texto_corregido, hubo_correcciones).
        """
        # Expandir abreviaturas de chat primero
        for abrev, expansion in ABREVIATURAS.items():
            patron = r"(?<![a-záéíóúñ])" + re.escape(abrev) + r"(?![a-záéíóúñ])"
            texto = re.sub(patron, expansion, texto, flags=re.IGNORECASE)

        tokens = re.findall(r"[a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+|[^a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+", texto)
        corregido = []
        cambios = False

        for tok in tokens:
            if re.match(r"[a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+", tok, re.IGNORECASE):
                nuevo = self.corregir_palabra(tok)
                if nuevo.lower() != tok.lower():
                    cambios = True
                corregido.append(nuevo)
            else:
                corregido.append(tok)

        return "".join(corregido), cambios

    def similitud_consulta(self, consulta: str, referencia: str) -> float:
        """
        Calcula la similitud semántica entre una consulta y una referencia.
        Útil para la búsqueda en memoria con tolerancia a errores.
        """
        palabras_q = re.findall(r"[a-záéíóúñü]+", consulta.lower())
        palabras_r = re.findall(r"[a-záéíóúñü]+", referencia.lower())

        if not palabras_q or not palabras_r:
            return 0.0

        total_sim = 0.0
        for pq in palabras_q:
            if len(pq) <= 2:
                continue
            mejor = max(
                (similitud_total(pq, pr) for pr in palabras_r if len(pr) > 2),
                default=0.0
            )
            total_sim += mejor

        return total_sim / max(len([p for p in palabras_q if len(p) > 2]), 1)


# Instancia global
fuzzy = PakoFuzzy()
