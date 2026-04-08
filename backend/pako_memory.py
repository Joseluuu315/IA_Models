"""
pako_memory.py — Gestión de toda la memoria persistente de PAKO.

Almacena:
  - Conocimiento aprendido (manual, web, github, archivos)
  - Historial de conversaciones
  - Actividad y logs del sistema
  - Configuración de usuario
"""

import json
import time
import hashlib
import threading
from pathlib import Path
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional


# ══════════════════════════════════════════════════════════════════
# TIPOS DE FUENTE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════

SOURCE_MANUAL   = "manual"
SOURCE_WEB      = "web"
SOURCE_GITHUB   = "github"
SOURCE_FILE     = "archivo"
SOURCE_BASE     = "base"

STATUS_OK       = "ok"
STATUS_PENDING  = "pendiente"
STATUS_REJECTED = "rechazado"


@dataclass
class EntradaConocimiento:
    clave:       str
    valor:       str
    fuente:      str          # manual | web | github | archivo | base
    status:      str          # ok | pendiente | rechazado
    confianza:   float        # 0.0 - 1.0
    timestamp:   float
    url:         str  = ""
    repo:        str  = ""
    veces_usado: int  = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "EntradaConocimiento":
        return EntradaConocimiento(**d)


@dataclass
class EntradaActividad:
    tipo:      str    # aprendizaje | busqueda | error | sistema
    mensaje:   str
    timestamp: float
    detalle:   str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════
