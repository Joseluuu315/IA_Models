"""
pako_web_agent.py — Agente de navegación web de PAKO.

Busca información en internet, extrae conocimiento relevante
y lo propone para guardarse en la memoria de PAKO.

Usa solo la librería estándar de Python (urllib) + html.parser.
Sin dependencias externas obligatorias.
"""

import re
import time
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pako_memory import PakoMemory


# ══════════════════════════════════════════════════════════════════
# PARSER DE HTML
# ══════════════════════════════════════════════════════════════════

class TextExtractor(HTMLParser):
    """Extrae texto limpio de HTML, ignorando scripts, estilos, etc."""

    IGNORAR_TAGS = {"script","style","nav","footer","header","aside",
                    "form","button","input","select","option","iframe",
                    "noscript","svg","img","figure","figcaption"}

    def __init__(self):
        super().__init__()
        self.textos:    list[str] = []
        self._ignorar:  int       = 0
        self._titulo:   str       = ""
        self._en_titulo: bool     = False

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR_TAGS:
            self._ignorar += 1
        if tag == "title":
            self._en_titulo = True

    def handle_endtag(self, tag):
        if tag in self.IGNORAR_TAGS and self._ignorar > 0:
            self._ignorar -= 1
        if tag == "title":
            self._en_titulo = False

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
        if self._en_titulo:
            self._titulo = data
            return
        if self._ignorar == 0 and len(data) > 10:
            self.textos.append(data)

    def get_texto(self) -> str:
        return "\n".join(self.textos)

    def get_titulo(self) -> str:
        return self._titulo


def _limpiar_texto(texto: str) -> str:
    """Limpia y normaliza texto extraído de HTML."""
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Eliminar líneas muy cortas (menú, botones)
    lineas = [l.strip() for l in texto.split("\n") if len(l.strip()) > 20]
    return "\n".join(lineas[:80])  # máx 80 párrafos


def _extraer_oraciones_relevantes(texto: str, query: str, max_oraciones: int = 5) -> list[str]:
    """Extrae las oraciones más relevantes para la query."""
    from pako_brain import tokenizar, tokens_significativos
    tokens_q = set(tokens_significativos(tokenizar(query)))

    oraciones = re.split(r"[.!?]\s+", texto)
    scored = []
    for oracion in oraciones:
        oracion = oracion.strip()
        if len(oracion) < 30:
            continue
        tokens_o = set(tokens_significativos(tokenizar(oracion)))
        if not tokens_o:
            continue
        comunes = tokens_q & tokens_o
        score   = len(comunes) / max(len(tokens_q), 1)
        scored.append((score, oracion))

    scored.sort(key=lambda x: -x[0])
    return [o for _, o in scored[:max_oraciones] if _ > 0.1]


# ══════════════════════════════════════════════════════════════════
# FUENTES DE BÚSQUEDA
# ══════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PAKO-Bot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

