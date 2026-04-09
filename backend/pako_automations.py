"""
pako_automations.py — Motor de automatizaciones de PAKO (lógica n8n).

Gestiona:
  - Definición y almacenamiento de flujos (workflows)
  - Tipos de nodos: trigger, acción, condición, IA, transformación
  - Ejecución simulada de flujos
  - PAKO como motor IA en nodos de procesamiento de lenguaje
"""

import json
import time
import uuid
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pako_memory import PakoMemory
    from pako_brain  import PakoBrain


# ══════════════════════════════════════════════════════════════════
# TIPOS DE NODOS DISPONIBLES
# ══════════════════════════════════════════════════════════════════

TIPOS_NODO = {
    # TRIGGERS
    "trigger_webhook":   {"categoria": "trigger",  "label": "Webhook",         "icono": "🔗", "color": "#f59e0b"},
    "trigger_schedule":  {"categoria": "trigger",  "label": "Programación",    "icono": "⏰", "color": "#f59e0b"},
    "trigger_email":     {"categoria": "trigger",  "label": "Email recibido",  "icono": "📧", "color": "#f59e0b"},
    "trigger_manual":    {"categoria": "trigger",  "label": "Manual",          "icono": "▶️", "color": "#f59e0b"},
    "trigger_formulario":{"categoria": "trigger",  "label": "Formulario",      "icono": "📋", "color": "#f59e0b"},

    # ACCIONES
    "accion_email":      {"categoria": "accion",   "label": "Enviar Email",    "icono": "📤", "color": "#6366f1"},
    "accion_http":       {"categoria": "accion",   "label": "Petición HTTP",   "icono": "🌐", "color": "#6366f1"},
    "accion_slack":      {"categoria": "accion",   "label": "Slack",           "icono": "💬", "color": "#6366f1"},
    "accion_telegram":   {"categoria": "accion",   "label": "Telegram",        "icono": "✈️", "color": "#6366f1"},
    "accion_bbdd":       {"categoria": "accion",   "label": "Base de datos",   "icono": "🗄️", "color": "#6366f1"},
    "accion_archivo":    {"categoria": "accion",   "label": "Archivo",         "icono": "📁", "color": "#6366f1"},
    "accion_notificacion":{"categoria":"accion",   "label": "Notificación",    "icono": "🔔", "color": "#6366f1"},

    # LÓGICA / CONTROL
    "logica_condicion":  {"categoria": "logica",   "label": "Condición SI/NO", "icono": "🔀", "color": "#10b981"},
    "logica_bucle":      {"categoria": "logica",   "label": "Bucle",           "icono": "🔁", "color": "#10b981"},
    "logica_espera":     {"categoria": "logica",   "label": "Esperar",         "icono": "⏳", "color": "#10b981"},
    "logica_merge":      {"categoria": "logica",   "label": "Fusionar",        "icono": "🔗", "color": "#10b981"},
    "logica_split":      {"categoria": "logica",   "label": "Dividir",         "icono": "🔱", "color": "#10b981"},

    # IA (PAKO)
    "ia_resumir":        {"categoria": "ia",       "label": "Resumir texto",   "icono": "📝", "color": "#ec4899"},
    "ia_clasificar":     {"categoria": "ia",       "label": "Clasificar",      "icono": "🏷️", "color": "#ec4899"},
    "ia_sentimiento":    {"categoria": "ia",       "label": "Analizar sentimiento","icono": "😊", "color": "#ec4899"},
    "ia_extraer":        {"categoria": "ia",       "label": "Extraer datos",   "icono": "🔍", "color": "#ec4899"},
    "ia_generar":        {"categoria": "ia",       "label": "Generar texto",   "icono": "✨", "color": "#ec4899"},
    "ia_traducir":       {"categoria": "ia",       "label": "Traducir",        "icono": "🌍", "color": "#ec4899"},
    "ia_responder":      {"categoria": "ia",       "label": "Responder con IA","icono": "🤖", "color": "#ec4899"},

    # TRANSFORMACION
    "trans_json":        {"categoria": "transform","label": "Parsear JSON",    "icono": "📦", "color": "#8b5cf6"},
    "trans_filtrar":     {"categoria": "transform","label": "Filtrar datos",   "icono": "🔽", "color": "#8b5cf6"},
    "trans_mapear":      {"categoria": "transform","label": "Mapear campos",   "icono": "🗺️", "color": "#8b5cf6"},
    "trans_formatear":   {"categoria": "transform","label": "Formatear",       "icono": "✏️", "color": "#8b5cf6"},
}