# MEMORIA PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class PakoMemory:
    """
    Gestiona toda la persistencia de PAKO.
    Thread-safe con lock interno.
    """

    def __init__(self, data_dir: str = "."):
        self._dir   = Path(data_dir)
        self._lock  = threading.Lock()

        self._ruta_conocimiento = self._dir / "pako_conocimiento.json"
        self._ruta_config       = self._dir / "pako_config.json"
        self._ruta_actividad    = self._dir / "pako_actividad.json"

        # Estructuras en memoria
        self.conocimiento: dict[str, EntradaConocimiento] = {}
        self.actividad:    deque = deque(maxlen=500)
        self.config:       dict  = self._config_default()

        self._cargar_todo()

    # ── Config ───────────────────────────────────────────────────

    def _config_default(self) -> dict:
        return {
            "autoaprendizaje_web":    False,
            "autoaprendizaje_github": False,
            "validacion_manual":      True,
            "carpetas_permitidas":    [],
            "github_token":           "",
            "max_entradas":           10000,
            "umbral_confianza_auto":  0.6,
        }

    def get_config(self, clave: str, default=None):
        return self.config.get(clave, default)

    def set_config(self, clave: str, valor) -> None:
        with self._lock:
            self.config[clave] = valor
            self._guardar_config()

    # ── Carga y guardado ─────────────────────────────────────────

    def _cargar_todo(self) -> None:
        # Conocimiento
        if self._ruta_conocimiento.exists():
            try:
                raw = json.loads(self._ruta_conocimiento.read_text(encoding="utf-8"))
                # Formato legacy (paco_aprendido.json): {hashes:{}, raw:{}}
                if "raw" in raw and "hashes" in raw:
                    for clave, valor in raw["raw"].items():
                        clave_limpia = clave.strip("[]")
                        e = EntradaConocimiento(
                            clave=clave_limpia, valor=valor,
                            fuente=SOURCE_BASE, status=STATUS_OK,
                            confianza=1.0, timestamp=time.time()
                        )
                        self.conocimiento[self._hash(clave_limpia)] = e
                # Formato nativo
                elif "entradas" in raw:
                    for h, d in raw["entradas"].items():
                        self.conocimiento[h] = EntradaConocimiento.from_dict(d)
            except Exception as ex:
                self._log("error", f"Error cargando conocimiento: {ex}")

        # Config
        if self._ruta_config.exists():
            try:
                saved = json.loads(self._ruta_config.read_text(encoding="utf-8"))
                self.config.update(saved)
            except Exception:
                pass

        # Actividad
        if self._ruta_actividad.exists():
            try:
                raw = json.loads(self._ruta_actividad.read_text(encoding="utf-8"))
                for item in raw.get("actividad", []):
                    self.actividad.append(EntradaActividad(**item))
            except Exception:
                pass

    def cargar_desde_json_legacy(self, ruta: str) -> int:
        """Importa un paco_aprendido.json antiguo. Retorna nº de entradas importadas."""
        p = Path(ruta)
        if not p.exists():
            return 0
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            raw_dict = raw.get("raw", {})
            count = 0
            for clave, valor in raw_dict.items():
                clave_limpia = clave.strip("[]")
                self.guardar_conocimiento(
                    clave=clave_limpia, valor=valor,
                    fuente=SOURCE_BASE, confianza=1.0, auto_ok=True
                )
                count += 1
            return count
        except Exception as ex:
            self._log("error", f"Error importando legacy: {ex}")
            return 0

    def _guardar_conocimiento(self) -> None:
        data = {"entradas": {h: e.to_dict() for h, e in self.conocimiento.items()}}
        self._ruta_conocimiento.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _guardar_config(self) -> None:
        self._ruta_config.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _guardar_actividad(self) -> None:
        data = {"actividad": [a.to_dict() for a in self.actividad]}
        self._ruta_actividad.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Conocimiento ─────────────────────────────────────────────

    def _hash(self, clave: str) -> str:
        return hashlib.md5(clave.lower().strip().encode()).hexdigest()

    def guardar_conocimiento(
        self,
        clave: str,
        valor: str,
        fuente: str = SOURCE_MANUAL,
        confianza: float = 1.0,
        url: str = "",
        repo: str = "",
        auto_ok: bool = False,
    ) -> tuple[bool, str]:
        """
        Guarda una entrada de conocimiento.
        Retorna (éxito, mensaje).
        Con validacion_manual=True y auto_ok=False → queda en PENDING.
        """
        clave = clave.strip()
        valor = valor.strip()
        if not clave or not valor:
            return False, "Clave o valor vacíos."

        h = self._hash(clave)

        with self._lock:
            # Comprobar duplicado
            if h in self.conocimiento:
                existing = self.conocimiento[h]
                if existing.valor.lower() == valor.lower():
                    existing.veces_usado += 1
                    self._guardar_conocimiento()
                    return True, "Ya lo sabía."
                # Actualizar si nueva confianza es mayor
                if confianza >= existing.confianza:
                    existing.valor     = valor
                    existing.fuente    = fuente
                    existing.confianza = confianza
                    existing.timestamp = time.time()
                    self._guardar_conocimiento()
                    return True, "Actualizado."

            # Determinar status
            necesita_validacion = (
                self.config.get("validacion_manual", True)
                and not auto_ok
                and fuente in (SOURCE_WEB, SOURCE_GITHUB, SOURCE_FILE)
                and confianza < self.config.get("umbral_confianza_auto", 0.6)
            )
            status = STATUS_PENDING if necesita_validacion else STATUS_OK

            entrada = EntradaConocimiento(
                clave=clave, valor=valor,
                fuente=fuente, status=status,
                confianza=confianza,
                timestamp=time.time(),
                url=url, repo=repo
            )
            self.conocimiento[h] = entrada
            self._guardar_conocimiento()

        msg = f"Guardado ({'pendiente de validación' if status == STATUS_PENDING else 'OK'})"
        self._log("aprendizaje", f"[{fuente}] {clave[:50]} → {valor[:80]}")
        return True, msg

    def aprobar_pendiente(self, h: str) -> bool:
        with self._lock:
            if h in self.conocimiento and self.conocimiento[h].status == STATUS_PENDING:
                self.conocimiento[h].status = STATUS_OK
                self._guardar_conocimiento()
                return True
        return False

    def rechazar_pendiente(self, h: str) -> bool:
        with self._lock:
            if h in self.conocimiento:
                self.conocimiento[h].status = STATUS_REJECTED
                self._guardar_conocimiento()
                return True
        return False

    def buscar(self, texto: str, solo_ok: bool = True) -> list[EntradaConocimiento]:
        """Devuelve entradas cuya clave coincide aproximadamente con el texto."""
        from pako_brain import tokenizar, tokens_significativos
        tokens_in = set(tokens_significativos(tokenizar(texto)))
        resultados = []
        for entrada in self.conocimiento.values():
            if solo_ok and entrada.status != STATUS_OK:
                continue
            tokens_clave = set(tokens_significativos(tokenizar(entrada.clave)))
            if not tokens_clave:
                continue
            comunes = tokens_in & tokens_clave
            sim = len(comunes) / max(len(tokens_clave), len(tokens_in), 1)
            if sim >= 0.35:
                resultados.append((sim, entrada))
        resultados.sort(key=lambda x: -x[0])
        return [e for _, e in resultados[:5]]

    def get_pendientes(self) -> list[dict]:
        return [
            {"hash": h, **e.to_dict()}
            for h, e in self.conocimiento.items()
            if e.status == STATUS_PENDING
        ]

    def get_recientes(self, n: int = 20) -> list[dict]:
        entradas = sorted(
            self.conocimiento.values(),
            key=lambda e: e.timestamp, reverse=True
        )
        return [e.to_dict() for e in entradas[:n]]

    def stats(self) -> dict:
        total = len(self.conocimiento)
        por_fuente: dict[str, int] = {}
        pendientes = 0
        for e in self.conocimiento.values():
            por_fuente[e.fuente] = por_fuente.get(e.fuente, 0) + 1
            if e.status == STATUS_PENDING:
                pendientes += 1
        return {
            "total": total,
            "por_fuente": por_fuente,
            "pendientes": pendientes,
            "actividad_reciente": len(self.actividad),
        }

    # ── Actividad / Logs ─────────────────────────────────────────

    def _log(self, tipo: str, mensaje: str, detalle: str = "") -> None:
        entrada = EntradaActividad(
            tipo=tipo, mensaje=mensaje,
            timestamp=time.time(), detalle=detalle
        )
        self.actividad.appendleft(entrada)
        # Guardar de forma async-ish (cada 10 eventos)
        if len(self.actividad) % 10 == 0:
            self._guardar_actividad()

    def log(self, tipo: str, mensaje: str, detalle: str = "") -> None:
        self._log(tipo, mensaje, detalle)

    def get_actividad(self, n: int = 50) -> list[dict]:
        return [a.to_dict() for a in list(self.actividad)[:n]]
