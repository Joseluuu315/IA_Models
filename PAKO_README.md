# PAKO — IA Propia v2.0
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

Sistema de IA híbrida local: memoria persistente + búsqueda web + GitHub + archivos locales.
**Sin modelos externos. Sin tokens de OpenAI. 100% tuyo.**

---

## Estructura del proyecto

```
PAKO/
├── pako.py                    ← Punto de entrada (EJECUTA ESTE)
├── backend/
│   ├── pako_brain.py          ← Cerebro: NLP, intenciones, motor de respuesta
│   ├── pako_memory.py         ← Memoria persistente (JSON estructurado)
│   ├── pako_server.py         ← Servidor HTTP + API REST + UI embebida
│   ├── pako_web_agent.py      ← Agente web: Wikipedia + DuckDuckGo
│   ├── pako_github_agent.py   ← Agente GitHub: lee tus repos (solo lectura)
│   └── pako_file_agent.py     ← Agente de archivos locales (solo lectura)
└── data/
    └── pako_conocimiento_base.json  ← 212 temas de informática precargados
```

---
## Instalación

### Requisitos
- Python 3.10 o superior
- **Sin dependencias externas** (usa solo la librería estándar de Python)

### Pasos

```bash
# 1. Crear carpeta del proyecto
mkdir PAKO && cd PAKO

# 2. Copiar todos los archivos descargados:
#    pako.py (renombrar desde pako_main.py)
#    backend/ (carpeta con todos los .py)
#    data/ (con pako_conocimiento_base.json → renombrar a pako_conocimiento.json)

# 3. Estructura final:
# PAKO/
# ├── pako.py
# ├── backend/
# │   ├── pako_brain.py
# │   ├── pako_memory.py
# │   ├── pako_server.py
# │   ├── pako_web_agent.py
# │   ├── pako_github_agent.py
# │   └── pako_file_agent.py
# └── data/
#     └── pako_conocimiento.json   ← renombrar desde pako_conocimiento_base.json

# 4. Arrancar PAKO
python pako.py

# 5. Abrir en el navegador
# http://localhost:8765
```

---

## Uso

### Arrancar
```bash
python pako.py                          # localhost:8765
python pako.py --port 9000              # puerto personalizado
python pako.py --host 0.0.0.0           # accesible en la red local
```

### Comandos de conversación

| Lo que dices | Qué hace PAKO |
|---|---|
| `hola` | Saluda con personalidad |
| `¿cuánto es 347 * 28?` | Calcula |
| `15% de 200` | Porcentaje |
| `analiza: 10, 25, 37, 48` | Estadísticas (media, mediana, desv.) |
| `qué es SOLID` | Responde desde memoria (212 temas de informática) |
| `busca qué es FastAPI` | Busca en Wikipedia + DuckDuckGo |
| `aprende que X es Y` | Guarda en memoria permanente |
| `aprende de mis repos` | Lee todos tus repos de GitHub (requiere token) |
| `aprende del repo nombre-repo` | Lee un repo específico |
| `lee el archivo notas.txt` | Lee archivo local (carpeta configurada) |
| `qué hora es` | Hora y fecha actual |
| `número aleatorio entre 1 y 100` | Número aleatorio |
| `cuéntame un chiste` | Chiste de informática |

### Conectar GitHub
1. Crea un **Personal Access Token** en: https://github.com/settings/tokens
2. Permisos necesarios: `repo` (solo lectura)
3. En el panel lateral de la UI, pega el token y haz clic en "Conectar GitHub"
4. Di: **"aprende de mis repos"** para que PAKO aprenda de tu código

### Configurar carpetas de archivos locales
Desde la conversación:
```
añade carpeta /ruta/a/tus/documentos
```
Luego: `lee el archivo miarchivo.py`

---

## API REST

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/api/chat` | Enviar mensaje a PAKO |
| GET | `/api/stats` | Estadísticas del sistema |
| GET | `/api/actividad` | Log de actividad reciente |
| GET | `/api/pendientes` | Conocimiento pendiente de validar |
| POST | `/api/config` | Cambiar configuración |
| POST | `/api/github/connect` | Conectar GitHub con token |
| GET | `/api/github/repos` | Listar repositorios |
| POST | `/api/pendientes/aprobar` | Aprobar entrada pendiente |
| POST | `/api/pendientes/rechazar` | Rechazar entrada pendiente |

### Ejemplo de uso de la API

```python
import requests

# Enviar mensaje
r = requests.post("http://localhost:8765/api/chat",
    json={"mensaje": "busca qué es Rust"})
print(r.json()["respuesta"])

# Conectar GitHub
r = requests.post("http://localhost:8765/api/github/connect",
    json={"token": "ghp_xxxxxxxxxxxx"})
print(r.json())
```

---

## Cómo funciona PAKO por dentro

### Motor de respuesta (en orden de prioridad)
1. **Aprendizaje explícito** → detecta "aprende que X es Y"
2. **Calculadora natural** → extrae y evalúa expresiones matemáticas del texto
3. **Análisis estadístico** → detecta listas de números
4. **Memoria local** → busca en el conocimiento guardado (similitud por tokens)
5. **Agente web** → si se detecta intención de búsqueda, consulta Wikipedia/DDG
6. **Intenciones** → bag-of-words + similitud coseno sobre patrones predefinidos
7. **Fallback** → respuesta genérica con sugerencia de búsqueda

### Tipos de fuente de conocimiento
- `base` — Precargado (212 temas de informática)
- `manual` — Enseñado por el usuario ("aprende que X es Y")
- `web` — Extraído de internet por el agente web
- `github` — Extraído de repositorios de GitHub
- `archivo` — Extraído de archivos locales

### Sistema de validación
Con **validación manual activada** (por defecto), el conocimiento de fuentes
automáticas (web, GitHub, archivos) queda en estado **pendiente** hasta que
el usuario lo aprueba o rechaza desde la UI.

Con **autoaprendizaje activado**, el conocimiento de confianza alta se aprueba
automáticamente sin intervención del usuario.

---

## Seguridad

- **GitHub**: Solo lectura. Nunca modifica repositorios.
- **Archivos**: Solo carpetas explícitamente configuradas. Nunca borra ni modifica.
- **Web**: Solo lectura. Nunca envía datos personales a internet.
- **Código externo**: Nunca ejecuta código de repositorios ni archivos.
- **Evaluación matemática**: Usa `eval()` con `__builtins__: {}` (sin acceso al sistema).

---

## Próximos pasos sugeridos

- Añadir embeddings semánticos (sentence-transformers) para búsqueda más precisa
- Integrar un LLM local (Ollama + llama3) como motor de respuesta adicional
- Migrar a SQLite o Chroma (vector DB) para escalar a millones de entradas
- Añadir soporte para PDFs (pypdf2) y archivos Word (python-docx)
