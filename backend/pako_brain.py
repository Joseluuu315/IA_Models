"""
pako_brain.py — Cerebro de PAKO v5.0

BUGS CORREGIDOS vs v4:
  ❌ Memoria disparándose siempre (condición `len > 0` sin score mínimo)
  ❌ "¿Qué puedes hacer?" → devolvía SOLID (memoria ganaba a intenciones)
  ❌ "busca Docker" → devolvía A* (memoria antes que trigger_web)
  ❌ "hola" → devolvía la hora (tiempo matcheaba antes que saludo)
  ❌ "hol" → devolvía SOLID (fuzzy+memoria sin umbral)
  ❌ Sin soporte de generación de código

FLUJO CORRECTO DE PRIORIDAD:
  1. Comandos de sistema (nombre, carpeta, stats...)
  2. Aprendizaje explícito ("aprende que X es Y")
  3. Intenciones DIRECTAS de alta confianza (saludo, ayuda, hora, dado...)
     → ANTES de consultar memoria para evitar falsos positivos
  4. Calculadora + análisis de datos
  5. Trigger de búsqueda web EXPLÍCITA ("busca X", "qué es X")
     → Si el usuario pide explícitamente buscar, NO tocar la memoria primero
  6. Memoria local CON UMBRAL REAL (score mínimo 0.55)
  7. Búsqueda web automática (fallback)
  8. Intenciones de baja confianza
  9. Fallback
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

from pako_fuzzy import fuzzy as _fuzzy_global


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
    "puedo","puede","quiero","quiere","saber","decir","ver","ir",
}


def normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    for s, d in [
        ("á","a"),("à","a"),("ä","a"),("é","e"),("è","e"),("ë","e"),
        ("í","i"),("ì","i"),("ï","i"),("ó","o"),("ò","o"),("ö","o"),
        ("ú","u"),("ù","u"),("ü","u"),("ñ","n"),("¿",""),("¡",""),
    ]:
        texto = texto.replace(s, d)
    return texto


def tokenizar(texto: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalizar(texto)) if len(t) > 1]


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
    for pat, rep in [
        (r"\belevado al cuadrado\b", "**2"),
        (r"\belevado al cubo\b",     "**3"),
        (r"\belevado a (\d+)\b",     r"**\1"),
        (r"\braiz cuadrada de\b",    "sqrt"),
        (r"\braiz de\b",             "sqrt"),
        (r"\b(por|multiplicado por)\b", "*"),
        (r"\b(entre|dividido entre|dividido por|sobre)\b", "/"),
        (r"\b(mas|sumado a)\b", "+"),
        (r"\bmenos\b", "-"),
        (r"\^", "**"), (r"÷", "/"), (r"×", "*"),
    ]:
        e = re.sub(pat, rep, e)

    pct = re.match(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", e.strip())
    if pct:
        return _fmt(float(pct.group(1)) / 100 * float(pct.group(2)))

    sqrt_m = re.search(r"sqrt\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", e)
    if sqrt_m:
        return _fmt(math.sqrt(float(sqrt_m.group(1))))

    e2 = re.sub(r"[^0-9+\-*/().%\s]", " ", e).strip()
    candidates = re.findall(r"\d[\d\s+\-*/().%]*\d", e2) or re.findall(r"[\d+\-*/().%]+", e2)
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
    if isinstance(n, (int, float)) and float(n) == int(float(n)):
        return f"{int(float(n)):,}".replace(",", ".")
    return str(round(float(n), 6))


def analizar_datos(texto: str) -> Optional[str]:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", texto)]
    if len(nums) < 2:
        return None
    n      = len(nums)
    media  = sum(nums) / n
    ordn   = sorted(nums)
    med    = ordn[n // 2] if n % 2 else (ordn[n // 2 - 1] + ordn[n // 2]) / 2
    desv   = math.sqrt(sum((x - media) ** 2 for x in nums) / n)
    return (
        f"📊 Análisis de {n} valores:\n"
        f"  • Suma: {round(sum(nums),4)}\n"
        f"  • Media: {round(media,4)}\n"
        f"  • Mediana: {round(med,4)}\n"
        f"  • Mín: {min(nums)}  Máx: {max(nums)}\n"
        f"  • Rango: {round(max(nums)-min(nums),4)}\n"
        f"  • Desviación estándar: {round(desv,4)}"
    )


# ══════════════════════════════════════════════════════════════════
# GENERACIÓN DE CÓDIGO
# ══════════════════════════════════════════════════════════════════

# Plantillas de código por tema detectado
_CODE_TEMPLATES: dict[str, dict] = {
    "hello world python": {
        "lang": "python",
        "code": 'print("Hello, World!")',
        "desc": "El programa más básico en Python"
    },
    "hello world javascript": {
        "lang": "javascript",
        "code": 'console.log("Hello, World!");',
        "desc": "Hello World en JavaScript"
    },
    "servidor flask": {
        "lang": "python",
        "code": """from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "¡Hola desde Flask!"

