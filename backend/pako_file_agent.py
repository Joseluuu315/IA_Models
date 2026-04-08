"""
pako_file_agent.py — Agente de lectura de archivos locales (SOLO LECTURA).

Lee archivos del usuario de carpetas específicas y configurables.
NUNCA borra, modifica ni ejecuta archivos.
"""

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pako_memory import PakoMemory

EXTENSIONES_PERMITIDAS = {
    ".txt", ".md", ".py", ".js", ".ts", ".java", ".go",
    ".rs", ".cpp", ".c", ".cs", ".rb", ".php", ".swift",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".sh", ".bat",
}

MAX_BYTES = 200_000


class PakoFileAgent:
    def __init__(self, memory: "PakoMemory"):
        self.memory = memory

    def _carpetas_permitidas(self) -> list[Path]:
        raw = self.memory.get_config("carpetas_permitidas", [])
        return [Path(c).expanduser().resolve() for c in raw if c]

    def _es_ruta_permitida(self, ruta: Path) -> bool:
        permitidas = self._carpetas_permitidas()
        if not permitidas:
            return False  # sin config, no se accede a nada
        ruta_res = ruta.resolve()
        return any(
            str(ruta_res).startswith(str(c)) for c in permitidas
        )

    def agregar_carpeta(self, carpeta: str) -> tuple[bool, str]:
        """Añade una carpeta a la lista de permitidas."""
        p = Path(carpeta).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return False, f"La carpeta '{carpeta}' no existe."
        carpetas = self.memory.get_config("carpetas_permitidas", [])
        if str(p) not in carpetas:
            carpetas.append(str(p))
            self.memory.set_config("carpetas_permitidas", carpetas)
        return True, f"Carpeta '{p}' añadida."

    def leer_archivo(self, ruta_str: str) -> tuple[Optional[str], str]:
        """
        Lee un archivo (SOLO LECTURA).
        Retorna (contenido, mensaje).
        """
        ruta = Path(ruta_str).expanduser().resolve()

        if not self._es_ruta_permitida(ruta):
            return None, f"Carpeta no permitida. Añade la carpeta con 'añade carpeta [ruta]'."

        if not ruta.exists():
            return None, f"Archivo no encontrado: {ruta}"

        if not ruta.is_file():
            return None, "La ruta no es un archivo."

        if ruta.suffix.lower() not in EXTENSIONES_PERMITIDAS:
            return None, f"Extensión '{ruta.suffix}' no soportada."

        tamanio = ruta.stat().st_size
        if tamanio > MAX_BYTES:
            return None, f"Archivo demasiado grande ({tamanio//1024}KB). Máximo: {MAX_BYTES//1024}KB."

        try:
            contenido = ruta.read_text(encoding="utf-8", errors="replace")
            return contenido, f"Leído: {ruta.name} ({tamanio} bytes)"
        except Exception as e:
            return None, f"Error al leer: {e}"

    def aprender_de_archivo(self, ruta_str: str) -> tuple[int, str]:
        """Lee un archivo y extrae conocimiento."""
        from pako_github_agent import _extraer_conocimiento_archivo

        contenido, msg = self.leer_archivo(ruta_str)
        if contenido is None:
            return 0, msg

        ruta = Path(ruta_str)
        entradas = _extraer_conocimiento_archivo(ruta.name, contenido)

        guardadas = 0
        for e in entradas:
            ok, _ = self.memory.guardar_conocimiento(
                clave=e["clave"], valor=e["valor"],
                fuente="archivo", confianza=e["confianza"],
                url=str(ruta),
                auto_ok=False,
            )
            if ok:
                guardadas += 1

        return guardadas, f"Extraídas {guardadas} entradas de '{ruta.name}'."

    def listar_carpeta(self, ruta_str: str) -> list[dict]:
        """Lista el contenido de una carpeta permitida."""
        ruta = Path(ruta_str).expanduser().resolve()
        if not self._es_ruta_permitida(ruta):
            return []
        if not ruta.is_dir():
            return []
        resultado = []
        for item in sorted(ruta.iterdir())[:50]:
            resultado.append({
                "nombre":    item.name,
                "tipo":      "carpeta" if item.is_dir() else "archivo",
                "extension": item.suffix.lower() if item.is_file() else "",
                "tamanio":   item.stat().st_size if item.is_file() else 0,
            })
        return resultado