def _fetch(url: str, timeout: int = 8) -> Optional[str]:
    """Descarga una URL y devuelve el HTML."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "html" not in content_type and "text" not in content_type:
                return None
            raw = resp.read(300_000)  # máx 300KB
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].strip().split(";")[0]
            try:
                return raw.decode(encoding, errors="replace")
            except Exception:
                return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def buscar_ddg(query: str) -> list[dict]:
    """
    Busca en DuckDuckGo (HTML) y devuelve lista de resultados.
    Usa el endpoint HTML de DDG que no requiere API key.
    """
    q = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}&kl=es-es"
    html = _fetch(url)
    if not html:
        return []

    resultados = []
    # Extraer enlaces de resultados de DDG HTML
    patron_resultado = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
        html
    )
    patron_snippet = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>([^<]+)</a>',
        html
    )

    for i, (href, titulo) in enumerate(patron_resultado[:5]):
        snippet = patron_snippet[i] if i < len(patron_snippet) else ""
        resultados.append({
            "url":     href,
            "titulo":  titulo.strip(),
            "snippet": snippet.strip(),
        })

    return resultados


def buscar_wikipedia(query: str, lang: str = "es") -> Optional[dict]:
    """
    Busca directamente en la API de Wikipedia.
    Más fiable que scraping general.
    """
    q = urllib.parse.quote_plus(query)
    # Búsqueda de artículo
    api_search = (
        f"https://{lang}.wikipedia.org/w/api.php"
        f"?action=query&list=search&srsearch={q}&format=json&srlimit=1"
    )
    try:
        req = urllib.request.Request(api_search, headers={"User-Agent": "PAKO-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            import json
            data = json.loads(r.read().decode("utf-8"))
        hits = data.get("query", {}).get("search", [])
        if not hits:
            # Intentar en inglés si no hay resultados en español
            if lang == "es":
                return buscar_wikipedia(query, lang="en")
            return None
        titulo_art = hits[0]["pageid"]
        snippet    = re.sub(r"<[^>]+>", "", hits[0].get("snippet",""))

        # Obtener extracto del artículo
        api_extract = (
            f"https://{lang}.wikipedia.org/w/api.php"
            f"?action=query&prop=extracts&exintro&explaintext"
            f"&pageids={titulo_art}&format=json"
        )
        req2 = urllib.request.Request(api_extract, headers={"User-Agent": "PAKO-Bot/1.0"})
        with urllib.request.urlopen(req2, timeout=8) as r2:
            data2 = json.loads(r2.read().decode("utf-8"))

        pages = data2.get("query", {}).get("pages", {})
        for page in pages.values():
            extracto = page.get("extract", "")
            if extracto:
                # Tomar los primeros 3 párrafos
                parrafos = [p.strip() for p in extracto.split("\n") if len(p.strip()) > 40]
                resumen = " ".join(parrafos[:3])
                return {
                    "titulo":  page.get("title",""),
                    "extracto": resumen[:1000],
                    "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(page.get('title',''))}",
                }
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════
# PROCESADOR DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════

def _normalizar_query(texto: str) -> str:
    """Limpia la query del usuario para buscar."""
    texto = texto.lower().strip()
    for prefix in ["busca ","buscar ","qué es ","que es ","cómo funciona ",
                   "como funciona ","explica ","explícame ","dime sobre ",
                   "información sobre ","informacion sobre ","cuéntame sobre "]:
        if texto.startswith(prefix):
            texto = texto[len(prefix):]
            break
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        texto = texto.replace(src, dst)
    return texto.strip()


def _texto_a_conocimiento(query: str, texto: str, url: str) -> list[dict]:
    """
    Convierte texto extraído en pares clave-valor de conocimiento.
    """
    conocimiento = []
    oraciones = _extraer_oraciones_relevantes(texto, query, max_oraciones=4)

    if oraciones:
        # Principal: combinación de las mejores oraciones
        resumen = ". ".join(oraciones[:2])
        if len(resumen) > 50:
            conocimiento.append({
                "clave":     query,
                "valor":     resumen,
                "confianza": 0.7,
                "url":       url,
            })

        # Secundario: oraciones adicionales
        for i, oracion in enumerate(oraciones[2:], 1):
            if len(oracion) > 60:
                conocimiento.append({
                    "clave":     f"{query} (detalle {i})",
                    "valor":     oracion,
                    "confianza": 0.5,
                    "url":       url,
                })

    return conocimiento


# ══════════════════════════════════════════════════════════════════
# AGENTE WEB PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoWebAgent:
    def __init__(self, memory: "PakoMemory"):
        self.memory  = memory
        self.activo  = True
        self._cache: dict[str, str] = {}  # query → respuesta cacheada

    def buscar_y_aprender(self, texto_usuario: str) -> Optional[str]:
        """
        Punto de entrada principal: busca información y retorna respuesta.
        """
        if not self.activo:
            return None

        query = _normalizar_query(texto_usuario)
        if not query or len(query) < 3:
            return None

        # Cache en sesión
        if query in self._cache:
            return f"🌐 (cached) {self._cache[query]}"

        self.memory.log("busqueda", f"Buscando: '{query}'")

        # Intentar Wikipedia primero (más fiable)
        resultado_wiki = buscar_wikipedia(query)
        if resultado_wiki:
            extracto = resultado_wiki["extracto"]
            url      = resultado_wiki["url"]
            titulo   = resultado_wiki["titulo"]

            # Guardar en memoria
            if len(extracto) > 50:
                self.memory.guardar_conocimiento(
                    clave=query,
                    valor=extracto[:600],
                    fuente="web",
                    confianza=0.75,
                    url=url,
                    auto_ok=self.memory.get_config("autoaprendizaje_web", False),
                )

            # Generar respuesta
            resp = f"🌐 **{titulo}**\n\n{extracto[:500]}"
            if len(extracto) > 500:
                resp += "..."
            resp += f"\n\n📎 Fuente: {url}"
            self._cache[query] = resp
            return resp

        # Fallback: DuckDuckGo
        resultados = buscar_ddg(query)
        if resultados:
            mejor = resultados[0]
            snippet = mejor.get("snippet", "")
            if snippet and len(snippet) > 30:
                self.memory.guardar_conocimiento(
                    clave=query,
                    valor=snippet,
                    fuente="web",
                    confianza=0.5,
                    url=mejor["url"],
                    auto_ok=False,
                )
                resp = f"🌐 **{mejor['titulo']}**\n\n{snippet}\n\n📎 {mejor['url']}"
                self._cache[query] = resp
                return resp

        self.memory.log("busqueda", f"Sin resultados para: '{query}'")
        return None

    def aprender_de_url(self, url: str) -> tuple[int, str]:
        """
        Lee una URL específica y extrae conocimiento.
        Retorna (número de entradas guardadas, mensaje).
        """
        html = _fetch(url)
        if not html:
            return 0, "No se pudo acceder a la URL."

        parser = TextExtractor()
        parser.feed(html)
        texto  = _limpiar_texto(parser.get_texto())
        titulo = parser.get_titulo()

        if len(texto) < 100:
            return 0, "Contenido insuficiente en la página."

        # Usar el título como query
        query = titulo or url.split("/")[-1]
        entradas = _texto_a_conocimiento(query, texto, url)

        guardadas = 0
        for e in entradas:
            ok, _ = self.memory.guardar_conocimiento(
                clave=e["clave"],
                valor=e["valor"],
                fuente="web",
                confianza=e["confianza"],
                url=e["url"],
                auto_ok=False,  # Siempre validar URLs manuales
            )
            if ok:
                guardadas += 1

        return guardadas, f"Se extrajeron {guardadas} entradas de conocimiento de '{titulo or url}'."