if __name__ == "__main__":
    app.run(debug=True)""",
        "desc": "Servidor web básico con Flask"
    },
    "servidor fastapi": {
        "lang": "python",
        "code": """from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"mensaje": "¡Hola desde FastAPI!"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}""",
        "desc": "API REST básica con FastAPI"
    },
    "decorador python": {
        "lang": "python",
        "code": """def mi_decorador(func):
    def wrapper(*args, **kwargs):
        print(f"Antes de llamar a {func.__name__}")
        resultado = func(*args, **kwargs)
        print(f"Después de llamar a {func.__name__}")
        return resultado
    return wrapper

@mi_decorador
def saludar(nombre):
    print(f"¡Hola, {nombre}!")

saludar("mundo")""",
        "desc": "Ejemplo de decorador en Python"
    },
    "clase python": {
        "lang": "python",
        "code": """class Animal:
    def __init__(self, nombre: str, especie: str):
        self.nombre = nombre
        self.especie = especie

    def hablar(self) -> str:
        return f"{self.nombre} hace un sonido"

    def __repr__(self) -> str:
        return f"Animal(nombre={self.nombre!r}, especie={self.especie!r})"


class Perro(Animal):
    def hablar(self) -> str:
        return f"{self.nombre} dice: ¡Guau!"


rex = Perro("Rex", "Canis lupus familiaris")
print(rex.hablar())
print(repr(rex))""",
        "desc": "Clase y herencia en Python"
    },
    "fetch api javascript": {
        "lang": "javascript",
        "code": """async function obtenerDatos(url) {
  try {
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error al obtener datos:", error);
    throw error;
  }
}

// Uso
obtenerDatos("https://api.ejemplo.com/datos")
  .then(data => console.log(data))
  .catch(err => console.error(err));""",
        "desc": "Fetch con async/await en JavaScript"
    },
    "conexion mysql python": {
        "lang": "python",
        "code": """import mysql.connector

# pip install mysql-connector-python
conexion = mysql.connector.connect(
    host="localhost",
    user="tu_usuario",
    password="tu_contraseña",
    database="tu_base_de_datos"
)

cursor = conexion.cursor()

# Consulta
cursor.execute("SELECT * FROM usuarios LIMIT 10")
filas = cursor.fetchall()

for fila in filas:
    print(fila)

cursor.close()
conexion.close()""",
        "desc": "Conexión a MySQL desde Python"
    },
    "conexion sqlite python": {
        "lang": "python",
        "code": "import sqlite3\n\nconn = sqlite3.connect('mi_base.db')\ncursor = conn.cursor()\ncursor.execute('CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, email TEXT UNIQUE)')\ncursor.execute('INSERT INTO usuarios (nombre, email) VALUES (?, ?)', ('Juan Garcia', 'juan@ej.com'))\nconn.commit()\nfor row in cursor.execute('SELECT * FROM usuarios'):\n    print(row)\nconn.close()",
        "desc": "Base de datos SQLite en Python"
    },
    "lista comprension python": {
        "lang": "python",
        "code": """# List comprehension básica
cuadrados = [x**2 for x in range(10)]
print(cuadrados)  # [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

# Con condición
pares = [x for x in range(20) if x % 2 == 0]
print(pares)  # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

# Anidada
matriz = [[i * j for j in range(1, 4)] for i in range(1, 4)]
print(matriz)  # [[1, 2, 3], [2, 4, 6], [3, 6, 9]]