# ══════════════════════════════════════════════════════════════════
# MODELOS DE DATOS
# ══════════════════════════════════════════════════════════════════

@dataclass
class NodoWorkflow:
    id:          str
    tipo:        str
    label:       str
    config:      dict = field(default_factory=dict)
    posicion_x:  int  = 0
    posicion_y:  int  = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "NodoWorkflow":
        return NodoWorkflow(**d)


@dataclass
class ConexionWorkflow:
    id:          str
    desde_nodo:  str
    hasta_nodo:  str
    etiqueta:    str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Workflow:
    id:          str
    nombre:      str
    descripcion: str
    activo:      bool
    nodos:       list  # list[NodoWorkflow]
    conexiones:  list  # list[ConexionWorkflow]
    creado_en:   float
    modificado:  float
    ejecuciones: int   = 0
    ultima_ejec: float = 0.0
    tags:        list  = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Workflow":
        wf = Workflow(
            id=d["id"], nombre=d["nombre"], descripcion=d.get("descripcion",""),
            activo=d.get("activo", False),
            nodos=[NodoWorkflow.from_dict(n) for n in d.get("nodos",[])],
            conexiones=[ConexionWorkflow(**c) for c in d.get("conexiones",[])],
            creado_en=d.get("creado_en", time.time()),
            modificado=d.get("modificado", time.time()),
            ejecuciones=d.get("ejecuciones", 0),
            ultima_ejec=d.get("ultima_ejec", 0.0),
            tags=d.get("tags", []),
        )
        return wf


@dataclass
class EjecucionLog:
    id:         str
    workflow_id: str
    inicio:     float
    fin:        float
    estado:     str    # ok | error | running
    log:        list   # list of step results
    error:      str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════
# GESTOR DE AUTOMATIZACIONES
# ══════════════════════════════════════════════════════════════════

