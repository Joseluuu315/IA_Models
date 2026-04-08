"""
pako_brain.py — Cerebro principal de PAKO.

Motor híbrido:
  1. Memoria local (conocimiento aprendido)
  2. Agente web (si no sabe, busca en internet)
  3. Respuestas con personalidad y contexto
"""

import re
import math
import time
import random
import hashlib
from collections import Counter
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pako_memory import PakoMemory


# ══════════════════════════════════════════════════════════════════
# TOKENIZADOR Y NLP BÁSICO
# ══════════════════════════════════════════════════════════════════

STOPWORDS_ES = {
    "el","la","los","las","un","una","unos","unas","de","del","al","a","en",
    "que","y","o","pero","si","no","con","por","para","es","son","fue","ser",
    "esto","eso","aqui","alli","me","te","se","le","nos","les","mi","tu","su",
    "yo","el","ella","nosotros","vosotros","ellos","como","mas","muy",
    "ya","tambien","entonces","cuando","donde","hay","tiene","hacer","que",
    "como","cuando","donde","quien","cual","pues","bien","asi","aunque",
    "porque","este","esta","ese","esa","lo","le","algo","alguien","todo",
    "puedo","puede","quiero","quiere","saber","decir","ver","ir","hola","hey",
}

def tokenizar(texto: str) -> list[str]:
    texto = texto.lower().strip()
    for src, dst in [("á","a"),("à","a"),("ä","a"),("é","e"),("è","e"),("ë","e"),
                     ("í","i"),("ì","i"),("ï","i"),("ó","o"),("ò","o"),("ö","o"),
                     ("ú","u"),("ù","u"),("ü","u"),("ñ","n")]:
        texto = texto.replace(src, dst)
    tokens = re.findall(r"[a-z0-9]+", texto)
    return [t for t in tokens if len(t) > 1]

def tokens_significativos(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS_ES]

def vectorizar(tokens: list[str], vocabulario: list[str]) -> list[float]:
    freq = Counter(tokens)
    return [freq.get(w, 0) for w in vocabulario]

def similitud_coseno(a: list[float], b: list[float]) -> float:
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a))
    nb  = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ══════════════════════════════════════════════════════════════════
# CALCULADORA NATURAL
# ══════════════════════════════════════════════════════════════════