# Dict comprehension
cuadrados_dict = {x: x**2 for x in range(6)}
print(cuadrados_dict)  # {0: 0, 1: 1, 2: 4, 3: 9, 4: 16, 5: 25}""",
        "desc": "List comprehensions y dict comprehensions en Python"
    },
    "generador python": {
        "lang": "python",
        "code": """# Función generadora
def fibonacci(n: int):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Uso
for num in fibonacci(10):
    print(num, end=" ")
# 0 1 1 2 3 5 8 13 21 34

# Generator expression (más ligero que lista)
suma_cuadrados = sum(x**2 for x in range(1_000_000))
print(suma_cuadrados)""",
        "desc": "Generadores con yield en Python"
    },
    "async python": {
        "lang": "python",
        "code": """import asyncio
import aiohttp  # pip install aiohttp

async def obtener_url(session, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()

async def main():
    urls = [
        "https://httpbin.org/get",
        "https://httpbin.org/ip",
    ]
    async with aiohttp.ClientSession() as session:
        tareas = [obtener_url(session, url) for url in urls]
        resultados = await asyncio.gather(*tareas)
        for url, res in zip(urls, resultados):
            print(f"{url}: {len(res)} bytes")

asyncio.run(main())""",
        "desc": "Async/await con aiohttp en Python"
    },
    "react componente": {
        "lang": "jsx",
        "code": """import { useState, useEffect } from 'react';

function Contador({ inicio = 0 }) {
  const [cuenta, setCuenta] = useState(inicio);
  const [historial, setHistorial] = useState([]);

  useEffect(() => {
    document.title = `Cuenta: ${cuenta}`;
  }, [cuenta]);

  const incrementar = () => {
    setCuenta(prev => prev + 1);
    setHistorial(prev => [...prev, `+1 → ${cuenta + 1}`]);
  };

  return (
    <div className="contador">
      <h2>Contador: {cuenta}</h2>
      <button onClick={incrementar}>+1</button>
      <button onClick={() => setCuenta(inicio)}>Reset</button>
      <ul>
        {historial.slice(-5).map((h, i) => <li key={i}>{h}</li>)}
      </ul>
    </div>
  );
}

export default Contador;""",
        "desc": "Componente React con useState y useEffect"
    },
    "dockerfile": {
        "lang": "dockerfile",
        "code": """# Imagen base
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias primero (capa cacheada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Variable de entorno
ENV PORT=8000

# Exponer puerto
EXPOSE ${PORT}

# Usuario no-root (seguridad)
RUN adduser --disabled-password --no-create-home appuser
USER appuser

# Comando de arranque
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]""",
        "desc": "Dockerfile para una app Python"
    },
    "docker compose": {
        "lang": "yaml",
        "code": """version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:""",
        "desc": "Docker Compose con app, PostgreSQL y Redis"
    },
    "expresiones regulares python": {
        "lang": "python",
        "code": r"""import re

texto = "Mi email es juan@ejemplo.com y teléfono 612-345-678"

# Buscar un patrón
email_patron = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
email = re.search(email_patron, texto)
if email:
    print(f"Email encontrado: {email.group()}")

# Encontrar todos
telefonos = re.findall(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{3}', texto)
print(f"Teléfonos: {telefonos}")

# Reemplazar
texto_limpio = re.sub(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{3}', '[TELÉFONO]', texto)
print(texto_limpio)

# Grupos con nombre
patron = r'(?P<usuario>\w+)@(?P<dominio>[\w.]+)'
m = re.search(patron, texto)
if m:
    print(f"Usuario: {m.group('usuario')}, Dominio: {m.group('dominio')}")""",
        "desc": "Expresiones regulares en Python"
    },
}


def detectar_peticion_codigo(texto: str) -> Optional[dict]:
    """
    Detecta si el usuario pide código y devuelve la plantilla adecuada.
    Retorna dict con {lang, code, desc} o None.
    """
    norm = normalizar(texto)

    # Palabras que indican petición de código
    trigger_code = any(p in norm for p in [
        "codigo", "code", "ejemplo", "escribe", "crea", "genera", "muestra",
        "hazme", "como se hace", "como se escribe", "implementa", "programa",
        "script", "funcion", "clase", "metodo",
    ])
    if not trigger_code:
        return None

    # Buscar la plantilla más relevante
    mejor_score = 0
    mejor_tpl   = None

    for key, tpl in _CODE_TEMPLATES.items():
        key_tokens = set(tokenizar(key))
        inp_tokens = set(tokenizar(norm))
        if not key_tokens:
            continue
        comunes = key_tokens & inp_tokens
        score   = len(comunes) / len(key_tokens)
        if score > mejor_score:
            mejor_score = score
            mejor_tpl   = tpl

    if mejor_tpl and mejor_score >= 0.35:
        return mejor_tpl

    # Detección por lenguaje explícito + tipo
    lang_map = {
        "python": "python", "py": "python",
        "javascript": "javascript", "js": "javascript",
        "react": "jsx", "jsx": "jsx",
        "typescript": "typescript", "ts": "typescript",
        "docker": "dockerfile",
        "sql": "sql", "mysql": "sql", "sqlite": "sql",
    }
    detected_lang = None
    for kw, lang in lang_map.items():
        if kw in norm:
            detected_lang = lang
            break

    if detected_lang:
        # Buscar plantilla de ese lenguaje
        for key, tpl in _CODE_TEMPLATES.items():
            if tpl["lang"] == detected_lang or detected_lang in key:
                if any(t in norm for t in tokenizar(key)):
                    return tpl

    return None


# ══════════════════════════════════════════════════════════════════
# INTENCIONES
# ══════════════════════════════════════════════════════════════════

