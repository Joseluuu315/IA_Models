"""
pako_github_agent.py — Agente de integración con GitHub de PAKO.

Lee repositorios del usuario autenticado (SOLO LECTURA):
  - README.md
  - Código fuente (.py, .js, .ts, .java, .go, etc.)
  - Extrae conocimiento: funciones, clases, comentarios, docstrings

NUNCA modifica ni ejecuta código externo.
"""

import re
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pako_memory import PakoMemory


GITHUB_API = "https://api.github.com"
HEADERS_BASE = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "PAKO-Bot/1.0",
}

EXTENSIONES_CODIGO = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".kt", ".go", ".rs", ".cpp",
    ".c", ".cs", ".rb", ".php", ".swift",
    ".md", ".txt", ".yaml", ".yml", ".json",
    ".toml", ".ini", ".cfg",
}

MAX_ARCHIVO_BYTES = 150_000   # 150 KB máx por archivo
MAX_ARCHIVOS_REPO = 30        # máx archivos por repositorio


# ══════════════════════════════════════════════════════════════════
# CLIENTE API GITHUB
# ══════════════════════════════════════════════════════════════════

class GitHubClient:
    def __init__(self, token: str):
        self.token = token

    def _headers(self) -> dict:
        h = HEADERS_BASE.copy()
        if self.token:
            h["Authorization"] = f"token {self.token}"
        return h

    def _get(self, path: str) -> Optional[dict]:
        url = f"{GITHUB_API}{path}" if not path.startswith("http") else path
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"_error": e.code, "_msg": str(e)}
        except Exception as e:
            return {"_error": str(e)}

    def _get_raw(self, url: str) -> Optional[bytes]:
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read(MAX_ARCHIVO_BYTES)
        except Exception:
            return None

    def get_user(self) -> Optional[dict]:
        return self._get("/user")

    def get_repos(self) -> list[dict]:
        repos = []
        page  = 1
        while len(repos) < 100:
            data = self._get(f"/user/repos?per_page=30&page={page}&sort=updated")
            if not isinstance(data, list) or not data:
                break
            repos.extend(data)
            page += 1
        return repos

    def get_readme(self, owner: str, repo: str) -> Optional[str]:
        data = self._get(f"/repos/{owner}/{repo}/readme")
        if not data or "_error" in data:
            return None
        import base64
        try:
            content = data.get("content", "")
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None

    def get_tree(self, owner: str, repo: str, branch: str = "") -> list[dict]:
        if not branch:
            repo_data = self._get(f"/repos/{owner}/{repo}")
            if not repo_data or "_error" in repo_data:
                return []
            branch = repo_data.get("default_branch", "main")

        data = self._get(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
        if not data or "_error" in data:
            return []
        return data.get("tree", [])

    def get_file_content(self, url: str) -> Optional[str]:
        raw = self._get_raw(url)
        if not raw:
            return None
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None

    def verificar_token(self) -> tuple[bool, str]:
        data = self.get_user()
        if not data or "_error" in data:
            return False, "Token inválido o sin conexión."
        return True, data.get("login", "usuario")


# ══════════════════════════════════════════════════════════════════
# EXTRACTOR DE CONOCIMIENTO DE CÓDIGO
# ══════════════════════════════════════════════════════════════════

def _extraer_de_readme(texto: str, repo_nombre: str) -> list[dict]:
    """Extrae conocimiento de un README.md."""
    entradas = []

    # Título del proyecto (primera línea # )
    m_titulo = re.search(r"^#\s+(.+)", texto, re.MULTILINE)
    titulo = m_titulo.group(1).strip() if m_titulo else repo_nombre

    # Descripción: primeros párrafos antes de la primera sección
    partes = re.split(r"\n##?\s+", texto, maxsplit=1)
    intro = partes[0] if partes else texto
    intro = re.sub(r"#[^#].*", "", intro)        # quitar título
    intro = re.sub(r"!\[.*?\]\(.*?\)", "", intro) # quitar imágenes
    intro = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", intro)  # links → texto
    intro = re.sub(r"```.*?```", "", intro, flags=re.DOTALL)  # quitar código
    intro = re.sub(r"\s+", " ", intro).strip()

    if len(intro) > 50:
        entradas.append({
            "clave": f"repo {repo_nombre}",
            "valor": f"{titulo}: {intro[:400]}",
            "confianza": 0.8,
        })

    # Secciones del README
    secciones = re.findall(r"^##?\s+(.+)\n([\s\S]+?)(?=^##?\s|\Z)", texto, re.MULTILINE)
    for nombre_sec, contenido_sec in secciones[:5]:
        nombre_sec = nombre_sec.strip().lower()
        contenido_sec = re.sub(r"```.*?```", "", contenido_sec, flags=re.DOTALL)
        contenido_sec = re.sub(r"\s+", " ", contenido_sec).strip()
        if len(contenido_sec) > 60:
            entradas.append({
                "clave": f"repo {repo_nombre} {nombre_sec}",
                "valor": contenido_sec[:300],
                "confianza": 0.65,
            })

    return entradas


def _extraer_de_python(codigo: str, archivo: str) -> list[dict]:
    """Extrae docstrings, funciones y clases de código Python."""
    entradas = []
    nombre_base = archivo.replace(".py", "").replace("/",".")

    # Docstring del módulo
    m_doc = re.match(r'^\s*"""([\s\S]+?)"""', codigo)
    if m_doc:
        doc = m_doc.group(1).strip()
        if len(doc) > 20:
            entradas.append({
                "clave": f"modulo {nombre_base}",
                "valor": doc[:300],
                "confianza": 0.7,
            })

    # Funciones con docstring
    patron_func = re.finditer(
        r'def\s+(\w+)\s*\([^)]*\)\s*(?:->[^:]+)?\s*:\s*\n\s*"""([\s\S]+?)"""',
        codigo
    )
    for m in patron_func:
        fname = m.group(1)
        doc   = re.sub(r"\s+", " ", m.group(2)).strip()
        if fname.startswith("_") or len(doc) < 15:
            continue
        entradas.append({
            "clave": f"funcion {nombre_base}.{fname}",
            "valor": doc[:250],
            "confianza": 0.65,
        })

    # Clases con docstring
    patron_clase = re.finditer(
        r'class\s+(\w+)[^:]*:\s*\n\s*"""([\s\S]+?)"""',
        codigo
    )
    for m in patron_clase:
        cname = m.group(1)
        doc   = re.sub(r"\s+", " ", m.group(2)).strip()
        if len(doc) < 15:
            continue
        entradas.append({
            "clave": f"clase {nombre_base}.{cname}",
            "valor": doc[:250],
            "confianza": 0.65,
        })

    return entradas


def _extraer_de_js_ts(codigo: str, archivo: str) -> list[dict]:
    """Extrae comentarios JSDoc y funciones de JS/TS."""
    entradas = []
    nombre_base = re.sub(r"\.(js|ts|jsx|tsx)$", "", archivo).replace("/",".")

    # Comentarios JSDoc
    patron_jsdoc = re.finditer(
        r'/\*\*([\s\S]+?)\*/\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)',
        codigo
    )
    for m in patron_jsdoc:
        doc   = re.sub(r"\s*\*\s*", " ", m.group(1)).strip()
        doc   = re.sub(r"@\w+\s+[^\n]+", "", doc).strip()
        fname = m.group(2)
        if len(doc) < 10:
            continue
        entradas.append({
            "clave": f"funcion {nombre_base}.{fname}",
            "valor": doc[:250],
            "confianza": 0.6,
        })

    return entradas


def _extraer_conocimiento_archivo(ruta: str, contenido: str) -> list[dict]:
    """Dispatch según extensión."""
    ext = "." + ruta.rsplit(".", 1)[-1].lower() if "." in ruta else ""
    nombre = ruta.split("/")[-1]

    if ext == ".md":
        return _extraer_de_readme(contenido, nombre.replace(".md", ""))
    if ext == ".py":
        return _extraer_de_python(contenido, ruta)
    if ext in {".js", ".ts", ".jsx", ".tsx"}:
        return _extraer_de_js_ts(contenido, ruta)
    return []


# ══════════════════════════════════════════════════════════════════
# AGENTE GITHUB PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoGitHubAgent:
    def __init__(self, memory: "PakoMemory"):
        self.memory  = memory
        self._client: Optional[GitHubClient] = None
        self._usuario: str = ""

    @property
    def conectado(self) -> bool:
        return self._client is not None and bool(self._usuario)

    def conectar(self, token: str) -> tuple[bool, str]:
        """Conecta con GitHub usando un Personal Access Token."""
        client = GitHubClient(token)
        ok, result = client.verificar_token()
        if ok:
            self._client  = client
            self._usuario = result
            self.memory.set_config("github_token", token)
            self.memory.log("sistema", f"GitHub conectado como @{result}")
            return True, f"Conectado como @{result}"
        return False, result

    def reconectar(self) -> bool:
        """Reconecta usando el token guardado en config."""
        token = self.memory.get_config("github_token", "")
        if not token:
            return False
        ok, _ = self.conectar(token)
        return ok

    def listar_repos(self) -> list[dict]:
        if not self.conectado:
            return []
        repos = self._client.get_repos()
        return [
            {
                "nombre":   r.get("name",""),
                "desc":     r.get("description",""),
                "lang":     r.get("language",""),
                "stars":    r.get("stargazers_count",0),
                "privado":  r.get("private", False),
                "url":      r.get("html_url",""),
                "actualizado": r.get("updated_at",""),
            }
            for r in repos
        ]

    def aprender_de_repo(self, repo_nombre: str) -> tuple[int, str]:
        """
        Lee un repositorio completo y extrae conocimiento.
        SOLO LECTURA. Retorna (n_entradas, mensaje).
        """
        if not self.conectado:
            return 0, "No conectado a GitHub."

        owner = self._usuario
        self.memory.log("aprendizaje", f"Leyendo repo: {owner}/{repo_nombre}")

        guardadas = 0

        # 1. README
        readme = self._client.get_readme(owner, repo_nombre)
        if readme:
            entradas = _extraer_de_readme(readme, repo_nombre)
            for e in entradas:
                ok, _ = self.memory.guardar_conocimiento(
                    clave=e["clave"], valor=e["valor"],
                    fuente="github", confianza=e["confianza"],
                    repo=f"{owner}/{repo_nombre}",
                    auto_ok=self.memory.get_config("autoaprendizaje_github", False),
                )
                if ok:
                    guardadas += 1

        # 2. Árbol de archivos
        tree = self._client.get_tree(owner, repo_nombre)
        archivos_code = [
            item for item in tree
            if item.get("type") == "blob"
            and "." in item.get("path","")
            and "." + item["path"].rsplit(".",1)[-1].lower() in EXTENSIONES_CODIGO
            and item.get("size", 0) < MAX_ARCHIVO_BYTES
        ][:MAX_ARCHIVOS_REPO]

        for item in archivos_code:
            ruta    = item["path"]
            url_raw = item.get("url","")
            if not url_raw:
                continue

            # Obtener contenido raw
            data = self._client._get(url_raw)
            if not data or "_error" in data:
                continue

            import base64
            try:
                contenido = base64.b64decode(
                    data.get("content","").replace("\n","")
                ).decode("utf-8", errors="replace")
            except Exception:
                continue

            entradas = _extraer_conocimiento_archivo(ruta, contenido)
            for e in entradas:
                ok, _ = self.memory.guardar_conocimiento(
                    clave=e["clave"], valor=e["valor"],
                    fuente="github", confianza=e["confianza"],
                    repo=f"{owner}/{repo_nombre}",
                    auto_ok=self.memory.get_config("autoaprendizaje_github", False),
                )
                if ok:
                    guardadas += 1

        msg = f"Aprendidas {guardadas} entradas del repo '{repo_nombre}'."
        self.memory.log("aprendizaje", msg)
        return guardadas, msg

    def aprender_de_todos_los_repos(self) -> tuple[int, str]:
        """Aprende de todos los repos del usuario. Puede tardar varios segundos."""
        if not self.conectado:
            return 0, "No conectado."
        repos = self.listar_repos()
        total = 0
        for repo in repos:
            n, _ = self.aprender_de_repo(repo["nombre"])
            total += n
        return total, f"Total aprendido de {len(repos)} repositorios: {total} entradas."

    def info(self) -> dict:
        if not self.conectado:
            return {"conectado": False}
        repos = self.listar_repos()
        return {
            "conectado": True,
            "usuario":   self._usuario,
            "repos":     len(repos),
            "lista":     repos[:10],
        }
