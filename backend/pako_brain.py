"""
pako_brain.py — Cerebro de PAKO v4.0

Novedades:
  - Fuzzy matching integrado: corrige silenciosamente errores tipográficos
  - Contexto de conversación persistente
  - Respuestas naturales y personalizadas
  - Soporte de comandos para automatizaciones
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

from pako_fuzzy import PakoFuzzy, fuzzy as _fuzzy_global


# ══════════════════════════════════════════════════════════════════
# NLP BASE
# ══════════════════════════════════════════════════════════════════

STOPWORDS_ES = {
    "el","la","los","las","un","una","unos","unas","de","del","al","a","en",
    "que","y","o","pero","si","no","con","por","para","es","son","fue","ser",
    "esto","eso","aqui","alli","me","te","se","le","nos","les","mi","tu","su",
    "yo","el","ella","nosotros","vosotros","ellos","como","mas","muy","ya",
    "tambien","entonces","cuando","donde","hay","tiene","hacer","pues","bien",
    "asi","aunque","porque","este","esta","ese","esa","lo","algo","todo",
    "puedo","puede","quiero","quiere","saber","decir","ver","ir","hola","hey",
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
    return [t for t in re.findall(r"[a-z0-9]+", norm) if len(t) > 1]


def tokens_sig(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS_ES]


def vectorizar(tokens: list[str], vocab: list[str]) -> list[float]:
    freq  = Counter(tokens)
    total = max(sum(freq.values()), 1)
    return [freq.get(w, 0) / total for w in vocab]


def cos_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ══════════════════════════════════════════════════════════════════
# CALCULADORA
# ══════════════════════════════════════════════════════════════════

def calcular(expr: str) -> Optional[str]:
    e = normalizar(expr)
    reemplazos = [
        (r"\belevado al cuadrado\b", "**2"),
        (r"\belevado al cubo\b",     "**3"),
        (r"\belevado a (\d+)\b",     r"**\1"),
        (r"\braiz cuadrada de\b",    "sqrt"),
        (r"\braiz de\b",             "sqrt"),
        (r"\b(por|multiplicado por|x)\b", "*"),
        (r"\b(entre|dividido entre|dividido por|sobre)\b", "/"),
        (r"\b(mas|sumado a|sumado)\b",   "+"),
        (r"\b(menos|restado)\b",         "-"),
        (r"\^", "**"), (r"÷", "/"), (r"×", "*"),
    ]
    for pat, rep in reemplazos:
        e = re.sub(pat, rep, e)

    pct = re.match(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", e.strip())
    if pct:
        a, b = float(pct.group(1)), float(pct.group(2))
        r = a / 100 * b
        return _fmt(r)

    sqrt_m = re.search(r"sqrt\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", e)
    if sqrt_m:
        return _fmt(math.sqrt(float(sqrt_m.group(1))))

    e_clean = re.sub(r"[^0-9+\-*/().%\s]", " ", e).strip()
    candidates = re.findall(r"\d[\d\s+\-*/().%]*\d", e_clean) or re.findall(r"[\d+\-*/().%]+", e_clean)
    SAFE = {"__builtins__": {}}
    for cand in sorted(candidates, key=len, reverse=True):
        cand = cand.strip()
        if not re.search(r"[+\-*/]", cand):
            continue
        try:
            res = eval(cand, SAFE)
            return _fmt(res)
        except Exception:
            continue
    return None


def _fmt(n) -> str:
    if isinstance(n, float) and n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return str(round(n, 6))


def analizar_datos(texto: str) -> Optional[str]:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", texto)]
    if len(nums) < 2:
        return None
    n = len(nums)
    media   = sum(nums) / n
    ord_n   = sorted(nums)
    mediana = ord_n[n // 2] if n % 2 else (ord_n[n // 2 - 1] + ord_n[n // 2]) / 2
    desv    = math.sqrt(sum((x - media) ** 2 for x in nums) / n)
    return (
        f"📊 Análisis de {n} valores:\n"
        f"  • Suma: {round(sum(nums),4)}\n"
        f"  • Media: {round(media,4)}\n"
        f"  • Mediana: {round(mediana,4)}\n"
        f"  • Mín: {min(nums)}  Máx: {max(nums)}\n"
        f"  • Rango: {round(max(nums)-min(nums),4)}\n"
        f"  • Desviación estándar: {round(desv,4)}"
    )


# ══════════════════════════════════════════════════════════════════
# INTENCIONES
# ══════════════════════════════════════════════════════════════════

INTENCIONES = {
    "saludo": {
        "patrones": [["hola","hey","buenas","saludos","ey","que tal","como estas","buenos dias","buenas tardes","buenas noches","hi","hello"]],
        "respuestas": [],
    },
    "identidad": {
        "patrones": [["quien eres","como te llamas","eres una ia","que eres","presentate","tu nombre","eres humano","quien es pako"]],
        "respuestas": [
            "Soy **PAKO**, tu asistente de IA integrado en esta plataforma. Gestiono el chat, automatizaciones, archivos y más. 🤖",
            "Me llamo **PAKO**. Motor de IA central de la plataforma: respondo, aprendo, automatizo y corrijo tus errores tipográficos sin decirte nada. 😄",
        ],
    },
    "despedida": {
        "patrones": [["adios","hasta luego","bye","chao","hasta pronto","nos vemos","me voy"]],
        "respuestas": ["¡Hasta luego! Lo aprendido hoy quedará en memoria. 🧠","¡Cuídate! Aquí estaré. 👋"],
    },
    "gracias": {
        "patrones": [["gracias","muchas gracias","genial","perfecto","muy bien","excelente","crack","de lujo"]],
        "respuestas": ["¡De nada! ¿Algo más? 😊","¡Con gusto! ¿En qué más te ayudo?"],
    },
    "ayuda": {
        "patrones": [["ayuda","help","que puedes hacer","que sabes","capacidades","para que sirves","funciones","comandos"]],
        "respuestas": [
            (
                "Esto es lo que puedo hacer:\n\n"
                "🧮 **Calcular** → '¿cuánto es 234 × 17?'\n"
                "📊 **Analizar datos** → 'analiza: 12, 45, 7, 89'\n"
                "🌐 **Buscar en internet** → 'busca qué es Docker'\n"
                "🤖 **Automatizaciones** → ve a la página de Automatizaciones\n"
                "🐙 **GitHub** → conecta tu cuenta y aprendo de tus repos\n"
                "📁 **Archivos** → lee archivos locales\n"
                "🧠 **Responder** → tengo +200 conceptos de informática\n"
                "📚 **Aprender** → 'aprende que X es Y'\n\n"
                "¿Por dónde empezamos?"
            ),
        ],
    },
    "automatizacion": {
        "patrones": [["automatizacion","automatizar","workflow","flujo","nodo","trigger","crear automatizacion","nueva automatizacion","n8n"]],
        "respuestas": [],
    },
    "calculo": {
        "patrones": [["cuanto es","calcula","resultado","suma","resta","multiplica","divide","potencia","raiz","porcentaje"]],
        "respuestas": [],
    },
    "analisis": {
        "patrones": [["analiza","estadistica","media","promedio","mediana","desviacion","datos","valores","numeros"]],
        "respuestas": [],
    },
    "tiempo": {
        "patrones": [["que hora es","hora actual","que dia es","fecha","hoy","cuando estamos"]],
        "respuestas": [],
    },
    "aleatorio": {
        "patrones": [["numero aleatorio","numero random","al azar","entre","random","dado"]],
        "respuestas": [],
    },
    "buscar_web": {
        "patrones": [["busca","buscar","que es","dime sobre","informacion sobre","explica","como funciona","para que sirve","quien es","define"]],
        "respuestas": [],
    },
    "memoria": {
        "patrones": [["que sabes","cuanto sabes","tu memoria","que has aprendido","estadisticas","stats"]],
        "respuestas": [],
    },
    "broma": {
        "patrones": [["chiste","broma","hazme reir","algo gracioso","joke"]],
        "respuestas": [
            "¿Por qué los programadores odian la naturaleza? Porque tiene demasiados bugs. 🐛",
            "Un programador va al supermercado: 'trae pan, y si hay huevos trae una docena'. Volvió con 12 barras. 🥖",
            "¿Cómo llamas a un programador de JavaScript? Un `undefined`. 😅",
        ],
    },
    "curiosidad": {
        "patrones": [["cuentame algo","sabias que","dato curioso","curiosidad","sorprendeme"]],
        "respuestas": [
            "🔍 El primer 'bug' fue una polilla real atrapada en un relé en 1947. Grace Hopper la encontró.",
            "🐧 Linus Torvalds creó Linux como hobby en 1991. Hoy tiene 27+ millones de líneas de código.",
            "👩‍💻 Ada Lovelace escribió el primer algoritmo para una máquina en 1843, antes de que existieran los ordenadores.",
        ],
    },
    "desconocido": {
        "patrones": [],
        "respuestas": [
            "No lo sé todavía. Di **'busca [tema]'** y lo investigo. 🔍",
            "Eso no lo tengo guardado. Puedes enseñármelo: **'aprende que X es Y'**",
            "Hmm, no tengo esa info. ¿Quieres que lo busque en internet?",
        ],
    },
}

PATRON_APRENDER = re.compile(
    r"aprende\s+que\s+(.+?)\s+(?:significa|es|son|equivale\s*a|quiere\s*decir)\s+(.+)",
    re.IGNORECASE
)
PATRON_RECUERDA = re.compile(
    r"recuerda\s+que\s+(.+?)\s+(?:es|son|significa)\s+(.+)", re.IGNORECASE
)
PATRON_GUARDA = re.compile(
    r"(?:guarda|memoriza)\s+que\s+(.+?)\s+(?:es|son)\s+(.+)", re.IGNORECASE
)
PATRON_LEE = re.compile(r"(?:lee|abre|lee\s+(?:el\s+)?archivo)\s+(.+)", re.IGNORECASE)
PATRON_CARPETA = re.compile(r"(?:añade|agrega)\s+carpeta\s+(.+)", re.IGNORECASE)
PATRON_APRENDE_REPO = re.compile(r"aprende\s+del?\s+repo(?:sitorio)?\s+(.+)", re.IGNORECASE)
PATRON_APRENDE_TODO = re.compile(r"aprende\s+de\s+(?:todos\s+)?mis\s+repos?", re.IGNORECASE)
PATRON_URL = re.compile(r"(?:lee|aprende\s+de)\s+(https?://\S+)", re.IGNORECASE)
PATRON_NOMBRE = re.compile(r"(?:mi\s+nombre\s+es|llamame|soy)\s+([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)", re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════
# CEREBRO
# ══════════════════════════════════════════════════════════════════

class PakoBrain:
    def __init__(self, memory: "PakoMemory"):
        self.memory = memory
        self.fuzzy  = _fuzzy_global
        self.umbral = 0.12

        self.web_agent    = None
        self.github_agent = None
        self.file_agent   = None
        self.automations  = None  # PakoAutomations

        self.buscando_web   = False
        self.leyendo_github = False

        self._contexto:     list[dict] = []
        self._ultimo_tema:  str = ""
        self._vocab:        list[str] = []
        self._pat_vecs:     list[tuple[str, list[float]]] = []
        self._construir_vectores()

        # Enriquecer vocabulario fuzzy con el conocimiento de la memoria
        self._enriquecer_fuzzy()

    def _enriquecer_fuzzy(self) -> None:
        claves = [e.clave for e in self.memory.conocimiento.values()]
        palabras = []
        for c in claves:
            palabras.extend(tokenizar(c))
        self.fuzzy.enriquecer_vocabulario(palabras)

    def _construir_vectores(self) -> None:
        palabras: set[str] = set()
        for data in INTENCIONES.values():
            for grupo in data["patrones"]:
                for frase in grupo:
                    palabras.update(tokenizar(frase))
        self._vocab = sorted(palabras)
        self._pat_vecs = []
        for intent, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    vec = vectorizar(tokenizar(frase), self._vocab)
                    self._pat_vecs.append((intent, vec))

    # ── Fuzzy: corregir entrada silenciosamente ───────────────────

    def _corregir_entrada(self, texto: str) -> str:
        """Corrige silenciosamente el texto del usuario sin avisarle."""
        corregido, _ = self.fuzzy.corregir_texto(texto)
        return corregido

    # ── Intención ─────────────────────────────────────────────────

    def detectar_intencion(self, texto: str) -> tuple[str, float]:
        tokens = tokenizar(texto)
        sig    = tokens_sig(tokens) or tokens
        vec_in = vectorizar(sig, self._vocab)

        mejor_int = "desconocido"
        mejor_sim = 0.0
        for intent, vec_pat in self._pat_vecs:
            s = cos_sim(vec_in, vec_pat)
            if s > mejor_sim:
                mejor_sim, mejor_int = s, intent

        # Refuerzo por substring exacto
        norm = normalizar(texto)
        for intent, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    if frase in norm:
                        return intent, max(mejor_sim, 0.85)

        return mejor_int, mejor_sim

    # ── Comandos de sistema ───────────────────────────────────────

    def _cmd_sistema(self, texto: str) -> Optional[tuple[str, str]]:
        # Nombre de usuario
        m = PATRON_NOMBRE.search(texto)
        if m:
            nombre = m.group(1).strip()
            self.memory.set_config("nombre_usuario", nombre)
            return f"¡Perfecto, {nombre}! Te recuerdo para siempre. 😊", "sistema"

        # Carpeta
        m = PATRON_CARPETA.search(texto)
        if m and self.file_agent:
            ok, msg = self.file_agent.agregar_carpeta(m.group(1).strip())
            return (f"✅ {msg}" if ok else f"❌ {msg}"), "sistema"

        # Leer archivo
        m = PATRON_LEE.search(texto)
        if m and self.file_agent:
            contenido, msg = self.file_agent.leer_archivo(m.group(1).strip())
            if contenido:
                prev = contenido[:800] + (f"\n... ({len(contenido)} bytes)" if len(contenido) > 800 else "")
                return f"📄 **{m.group(1).strip()}**\n\n```\n{prev}\n```\n\n{msg}", "archivo"
            return f"❌ {msg}", "sistema"

        # URL
        m = PATRON_URL.search(texto)
        if m and self.web_agent:
            n, msg = self.web_agent.aprender_de_url(m.group(1))
            return f"🌐 {msg}", "web"

        # GitHub
        if PATRON_APRENDE_TODO.search(texto):
            if not self.github_agent or not self.github_agent.conectado:
                return "No conectado a GitHub. Conecta en el panel lateral.", "sistema"
            n, msg = self.github_agent.aprender_de_todos_los_repos()
            return f"🐙 {msg}", "github"
        m = PATRON_APRENDE_REPO.search(texto)
        if m:
            if not self.github_agent or not self.github_agent.conectado:
                return "No conectado a GitHub.", "sistema"
            n, msg = self.github_agent.aprender_de_repo(m.group(1).strip())
            return f"🐙 {msg}", "github"

        # Mis repos
        if re.search(r"(?:mis\s+)?repos(?:itorios)?", normalizar(texto)):
            if self.github_agent and self.github_agent.conectado:
                repos = self.github_agent.listar_repos()
                lista = "\n".join(f"  • **{r['nombre']}** {'🔒' if r['privado'] else '🔓'} — {r['desc'] or 'sin descripción'}" for r in repos[:10])
                return f"🐙 Tus repos ({len(repos)}):\n\n{lista}", "github"

        # Stats
        if re.search(r"estadisticas|stats|cuanto\s+sabes|estado\s+del\s+sistema", normalizar(texto)):
            return self._stats_texto(), "sistema"

        # Historial
        if re.search(r"(?:limpia|borra)\s+historial", normalizar(texto)):
            self.memory.limpiar_historial()
            self._contexto.clear()
            return "🗑️ Historial limpiado. ¡Empezamos de cero!", "sistema"

        return None

    def _stats_texto(self) -> str:
        s = self.memory.stats()
        f = s.get("por_fuente", {})
        nombre = self.memory.get_config("nombre_usuario", "Usuario")
        auto_stats = ""
        if self.automations:
            a = self.automations.stats()
            auto_stats = f"\n🤖 Workflows: **{a['total_workflows']}** ({a['activos']} activos, {a['total_ejecuciones']} ejecuciones)"
        return (
            f"📊 **Estado de PAKO** (para {nombre})\n\n"
            f"🧠 Conocimiento: **{s['total']}** entradas ({s['ok']} activas)\n"
            f"📚 Manual: {f.get('manual',0)}  |  🌐 Web: {f.get('web',0)}  |  🐙 GH: {f.get('github',0)}\n"
            f"⏳ Pendientes: {s['pendientes']}\n"
            f"💬 Historial: {s['historial_mensajes']} mensajes"
            f"{auto_stats}"
        )

    # ── Aprendizaje ───────────────────────────────────────────────

    def _intentar_aprender(self, texto: str) -> Optional[str]:
        for pat in [PATRON_APRENDER, PATRON_RECUERDA, PATRON_GUARDA]:
            m = pat.search(texto)
            if m:
                clave = re.sub(r"['\"""''`]", "", m.group(1)).strip()
                valor = re.sub(r"['\"""''`]", "", m.group(2)).strip()
                if len(clave) < 2 or len(valor) < 2:
                    return "Necesito más detalle. Ej: **'aprende que Python es un lenguaje de programación'**"
                ok, msg = self.memory.guardar_conocimiento(clave=clave, valor=valor, fuente="manual", confianza=1.0, auto_ok=True)
                self.fuzzy.enriquecer_vocabulario(tokenizar(clave))
                self._ultimo_tema = clave
                if "Ya lo sabía" in msg:
                    return f"✅ Ya sabía que **{clave}** es **{valor}**."
                return f"✅ ¡Aprendido! Ahora sé que **{clave}** es:\n\n_{valor}_\n\nLo recordaré siempre. 🧠"
        return None

    # ── Resolver contexto ─────────────────────────────────────────

    def _resolver_contexto(self, texto: str) -> str:
        norm = normalizar(texto)
        refs = ["eso","esto","el tema","lo mismo","lo anterior","eso que dijiste"]
        if any(r in norm for r in refs) and self._ultimo_tema:
            return texto + f" (sobre {self._ultimo_tema})"
        return texto

    # ── RESPONDER ─────────────────────────────────────────────────

    def responder(self, texto_usuario: str) -> tuple[str, str]:
        texto = texto_usuario.strip()[:2000]
        if not texto:
            return "No te he oído. ¿Puedes repetirlo?", ""

        # 1. Corrección fuzzy silenciosa
        texto_corr = self._corregir_entrada(texto)
        texto_res  = self._resolver_contexto(texto_corr)

        # 2. Comandos de sistema
        cmd = self._cmd_sistema(texto_res)
        if cmd:
            self._upd_ctx(texto, cmd[0], cmd[1])
            self.memory.agregar_mensaje("pako", cmd[0], cmd[1])
            return cmd

        # 3. Aprendizaje explícito
        r = self._intentar_aprender(texto_res)
        if r:
            self._upd_ctx(texto, r, "manual")
            self.memory.agregar_mensaje("pako", r, "manual")
            return r, "manual"

        # 4. Calculadora
        r_calc = calcular(texto_res)
        if r_calc:
            norm = normalizar(texto_res)
            kw_calc = {"cuanto","calcula","resultado","suma","resta","multiplica","divide","cuantos","opera"}
            if any(t in kw_calc for t in tokenizar(texto_res)) or bool(re.search(r"\d\s*[+\-*/^×÷]\s*\d", texto_res)):
                resp = f"🧮 El resultado es: **{r_calc}**"
                self.memory.agregar_mensaje("pako", resp, "calculo")
                return resp, "calculo"

        # 5. Análisis de datos
        norm_low = normalizar(texto_res)
        if any(w in norm_low for w in ["analiza","estadistica","media","promedio","datos","valores","numeros"]):
            r_anal = analizar_datos(texto_res)
            if r_anal:
                self.memory.agregar_mensaje("pako", r_anal, "calculo")
                return r_anal, "calculo"

        # 6. Intención directa (tiempo, aleatorio, saludo…)
        intent, conf = self.detectar_intencion(texto_res)

        if intent == "tiempo":
            r = self._hora_fecha(); self.memory.agregar_mensaje("pako", r, ""); return r, ""
        if intent == "aleatorio":
            r = self._aleatorio(texto_res); self.memory.agregar_mensaje("pako", r, ""); return r, ""
        if intent == "saludo" and conf >= 0.3:
            r = self._saludo(); self.memory.agregar_mensaje("pako", r, ""); return r, ""
        if intent == "memoria" and conf >= 0.3:
            r = self._stats_texto(); self.memory.agregar_mensaje("pako", r, "sistema"); return r, "sistema"
        if intent == "automatizacion" and conf >= 0.2:
            r = ("Para gestionar automatizaciones ve a la **página de Automatizaciones** en el menú lateral. 🤖\n\n"
                 "Ahí puedes crear flujos de trabajo con nodos, triggers y acciones — con **PAKO como motor de IA** para los nodos inteligentes.")
            self.memory.agregar_mensaje("pako", r, ""); return r, ""

        # 7. Memoria local
        resultados = self.memory.buscar(texto_res, limite=5)
        if resultados:
            # Fuzzy sobre los resultados también
            mejor = resultados[0]
            sim_fuzzy = self.fuzzy.similitud_consulta(texto_res, mejor.clave + " " + mejor.valor)
            if sim_fuzzy > 0.3 or len(resultados) > 0:
                self._ultimo_tema = texto_res[:50]
                resp = f"📚 {mejor.valor}"
                if mejor.confianza < 0.5:
                    resp += "\n\n_(Confianza media — di 'busca' para verificar)_"
                self._upd_ctx(texto, resp, "memoria")
                self.memory.agregar_mensaje("pako", resp, "memoria")
                return resp, "memoria"

        # 8. Web
        trigger_web = (
            intent == "buscar_web" or
            any(norm_low.startswith(t) for t in ["busca ","buscar ","que es ","como funciona ","para que sirve ","explica ","dime sobre ","quien es ","define "])
        )
        if trigger_web and self.web_agent and self.memory.get_config("busqueda_web_auto", True):
            self.buscando_web = True
            r_web = self._buscar_web(texto_res)
            self.buscando_web = False
            if r_web:
                self._ultimo_tema = texto_res[:50]
                self._upd_ctx(texto, r_web, "web")
                self.memory.agregar_mensaje("pako", r_web, "web")
                return r_web, "web"

        # 9. Intenciones base
        if intent in INTENCIONES and conf >= self.umbral:
            resps = INTENCIONES[intent]["respuestas"]
            if resps:
                r = random.choice(resps)
                self.memory.agregar_mensaje("pako", r, ""); return r, ""

        # 10. Auto-búsqueda web si la confianza es baja
        if self.web_agent and len(tokenizar(texto_res)) >= 2 and conf < 0.2:
            self.buscando_web = True
            r_web = self._buscar_web(texto_res)
            self.buscando_web = False
            if r_web:
                self._upd_ctx(texto, r_web, "web")
                self.memory.agregar_mensaje("pako", r_web, "web")
                return r_web, "web"

        # 11. Fallback
        r = random.choice(INTENCIONES["desconocido"]["respuestas"])
        self.memory.agregar_mensaje("pako", r, ""); return r, ""

    # ── Helpers ───────────────────────────────────────────────────

    def _buscar_web(self, texto: str) -> Optional[str]:
        if not self.web_agent:
            return None
        try:
            return self.web_agent.buscar_y_aprender(texto)
        except Exception as ex:
            self.memory.log("error", f"Web agent: {ex}")
            return None

    def _upd_ctx(self, txt: str, resp: str, fuente: str) -> None:
        self._contexto.append({"texto": txt, "respuesta": resp[:200], "fuente": fuente})
        if len(self._contexto) > 10:
            self._contexto = self._contexto[-10:]

    def _saludo(self) -> str:
        hora = time.localtime().tm_hour
        momento = "¡Buenos días" if hora < 12 else "¡Buenas tardes" if hora < 20 else "¡Buenas noches"
        nombre = self.memory.get_config("nombre_usuario", "")
        base   = f"{momento}{', ' + nombre if nombre and nombre != 'Usuario' else ''}! Soy PAKO. ¿En qué te ayudo?"
        s = self.memory.stats()
        if s["total"] > 0:
            base += f"\n\n💡 Tengo {s['total']} conceptos aprendidos."
        return base

    def _hora_fecha(self) -> str:
        loc   = time.localtime()
        dias  = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
        return (f"🕒 Son las **{loc.tm_hour:02d}:{loc.tm_min:02d}**. "
                f"Hoy es **{dias[loc.tm_wday]}, {loc.tm_mday} de {meses[loc.tm_mon-1]} de {loc.tm_year}**.")

    def _aleatorio(self, texto: str) -> str:
        nums = re.findall(r"\d+", texto)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            if a > b: a, b = b, a
            return f"🎲 Número aleatorio entre {a} y {b}: **{random.randint(a, b)}**"
        return f"🎲 Número aleatorio: **{random.randint(1, 100)}**"

    def stats(self) -> dict:
        ms = self.memory.stats()
        return {
            **ms,
            "web_agent":        self.web_agent is not None,
            "github_agent":     self.github_agent is not None,
            "github_conectado": bool(self.github_agent and self.github_agent.conectado),
            "buscando_web":     self.buscando_web,
            "vocabulario":      len(self._vocab),
        }