class PakoAutomations:
    def __init__(self, data_dir: str, memory: "PakoMemory"):
        self._dir    = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ruta   = self._dir / "pako_workflows.json"
        self._ruta_logs = self._dir / "pako_exec_logs.json"
        self.memory  = memory
        self._lock   = threading.Lock()

        self.workflows:  dict[str, Workflow]    = {}
        self.exec_logs:  list[EjecucionLog]     = []

        self._brain: Optional["PakoBrain"] = None
        self._cargar()

    def set_brain(self, brain: "PakoBrain") -> None:
        self._brain = brain

    # ── Persistencia ─────────────────────────────────────────────

    def _cargar(self) -> None:
        if self._ruta.exists():
            try:
                raw = json.loads(self._ruta.read_text(encoding="utf-8"))
                for d in raw.get("workflows", []):
                    wf = Workflow.from_dict(d)
                    self.workflows[wf.id] = wf
            except Exception as ex:
                self.memory.log("error", f"Error cargando workflows: {ex}")

        if self._ruta_logs.exists():
            try:
                raw = json.loads(self._ruta_logs.read_text(encoding="utf-8"))
                for d in raw.get("logs", [])[-200:]:
                    self.exec_logs.append(EjecucionLog(**d))
            except Exception:
                pass

    def _guardar(self) -> None:
        try:
            data = {"workflows": [wf.to_dict() for wf in self.workflows.values()]}
            tmp  = self._ruta.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._ruta)
        except Exception as ex:
            self.memory.log("error", f"Error guardando workflows: {ex}")

    def _guardar_logs(self) -> None:
        try:
            data = {"logs": [l.to_dict() for l in self.exec_logs[-200:]]}
            self._ruta_logs.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── CRUD de Workflows ─────────────────────────────────────────

    def crear_workflow(self, nombre: str, descripcion: str = "") -> Workflow:
        wf_id = str(uuid.uuid4())[:8]
        wf = Workflow(
            id=wf_id, nombre=nombre, descripcion=descripcion,
            activo=False, nodos=[], conexiones=[],
            creado_en=time.time(), modificado=time.time(),
        )
        with self._lock:
            self.workflows[wf_id] = wf
            self._guardar()
        self.memory.log("sistema", f"Workflow creado: '{nombre}'")
        return wf

    def eliminar_workflow(self, wf_id: str) -> bool:
        with self._lock:
            if wf_id in self.workflows:
                del self.workflows[wf_id]
                self._guardar()
                return True
        return False

    def duplicar_workflow(self, wf_id: str) -> Optional[Workflow]:
        wf = self.workflows.get(wf_id)
        if not wf:
            return None
        nuevo_id = str(uuid.uuid4())[:8]
        import copy
        nuevo = copy.deepcopy(wf)
        nuevo.id = nuevo_id
        nuevo.nombre = f"{wf.nombre} (copia)"
        nuevo.activo = False
        nuevo.creado_en = time.time()
        nuevo.modificado = time.time()
        nuevo.ejecuciones = 0
        nuevo.ultima_ejec = 0.0
        # Reasignar IDs de nodos
        id_map = {}
        for n in nuevo.nodos:
            nuevo_nid = str(uuid.uuid4())[:6]
            id_map[n.id] = nuevo_nid
            n.id = nuevo_nid
        for c in nuevo.conexiones:
            c.id = str(uuid.uuid4())[:6]
            c.desde_nodo = id_map.get(c.desde_nodo, c.desde_nodo)
            c.hasta_nodo = id_map.get(c.hasta_nodo, c.hasta_nodo)
        with self._lock:
            self.workflows[nuevo_id] = nuevo
            self._guardar()
        return nuevo

    def toggle_activo(self, wf_id: str) -> Optional[bool]:
        with self._lock:
            wf = self.workflows.get(wf_id)
            if wf:
                wf.activo = not wf.activo
                wf.modificado = time.time()
                self._guardar()
                return wf.activo
        return None

    def actualizar_workflow(self, wf_id: str, data: dict) -> bool:
        """Actualiza nodos y conexiones de un workflow (guardado del editor)."""
        with self._lock:
            wf = self.workflows.get(wf_id)
            if not wf:
                return False
            if "nombre" in data:
                wf.nombre = data["nombre"][:100]
            if "descripcion" in data:
                wf.descripcion = data["descripcion"][:500]
            if "nodos" in data:
                wf.nodos = [NodoWorkflow.from_dict(n) for n in data["nodos"]]
            if "conexiones" in data:
                wf.conexiones = [ConexionWorkflow(**c) for c in data["conexiones"]]
            if "tags" in data:
                wf.tags = data["tags"]
            wf.modificado = time.time()
            self._guardar()
        return True

    def agregar_nodo(self, wf_id: str, tipo: str, label: str = "", config: dict = None, x: int = 0, y: int = 0) -> Optional[NodoWorkflow]:
        with self._lock:
            wf = self.workflows.get(wf_id)
            if not wf:
                return None
            info = TIPOS_NODO.get(tipo, {})
            nodo = NodoWorkflow(
                id=str(uuid.uuid4())[:6],
                tipo=tipo,
                label=label or info.get("label", tipo),
                config=config or {},
                posicion_x=x,
                posicion_y=y,
            )
            wf.nodos.append(nodo)
            wf.modificado = time.time()
            self._guardar()
        return nodo

    def conectar_nodos(self, wf_id: str, desde: str, hasta: str, etiqueta: str = "") -> Optional[ConexionWorkflow]:
        with self._lock:
            wf = self.workflows.get(wf_id)
            if not wf:
                return None
            conn = ConexionWorkflow(
                id=str(uuid.uuid4())[:6],
                desde_nodo=desde,
                hasta_nodo=hasta,
                etiqueta=etiqueta,
            )
            wf.conexiones.append(conn)
            wf.modificado = time.time()
            self._guardar()
        return conn

    # ── Ejecución de Workflows ────────────────────────────────────

    def ejecutar_workflow(self, wf_id: str, input_data: dict = None) -> EjecucionLog:
        """
        Ejecuta un workflow paso a paso (simulado).
        Los nodos IA usan PAKO como motor.
        """
        wf = self.workflows.get(wf_id)
        if not wf:
            log = EjecucionLog(
                id=str(uuid.uuid4())[:8],
                workflow_id=wf_id,
                inicio=time.time(), fin=time.time(),
                estado="error", log=[],
                error="Workflow no encontrado"
            )
            return log

        exec_id = str(uuid.uuid4())[:8]
        inicio = time.time()
        pasos = []
        datos_actuales = input_data or {}

        self.memory.log("sistema", f"Ejecutando workflow '{wf.nombre}'")

        # Ordenar nodos: primero triggers, luego por conexiones (BFS simple)
        orden_nodos = self._ordenar_nodos(wf)

        estado_final = "ok"
        error_msg = ""

        for nodo in orden_nodos:
            paso_inicio = time.time()
            try:
                resultado = self._ejecutar_nodo(nodo, datos_actuales)
                datos_actuales.update(resultado.get("output", {}))
                pasos.append({
                    "nodo_id":   nodo.id,
                    "nodo_tipo": nodo.tipo,
                    "nodo_label": nodo.label,
                    "estado":    "ok",
                    "output":    resultado.get("output", {}),
                    "mensaje":   resultado.get("mensaje", ""),
                    "duracion":  round(time.time() - paso_inicio, 3),
                })
            except Exception as ex:
                estado_final = "error"
                error_msg = str(ex)
                pasos.append({
                    "nodo_id":   nodo.id,
                    "nodo_tipo": nodo.tipo,
                    "nodo_label": nodo.label,
                    "estado":    "error",
                    "mensaje":   str(ex),
                    "duracion":  round(time.time() - paso_inicio, 3),
                })
                break

        fin = time.time()
        with self._lock:
            wf.ejecuciones += 1
            wf.ultima_ejec = fin
            self._guardar()

        log = EjecucionLog(
            id=exec_id,
            workflow_id=wf_id,
            inicio=inicio, fin=fin,
            estado=estado_final,
            log=pasos,
            error=error_msg,
        )
        self.exec_logs.append(log)
        if len(self.exec_logs) % 10 == 0:
            self._guardar_logs()

        return log

    def _ordenar_nodos(self, wf: Workflow) -> list[NodoWorkflow]:
        """BFS desde nodos trigger."""
        if not wf.nodos:
            return []

        # Mapa nodo_id -> nodo
        nodo_map = {n.id: n for n in wf.nodos}
        # Mapa desde -> lista de hasta
        conexiones_map: dict[str, list[str]] = {}
        for c in wf.conexiones:
            if c.desde_nodo not in conexiones_map:
                conexiones_map[c.desde_nodo] = []
            conexiones_map[c.desde_nodo].append(c.hasta_nodo)

        # Encontrar triggers (sin predecesores)
        tiene_entrante = {c.hasta_nodo for c in wf.conexiones}
        triggers = [n for n in wf.nodos if n.id not in tiene_entrante]
        if not triggers:
            triggers = [wf.nodos[0]]  # fallback

        visitados = set()
        orden = []
        cola = list(triggers)

        while cola:
            nodo = cola.pop(0)
            if nodo.id in visitados:
                continue
            visitados.add(nodo.id)
            orden.append(nodo)
            for siguiente_id in conexiones_map.get(nodo.id, []):
                if siguiente_id not in visitados and siguiente_id in nodo_map:
                    cola.append(nodo_map[siguiente_id])

        # Añadir nodos no conectados al final
        for n in wf.nodos:
            if n.id not in visitados:
                orden.append(n)

        return orden

    def _ejecutar_nodo(self, nodo: NodoWorkflow, datos: dict) -> dict:
        """Ejecuta un nodo individual. Los nodos IA usan PAKO."""
        cfg  = nodo.config
        tipo = nodo.tipo

        # TRIGGERS
        if tipo.startswith("trigger_"):
            return {"output": datos, "mensaje": f"Disparador '{nodo.label}' activado"}

        # NODOS IA — PAKO como motor
        if tipo.startswith("ia_"):
            return self._ejecutar_nodo_ia(nodo, datos)

        # CONDICIÓN
        if tipo == "logica_condicion":
            campo   = cfg.get("campo", "")
            operador = cfg.get("operador", "existe")
            valor   = cfg.get("valor", "")
            resultado = self._evaluar_condicion(datos.get(campo), operador, valor)
            return {
                "output": {**datos, "_condicion": resultado},
                "mensaje": f"Condición: {campo} {operador} {valor} → {'✓ VERDADERO' if resultado else '✗ FALSO'}"
            }

        # ESPERA
        if tipo == "logica_espera":
            segundos = int(cfg.get("segundos", 1))
            return {"output": datos, "mensaje": f"Esperó {segundos}s (simulado)"}

        # TRANSFORMACIÓN
        if tipo == "trans_json":
            texto = str(datos.get(cfg.get("campo_entrada", "texto"), "{}"))
            try:
                parsed = json.loads(texto)
                return {"output": {**datos, "json_parseado": parsed}, "mensaje": "JSON parseado correctamente"}
            except Exception:
                return {"output": datos, "mensaje": "JSON no válido (simulado)"}

        if tipo == "trans_filtrar":
            return {"output": datos, "mensaje": "Datos filtrados (simulado)"}

        if tipo == "trans_mapear":
            return {"output": datos, "mensaje": "Campos mapeados (simulado)"}

        # ACCIONES
        if tipo == "accion_email":
            para = cfg.get("para", "destinatario@ejemplo.com")
            asunto = cfg.get("asunto", "Sin asunto")
            return {"output": datos, "mensaje": f"Email enviado a {para}: '{asunto}' (simulado)"}

        if tipo == "accion_http":
            url = cfg.get("url", "https://api.ejemplo.com")
            metodo = cfg.get("metodo", "GET")
            return {"output": {**datos, "http_status": 200}, "mensaje": f"HTTP {metodo} {url} → 200 OK (simulado)"}

        if tipo == "accion_slack":
            canal = cfg.get("canal", "#general")
            return {"output": datos, "mensaje": f"Mensaje enviado a Slack {canal} (simulado)"}

        if tipo == "accion_telegram":
            return {"output": datos, "mensaje": "Mensaje enviado por Telegram (simulado)"}

        if tipo == "accion_bbdd":
            operacion = cfg.get("operacion", "INSERT")
            tabla = cfg.get("tabla", "tabla")
            return {"output": {**datos, "db_filas": 1}, "mensaje": f"BD: {operacion} en '{tabla}' (simulado)"}

        if tipo == "accion_notificacion":
            return {"output": datos, "mensaje": f"Notificación enviada: {cfg.get('titulo', 'Notificación')}"}

        return {"output": datos, "mensaje": f"Nodo '{nodo.label}' ejecutado"}

    def _ejecutar_nodo_ia(self, nodo: NodoWorkflow, datos: dict) -> dict:
        """Ejecuta nodos IA usando PAKO como modelo."""
        tipo = nodo.tipo
        cfg  = nodo.config
        campo_entrada = cfg.get("campo_entrada", "texto")
        texto_entrada = str(datos.get(campo_entrada, cfg.get("texto_prueba", "texto de ejemplo")))

        if not self._brain:
            return {"output": datos, "mensaje": "⚠️ Motor IA no disponible"}

        if tipo == "ia_resumir":
            prompt = f"Resume este texto en máximo 3 frases: {texto_entrada[:1000]}"
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "resumen": resultado}, "mensaje": "Texto resumido por PAKO"}

        if tipo == "ia_clasificar":
            categorias = cfg.get("categorias", "positivo, negativo, neutro")
            prompt = f"Clasifica este texto en una de estas categorías ({categorias}): '{texto_entrada[:500]}'. Responde solo con la categoría."
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "categoria": resultado.strip()}, "mensaje": f"Clasificado: {resultado.strip()}"}

        if tipo == "ia_sentimiento":
            prompt = f"Analiza el sentimiento de este texto (positivo/negativo/neutro): '{texto_entrada[:500]}'"
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "sentimiento": resultado}, "mensaje": f"Sentimiento: {resultado[:50]}"}

        if tipo == "ia_extraer":
            campos = cfg.get("campos", "nombre, fecha, valor")
            prompt = f"Extrae los siguientes datos ({campos}) de este texto: '{texto_entrada[:800]}'. Responde en formato JSON."
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "datos_extraidos": resultado}, "mensaje": "Datos extraídos por PAKO"}

        if tipo == "ia_generar":
            instruccion = cfg.get("instruccion", "Genera una respuesta para")
            prompt = f"{instruccion}: {texto_entrada[:500]}"
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "texto_generado": resultado}, "mensaje": "Texto generado por PAKO"}

        if tipo == "ia_traducir":
            idioma = cfg.get("idioma_destino", "inglés")
            prompt = f"Traduce al {idioma}: '{texto_entrada[:500]}'"
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "traduccion": resultado}, "mensaje": f"Traducido al {idioma}"}

        if tipo == "ia_responder":
            contexto = cfg.get("contexto", "")
            prompt = f"{contexto} {texto_entrada}".strip()
            resultado, _ = self._brain.responder(prompt)
            return {"output": {**datos, "respuesta_ia": resultado}, "mensaje": "PAKO respondió"}

        return {"output": datos, "mensaje": f"Nodo IA '{nodo.label}' ejecutado"}

    def _evaluar_condicion(self, valor, operador: str, referencia) -> bool:
        if operador == "existe":
            return valor is not None and valor != ""
        if operador == "igual":
            return str(valor) == str(referencia)
        if operador == "contiene":
            return str(referencia).lower() in str(valor).lower()
        if operador == "mayor":
            try: return float(valor) > float(referencia)
            except: return False
        if operador == "menor":
            try: return float(valor) < float(referencia)
            except: return False
        return False

    # ── Consultas ─────────────────────────────────────────────────

    def listar_workflows(self) -> list[dict]:
        return [
            {
                "id":          wf.id,
                "nombre":      wf.nombre,
                "descripcion": wf.descripcion,
                "activo":      wf.activo,
                "nodos":       len(wf.nodos),
                "conexiones":  len(wf.conexiones),
                "ejecuciones": wf.ejecuciones,
                "ultima_ejec": wf.ultima_ejec,
                "tags":        wf.tags,
                "modificado":  wf.modificado,
            }
            for wf in self.workflows.values()
        ]

    def get_workflow(self, wf_id: str) -> Optional[dict]:
        wf = self.workflows.get(wf_id)
        return wf.to_dict() if wf else None

    def get_logs(self, wf_id: str = None, n: int = 50) -> list[dict]:
        logs = self.exec_logs if not wf_id else [l for l in self.exec_logs if l.workflow_id == wf_id]
        return [l.to_dict() for l in logs[-n:]]

    def tipos_nodo(self) -> dict:
        return TIPOS_NODO

    def stats(self) -> dict:
        total = len(self.workflows)
        activos = sum(1 for wf in self.workflows.values() if wf.activo)
        total_ejec = sum(wf.ejecuciones for wf in self.workflows.values())
        return {
            "total_workflows": total,
            "activos": activos,
            "inactivos": total - activos,
            "total_ejecuciones": total_ejec,
            "logs_guardados": len(self.exec_logs),
        }

    def generar_workflow_desde_descripcion(self, descripcion: str) -> dict:
        """
        Genera un workflow sugerido a partir de una descripción en lenguaje natural.
        Retorna un dict con estructura de nodos y conexiones sugeridos.
        """
        desc = descripcion.lower()

        # Detectar trigger
        trigger = "trigger_manual"
        if any(x in desc for x in ["correo", "email", "mail"]):
            trigger = "trigger_email"
        elif any(x in desc for x in ["webhook", "http", "api", "petición"]):
            trigger = "trigger_webhook"
        elif any(x in desc for x in ["cada", "programad", "horario", "diario", "semanal", "schedule"]):
            trigger = "trigger_schedule"
        elif any(x in desc for x in ["formulario", "form"]):
            trigger = "trigger_formulario"

        # Detectar nodos IA
        nodos_ia = []
        if any(x in desc for x in ["resum", "resume"]):
            nodos_ia.append("ia_resumir")
        if any(x in desc for x in ["clasific", "categoriz"]):
            nodos_ia.append("ia_clasificar")
        if any(x in desc for x in ["sentimiento", "tono", "emocion"]):
            nodos_ia.append("ia_sentimiento")
        if any(x in desc for x in ["extrae", "extraer", "sacar datos"]):
            nodos_ia.append("ia_extraer")
        if any(x in desc for x in ["genera", "generar", "escrib", "redact"]):
            nodos_ia.append("ia_generar")
        if any(x in desc for x in ["traduc", "traducir"]):
            nodos_ia.append("ia_traducir")
        if not nodos_ia and any(x in desc for x in ["ia", "pako", "inteligencia"]):
            nodos_ia.append("ia_responder")

        # Detectar condiciones
        tiene_condicion = any(x in desc for x in ["si ", "si es", "cuando sea", "condicion", "condición", "dependiendo"])

        # Detectar acciones finales
        acciones = []
        if any(x in desc for x in ["enviar email", "manda correo", "mail a", "notificar por email"]):
            acciones.append("accion_email")
        if any(x in desc for x in ["slack"]):
            acciones.append("accion_slack")
        if any(x in desc for x in ["telegram"]):
            acciones.append("accion_telegram")
        if any(x in desc for x in ["guarda", "guardar", "base de datos", "bbdd", "db"]):
            acciones.append("accion_bbdd")
        if any(x in desc for x in ["notifica", "avisa"]):
            acciones.append("accion_notificacion")
        if not acciones:
            acciones.append("accion_notificacion")

        # Construir estructura
        nodos_sugeridos = []
        conexiones_sugeridas = []
        x, y = 100, 200

        def add_nodo(tipo, lbl=""):
            nonlocal x
            info = TIPOS_NODO.get(tipo, {})
            n = {"tipo": tipo, "label": lbl or info.get("label", tipo), "id": str(uuid.uuid4())[:6], "posicion_x": x, "posicion_y": y}
            nodos_sugeridos.append(n)
            x += 200
            return n["id"]

        ids = []
        ids.append(add_nodo(trigger))

        for ia_tipo in nodos_ia:
            ids.append(add_nodo(ia_tipo))

        if tiene_condicion:
            ids.append(add_nodo("logica_condicion", "Condición"))

        for accion in acciones:
            ids.append(add_nodo(accion))

        for i in range(len(ids) - 1):
            conexiones_sugeridas.append({
                "id": str(uuid.uuid4())[:6],
                "desde_nodo": ids[i],
                "hasta_nodo": ids[i+1],
                "etiqueta": ""
            })

        return {
            "nodos":      nodos_sugeridos,
            "conexiones": conexiones_sugeridas,
            "descripcion_analizada": {
                "trigger":    trigger,
                "nodos_ia":   nodos_ia,
                "condicion":  tiene_condicion,
                "acciones":   acciones,
            }
        }