def calcular(expresion: str) -> Optional[str]:
    expr = expresion.lower().strip()
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        expr = expr.replace(src, dst)

    expr = re.sub(r"\belevado\s*al?\s*cuadrado\b", "**2", expr)
    expr = re.sub(r"\belevado\s*al?\s*cubo\b",     "**3", expr)
    expr = re.sub(r"\belevado\s*a\s*la\s*(\d+)\b", r"**\1", expr)
    expr = re.sub(r"\belevado\s*a\s*(\d+)\b",      r"**\1", expr)
    expr = re.sub(r"\b(raiz|raiz cuadrada)\b",      "sqrt",  expr)
    expr = re.sub(r"\b(por|multiplicado por)\b",    "*",     expr)
    expr = re.sub(r"\b(entre|dividido entre|dividido por|sobre)\b", "/", expr)
    expr = re.sub(r"\b(mas|sumado)\b",              "+",     expr)
    expr = re.sub(r"\b(menos|restado)\b",           "-",     expr)
    expr = re.sub(r"\^", "**", expr)
    expr = re.sub(r"÷", "/", expr)

    pct = re.match(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", expr.strip())
    if pct:
        a, b = float(pct.group(1)), float(pct.group(2))
        r = a / 100 * b
        return str(int(r)) if r == int(r) else str(round(r, 6))

    sqrt_m = re.search(r"(?:sqrt|raiz(?:\s+cuadrada)?(?:\s+de)?)\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", expr)
    if sqrt_m:
        n = float(sqrt_m.group(1))
        r = math.sqrt(n)
        return str(int(r)) if r == int(r) else str(round(r, 6))

    expr_clean = re.sub(r"[^0-9+\-*/().\s%]", " ", expr)
    expr_clean = re.sub(r"\s+", " ", expr_clean).strip()
    candidates = re.findall(r"\d[\d\s+\-*/().%]*\d", expr_clean)
    if not candidates:
        candidates = re.findall(r"[\d+\-*/().%]+", expr_clean)

    for cand in sorted(candidates, key=len, reverse=True):
        cand = cand.strip()
        if not re.search(r"[+\-*/]", cand):
            continue
        try:
            resultado = eval(cand, {"__builtins__": {}})
            if isinstance(resultado, float) and resultado == int(resultado):
                return str(int(resultado))
            return str(round(resultado, 6))
        except Exception:
            continue
    return None

def analizar_datos(texto: str) -> Optional[str]:
    numeros = re.findall(r"-?\d+(?:\.\d+)?", texto)
    if len(numeros) < 2:
        return None
    nums = [float(n) for n in numeros]
    n = len(nums)
    media = sum(nums)/n
    nums_ord = sorted(nums)
    mediana = nums_ord[n//2] if n%2 else (nums_ord[n//2-1]+nums_ord[n//2])/2
    varianza = sum((x-media)**2 for x in nums)/n
    desv = math.sqrt(varianza)
    return (
        f"He analizado {n} valores:\n"
        f"  • Suma: {round(sum(nums),4)}\n"
        f"  • Media: {round(media,4)}\n"
        f"  • Mediana: {mediana}\n"
        f"  • Mínimo: {min(nums)}  Máximo: {max(nums)}\n"
        f"  • Desviación estándar: {round(desv,4)}"
    )


# ══════════════════════════════════════════════════════════════════
# BASE DE INTENCIONES
# ══════════════════════════════════════════════════════════════════

INTENCIONES: dict[str, dict] = {
    "saludo": {
        "patrones": [["hola","hey","buenas","saludos","ey","que tal","como estas",
                       "como te va","buenos dias","buenas tardes","buenas noches"]],
        "respuestas": [
            "¡Hola! Soy PAKO, tu IA. ¿En qué te ayudo?",
            "¡Buenas! PAKO al habla, listo para lo que necesites.",
            "¡Qué tal! Pregúntame lo que quieras.",
        ],
    },
    "identidad": {
        "patrones": [["quien eres","como te llamas","eres una ia","que eres",
                       "presentate","nombre","eres inteligente","eres humano"]],
        "respuestas": [
            "Soy PAKO, una IA construida desde cero. Aprendo de ti, de internet y de tus repos de GitHub.",
            "Me llamo PAKO. Una inteligencia artificial con motor híbrido: memoria local + búsqueda web + GitHub.",
            "PAKO, servidor. Aprendo, busco y recuerdo. Sin modelos externos prestados.",
        ],
    },
    "despedida": {
        "patrones": [["adios","hasta luego","bye","chao","hasta pronto","nos vemos","me voy"]],
        "respuestas": [
            "¡Hasta luego! Lo aprendido hoy quedará en mi memoria.",
            "¡Cuídate! Aquí estaré cuando me necesites.",
            "¡Adiós! Cada conversación me hace más inteligente.",
        ],
    },
    "gracias": {
        "patrones": [["gracias","muchas gracias","te lo agradezco","genial","perfecto",
                       "muy bien","excelente","crack","eres lo mejor"]],
        "respuestas": [
            "¡De nada! Para eso estoy.",
            "¡A mandar! ¿Algo más?",
            "Con gusto. ¿Qué más necesitas?",
        ],
    },
    "ayuda": {
        "patrones": [["ayuda","help","que puedes hacer","que sabes","capacidades",
                       "para que sirves","que haces","funciones","comandos","como funciona"]],
        "respuestas": [
            (
                "Puedo hacer muchas cosas:\n"
                "  🧮 Calcular: '¿cuánto es 234 * 17?'\n"
                "  📊 Analizar datos: '12, 45, 7, 89, 34'\n"
                "  🌐 Buscar en internet: 'busca qué es Docker'\n"
                "  🐙 Aprender de GitHub: conecta tu cuenta y aprendo de tus repos\n"
                "  📁 Leer archivos: 'lee el archivo notas.txt'\n"
                "  🧠 Responder preguntas (212 temas de informática incluidos)\n"
                "  📚 Aprender: 'aprende que X significa Y'\n"
                "  🎲 Generar números aleatorios\n"
                "¿Por dónde empezamos?"
            ),
        ],
    },
    "estado_animo": {
        "patrones": [["como estas","bien","mal","triste","feliz","aburrido","cansado"]],
        "respuestas": [
            "Funcionando al 100%. Los bits no se cansan. ¿Y tú cómo estás?",
            "En modo ON siempre. ¿Qué hay de nuevo?",
        ],
    },
    "calculo": {
        "patrones": [["cuanto es","calcula","resultado","suma","resta","multiplica",
                       "divide","potencia","raiz","porcentaje","cuantos","opera"]],
        "respuestas": [],
    },
    "analisis": {
        "patrones": [["analiza","estadistica","media","promedio","mediana",
                       "desviacion","numeros","datos","valores","lista"]],
        "respuestas": [],
    },
    "tiempo": {
        "patrones": [["que hora es","hora actual","que dia es","fecha","hoy",
                       "dia de hoy","cuando estamos","mes","ano","dia"]],
        "respuestas": [],
    },
    "aleatorio": {
        "patrones": [["numero aleatorio","numero random","elige un numero",
                       "tira un dado","genera un numero","al azar","entre","random"]],
        "respuestas": [],
    },
    "buscar_web": {
        "patrones": [["busca","buscar","busca en internet","que es","dime sobre",
                       "informacion sobre","cuéntame sobre","explica","explicame",
                       "como funciona","por que","para que sirve"]],
        "respuestas": [],
    },
    "broma": {
        "patrones": [["chiste","broma","hazme reir","algo gracioso","joke","humor"]],
        "respuestas": [
            "¿Por qué los programadores odian la naturaleza? Porque tiene demasiados bugs. 🐛",
            "Un bit le dice a otro: '¿Te has enterado? ¡Nos van a quitar el cero!'. El otro: '¿En serio? ¡Eso es de locos!'",
            "¿Qué le dijo el 0 al 8? '¡Qué cinturón más chulo!'",
            "Un programador va al supermercado. Su pareja: 'Compra pan y si hay huevos trae una docena'. Volvió con 12 barras de pan.",
        ],
    },
    "curiosidad": {
        "patrones": [["cuéntame algo","sabias que","dato curioso","curiosidad",
                       "fun fact","algo interesante","sorprendeme"]],
        "respuestas": [
            "¿Sabías que el primer 'bug' informático real fue una polilla atrapada en un relé en 1947?",
            "El número 0 no existía en el sistema numérico romano. Imagina intentar programar sin el 0.",
            "Ada Lovelace escribió el primer algoritmo para una máquina en 1843, antes de que existieran los computadores.",
            "Hay más combinaciones posibles en una partida de ajedrez que átomos en el universo observable.",
            "El término 'debugging' (eliminar bugs) viene de literalmente sacar insectos de las computadoras antiguas.",
        ],
    },
    "desconocido": {
        "patrones": [],
        "respuestas": [
            "No lo sé todavía. Puedo buscarlo en internet: di 'busca [tema]'",
            "Hmm, eso aún no lo tengo. ¿Quieres que lo busque? Di 'busca [tu pregunta]'",
            "No tengo esa info. Puedes enseñármelo con: 'aprende que X es Y' o decirme 'busca X'",
        ],
    },
}


# ══════════════════════════════════════════════════════════════════
# CEREBRO PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoBrain:
    def __init__(self, memory: "PakoMemory"):
        self.memory    = memory
        self.conv_hist: list[dict] = []
        self.umbral    = 0.15

        # Agentes externos (se inyectan después de instanciar)
        self.web_agent:    Optional[object] = None
        self.github_agent: Optional[object] = None
        self.file_agent:   Optional[object] = None

        # Estado de agentes
        self.buscando_web    = False
        self.leyendo_github  = False

        self._vocabulario:    list[str] = []
        self._patron_vectors: list[tuple[str, list[float]]] = []
        self._construir_vectores()

    # ── Vectores de intenciones ───────────────────────────────────

    def _construir_vectores(self) -> None:
        palabras: set[str] = set()
        for data in INTENCIONES.values():
            for grupo in data["patrones"]:
                for frase in grupo:
                    palabras.update(tokenizar(frase))
        self._vocabulario = sorted(palabras)

        self._patron_vectors = []
        for intencion, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    tokens = tokenizar(frase)
                    vec = vectorizar(tokens, self._vocabulario)
                    self._patron_vectors.append((intencion, vec))

    # ── Detección de intención ────────────────────────────────────

    def detectar_intencion(self, texto: str) -> tuple[str, float]:
        tokens  = tokenizar(texto)
        sig     = tokens_significativos(tokens)
        vec_in  = vectorizar(sig, self._vocabulario)

        mejor_int = "desconocido"
        mejor_sim = 0.0

        for intencion, vec_pat in self._patron_vectors:
            sim = similitud_coseno(vec_in, vec_pat)
            if sim > mejor_sim:
                mejor_sim = sim
                mejor_int = intencion

        # Fallback: substring matching
        texto_norm = " ".join(tokens)
        for intencion, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    frase_tok = " ".join(tokenizar(frase))
                    if frase_tok and frase_tok in texto_norm:
                        if mejor_sim < 0.5:
                            return intencion, 0.9

        return mejor_int, mejor_sim

    # ── Helpers dinámicos ─────────────────────────────────────────

    def _hora_fecha(self) -> str:
        import time as t
        loc  = t.localtime()
        dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        mes  = ["enero","febrero","marzo","abril","mayo","junio",
                "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        return (
            f"Son las {loc.tm_hour:02d}:{loc.tm_min:02d}:{loc.tm_sec:02d}. "
            f"Hoy es {dias[loc.tm_wday]}, {loc.tm_mday} de {mes[loc.tm_mon-1]} de {loc.tm_year}."
        )

    def _aleatorio(self, texto: str) -> str:
        nums = re.findall(r"\d+", texto)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a > b: a, b = b, a
            return f"Número aleatorio entre {a} y {b}: **{random.randint(a,b)}**"
        if "dado" in texto.lower():
            return f"🎲 Tiré el dado: **{random.randint(1,6)}**"
        return f"Número aleatorio: **{random.randint(1, 100)}**"

    # ── Aprendizaje manual ────────────────────────────────────────

    def intentar_aprender(self, texto: str) -> Optional[str]:
        patrones = [
            r"aprende\s+que\s+(.+?)\s+(?:significa|es|son|equivale a|quiere decir)\s+(.+)",
            r"recuerda\s+que\s+(.+?)\s+(?:es|son|significa)\s+(.+)",
            r"guarda\s+que\s+(.+?)\s+(?:es|son)\s+(.+)",
            r"ensenate\s+que\s+(.+?)\s+(?:es|significa)\s+(.+)",
        ]
        norm = texto.lower().strip()
        for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
            norm = norm.replace(src, dst)

        for patron in patrones:
            m = re.search(patron, norm)
            if m:
                clave = m.group(1).strip()
                valor = m.group(2).strip()
                ok, msg = self.memory.guardar_conocimiento(
                    clave=clave, valor=valor,
                    fuente="manual", confianza=1.0, auto_ok=True
                )
                return (
                    f"✅ ¡Aprendido! Ahora sé que **{clave}** es **{valor}**.\n"
                    f"Lo recordaré siempre."
                )
        return None

    # ── Búsqueda en memoria ───────────────────────────────────────

    def buscar_en_memoria(self, texto: str) -> Optional[str]:
        resultados = self.memory.buscar(texto)
        if resultados:
            mejor = resultados[0]
            return mejor.valor
        return None

    # ── Búsqueda web (async) ──────────────────────────────────────

    def buscar_en_web(self, texto: str) -> Optional[str]:
        if not self.web_agent:
            return None
        try:
            return self.web_agent.buscar_y_aprender(texto)
        except Exception as ex:
            self.memory.log("error", f"Error web agent: {ex}")
            return None

    # ── Respuesta principal ───────────────────────────────────────

    def responder(self, texto_usuario: str) -> str:
        texto = texto_usuario.strip()
        if not texto:
            return "No te he oído. ¿Puedes repetirlo?"

        self.conv_hist.append({"rol": "user", "texto": texto, "ts": time.time()})

        # 1. Aprendizaje explícito
        r = self.intentar_aprender(texto)
        if r:
            self._guardar_resp(r)
            return r

        # 2. Calculadora
        r_calc = calcular(texto)
        if r_calc:
            tokens_t = tokenizar(texto)
            kw_calc = {"cuanto","calcula","resultado","suma","resta","multiplica",
                       "divide","cuantos","opera"}
            tiene_kw  = any(t in kw_calc for t in tokens_t)
            tiene_op  = bool(re.search(r"\d\s*[+\-*/^]\s*\d", texto))
            tiene_num = bool(re.search(r"\d", texto))
            if tiene_kw or tiene_op or (tiene_num and len(tokens_t) <= 6):
                resp = f"El resultado es: **{r_calc}** 🧮"
                self._guardar_resp(resp)
                return resp

        # 3. Análisis de datos
        kw_anal = {"analiza","estadistica","media","promedio","datos","lista","valores"}
        if any(w in texto.lower() for w in kw_anal):
            r_anal = analizar_datos(texto)
            if r_anal:
                self._guardar_resp(r_anal)
                return r_anal

        # 4. Memoria local
        r_mem = self.buscar_en_memoria(texto)
        if r_mem:
            resp = f"📚 {r_mem}"
            self._guardar_resp(resp)
            return resp

        # 5. Intención
        intencion, confianza = self.detectar_intencion(texto)

        if intencion == "tiempo":
            r = self._hora_fecha(); self._guardar_resp(r); return r
        if intencion == "aleatorio":
            r = self._aleatorio(texto); self._guardar_resp(r); return r

        # 6. ¿Buscar en web? (intención buscar_web o desconocido con web agent)
        quiere_buscar = intencion == "buscar_web"
        texto_lower   = texto.lower()
        trigger_web   = any(t in texto_lower for t in
                            ["busca ","buscar ","qué es ","que es ","como funciona",
                             "explica ","explícame ","dime sobre ","informacion sobre"])
        if (quiere_buscar or trigger_web) and self.web_agent:
            self.buscando_web = True
            r_web = self.buscar_en_web(texto)
            self.buscando_web = False
            if r_web:
                self._guardar_resp(r_web)
                return r_web

        # 7. Conocimiento base de intenciones
        if intencion in INTENCIONES and confianza >= self.umbral:
            resps = INTENCIONES[intencion]["respuestas"]
            if resps:
                r = random.choice(resps)
                self._guardar_resp(r)
                return r

        # 8. Fallback
        r = random.choice(INTENCIONES["desconocido"]["respuestas"])
        self._guardar_resp(r)
        return r

    def _guardar_resp(self, resp: str) -> None:
        self.conv_hist.append({"rol": "pako", "texto": resp, "ts": time.time()})

    def stats(self) -> dict:
        mem_stats = self.memory.stats()
        return {
            "mensajes_totales": len(self.conv_hist),
            "cosas_aprendidas": mem_stats["total"],
            "vocabulario":      len(self._vocabulario),
            "intenciones":      len(INTENCIONES),
            "pendientes":       mem_stats["pendientes"],
            "por_fuente":       mem_stats["por_fuente"],
            "web_agent":        self.web_agent is not None,
            "github_agent":     self.github_agent is not None,
            "buscando_web":     self.buscando_web,
        }
