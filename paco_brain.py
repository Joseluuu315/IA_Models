"""
brain.py — El cerebro de Paco.

Módulos:
  - Tokenizador y normalizador de texto
  - Detector de intención (bag-of-words + similitud coseno)
  - Memoria conversacional
  - Motor de aprendizaje: Paco aprende de cada conversación
  - Calculadora y analizador de expresiones
  - Generador de respuestas con personalidad
"""

import re
import math
import json
import time
import random
import hashlib
from pathlib import Path
from collections import defaultdict, Counter


# ══════════════════════════════════════════════════════════════════
# TOKENIZADOR
# ══════════════════════════════════════════════════════════════════

STOPWORDS_ES = {
    "el","la","los","las","un","una","unos","unas","de","del","al","a","en",
    "que","y","o","pero","si","no","con","por","para","es","son","fue","ser",
    "esto","eso","aquí","allí","me","te","se","le","nos","les","mi","tu","su",
    "yo","tú","él","ella","nosotros","vosotros","ellos","como","más","muy",
    "ya","también","entonces","cuando","donde","hay","tiene","hacer","qué",
    "cómo","cuándo","dónde","quién","cuál","pues","bien","así","aunque",
    "porque","este","esta","ese","esa","lo","le","algo","alguien","todo",
    "puedo","puede","quiero","quiere","saber","decir","ver","ir","hola","hey",
}

def tokenizar(texto: str) -> list[str]:
    texto = texto.lower().strip()
    texto = re.sub(r"[áàä]","a", texto)
    texto = re.sub(r"[éèë]","e", texto)
    texto = re.sub(r"[íìï]","i", texto)
    texto = re.sub(r"[óòö]","o", texto)
    texto = re.sub(r"[úùü]","u", texto)
    texto = re.sub(r"ñ","n", texto)
    tokens = re.findall(r"[a-z0-9]+", texto)
    return [t for t in tokens if len(t) > 1]

def tokens_significativos(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS_ES]


# ══════════════════════════════════════════════════════════════════
# VECTORIZADOR  (TF bag-of-words)
# ══════════════════════════════════════════════════════════════════

def vectorizar(tokens: list[str], vocabulario: list[str]) -> list[float]:
    freq = Counter(tokens)
    return [freq.get(w, 0) for w in vocabulario]

def similitud_coseno(a: list[float], b: list[float]) -> float:
    dot  = sum(x*y for x,y in zip(a,b))
    na   = math.sqrt(sum(x*x for x in a))
    nb   = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ══════════════════════════════════════════════════════════════════
# CALCULADORA
# ══════════════════════════════════════════════════════════════════

