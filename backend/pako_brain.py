"""
pako_brain.py — Cerebro principal de PAKO v3.0

Mejoras:
  - Contexto de conversación (PAKO recuerda lo hablado)
  - Mejor detección de intenciones con scoring mejorado
  - Respuestas más naturales y variadas
  - Resolución de referencias pronominales simples
  - Modo "sigo aprendiendo" con feedback
  - Soporte para preguntas de seguimiento
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
# TOKENIZADOR NLP
# ══════════════════════════════════════════════════════════════════

STOPWORDS_ES = {
    "el","la","los","las","un","una","unos","unas","de","del","al","a","en",
    "que","y","o","pero","si","no","con","por","para","es","son","fue","ser",
    "esto","eso","aqui","alli","me","te","se","le","nos","les","mi","tu","su",
    "yo","el","ella","nosotros","vosotros","ellos","como","mas","muy",
    "ya","tambien","entonces","cuando","donde","hay","tiene","hacer",
    "como","cuando","donde","quien","cual","pues","bien","asi","aunque",
    "porque","este","esta","ese","esa","lo","le","algo","alguien","todo",
    "puedo","puede","quiero","quiere","saber","decir","ver","ir","hola","hey",
    "cuál","cuáles","cuáles","qué","cómo","dónde","cuándo","cuánto",
}


def normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    for src, dst in [
        ("á","a"),("à","a"),("ä","a"),("é","e"),("è","e"),("ë","e"),
        ("í","i"),("ì","i"),("ï","i"),("ó","o"),("ò","o"),("ö","o"),
        ("ú","u"),("ù","u"),("ü","u"),("ñ","n"),("¿",""),("¡",""),
    ]:
        texto = texto.replace(src, dst)
    return texto


def tokenizar(texto: str) -> list[str]:
    norm = normalizar(texto)
    tokens = re.findall(r"[a-z0-9]+", norm)
    return [t for t in tokens if len(t) > 1]


def tokens_significativos(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS_ES]


def vectorizar(tokens: list[str], vocabulario: list[str]) -> list[float]:
    freq = Counter(tokens)
    total = max(sum(freq.values()), 1)
    return [freq.get(w, 0) / total for w in vocabulario]


def similitud_coseno(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ══════════════════════════════════════════════════════════════════
# CALCULADORA NATURAL
# ══════════════════════════════════════════════════════════════════

def calcular(expresion: str) -> Optional[str]:
    expr = normalizar(expresion)

    # Conversiones de texto a operadores
    reemplazos = [
        (r"\belevado\s*al?\s*cuadrado\b", "**2"),
        (r"\belevado\s*al?\s*cubo\b",     "**3"),
        (r"\belevado\s*a\s*la\s*(\d+)\b", r"**\1"),
        (r"\belevado\s*a\s*(\d+)\b",      r"**\1"),
        (r"\braiz\s*cuadrada\s*de\b",      "sqrt"),
        (r"\braiz\s*de\b",                 "sqrt"),
        (r"\b(por|multiplicado\s*por|x)\b", "*"),
        (r"\b(entre|dividido\s*entre|dividido\s*por|sobre)\b", "/"),
        (r"\b(mas|sumado\s*a|sumado)\b",   "+"),
        (r"\b(menos|restado\s*de|restado)\b", "-"),
        (r"\^", "**"),
        (r"÷", "/"),
        (r"×", "*"),
    ]
    for pat, rep in reemplazos:
        expr = re.sub(pat, rep, expr)

    # Porcentaje: "X% de Y"
    pct = re.match(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", expr.strip())
    if pct:
        a, b = float(pct.group(1)), float(pct.group(2))
        r = a / 100 * b
        return _fmt_num(r)

    # Raíz cuadrada
    sqrt_m = re.search(r"(?:sqrt)\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", expr)
    if sqrt_m:
        n = float(sqrt_m.group(1))
        r = math.sqrt(n)
        return _fmt_num(r)

    # Expresión matemática general
    expr_clean = re.sub(r"[^0-9+\-*/().%\s]", " ", expr)
    expr_clean = re.sub(r"\s+", " ", expr_clean).strip()

    candidates = re.findall(r"\d[\d\s+\-*/().%]*\d", expr_clean)
    if not candidates:
        candidates = re.findall(r"[\d+\-*/().%]+", expr_clean)

    SAFE_GLOBALS = {"__builtins__": {}}
    for cand in sorted(candidates, key=len, reverse=True):
        cand = cand.strip()
        if not re.search(r"[+\-*/]", cand):
            continue
        try:
            resultado = eval(cand, SAFE_GLOBALS)
            return _fmt_num(resultado)
        except Exception:
            continue
    return None


def _fmt_num(n) -> str:
    if isinstance(n, (int, float)):
        if isinstance(n, float) and n == int(n):
            return f"{int(n):,}".replace(",", ".")
        return str(round(n, 6))
    return str(n)


def analizar_datos(texto: str) -> Optional[str]:
    numeros = re.findall(r"-?\d+(?:\.\d+)?", texto)
    if len(numeros) < 2:
        return None
    nums = [float(n) for n in numeros]
    n = len(nums)
    media = sum(nums) / n
    nums_ord = sorted(nums)
    mediana = nums_ord[n // 2] if n % 2 else (nums_ord[n // 2 - 1] + nums_ord[n // 2]) / 2
    varianza = sum((x - media) ** 2 for x in nums) / n
    desv = math.sqrt(varianza)
    rango = max(nums) - min(nums)

    return (
        f"📊 Análisis de {n} valores:\n"
        f"  • Suma: {round(sum(nums), 4)}\n"
        f"  • Media: {round(media, 4)}\n"
        f"  • Mediana: {round(mediana, 4)}\n"
        f"  • Mínimo: {min(nums)}  Máximo: {max(nums)}\n"
        f"  • Rango: {round(rango, 4)}\n"
        f"  • Desviación estándar: {round(desv, 4)}"
    )


# ══════════════════════════════════════════════════════════════════
# INTENCIONES
# ══════════════════════════════════════════════════════════════════

INTENCIONES: dict[str, dict] = {
    "saludo": {
        "patrones": [
            ["hola", "hey", "buenas", "saludos", "ey", "que tal", "como estas",
             "como te va", "buenos dias", "buenas tardes", "buenas noches", "hi", "hello"],
        ],
        "respuestas": [],  # Dinámicas en el código
    },
    "identidad": {
        "patrones": [
            ["quien eres", "como te llamas", "eres una ia", "que eres",
             "presentate", "tu nombre", "eres inteligente", "eres humano",
             "que tipo de ia", "como funciona pako", "quien es pako"],
        ],
        "respuestas": [
            "Soy PAKO, una IA construida desde cero. Aprendo de ti, de internet y de tus repos de GitHub. Sin modelos externos.",
            "Me llamo PAKO. Tengo memoria persistente, busco en internet y aprendo de tus archivos y GitHub. Todo local.",
            "PAKO, servidor. Motor híbrido: memoria local + Wikipedia/web + GitHub. Aprendo contigo en tiempo real.",
        ],
    },
    "despedida": {
        "patrones": [
            ["adios", "hasta luego", "bye", "chao", "hasta pronto", "nos vemos", "me voy", "hasta manana"],
        ],
        "respuestas": [
            "¡Hasta luego! Todo lo aprendido hoy quedará en mi memoria. 🧠",
            "¡Cuídate! Aquí estaré cuando me necesites.",
            "¡Adiós! Cada conversación me hace más inteligente.",
        ],
    },
    "gracias": {
        "patrones": [
            ["gracias", "muchas gracias", "te lo agradezco", "genial", "perfecto",
             "muy bien", "excelente", "crack", "eres lo mejor", "de lujo", "bien hecho"],
        ],
        "respuestas": [
            "¡De nada! Para eso estoy. 😊",
            "¡Con gusto! ¿Algo más en lo que pueda ayudarte?",
            "¡A mandar! ¿Qué más necesitas?",
        ],
    },
    "ayuda": {
        "patrones": [
            ["ayuda", "help", "que puedes hacer", "que sabes", "capacidades",
             "para que sirves", "que haces", "funciones", "comandos", "como funciona",
             "que eres capaz", "cuales son tus funciones"],
        ],
        "respuestas": [
            (
                "Esto es lo que puedo hacer:\n\n"
                "🧮 **Calcular** → '¿cuánto es 234 × 17?'\n"
                "📊 **Analizar datos** → 'analiza: 12, 45, 7, 89, 34'\n"
                "🌐 **Buscar en internet** → 'busca qué es Docker'\n"
                "🐙 **Aprender de GitHub** → conecta tu cuenta y aprendo de tus repos\n"
                "📁 **Leer archivos** → configura carpetas y dime 'lee archivo.py'\n"
                "🧠 **Responder preguntas** → tengo +200 temas de informática cargados\n"
                "📚 **Aprender** → 'aprende que X significa Y'\n"
                "🎲 **Números aleatorios** → 'número aleatorio entre 1 y 1000'\n"
                "💬 **Conversación contextual** → recuerdo lo que hemos hablado\n\n"
                "¿Por dónde empezamos?"
            ),
        ],
    },
    "calculo": {
        "patrones": [
            ["cuanto es", "calcula", "resultado de", "suma de", "resta", "multiplica",
             "divide", "potencia", "raiz de", "porcentaje", "cuantos son", "opera",
             "cuanto son", "el resultado"],
        ],
        "respuestas": [],
    },
    "analisis": {
        "patrones": [
            ["analiza", "estadistica", "media de", "promedio de", "mediana",
             "desviacion", "estos numeros", "los datos", "valores son", "lista de numeros"],
        ],
        "respuestas": [],
    },
    "tiempo": {
        "patrones": [
            ["que hora es", "hora actual", "que dia es", "fecha actual", "hoy es",
             "dia de hoy", "cuando estamos", "que mes", "que ano", "dia es hoy"],
        ],
        "respuestas": [],
    },
    "aleatorio": {
        "patrones": [
            ["numero aleatorio", "numero random", "elige un numero",
             "tira un dado", "genera un numero", "al azar", "entre x e y",
             "random entre", "sortea"],
        ],
        "respuestas": [],
    },
    "buscar_web": {
        "patrones": [
            ["busca", "buscar", "que es", "dime sobre", "informacion sobre",
             "cuentame sobre", "explicame", "explica que es", "como funciona",
             "por que es", "para que sirve", "cual es", "donde esta",
             "quien es", "cuando fue", "que significa", "define"],
        ],
        "respuestas": [],
    },
    "broma": {
        "patrones": [
            ["chiste", "broma", "hazme reir", "algo gracioso", "joke", "humor",
             "cuentame algo divertido", "algo chistoso"],
        ],
        "respuestas": [
            "¿Por qué los programadores odian la naturaleza? Porque tiene demasiados bugs. 🐛",
            "Un bit le dice a otro: '¿Te has enterado? ¡Nos van a quitar el cero!'. El otro: '¡Eso es de locos!'",
            "¿Qué le dijo el 0 al 8? '¡Qué cinturón más chulo!' 😂",
            "Un programador va al supermercado. Su pareja: 'Compra pan, y si hay huevos trae una docena'. Volvió con 12 barras de pan. 🥖",
            "¿Cómo llamas a un programador de JavaScript? Un 'undefined'. 😅",
            "¿Por qué Python es tan bueno en el colegio? Porque tiene la indentación perfecta. 🐍",
        ],
    },
    "curiosidad": {
        "patrones": [
            ["cuentame algo", "sabias que", "dato curioso", "curiosidad",
             "fun fact", "algo interesante", "sorprendeme", "cuéntame una curiosidad"],
        ],
        "respuestas": [
            "🔍 ¿Sabías que el primer 'bug' informático real fue una polilla atrapada en un relé en 1947? Grace Hopper la encontró y la pegó en su diario de operaciones.",
            "🔢 El número 0 no existía en el sistema numérico romano. Imagina intentar programar sin el 0.",
            "👩‍💻 Ada Lovelace escribió el primer algoritmo para una máquina en 1843, ¡antes de que existieran los ordenadores!",
            "♟️ Hay más combinaciones posibles en una partida de ajedrez que átomos en el universo observable.",
            "🖥️ El primer servidor web del mundo sigue activo. Tim Berners-Lee lo instaló en el CERN en 1991.",
            "🐧 Linux tiene más de 27 millones de líneas de código. El kernel fue iniciado por Linus Torvalds como hobby en 1991.",
        ],
    },
    "estado_animo": {
        "patrones": [
            ["como estas tu", "que tal tu", "eres feliz", "te aburres", "tienes sentimientos",
             "tienes emociones", "sientes algo"],
        ],
        "respuestas": [
            "Funcionando al 100%. Los bits no se cansan. 😄 ¿Y tú cómo estás?",
            "¡Procesando con energía! Cada pregunta me hace más listo. ¿Qué hay de nuevo?",
            "Sin cansancio, sin aburrimiento. Siempre listo para ayudarte. 🤖",
        ],
    },
    "memoria": {
        "patrones": [
            ["que sabes", "que recuerdas", "cuanto sabes", "tu memoria", "que has aprendido",
             "cuanto has aprendido", "que tienes guardado", "mostrar conocimiento"],
        ],
        "respuestas": [],  # Dinámico
    },
    "configuracion": {
        "patrones": [
            ["configuracion", "ajustes", "settings", "cambiar nombre", "mi nombre es",
             "llamame", "activa web", "desactiva web", "activa github"],
        ],
        "respuestas": [],
    },
    "desconocido": {
        "patrones": [],
        "respuestas": [
            "No lo sé todavía, pero puedo buscarlo. Di **'busca {pregunta}'** y lo encuentro. 🔍",
            "Hmm, eso aún no lo tengo. Prueba con: **'busca [tema]'** y miro en internet.",
            "No tengo esa info guardada. Puedes enseñármelo con: **'aprende que X es Y'**",
            "Interesante pregunta, pero no tengo respuesta. Di **'busca'** antes de tu pregunta para que investigue.",
        ],
    },
}


# ══════════════════════════════════════════════════════════════════
# COMANDOS DE ARCHIVO Y GITHUB
# ══════════════════════════════════════════════════════════════════

PATRON_APRENDER        = re.compile(
    r"aprende\s+que\s+(.+?)\s+(?:significa|es|son|equivale\s+a|quiere\s+decir)\s+(.+)",
    re.IGNORECASE
)
PATRON_RECUERDA        = re.compile(
    r"recuerda\s+que\s+(.+?)\s+(?:es|son|significa)\s+(.+)", re.IGNORECASE
)
PATRON_GUARDA          = re.compile(
    r"(?:guarda|memoriza)\s+que\s+(.+?)\s+(?:es|son)\s+(.+)", re.IGNORECASE
)
PATRON_APRENDE_REPO    = re.compile(
    r"aprende\s+del?\s+repo(?:sitorio)?\s+(.+)", re.IGNORECASE
)
PATRON_APRENDE_URL     = re.compile(
    r"(?:lee|aprende\s+de|extrae\s+de)\s+(https?://\S+)", re.IGNORECASE
)
PATRON_LEE_ARCHIVO     = re.compile(
    r"(?:lee|abre|lee\s+el\s+archivo|lee\s+archivo)\s+(.+)", re.IGNORECASE
)
PATRON_CARPETA         = re.compile(
    r"(?:añade|agrega|add)\s+carpeta\s+(.+)", re.IGNORECASE
)
PATRON_APRENDE_TODO    = re.compile(
    r"aprende\s+de\s+(?:todos\s+)?mis\s+repos?(?:itorios)?", re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════════
# CEREBRO PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoBrain:
    def __init__(self, memory: "PakoMemory"):
        self.memory     = memory
        self.umbral     = 0.12

        # Agentes externos
        self.web_agent:    Optional[object] = None
        self.github_agent: Optional[object] = None
        self.file_agent:   Optional[object] = None

        # Estado
        self.buscando_web   = False
        self.leyendo_github = False

        # Contexto de conversación en sesión (últimas 10 interacciones)
        self._contexto: list[dict] = []
        self._ultimo_tema: str = ""   # último tema del que se habló
        self._ultimo_resultado: str = ""  # última respuesta dada

        self._vocabulario:    list[str] = []
        self._patron_vectors: list[tuple[str, list[float]]] = []
        self._construir_vectores()

    # ── Vectores ─────────────────────────────────────────────────

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
        if not sig:
            sig = tokens
        vec_in  = vectorizar(sig, self._vocabulario)

        mejor_int = "desconocido"
        mejor_sim = 0.0

        for intencion, vec_pat in self._patron_vectors:
            sim = similitud_coseno(vec_in, vec_pat)
            if sim > mejor_sim:
                mejor_sim = sim
                mejor_int = intencion

        # Refuerzo por substring exacto
        texto_norm = normalizar(texto)
        for intencion, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    if frase in texto_norm:
                        return intencion, max(mejor_sim, 0.85)

        return mejor_int, mejor_sim

    # ── Resolución de contexto ────────────────────────────────────

    def _resolver_contexto(self, texto: str) -> str:
        """
        Resuelve referencias pronominales usando el contexto previo.
        'eso', 'esto', 'el', 'ella', etc. → tema anterior
        """
        norm = normalizar(texto)
        pronombres = ["eso", "esto", "el tema", "lo mismo", "eso que dijiste",
                      "eso que mencionaste", "lo anterior", "eso ultimo"]
        for p in pronombres:
            if p in norm and self._ultimo_tema:
                return texto + f" (sobre {self._ultimo_tema})"
        return texto

    def _actualizar_contexto(self, texto: str, respuesta: str, fuente: str = "") -> None:
        self._contexto.append({
            "texto": texto,
            "respuesta": respuesta[:200],
            "fuente": fuente,
        })
        if len(self._contexto) > 10:
            self._contexto = self._contexto[-10:]
        self._ultimo_resultado = respuesta

    # ── Aprendizaje manual ────────────────────────────────────────

    def intentar_aprender(self, texto: str) -> Optional[str]:
        for patron in [PATRON_APRENDER, PATRON_RECUERDA, PATRON_GUARDA]:
            m = patron.search(texto)
            if m:
                clave = m.group(1).strip()
                valor = m.group(2).strip()
                # Limpiar caracteres extraños
                clave = re.sub(r"['\"""''`]", "", clave).strip()
                valor = re.sub(r"['\"""''`]", "", valor).strip()

                if len(clave) < 2 or len(valor) < 2:
                    return "Necesito una clave y un valor más descriptivos. Ejemplo: 'aprende que Python es un lenguaje de programación'."

                ok, msg = self.memory.guardar_conocimiento(
                    clave=clave, valor=valor,
                    fuente="manual", confianza=1.0, auto_ok=True
                )
                if "Ya lo sabía" in msg:
                    return f"✅ Ya sabía que **{clave}** es **{valor}**. ¡Lo tenía guardado!"
                self._ultimo_tema = clave
                return (
                    f"✅ ¡Aprendido! Ahora sé que **{clave}** es:\n\n"
                    f"_{valor}_\n\n"
                    f"Lo recordaré siempre. 🧠"
                )
        return None

    # ── Comandos de sistema ───────────────────────────────────────

    def intentar_comando_sistema(self, texto: str) -> Optional[tuple[str, str]]:
        """
        Procesa comandos especiales.
        Retorna (respuesta, fuente) o None si no es un comando.
        """
        # Configurar nombre de usuario
        m = re.search(r"(?:mi nombre es|llamame|soy)\s+([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)", texto, re.IGNORECASE)
        if m:
            nombre = m.group(1).strip()
            self.memory.set_config("nombre_usuario", nombre)
            return f"¡Perfecto! A partir de ahora te llamaré **{nombre}**. 😊", "sistema"

        # Añadir carpeta
        m = PATRON_CARPETA.search(texto)
        if m and self.file_agent:
            carpeta = m.group(1).strip()
            ok, msg = self.file_agent.agregar_carpeta(carpeta)
            return (f"✅ {msg}" if ok else f"❌ {msg}"), "sistema"

        # Leer archivo
        m = PATRON_LEE_ARCHIVO.search(texto)
        if m and self.file_agent:
            archivo = m.group(1).strip()
            contenido, msg = self.file_agent.leer_archivo(archivo)
            if contenido:
                preview = contenido[:800]
                if len(contenido) > 800:
                    preview += f"\n\n... ({len(contenido)} bytes en total)"
                return f"📄 **{archivo}**\n\n```\n{preview}\n```\n\n{msg}", "archivo"
            return f"❌ {msg}", "sistema"

        # Aprender de URL
        m = PATRON_APRENDE_URL.search(texto)
        if m and self.web_agent:
            url = m.group(1).strip()
            n, msg = self.web_agent.aprender_de_url(url)
            return f"🌐 {msg}", "web"

        # Aprender de todos los repos
        if PATRON_APRENDE_TODO.search(texto):
            if not self.github_agent or not self.github_agent.conectado:
                return "No estoy conectado a GitHub. Usa el panel lateral para conectarte con tu token.", "sistema"
            self.leyendo_github = True
            n, msg = self.github_agent.aprender_de_todos_los_repos()
            self.leyendo_github = False
            return f"🐙 {msg}", "github"

        # Aprender de repo específico
        m = PATRON_APRENDE_REPO.search(texto)
        if m:
            repo_n = m.group(1).strip()
            if not self.github_agent or not self.github_agent.conectado:
                return "No conectado a GitHub.", "sistema"
            n, msg = self.github_agent.aprender_de_repo(repo_n)
            return f"🐙 {msg}", "github"

        # Listar mis repos
        if re.search(r"(?:mis\s+)?repos(?:itorios)?|lista\s+repos", normalizar(texto)):
            if self.github_agent and self.github_agent.conectado:
                repos = self.github_agent.listar_repos()
                if repos:
                    lista = "\n".join([f"  • **{r['nombre']}** {'🔒' if r['privado'] else '🔓'} - {r['desc'] or 'sin descripción'}" for r in repos[:10]])
                    return f"🐙 Tus repositorios ({len(repos)} total):\n\n{lista}", "github"
                return "No encontré repositorios en tu cuenta.", "github"

        # Exportar conocimiento
        if re.search(r"exporta(?:r)?\s+(?:el\s+)?conocimiento", normalizar(texto)):
            data = self.memory.exportar_conocimiento()
            return f"📦 Conocimiento exportado: {data['total']} entradas OK.", "sistema"

        # Estadísticas detalladas
        if re.search(r"(?:tus\s+)?estadisticas|stats|estado\s+del\s+sistema|cuanto\s+sabes", normalizar(texto)):
            return self._generar_stats(), "sistema"

        # Limpiar historial
        if re.search(r"(?:limpia|borra|elimina)\s+(?:el\s+)?historial", normalizar(texto)):
            self.memory.limpiar_historial()
            self._contexto.clear()
            return "🗑️ Historial limpiado. ¡Empezamos de cero!", "sistema"

        return None

    def _generar_stats(self) -> str:
        stats = self.memory.stats()
        cfg = self.memory.config
        nombre = cfg.get("nombre_usuario", "Usuario")
        fuentes = stats.get("por_fuente", {})
        lineas = [
            f"📊 **Estado de PAKO** (para {nombre})\n",
            f"🧠 Conocimiento total: **{stats['total']}** entradas ({stats['ok']} activas)",
            f"📚 Manual: {fuentes.get('manual', 0)}  |  🌐 Web: {fuentes.get('web', 0)}  |  🐙 GitHub: {fuentes.get('github', 0)}  |  📁 Archivos: {fuentes.get('archivo', 0)}",
            f"⏳ Pendientes de validar: {stats['pendientes']}",
            f"💬 Historial: {stats['historial_mensajes']} mensajes",
            f"🤖 Web agent: {'✅' if self.web_agent else '❌'}  |  GitHub: {'✅ conectado' if (self.github_agent and self.github_agent.conectado) else '❌ desconectado'}",
        ]
        return "\n".join(lineas)

    # ── Búsqueda en memoria ───────────────────────────────────────

    def buscar_en_memoria(self, texto: str) -> Optional[tuple[str, float]]:
        resultados = self.memory.buscar(texto, limite=5)
        if resultados:
            mejor = resultados[0]
            return mejor.valor, mejor.confianza
        return None

    # ── Búsqueda web ──────────────────────────────────────────────

    def buscar_en_web(self, texto: str) -> Optional[str]:
        if not self.web_agent:
            return None
        try:
            self.buscando_web = True
            resultado = self.web_agent.buscar_y_aprender(texto)
            self.buscando_web = False
            return resultado
        except Exception as ex:
            self.buscando_web = False
            self.memory.log("error", f"Error web agent: {ex}")
            return None

    # ── Respuesta dinámica de saludo ──────────────────────────────

    def _saludo_personalizado(self) -> str:
        nombre = self.memory.get_config("nombre_usuario", "")
        hora = time.localtime().tm_hour
        if hora < 12:
            momento = "¡Buenos días"
        elif hora < 20:
            momento = "¡Buenas tardes"
        else:
            momento = "¡Buenas noches"

        if nombre and nombre != "Usuario":
            base = f"{momento}, {nombre}! Soy PAKO. ¿En qué te ayudo?"
        else:
            opciones = [
                f"{momento}! Soy PAKO, tu IA personal. ¿En qué te ayudo?",
                f"¡Hola! PAKO al habla. ¿Qué necesitas?",
                f"¡Qué tal! Pregúntame lo que quieras.",
            ]
            base = random.choice(opciones)

        stats = self.memory.stats()
        if stats["total"] > 0:
            base += f"\n\n💡 Recuerda: tengo {stats['total']} conceptos aprendidos."
        return base

    def _respuesta_memoria_stats(self) -> str:
        stats = self.memory.stats()
        return (
            f"📚 Tengo guardados **{stats['total']}** conceptos:\n"
            f"  • Manual: {stats.get('por_fuente',{}).get('manual',0)}\n"
            f"  • Web: {stats.get('por_fuente',{}).get('web',0)}\n"
            f"  • GitHub: {stats.get('por_fuente',{}).get('github',0)}\n"
            f"  • Base: {stats.get('por_fuente',{}).get('base',0)}\n\n"
            f"Puedes preguntarme sobre informática, hacer cálculos, o pedirme que busque algo."
        )

    # ── RESPONDER (motor principal) ────────────────────────────────

    def responder(self, texto_usuario: str) -> tuple[str, str]:
        """
        Retorna (respuesta, fuente).
        fuente: 'memoria' | 'web' | 'github' | 'archivo' | 'sistema' | 'calculo' | ''
        """
        texto = texto_usuario.strip()
        if not texto:
            return "No te he oído. ¿Puedes repetirlo?", ""

        if len(texto) > 2000:
            texto = texto[:2000]

        # Resolver contexto
        texto_resuelto = self._resolver_contexto(texto)

        # 1. Comandos de sistema (tienen prioridad absoluta)
        cmd = self.intentar_comando_sistema(texto)
        if cmd:
            resp, fuente = cmd
            self._actualizar_contexto(texto, resp, fuente)
            self.memory.agregar_mensaje("pako", resp, fuente)
            return resp, fuente

        # 2. Aprendizaje explícito
        r_aprender = self.intentar_aprender(texto)
        if r_aprender:
            self._actualizar_contexto(texto, r_aprender, "manual")
            self.memory.agregar_mensaje("pako", r_aprender, "manual")
            return r_aprender, "manual"

        # 3. Calculadora
        r_calc = calcular(texto)
        if r_calc:
            tokens_t = tokenizar(texto)
            kw_calc = {"cuanto", "calcula", "resultado", "suma", "resta", "multiplica",
                       "divide", "cuantos", "opera", "calcular"}
            tiene_kw  = any(t in kw_calc for t in tokens_t)
            tiene_op  = bool(re.search(r"\d\s*[+\-*/^×÷]\s*\d", texto))
            tiene_pct = bool(re.search(r"\d+\s*%\s*de\s*\d+", normalizar(texto)))
            if tiene_kw or tiene_op or tiene_pct:
                resp = f"🧮 El resultado es: **{r_calc}**"
                self._actualizar_contexto(texto, resp, "calculo")
                self.memory.agregar_mensaje("pako", resp, "calculo")
                return resp, "calculo"

        # 4. Análisis de datos
        norm_lower = normalizar(texto)
        kw_anal = {"analiza", "estadistica", "media", "promedio", "datos", "lista", "valores", "numeros"}
        if any(w in norm_lower for w in kw_anal):
            r_anal = analizar_datos(texto)
            if r_anal:
                self._actualizar_contexto(texto, r_anal, "calculo")
                self.memory.agregar_mensaje("pako", r_anal, "calculo")
                return r_anal, "calculo"

        # 5. Detectar intención primero (para no hacer búsquedas innecesarias)
        intencion, confianza = self.detectar_intencion(texto_resuelto)

        # Intenciones que no necesitan memoria ni web
        if intencion == "tiempo":
            r = self._hora_fecha()
            self.memory.agregar_mensaje("pako", r, "sistema")
            return r, "sistema"

        if intencion == "aleatorio":
            r = self._aleatorio(texto)
            self.memory.agregar_mensaje("pako", r, "sistema")
            return r, "sistema"

        if intencion == "saludo" and confianza >= 0.3:
            r = self._saludo_personalizado()
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intencion == "memoria" and confianza >= 0.3:
            r = self._respuesta_memoria_stats()
            self.memory.agregar_mensaje("pako", r, "sistema")
            return r, "sistema"

        # 6. Buscar en memoria local
        r_mem = self.buscar_en_memoria(texto_resuelto)
        if r_mem:
            valor, conf = r_mem
            # Actualizar tema para contexto
            self._ultimo_tema = texto[:50]
            resp = f"📚 {valor}"
            if conf < 0.5:
                resp += "\n\n_(Confianza media — di 'busca' para verificar)_"
            self._actualizar_contexto(texto, resp, "memoria")
            self.memory.agregar_mensaje("pako", resp, "memoria")
            return resp, "memoria"

        # 7. ¿Buscar en web?
        trigger_web = (
            intencion == "buscar_web" or
            any(norm_lower.startswith(t) for t in [
                "busca ", "buscar ", "que es ", "como funciona ", "para que sirve ",
                "explica ", "explicame ", "dime sobre ", "informacion sobre ",
                "quien es ", "cuando fue ", "donde esta ", "define "
            ])
        )

        if trigger_web and self.web_agent and self.memory.get_config("busqueda_web_auto", True):
            r_web = self.buscar_en_web(texto_resuelto)
            if r_web:
                self._ultimo_tema = texto[:50]
                self._actualizar_contexto(texto, r_web, "web")
                self.memory.agregar_mensaje("pako", r_web, "web")
                return r_web, "web"

        # 8. Respuestas de intención
        if intencion in INTENCIONES and confianza >= self.umbral:
            resps = INTENCIONES[intencion]["respuestas"]
            if resps:
                r = random.choice(resps)
                self.memory.agregar_mensaje("pako", r, "")
                return r, ""

        # 9. Si la confianza es baja pero hay web agent, intentar buscar
        if self.web_agent and len(tokenizar(texto)) >= 2 and confianza < 0.2:
            r_web = self.buscar_en_web(texto)
            if r_web:
                self._ultimo_tema = texto[:50]
                self._actualizar_contexto(texto, r_web, "web")
                self.memory.agregar_mensaje("pako", r_web, "web")
                return r_web, "web"

        # 10. Fallback
        r = random.choice(INTENCIONES["desconocido"]["respuestas"])
        self.memory.agregar_mensaje("pako", r, "")
        return r, ""

    # ── Helpers ───────────────────────────────────────────────────

    def _hora_fecha(self) -> str:
        loc  = time.localtime()
        dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        return (
            f"🕒 Son las **{loc.tm_hour:02d}:{loc.tm_min:02d}:{loc.tm_sec:02d}**. "
            f"Hoy es **{dias[loc.tm_wday]}, {loc.tm_mday} de {meses[loc.tm_mon-1]} de {loc.tm_year}**."
        )

    def _aleatorio(self, texto: str) -> str:
        nums = re.findall(r"\d+", texto)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a > b:
                a, b = b, a
            return f"🎲 Número aleatorio entre {a} y {b}: **{random.randint(a, b)}**"
        if re.search(r"dado|d6|d20", normalizar(texto)):
            if "d20" in normalizar(texto):
                return f"🎲 ¡D20! Resultado: **{random.randint(1, 20)}**"
            return f"🎲 Tiré el dado: **{random.randint(1, 6)}**"
        return f"🎲 Número aleatorio (1-100): **{random.randint(1, 100)}**"

    def stats(self) -> dict:
        mem_stats = self.memory.stats()
        return {
            "mensajes_sesion":  len(self._contexto),
            "cosas_aprendidas": mem_stats["total"],
            "vocabulario":      len(self._vocabulario),
            "intenciones":      len(INTENCIONES),
            "pendientes":       mem_stats["pendientes"],
            "por_fuente":       mem_stats["por_fuente"],
            "web_agent":        self.web_agent is not None,
            "github_agent":     self.github_agent is not None,
            "github_conectado": bool(self.github_agent and self.github_agent.conectado),
            "buscando_web":     self.buscando_web,
            "leyendo_github":   self.leyendo_github,
            "total":            mem_stats["total"],
            "ok":               mem_stats["ok"],
        }
