# PAKO v3.0 — Tu IA Personal

Sistema de IA híbrida local: memoria persistente + búsqueda web + GitHub + archivos.
**Sin modelos externos. Sin OpenAI. 100% tuyo. 100% privado.**

---

## ¿Qué hay de nuevo en v3.0?

### 🧠 Motor inteligente mejorado
- **Búsqueda TF-IDF con índice invertido** — 10× más rápida y precisa
- **Contexto de conversación** — PAKO recuerda lo que hablaron
- **Resolución de referencias** — entiende "eso", "lo mismo", "el tema anterior"
- **Respuestas personalizadas** — saludo según la hora, usa tu nombre
- **Fallback inteligente** — si no sabe, busca en web automáticamente

### 🔒 Seguridad real
- **Rate limiting** por IP (60 req/min)
- **Validación de inputs** en todos los endpoints
- **Sanitización** de texto de entrada
- **Validación de tokens GitHub** (formato `ghp_` o `github_pat_`)
- **Headers HTTP de seguridad** (CSP, X-Frame-Options, nosniff)
- **Prevención de path traversal** en archivos estáticos
- **Token GitHub nunca expuesto** en respuestas API
- **Guardado atómico** de datos (evita corrupción)

### 🎨 UI completamente nueva
- Diseño tipo ChatGPT moderno con fuentes IBM Plex Mono + Sora
- Renderizado de **Markdown** (bold, italic, `code`, bloques de código)
- **Typing indicator** con animación
- **Toast notifications** para feedback
- **Export** de conversación a .txt
- **Badges** de fuente (WEB / GH / MEM)
- Panel lateral con estadísticas en tiempo real
- Responsive y accesible

### 💬 Conversación mejorada
- Historial persistente (guarda entre sesiones)
- Nuevos comandos: `estadísticas`, `limpiar historial`, `mis repos`
- Configuración de nombre: `mi nombre es [nombre]`
- Comando `limpiar historial` para empezar de cero

---

## Instalación

### Requisitos
- **Python 3.10+** (sin dependencias externas)

### Estructura
```
PAKO/
├── pako.py                    ← EJECUTA ESTE
├── backend/
│   ├── pako_brain.py          ← Cerebro v3.0
│   ├── pako_memory.py         ← Memoria v3.0
│   ├── pako_server.py         ← Servidor v3.0
│   ├── pako_web_agent.py      ← Agente web
│   ├── pako_github_agent.py   ← Agente GitHub
│   └── pako_file_agent.py     ← Agente archivos
└── data/
    └── pako_conocimiento.json ← Base de conocimiento
```

### Arrancar
```bash
python pako.py
# → http://localhost:8765

python pako.py --port 9000
python pako.py --host 0.0.0.0   # red local
python pako.py --import-json paco_aprendido.json
```

---

## Comandos

| Dices | PAKO hace |
|---|---|
| `hola` | Saludo personalizado según la hora |
| `mi nombre es Carlos` | Recuerda tu nombre para siempre |
| `busca qué es FastAPI` | Busca en Wikipedia + DuckDuckGo |
| `aprende que X es Y` | Guarda en memoria permanente |
| `analiza: 12, 45, 7, 89` | Estadísticas completas |
| `¿cuánto es 347 * 28?` | Calculadora natural |
| `estadísticas` | Estado completo del sistema |
| `mis repos` | Lista tus repos de GitHub |
| `aprende de mis repos` | Aprende de todos tus repos |
| `aprende del repo nombre` | Aprende de un repo específico |
| `añade carpeta /ruta` | Permite leer archivos en esa carpeta |
| `lee archivo.py` | Lee y muestra el archivo |
| `limpiar historial` | Borra el historial de conversación |
| `dato curioso` | Curiosidad aleatoria sobre informática |

---

## API REST

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/api/chat` | Enviar mensaje |
| GET | `/api/stats` | Estadísticas (incluye config) |
| GET | `/api/actividad` | Log de actividad |
| GET | `/api/pendientes` | Conocimiento pendiente |
| GET | `/api/historial` | Historial de conversación |
| GET | `/api/config` | Configuración actual |
| POST | `/api/config` | Cambiar configuración |
| POST | `/api/github/connect` | Conectar GitHub |
| GET | `/api/github/repos` | Listar repos |
| POST | `/api/pendientes/aprobar` | Aprobar entrada |
| POST | `/api/pendientes/rechazar` | Rechazar entrada |
| POST | `/api/conocimiento/eliminar` | Eliminar entrada |

---

## Seguridad

| Aspecto | Implementación |
|---|---|
| Rate limiting | 60 req/min por IP, ventana deslizante |
| Inputs | Sanitización, límite 2000 chars |
| Token GitHub | Validación de formato, nunca en respuestas |
| Archivos | Solo carpetas explícitamente añadidas |
| GitHub | Solo lectura, nunca ejecuta código |
| Web | Solo lectura, no envía datos |
| Path traversal | Bloqueado en archivos estáticos |
| eval() | `__builtins__: {}` sin acceso al sistema |
| Tokens | Guardado atómico con .tmp + replace |

---

## Cómo funciona el motor

1. **Comandos de sistema** → nombre, carpetas, stats, historial
2. **Aprendizaje explícito** → "aprende que X es Y"
3. **Calculadora** → expresiones matemáticas en lenguaje natural
4. **Análisis de datos** → listas de números
5. **Búsqueda en memoria** → índice TF-IDF con scoring por frecuencia
6. **Intención directa** → saludo, hora, aleatorio, ayuda...
7. **Búsqueda web** → Wikipedia + DuckDuckGo si no hay respuesta
8. **Fallback** → sugerencia de búsqueda

---

## Próximos pasos

- [ ] Integrar Ollama (LLM local) como motor de respuesta adicional
- [ ] Embeddings semánticos con `sentence-transformers`
- [ ] Migrar a SQLite + FTS5 para escalar
- [ ] Soporte PDF/DOCX
- [ ] Notificaciones de aprendizaje en tiempo real (WebSockets)