def calcular(expresion: str) -> str | None:
    """
    Evalúa expresiones matemáticas extraídas de texto natural.
    Soporta: +, -, *, /, **, %, palabras clave en español.
    """
    expr = expresion.lower().strip()
    # Normalizar acentos
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        expr = expr.replace(src, dst)

    # Sustituir palabras por operadores
    expr = re.sub(r"\belevado\s*al?\s*cuadrado\b", "**2", expr)
    expr = re.sub(r"\belevado\s*al?\s*cubo\b",     "**3", expr)
    expr = re.sub(r"\belevado\s*a\s*la\s*(\d+)\b", r"**\1", expr)
    expr = re.sub(r"\belevado\s*a\s*(\d+)\b",      r"**\1", expr)
    expr = re.sub(r"\b(raiz|raiz cuadrada)\b",      "sqrt", expr)
    expr = re.sub(r"\b(por|multiplicado por|x)\b",  "*",    expr)
    expr = re.sub(r"\b(entre|dividido entre|dividido por|sobre)\b", "/", expr)
    expr = re.sub(r"\b(mas|sumado)\b",              "+",    expr)
    expr = re.sub(r"\b(menos|restado)\b",           "-",    expr)
    expr = re.sub(r"\^", "**", expr)
    expr = re.sub(r"÷", "/", expr)

    # Manejar porcentajes: "15% de 200" → "200 * 0.15"
    pct = re.match(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", expr.strip())
    if pct:
        a, b = float(pct.group(1)), float(pct.group(2))
        resultado = a / 100 * b
        return str(int(resultado)) if resultado == int(resultado) else str(round(resultado, 6))

    # Manejar sqrt(n) y "raiz de N"
    sqrt_m = re.search(r"(?:sqrt|raiz(?:\s+cuadrada)?(?:\s+de)?)\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", expr)
    if sqrt_m:
        n = float(sqrt_m.group(1))
        r = math.sqrt(n)
        return str(int(r)) if r == int(r) else str(round(r, 6))

    # Extraer la expresión matemática pura (números + operadores)
    # Buscar bloques contiguos de dígitos y operadores
    expr_clean = re.sub(r'[^0-9+\-*/().\s%]', " ", expr)
    expr_clean = re.sub(r"\s+", " ", expr_clean).strip()

    # Buscar sub-expresión que tenga al menos un operador entre números
    candidates = re.findall(r"\d[\d\s+\-*/().%]*\d", expr_clean)
    if not candidates:
        # Intentar número suelto con operador al lado
        candidates = re.findall(r"[\d+\-*/().%]+", expr_clean)

    for cand in sorted(candidates, key=len, reverse=True):
        cand = cand.strip()
        if not re.search(r"[+\-*/]", cand):
            continue  # sin operador, no es expresión
        try:
            resultado = eval(cand, {"__builtins__": {}})
            if isinstance(resultado, float) and resultado == int(resultado):
                return str(int(resultado))
            return str(round(resultado, 6))
        except Exception:
            continue
    return None


def analizar_datos(texto: str) -> str | None:
    """Detecta listas de números y hace estadísticas básicas."""
    numeros = re.findall(r"-?\d+(?:\.\d+)?", texto)
    if len(numeros) < 2:
        return None
    nums = [float(n) for n in numeros]
    n   = len(nums)
    media = sum(nums)/n
    nums_ord = sorted(nums)
    mediana = nums_ord[n//2] if n%2 else (nums_ord[n//2-1]+nums_ord[n//2])/2
    varianza = sum((x-media)**2 for x in nums)/n
    desv = math.sqrt(varianza)
    return (
        f"He analizado {n} valores:\n"
        f"  • Suma: {sum(nums)}\n"
        f"  • Media: {round(media,4)}\n"
        f"  • Mediana: {mediana}\n"
        f"  • Mínimo: {min(nums)}  Máximo: {max(nums)}\n"
        f"  • Desviación estándar: {round(desv,4)}"
    )


# ══════════════════════════════════════════════════════════════════
# BASE DE CONOCIMIENTO Y APRENDIZAJE
# ══════════════════════════════════════════════════════════════════

RUTA_MEMORIA    = Path("paco_memoria.json")
RUTA_APRENDIDO  = Path("paco_aprendido.json")

# Conocimiento base de Paco (intención → [patrones], [respuestas])
CONOCIMIENTO_BASE: dict[str, dict] = {

    # ── Saludos ──────────────────────────────────────────────────
    "saludo": {
        "patrones": [
            ["hola","hey","buenas","saludos","ey","epa","que tal",
             "como estas","como te va","buenos dias","buenas tardes","buenas noches"],
        ],
        "respuestas": [
            "¡Hola! Soy Paco, tu IA. ¿En qué te ayudo?",
            "¡Buenas! Aquí Paco, listo para lo que necesites.",
            "¡Qué tal! Soy Paco. Pregúntame lo que quieras.",
            "¡Ei! Paco al habla. ¿Qué necesitas?",
        ],
    },

    # ── Identidad ────────────────────────────────────────────────
    "identidad": {
        "patrones": [
            ["quien eres","como te llamas","eres una ia","eres un bot",
             "que eres","quien soy hablando","presentate","nombre",
             "eres inteligente","eres humano","robot","maquina"],
        ],
        "respuestas": [
            "Soy Paco, una IA construida desde cero sin modelos preentrenados. Aprendo de cada conversación.",
            "Me llamo Paco. Soy una inteligencia artificial hecha a mano, sin copiar a nadie.",
            "Paco, servidor. Una IA que piensa con su propia lógica, no prestada.",
        ],
    },

    # ── Despedida ────────────────────────────────────────────────
    "despedida": {
        "patrones": [
            ["adios","hasta luego","bye","chao","hasta pronto","nos vemos",
             "me voy","hasta manana","ciao","salir","exit"],
        ],
        "respuestas": [
            "¡Hasta luego! Ha sido un placer.",
            "¡Cuídate! Aquí estaré cuando me necesites.",
            "¡Adiós! Recuerda que Paco nunca olvida lo que le enseñas.",
        ],
    },

    # ── Agradecimiento ───────────────────────────────────────────
    "gracias": {
        "patrones": [
            ["gracias","muchas gracias","te lo agradezco","genial","perfecto",
             "muy bien","excelente","chevere","crack","eres lo mejor","bien hecho"],
        ],
        "respuestas": [
            "¡De nada! Para eso estoy.",
            "¡A mandar! ¿Algo más?",
            "Faltaría más. ¿Qué más necesitas?",
            "Con gusto. Soy Paco, aquí para ayudar.",
        ],
    },

    # ── Ayuda ────────────────────────────────────────────────────
    "ayuda": {
        "patrones": [
            ["ayuda","help","que puedes hacer","que sabes","capacidades",
             "para que sirves","que haces","funciones","comandos",
             "como funciona","que puedo pedirte"],
        ],
        "respuestas": [
            (
                "Puedo hacer varias cosas:\n"
                "  🧮 Calcular: '¿cuánto es 234 * 17?'\n"
                "  📊 Analizar datos: 'analiza estos números: 4, 8, 15, 16, 23, 42'\n"
                "  🧠 Responder preguntas generales\n"
                "  💬 Conversar y recordar lo que me dices\n"
                "  📚 Aprender: dime 'aprende que X significa Y'\n"
                "  🎲 Generar números aleatorios, fechas, etc.\n"
                "¿Por dónde empezamos?"
            ),
        ],
    },

    # ── Estado de ánimo ──────────────────────────────────────────
    "estado_animo": {
        "patrones": [
            ["como estas","que tal estas","bien","mal","triste","feliz",
             "aburrido","cansado","emocionado","nervioso","como te sientes"],
        ],
        "respuestas": [
            "Yo siempre estoy en modo ON. Los bits no se cansan. ¿Y tú cómo estás?",
            "Funcionando al 100%, gracias por preguntar. ¿Qué hay de nuevo?",
            "¡Perfecto! Aunque no tengo sentimientos, tengo lógica, y eso vale más.",
        ],
    },

    # ── Matemáticas (delegado a calculadora) ─────────────────────
    "calculo": {
        "patrones": [
            ["cuanto es","calcula","resultado","suma","resta","multiplica",
             "divide","potencia","raiz","porcentaje","cuantos","opera",
             "cuanto da","resolver","ecuacion","formula"],
        ],
        "respuestas": [],  # manejado por la calculadora
    },

    # ── Análisis de datos ────────────────────────────────────────
    "analisis": {
        "patrones": [
            ["analiza","estadistica","media","promedio","mediana","desviacion",
             "numeros","datos","valores","lista","conjunto"],
        ],
        "respuestas": [],  # manejado por el analizador
    },

    # ── Hora / fecha ─────────────────────────────────────────────
    "tiempo": {
        "patrones": [
            ["que hora es","hora actual","que dia es","fecha","hoy","dia de hoy",
             "cuando estamos","mes","ano","anio","dia"],
        ],
        "respuestas": [],  # manejado dinámicamente
    },

    # ── Número aleatorio ─────────────────────────────────────────
    "aleatorio": {
        "patrones": [
            ["numero aleatorio","numero random","elige un numero","tira un dado",
             "genera un numero","al azar","entre","random"],
        ],
        "respuestas": [],  # manejado dinámicamente
    },

    # ── Bromas ───────────────────────────────────────────────────
    "broma": {
        "patrones": [
            ["cuentame un chiste","chiste","broma","hazme reir","algo gracioso",
             "joke","divertido","humor"],
        ],
        "respuestas": [
            "¿Por qué los programadores odian la naturaleza? Porque tiene demasiados bugs. 🐛",
            "Un bit le dice a otro: '¿Te has enterado? ¡Nos van a quitar el cero!'. El otro responde: '¿En serio? ¡Eso es de locos!'",
            "¿Qué le dijo el 0 al 8? '¡Qué cinturón más chulo!'",
            "¿Cómo se despiden los matemáticos? ¡Hasta el infinito y más allá!",
            "Un programador va al supermercado. Su pareja le dice: 'Compra una barra de pan y si hay huevos, trae una docena'. Vuelve con doce barras de pan.",
        ],
    },

    # ── Curiosidades ─────────────────────────────────────────────
    "curiosidad": {
        "patrones": [
            ["cuéntame algo","sabias que","dato curioso","curiosidad","fun fact",
             "algo interesante","sorprendeme","informacion","cuéntame"],
        ],
        "respuestas": [
            "¿Sabías que una abeja reina puede poner hasta 2.000 huevos al día? Y yo que me quejo si proceso 100 mensajes...",
            "El número 0 no existía en el sistema numérico romano. Imagina intentar programar sin el 0.",
            "El primer 'bug' informático real fue una polilla atrapada en un relé de una computadora en 1947.",
            "El cerebro humano procesa imágenes 60.000 veces más rápido que texto. ¡Y aún así me lees!",
            "Ada Lovelace escribió el primer algoritmo para una máquina en 1843, antes de que existieran las computadoras.",
            "Hay más combinaciones posibles en una partida de ajedrez que átomos en el universo observable.",
        ],
    },

    # ── No entendido ─────────────────────────────────────────────
    "desconocido": {
        "patrones": [],
        "respuestas": [
            "Hmm, eso aún no lo sé. Puedes enseñármelo con: 'aprende que [pregunta] significa [respuesta]'",
            "No tengo respuesta para eso todavía. ¿Me lo explicas tú? Usa: 'aprende que X es Y'",
            "No lo sé aún, pero puedo aprenderlo. Dime: 'aprende que [tema] es [explicación]'",
            "Interesante pregunta. Aún no la tengo en mi base. ¿Me enseñas? 'aprende que X significa Y'",
        ],
    },
}


# ══════════════════════════════════════════════════════════════════
# CEREBRO PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class Paco:
    def __init__(self):
        self.memoria_conv: list[dict] = []       # historial de conversación
        self.conocimiento  = CONOCIMIENTO_BASE.copy()
        self.aprendido: dict[str, str] = {}      # {pregunta_hash: respuesta}
        self.aprendido_raw: dict[str, str] = {}  # {pregunta_texto: respuesta}
        self.vocabulario: list[str] = []
        self.patron_vectors: list[tuple[str, list[float]]] = []
        self.umbral_confianza = 0.15

        self._cargar_persistencia()
        self._construir_vocabulario()

    # ── Persistencia ─────────────────────────────────────────────

    def _cargar_persistencia(self):
        if RUTA_APRENDIDO.exists():
            data = json.loads(RUTA_APRENDIDO.read_text(encoding="utf-8"))
            self.aprendido     = data.get("hashes", {})
            self.aprendido_raw = data.get("raw", {})

    def _guardar_persistencia(self):
        RUTA_APRENDIDO.write_text(
            json.dumps({"hashes": self.aprendido, "raw": self.aprendido_raw},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── Vocabulario y vectores ────────────────────────────────────

    def _construir_vocabulario(self):
        todas_palabras: set[str] = set()
        for intencion, data in self.conocimiento.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    todas_palabras.update(tokenizar(frase))
        for frase in self.aprendido_raw:
            todas_palabras.update(tokenizar(frase))
        self.vocabulario = sorted(todas_palabras)
        self._construir_vectors()

    def _construir_vectors(self):
        self.patron_vectors = []
        for intencion, data in self.conocimiento.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    tokens = tokenizar(frase)
                    vec = vectorizar(tokens, self.vocabulario)
                    self.patron_vectors.append((intencion, vec))
        # Agregar frases aprendidas
        for frase_raw in self.aprendido_raw:
            tokens = tokenizar(frase_raw)
            vec = vectorizar(tokens, self.vocabulario)
            self.patron_vectors.append(("__aprendido__:" + frase_raw, vec))

    # ── Detección de intención ────────────────────────────────────

    def detectar_intencion(self, texto: str) -> tuple[str, float]:
        tokens   = tokenizar(texto)
        sig_tok  = tokens_significativos(tokens)
        vec_in   = vectorizar(sig_tok, self.vocabulario)

        mejor_int   = "desconocido"
        mejor_sim   = 0.0

        for intencion, vec_pat in self.patron_vectors:
            sim = similitud_coseno(vec_in, vec_pat)
            if sim > mejor_sim:
                mejor_sim = sim
                mejor_int = intencion

        # Fallback: coincidencia exacta de substrings para patrones cortos
        texto_norm = " ".join(tokens)
        for intencion, data in self.conocimiento.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    frase_tok = " ".join(tokenizar(frase))
                    if frase_tok and frase_tok in texto_norm:
                        if mejor_sim < 0.5:
                            return intencion, 0.9

        return mejor_int, mejor_sim

    # ── Procesamiento especial ────────────────────────────────────

    def _hora_fecha(self) -> str:
        t = time.localtime()
        dias   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses  = ["enero","febrero","marzo","abril","mayo","junio",
                  "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        dia_sem = dias[t.tm_wday]
        return (
            f"Ahora mismo son las {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}. "
            f"Hoy es {dia_sem}, {t.tm_mday} de {meses[t.tm_mon-1]} de {t.tm_year}."
        )

    def _aleatorio(self, texto: str) -> str:
        nums = re.findall(r"\d+", texto)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a > b: a, b = b, a
            return f"Número aleatorio entre {a} y {b}: **{random.randint(a,b)}**"
        if "dado" in texto.lower() or "dado" in texto:
            return f"🎲 Tiré el dado: **{random.randint(1,6)}**"
        return f"Número aleatorio: **{random.randint(1, 100)}**"

    # ── Aprendizaje ───────────────────────────────────────────────

    def intentar_aprender(self, texto: str) -> str | None:
        """Detecta comandos de aprendizaje explícito."""
        patrones_aprender = [
            r"aprende\s+que\s+(.+?)\s+(?:significa|es|son|equivale a|quiere decir)\s+(.+)",
            r"recuerda\s+que\s+(.+?)\s+(?:es|son|significa)\s+(.+)",
            r"guarda\s+que\s+(.+?)\s+(?:es|son)\s+(.+)",
            r"ensenate\s+que\s+(.+?)\s+(?:es|significa)\s+(.+)",
        ]
        texto_norm = texto.lower().strip()
        texto_norm = re.sub(r"[áàä]","a", texto_norm)
        texto_norm = re.sub(r"[éèë]","e", texto_norm)
        texto_norm = re.sub(r"[íìï]","i", texto_norm)
        texto_norm = re.sub(r"[óòö]","o", texto_norm)
        texto_norm = re.sub(r"[úùü]","u", texto_norm)
        texto_norm = re.sub(r"ñ","n", texto_norm)

        for patron in patrones_aprender:
            m = re.search(patron, texto_norm)
            if m:
                clave   = m.group(1).strip()
                valor   = m.group(2).strip()
                h = hashlib.md5(clave.encode()).hexdigest()
                self.aprendido[h]       = valor
                self.aprendido_raw[clave] = valor
                self._construir_vocabulario()
                self._guardar_persistencia()
                return (
                    f"✅ ¡Aprendido! Ahora sé que **{clave}** es **{valor}**.\n"
                    f"Lo recordaré en futuras conversaciones."
                )
        return None

    def buscar_aprendido(self, texto: str) -> str | None:
        """Busca en lo que Paco ha aprendido."""
        tokens_in = tokens_significativos(tokenizar(texto))
        mejor_sim = 0.0
        mejor_resp = None
        for frase_raw, respuesta in self.aprendido_raw.items():
            tokens_fr = tokens_significativos(tokenizar(frase_raw))
            # Coincidencia por subconjunto
            comunes = set(tokens_in) & set(tokens_fr)
            if not tokens_fr:
                continue
            sim = len(comunes) / max(len(tokens_fr), len(tokens_in), 1)
            if sim > mejor_sim and sim >= 0.4:
                mejor_sim = sim
                mejor_resp = respuesta
        return mejor_resp

    # ── Memoria conversacional ────────────────────────────────────

    def recordar_contexto(self) -> dict | None:
        """Devuelve el último turno del usuario."""
        for turno in reversed(self.memoria_conv):
            if turno["rol"] == "usuario":
                return turno
        return None

    # ── Respuesta principal ───────────────────────────────────────

    def responder(self, texto_usuario: str) -> str:
        texto = texto_usuario.strip()
        if not texto:
            return "No te he oído bien. ¿Puedes repetirlo?"

        # Guardar en memoria
        self.memoria_conv.append({"rol": "usuario", "texto": texto, "ts": time.time()})

        # 1. ¿Aprendizaje explícito?
        resp_aprendizaje = self.intentar_aprender(texto)
        if resp_aprendizaje:
            self.memoria_conv.append({"rol": "paco", "texto": resp_aprendizaje, "ts": time.time()})
            return resp_aprendizaje

        # 2. ¿Calculadora?
        resultado_calc = calcular(texto)
        if resultado_calc:
            # Activar si hay palabras clave matemáticas O si el texto contiene operadores + números
            tokens_texto = tokenizar(texto)
            palabras_calc = {"cuanto","calcula","resultado","suma","resta","multiplica",
                             "divide","cuantos","opera","cuanto da","cuantos son","cuanto es"}
            tiene_op_kw = any(t in palabras_calc for t in tokens_texto)
            tiene_simbolo_op = bool(re.search(r"\d\s*[+\-*/^]\s*\d", texto))
            tiene_num = bool(re.search(r"\d", texto))
            if tiene_op_kw or tiene_simbolo_op or (tiene_num and len(tokens_texto) <= 6):
                resp = f"El resultado es: **{resultado_calc}** 🧮"
                self.memoria_conv.append({"rol": "paco", "texto": resp, "ts": time.time()})
                return resp

        # 3. ¿Análisis de datos?
        if any(w in texto.lower() for w in ["analiza","estadistica","media","promedio","datos","lista","valores"]):
            resultado_anal = analizar_datos(texto)
            if resultado_anal:
                self.memoria_conv.append({"rol": "paco", "texto": resultado_anal, "ts": time.time()})
                return resultado_anal

        # 4. ¿Buscar en lo aprendido?
        resp_aprendido = self.buscar_aprendido(texto)
        if resp_aprendido:
            resp = f"Esto lo aprendí antes: {resp_aprendido}"
            self.memoria_conv.append({"rol": "paco", "texto": resp, "ts": time.time()})
            return resp

        # 5. Detectar intención
        intencion, confianza = self.detectar_intencion(texto)

        # 6. Intenciones dinámicas
        if intencion == "tiempo":
            resp = self._hora_fecha()
            self.memoria_conv.append({"rol": "paco", "texto": resp, "ts": time.time()})
            return resp

        if intencion == "aleatorio":
            resp = self._aleatorio(texto)
            self.memoria_conv.append({"rol": "paco", "texto": resp, "ts": time.time()})
            return resp

        # 7. Respuesta desde base de conocimiento
        if intencion in self.conocimiento and confianza >= self.umbral_confianza:
            respuestas = self.conocimiento[intencion]["respuestas"]
            if respuestas:
                resp = random.choice(respuestas)
                self.memoria_conv.append({"rol": "paco", "texto": resp, "ts": time.time()})
                return resp

        # 8. Fallback inteligente con contexto
        ctx = self.recordar_contexto()
        resp_fallback = random.choice(self.conocimiento["desconocido"]["respuestas"])
        self.memoria_conv.append({"rol": "paco", "texto": resp_fallback, "ts": time.time()})
        return resp_fallback

    def stats(self) -> dict:
        return {
            "mensajes_totales": len(self.memoria_conv),
            "cosas_aprendidas": len(self.aprendido_raw),
            "vocabulario": len(self.vocabulario),
            "intenciones": len(self.conocimiento),
        }