INTENCIONES: dict[str, dict] = {
    "saludo": {
        "patrones": [
            ["hola","hey","buenas","saludos","ey","buenos dias","buenas tardes",
             "buenas noches","hi","hello","que tal"],
        ],
        "respuestas": [],  # dinámico
    },
    "identidad": {
        "patrones": [
            ["quien eres","como te llamas","eres una ia","que eres","presentate",
             "tu nombre","eres humano","quien es pako","que tipo de ia eres"],
        ],
        "respuestas": [
            "Soy **PAKO**, tu asistente de IA integrado en esta plataforma. "
            "Puedo responder preguntas, calcular, buscar en internet, generar código, "
            "gestionar automatizaciones y aprender lo que me enseñes. 🤖",
            "Me llamo **PAKO**. Motor de IA local: memoria persistente, búsqueda web, "
            "GitHub, generación de código y automatizaciones. Todo sin APIs externas. 💡",
        ],
    },
    "ayuda": {
        "patrones": [
            ["que puedes hacer","que sabes hacer","ayuda","help","capacidades",
             "para que sirves","funciones","comandos","que haces","tus funciones"],
        ],
        "respuestas": [
            (
                "Esto es todo lo que puedo hacer:\n\n"
                "🧮 **Calcular** → `¿cuánto es 234 × 17?`\n"
                "📊 **Analizar datos** → `analiza: 12, 45, 7, 89`\n"
                "💻 **Generar código** → `código de un servidor Flask en Python`\n"
                "🌐 **Buscar en internet** → `busca qué es Docker`\n"
                "🧠 **Responder preguntas** → tengo +200 conceptos de informática\n"
                "📚 **Aprender** → `aprende que X es Y`\n"
                "⚡ **Automatizaciones** → ve al menú lateral\n"
                "🐙 **GitHub** → conecta y aprendo de tus repos\n\n"
                "¿Por dónde empezamos?"
            ),
        ],
    },
    "despedida": {
        "patrones": [["adios","hasta luego","bye","chao","hasta pronto","nos vemos","me voy"]],
        "respuestas": [
            "¡Hasta luego! Todo lo aprendido quedará en memoria. 🧠",
            "¡Cuídate! Aquí estaré cuando vuelvas. 👋",
        ],
    },
    "gracias": {
        "patrones": [["gracias","muchas gracias","genial","perfecto","excelente","crack","de lujo","muy bien"]],
        "respuestas": ["¡De nada! ¿Algo más en lo que pueda ayudarte? 😊", "¡Con gusto! 🤝"],
    },
    "estado_animo": {
        "patrones": [
            ["como estas","que tal estas","eres feliz","tienes sentimientos",
             "estas bien","que haces","como vas"],
        ],
        "respuestas": [
            "¡Funcionando al 100%! Los bits no se cansan. 😄 ¿En qué te ayudo?",
            "¡Perfecto! Listo para lo que necesites. ¿Qué hacemos?",
            "Procesando consultas con energía total. ¿Qué tienes para mí?",
        ],
    },
    "tiempo": {
        "patrones": [
            ["que hora es","hora actual","que dia es","la fecha","fecha de hoy",
             "que dia es hoy","cuando estamos","que dia tenemos"],
        ],
        "respuestas": [],
    },
    "calculo": {
        "patrones": [
            ["cuanto es","calcula","resultado de","cuanto son","cuantos son",
             "opera","suma","resta","multiplica","divide","porcentaje","raiz"],
        ],
        "respuestas": [],
    },
    "analisis": {
        "patrones": [
            ["analiza","estadistica","media de","promedio de","mediana de",
             "desviacion","estos numeros","los datos son"],
        ],
        "respuestas": [],
    },
    "aleatorio": {
        "patrones": [
            ["numero aleatorio","numero random","al azar","entre y","tira el dado",
             "sortea","genera un numero","random entre"],
        ],
        "respuestas": [],
    },
    "buscar_web": {
        "patrones": [
            ["busca","buscar","que es","dime sobre","informacion sobre","explicame",
             "como funciona","para que sirve","quien es","define","que significa",
             "cuentame sobre","habla de","explica"],
        ],
        "respuestas": [],
    },
    "codigo": {
        "patrones": [
            ["codigo","code","ejemplo de","escribe un","crea un script","hazme un",
             "como se hace en python","como se hace en javascript","implementa",
             "programa que","funcion que","clase que"],
        ],
        "respuestas": [],
    },
    "automatizacion": {
        "patrones": [
            ["automatizacion","automatizar","workflow","flujo de trabajo","nodo",
             "trigger","crear automatizacion","n8n"],
        ],
        "respuestas": [
            "Para gestionar automatizaciones, ve a la **página de Automatizaciones** "
            "en el menú lateral. ⚡\n\n"
            "Allí puedes crear flujos con nodos, triggers y acciones, con **PAKO "
            "como motor de IA** para los nodos inteligentes.",
        ],
    },
    "memoria_stats": {
        "patrones": [
            ["cuanto sabes","que sabes","estadisticas","mis estadisticas","estado del sistema",
             "cuanto has aprendido","que has aprendido","stats","tu memoria"],
        ],
        "respuestas": [],
    },
    "broma": {
        "patrones": [
            ["chiste","broma","hazme reir","algo gracioso","joke","cuentame algo divertido"],
        ],
        "respuestas": [
            "¿Por qué los programadores odian la naturaleza? Porque tiene demasiados bugs. 🐛",
            "Un programador va al supermercado:\n'Compra pan, y si hay huevos trae una docena.'\nVolvió con 12 barras de pan. 🥖",
            "¿Cómo llamas a un programador de JavaScript? Un `undefined`. 😅",
            "¿Por qué Python es tan querido? Porque la indentación es obligatoria y los programadores ordenados son felices. 🐍",
        ],
    },
    "curiosidad": {
        "patrones": [
            ["dato curioso","sabias que","algo interesante","sorprendeme","fun fact","curiosidad"],
        ],
        "respuestas": [
            "🔍 El primer 'bug' informático real fue una polilla atrapada en un relé en 1947. Grace Hopper la pegó en su diario de operaciones.",
            "🐧 Linus Torvalds creó Linux en 1991 como hobby. Hoy tiene más de 27 millones de líneas de código.",
            "👩‍💻 Ada Lovelace escribió el primer algoritmo para una máquina en 1843, décadas antes de que existieran los ordenadores.",
            "⚡ El término 'debugging' viene literalmente de sacar insectos de las computadoras de los años 40.",
        ],
    },
    "desconocido": {
        "patrones": [],
        "respuestas": [
            "No lo sé todavía. Di **`busca [tema]`** y lo investigo en internet. 🔍",
            "Eso no lo tengo guardado. Puedes enseñármelo: **`aprende que X es Y`**",
            "Hmm, no encuentro eso en mi memoria. ¿Quieres que lo busque en internet?",
        ],
    },
}

# Patrones de comandos
_RE_APRENDER   = re.compile(
    r"aprende\s+que\s+(.+?)\s+(?:significa|es|son|equivale\s*a|quiere\s*decir)\s+(.+)",
    re.IGNORECASE | re.DOTALL
)
_RE_RECUERDA   = re.compile(
    r"recuerda\s+que\s+(.+?)\s+(?:es|son|significa)\s+(.+)", re.IGNORECASE | re.DOTALL
)
_RE_GUARDA     = re.compile(
    r"(?:guarda|memoriza)\s+que\s+(.+?)\s+(?:es|son)\s+(.+)", re.IGNORECASE | re.DOTALL
)
_RE_LEE        = re.compile(r"(?:lee|abre|lee\s+(?:el\s+)?archivo)\s+(.+)", re.IGNORECASE)
_RE_CARPETA    = re.compile(r"(?:añade|agrega)\s+carpeta\s+(.+)", re.IGNORECASE)
_RE_APREP_REPO = re.compile(r"aprende\s+del?\s+repo(?:sitorio)?\s+(.+)", re.IGNORECASE)
_RE_APREP_TODO = re.compile(r"aprende\s+de\s+(?:todos\s+)?mis\s+repos?", re.IGNORECASE)
_RE_URL        = re.compile(r"(?:lee|aprende\s+de)\s+(https?://\S+)", re.IGNORECASE)
_RE_NOMBRE     = re.compile(r"(?:mi\s+nombre\s+es|llamame|soy)\s+([A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,30})", re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════
# CEREBRO
# ══════════════════════════════════════════════════════════════════

class PakoBrain:
    def __init__(self, memory: "PakoMemory"):
        self.memory = memory
        self.fuzzy  = _fuzzy_global
        # Umbral mínimo de similitud para la memoria (CORRIGE el bug principal)
        self.MEM_UMBRAL = 0.55

        self.web_agent    = None
        self.github_agent = None
        self.file_agent   = None
        self.automations  = None

        self.buscando_web   = False
        self.leyendo_github = False

        self._contexto:    list[dict] = []
        self._ultimo_tema: str = ""

        self._vocab:    list[str] = []
        self._pat_vecs: list[tuple[str, list[float]]] = []
        self._construir_vectores()
        self._enriquecer_fuzzy()

    # ── Vectores ─────────────────────────────────────────────────

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

    def _enriquecer_fuzzy(self) -> None:
        palabras = []
        for e in self.memory.conocimiento.values():
            palabras.extend(tokenizar(e.clave))
        self.fuzzy.enriquecer_vocabulario(palabras)

    # ── Detección de intención ────────────────────────────────────

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

        # Refuerzo por substring exacto (mayor confianza)
        norm = normalizar(texto)
        for intent, data in INTENCIONES.items():
            for grupo in data["patrones"]:
                for frase in grupo:
                    if len(frase) > 4 and frase in norm:
                        return intent, max(mejor_sim, 0.90)

        return mejor_int, mejor_sim

    # ── Comandos de sistema ───────────────────────────────────────

    def _cmd_sistema(self, texto: str) -> Optional[tuple[str, str]]:
        # Nombre usuario
        m = _RE_NOMBRE.search(texto)
        if m:
            nombre = m.group(1).strip()
            self.memory.set_config("nombre_usuario", nombre)
            return f"¡Perfecto, **{nombre}**! Te recuerdo para siempre. 😊", "sistema"

        # Carpeta
        m = _RE_CARPETA.search(texto)
        if m and self.file_agent:
            ok, msg = self.file_agent.agregar_carpeta(m.group(1).strip())
            return (f"✅ {msg}" if ok else f"❌ {msg}"), "sistema"

        # Leer archivo
        m = _RE_LEE.search(texto)
        if m and self.file_agent:
            ruta = m.group(1).strip()
            contenido, msg = self.file_agent.leer_archivo(ruta)
            if contenido:
                prev = contenido[:1000] + (f"\n\n… ({len(contenido):,} bytes totales)" if len(contenido) > 1000 else "")
                return f"📄 **{ruta}**\n\n```\n{prev}\n```\n\n_{msg}_", "archivo"
            return f"❌ {msg}", "sistema"

        # URL
        m = _RE_URL.search(texto)
        if m and self.web_agent:
            n, msg = self.web_agent.aprender_de_url(m.group(1))
            return f"🌐 {msg}", "web"

        # GitHub todo
        if _RE_APREP_TODO.search(texto):
            if not self.github_agent or not self.github_agent.conectado:
                return "No conectado a GitHub. Conecta desde el panel lateral.", "sistema"
            n, msg = self.github_agent.aprender_de_todos_los_repos()
            return f"🐙 {msg}", "github"

        # GitHub repo específico
        m = _RE_APREP_REPO.search(texto)
        if m:
            if not self.github_agent or not self.github_agent.conectado:
                return "No conectado a GitHub.", "sistema"
            n, msg = self.github_agent.aprender_de_repo(m.group(1).strip())
            return f"🐙 {msg}", "github"

        # Mis repos (listar)
        if re.search(r"(?:mis\s+)?repos(?:itorios)?", normalizar(texto)):
            if self.github_agent and self.github_agent.conectado:
                repos = self.github_agent.listar_repos()
                lista = "\n".join(
                    f"  • **{r['nombre']}** {'🔒' if r['privado'] else '🔓'} — {r['desc'] or 'sin descripción'}"
                    for r in repos[:10]
                )
                return f"🐙 Tus repositorios ({len(repos)}):\n\n{lista}", "github"

        # Stats
        if re.search(r"estadisticas|stats|cuanto\s+sabes|estado\s+del\s+sistema", normalizar(texto)):
            return self._stats_texto(), "sistema"

        # Limpiar historial
        if re.search(r"(?:limpia|borra)\s+(?:el\s+)?historial", normalizar(texto)):
            self.memory.limpiar_historial()
            self._contexto.clear()
            return "🗑️ Historial limpiado. ¡Empezamos de cero!", "sistema"

        return None

    def _stats_texto(self) -> str:
        s = self.memory.stats()
        f = s.get("por_fuente", {})
        nombre = self.memory.get_config("nombre_usuario", "Usuario")
        auto_txt = ""
        if self.automations:
            a = self.automations.stats()
            auto_txt = f"\n⚡ Workflows: **{a['total_workflows']}** ({a['activos']} activos, {a['total_ejecuciones']} ejecuciones)"
        return (
            f"📊 **Estado de PAKO** _(para {nombre})_\n\n"
            f"🧠 Conocimiento: **{s['total']}** entradas ({s['ok']} activas)\n"
            f"📚 Manual: {f.get('manual',0)}  |  🌐 Web: {f.get('web',0)}  "
            f"|  🐙 GitHub: {f.get('github',0)}  |  📦 Base: {f.get('base',0)}\n"
            f"⏳ Pendientes: {s['pendientes']}\n"
            f"💬 Historial: {s['historial_mensajes']} mensajes"
            f"{auto_txt}"
        )

    # ── Aprendizaje ───────────────────────────────────────────────

    def _intentar_aprender(self, texto: str) -> Optional[str]:
        for pat in [_RE_APRENDER, _RE_RECUERDA, _RE_GUARDA]:
            m = pat.search(texto)
            if m:
                clave = re.sub(r"['\"""''`]", "", m.group(1)).strip()[:200]
                valor = re.sub(r"['\"""''`]", "", m.group(2)).strip()[:2000]
                if len(clave) < 2 or len(valor) < 2:
                    return "Necesito más detalle. Ej: **`aprende que Python es un lenguaje de programación`**"
                ok, msg = self.memory.guardar_conocimiento(
                    clave=clave, valor=valor, fuente="manual", confianza=1.0, auto_ok=True
                )
                self.fuzzy.enriquecer_vocabulario(tokenizar(clave))
                self._ultimo_tema = clave
                if "Ya lo sabía" in msg:
                    return f"✅ Ya sabía que **{clave}** es _{valor}_."
                return (
                    f"✅ ¡Aprendido! Ahora sé que **{clave}** es:\n\n"
                    f"> {valor}\n\n"
                    f"Lo recordaré siempre. 🧠"
                )
        return None

    # ── Contexto ─────────────────────────────────────────────────

    def _resolver_contexto(self, texto: str) -> str:
        norm = normalizar(texto)
        if any(r in norm for r in ["eso","esto","lo mismo","lo anterior","eso que dijiste"]):
            if self._ultimo_tema:
                return texto + f" (sobre {self._ultimo_tema})"
        return texto

    def _upd_ctx(self, txt: str, resp: str, fuente: str) -> None:
        self._contexto.append({"texto": txt, "respuesta": resp[:200], "fuente": fuente})
        if len(self._contexto) > 10:
            self._contexto = self._contexto[-10:]

    # ── Búsqueda en memoria CON UMBRAL ────────────────────────────

    def _buscar_memoria(self, texto: str) -> Optional[tuple[str, float, str]]:
        """
        Busca en memoria SOLO si el score supera MEM_UMBRAL.
        CORRIGE el bug de "cualquier resultado se devuelve".
        Retorna (respuesta, score, clave) o None.
        """
        resultados = self.memory.buscar(texto, limite=5)
        if not resultados:
            return None

        mejor = resultados[0]
        # Calcular score real entre la consulta y la clave encontrada
        tokens_q  = set(t for t in tokens_sig(tokenizar(texto)) if len(t) > 2)
        tokens_k  = set(t for t in tokens_sig(tokenizar(mejor.clave)) if len(t) > 2)

        if not tokens_q or not tokens_k:
            return None

        comunes   = tokens_q & tokens_k
        precision = len(comunes) / len(tokens_q)  # cuánto de la consulta está en la clave
        recall    = len(comunes) / len(tokens_k)   # cuánto de la clave está en la consulta
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # También medir similitud fuzzy
        sim_fuzzy = self.fuzzy.similitud_consulta(texto, mejor.clave)

        score = max(f1, sim_fuzzy)

        if score < self.MEM_UMBRAL:
            return None

        return mejor.valor, score, mejor.clave

    # ── Búsqueda web ──────────────────────────────────────────────

    def _buscar_web(self, texto: str) -> Optional[str]:
        if not self.web_agent:
            return None
        try:
            self.buscando_web = True
            r = self.web_agent.buscar_y_aprender(texto)
            self.buscando_web = False
            return r
        except Exception as ex:
            self.buscando_web = False
            self.memory.log("error", f"Web agent: {ex}")
            return None

    # ── Helpers de respuesta ─────────────────────────────────────

    def _saludo(self) -> str:
        hora    = time.localtime().tm_hour
        momento = "¡Buenos días" if hora < 12 else ("¡Buenas tardes" if hora < 20 else "¡Buenas noches")
        nombre  = self.memory.get_config("nombre_usuario", "")
        sufijo  = f", **{nombre}**" if nombre and nombre != "Usuario" else ""
        base    = f"{momento}{sufijo}! Soy **PAKO**. ¿En qué te ayudo?"
        s = self.memory.stats()
        if s["total"] > 0:
            base += f"\n\n💡 Tengo **{s['total']}** conceptos aprendidos."
        return base

    def _hora_fecha(self) -> str:
        loc   = time.localtime()
        dias  = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
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
            if a > b: a, b = b, a
            return f"🎲 Número aleatorio entre **{a}** y **{b}**: **{random.randint(a, b)}**"
        if "dado" in normalizar(texto) or "d20" in normalizar(texto):
            if "d20" in normalizar(texto):
                return f"🎲 D20: **{random.randint(1, 20)}**"
            return f"🎲 Dado (1-6): **{random.randint(1, 6)}**"
        return f"🎲 Número aleatorio: **{random.randint(1, 100)}**"

    # ══════════════════════════════════════════════════════════════
    # RESPONDER — FLUJO CORRECTO
    # ══════════════════════════════════════════════════════════════

    def responder(self, texto_usuario: str) -> tuple[str, str]:
        """
        Retorna (respuesta, fuente).
        Flujo con prioridad CORRECTA que evita los bugs del log.
        """
        texto = texto_usuario.strip()[:2000]
        if not texto:
            return "No te he oído. ¿Puedes repetirlo?", ""

        # ── 0. Corrección fuzzy silenciosa ────────────────────────
        texto_corr, _ = self.fuzzy.corregir_texto(texto)
        texto_res      = self._resolver_contexto(texto_corr)
        norm           = normalizar(texto_res)

        # ── 1. Comandos de sistema ────────────────────────────────
        cmd = self._cmd_sistema(texto_res)
        if cmd:
            r, f = cmd
            self._upd_ctx(texto, r, f)
            self.memory.agregar_mensaje("pako", r, f)
            return r, f

        # ── 2. Aprendizaje explícito ──────────────────────────────
        r = self._intentar_aprender(texto_res)
        if r:
            self._upd_ctx(texto, r, "manual")
            self.memory.agregar_mensaje("pako", r, "manual")
            return r, "manual"

        # ── 3. Detectar intención PRIMERO (antes de memoria) ──────
        #    Esto evita que "¿Qué puedes hacer?" devuelva SOLID
        intent, conf = self.detectar_intencion(texto_res)

        # Intenciones de respuesta directa (no necesitan memoria ni web)
        if intent == "saludo" and conf >= 0.25:
            r = self._saludo()
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "tiempo" and conf >= 0.45:
            r = self._hora_fecha()
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "aleatorio" and conf >= 0.30:
            r = self._aleatorio(texto_res)
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "ayuda" and conf >= 0.30:
            r = random.choice(INTENCIONES["ayuda"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "estado_animo" and conf >= 0.30:
            r = random.choice(INTENCIONES["estado_animo"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "identidad" and conf >= 0.30:
            r = random.choice(INTENCIONES["identidad"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "despedida" and conf >= 0.30:
            r = random.choice(INTENCIONES["despedida"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "gracias" and conf >= 0.30:
            r = random.choice(INTENCIONES["gracias"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "broma" and conf >= 0.30:
            r = random.choice(INTENCIONES["broma"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "curiosidad" and conf >= 0.30:
            r = random.choice(INTENCIONES["curiosidad"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "automatizacion" and conf >= 0.25:
            r = random.choice(INTENCIONES["automatizacion"]["respuestas"])
            self.memory.agregar_mensaje("pako", r, "")
            return r, ""

        if intent == "memoria_stats" and conf >= 0.30:
            r = self._stats_texto()
            self.memory.agregar_mensaje("pako", r, "sistema")
            return r, "sistema"

        # ── 4. Calculadora ────────────────────────────────────────
        r_calc = calcular(texto_res)
        if r_calc:
            kw = {"cuanto","calcula","resultado","suma","resta","multiplica",
                  "divide","porcentaje","raiz","opera"}
            if any(t in kw for t in tokenizar(texto_res)) or \
               bool(re.search(r"\d\s*[+\-*/^×÷]\s*\d", texto_res)):
                resp = f"🧮 El resultado es: **{r_calc}**"
                self.memory.agregar_mensaje("pako", resp, "calculo")
                return resp, "calculo"

        # ── 5. Análisis de datos ──────────────────────────────────
        if any(w in norm for w in ["analiza","estadistica","media","promedio","mediana","desviacion"]):
            r_anal = analizar_datos(texto_res)
            if r_anal:
                self.memory.agregar_mensaje("pako", r_anal, "calculo")
                return r_anal, "calculo"

        # ── 6. Generación de código ───────────────────────────────
        tpl = detectar_peticion_codigo(texto_res)
        if tpl:
            resp = (
                f"💻 _{tpl['desc']}_\n\n"
                f"```{tpl['lang']}\n{tpl['code']}\n```"
            )
            self.memory.agregar_mensaje("pako", resp, "codigo")
            return resp, "codigo"

        # ── 7. Búsqueda web EXPLÍCITA ─────────────────────────────
        #    Si el usuario pide explícitamente buscar, vamos a web ANTES
        #    que a memoria (evita el bug de "busca Docker" → A*)
        PREFIJOS_WEB = [
            "busca ", "buscar ", "que es ", "qué es ", "como funciona ",
            "cómo funciona ", "para que sirve ", "para qué sirve ",
            "explica ", "explicame ", "dime sobre ", "dime que es ",
            "quien es ", "quién es ", "define ", "que significa ",
            "información sobre ", "informacion sobre ", "cuéntame sobre ",
        ]
        es_busqueda_explicita = (
            intent == "buscar_web" and conf >= 0.20
        ) or any(norm.startswith(p) for p in PREFIJOS_WEB)

        if es_busqueda_explicita:
            # Limpiar el prefijo para la búsqueda
            query = texto_res
            for pref in PREFIJOS_WEB:
                if norm.startswith(pref):
                    query = texto_res[len(pref):].strip()
                    break

            # Primero buscar en memoria con threshold alto
            mem_r = self._buscar_memoria(query)
            if mem_r and mem_r[1] >= 0.70:  # Solo si confianza muy alta
                val, score, clave = mem_r
                self._ultimo_tema = clave
                resp = f"📚 {val}"
                self._upd_ctx(texto, resp, "memoria")
                self.memory.agregar_mensaje("pako", resp, "memoria")
                return resp, "memoria"

            # Si no hay en memoria con alta confianza, buscar en web
            if self.web_agent:
                r_web = self._buscar_web(query)
                if r_web:
                    self._ultimo_tema = query[:50]
                    self._upd_ctx(texto, r_web, "web")
                    self.memory.agregar_mensaje("pako", r_web, "web")
                    return r_web, "web"

        # ── 8. Memoria local con UMBRAL REAL ──────────────────────
        #    Solo si el score supera el umbral (CORRIGE el bug principal)
        mem_r = self._buscar_memoria(texto_res)
        if mem_r:
            val, score, clave = mem_r
            self._ultimo_tema = clave
            resp = f"📚 {val}"
            if score < 0.65:
                resp += "\n\n_(Resultado aproximado — di `busca [tema]` para verificar)_"
            self._upd_ctx(texto, resp, "memoria")
            self.memory.agregar_mensaje("pako", resp, "memoria")
            return resp, "memoria"

        # ── 9. Búsqueda web automática (fallback) ─────────────────
        if self.web_agent and self.memory.get_config("busqueda_web_auto", True):
            tokens_q = tokenizar(texto_res)
            if len(tokens_q) >= 2:
                r_web = self._buscar_web(texto_res)
                if r_web:
                    self._upd_ctx(texto, r_web, "web")
                    self.memory.agregar_mensaje("pako", r_web, "web")
                    return r_web, "web"

        # ── 10. Intenciones de baja confianza ─────────────────────
        if intent in INTENCIONES and conf >= 0.12:
            resps = INTENCIONES[intent]["respuestas"]
            if resps:
                r = random.choice(resps)
                self.memory.agregar_mensaje("pako", r, "")
                return r, ""

        # ── 11. Fallback ──────────────────────────────────────────
        r = random.choice(INTENCIONES["desconocido"]["respuestas"])
        self.memory.agregar_mensaje("pako", r, "")
        return r, ""

    # ── Stats API ─────────────────────────────────────────────────

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
