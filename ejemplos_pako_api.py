"""
ejemplos_pako_api.py — Ejemplos de uso de la API de PAKO

Ejecuta el servidor primero:
  python pako_api_server.py

Luego corre este archivo:
  python ejemplos_pako_api.py
"""

import json
import requests

BASE_URL = "http://localhost:11434"
API_KEY  = "pako"   # cualquier valor si no hay autenticación


# ══════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ══════════════════════════════════════════════════════════════════

def ejemplo_health():
    print("=" * 50)
    print("1. HEALTH CHECK")
    r = requests.get(f"{BASE_URL}/health")
    data = r.json()
    print(f"   Status:     {data['status']}")
    print(f"   Modelo:     {data['model']}")
    print(f"   Uptime:     {data['uptime_s']}s")
    print(f"   Conocimiento: {data['knowledge']} entradas")


# ══════════════════════════════════════════════════════════════════
# 2. CHAT NATIVO (API de PAKO)
# ══════════════════════════════════════════════════════════════════

def ejemplo_chat_nativo():
    print("\n" + "=" * 50)
    print("2. CHAT NATIVO /api/chat")
    preguntas = [
        "qué es Docker?",
        "tomat",               # fuzzy: tomat → tomate (o búsqueda)
        "cuanto es 15% de 200",
        "aprende que Astro es un framework web para JavaScript moderno",
        "qué es Astro?",       # debe recordarlo
    ]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    for pregunta in preguntas:
        r = requests.post(f"{BASE_URL}/api/chat", json={"mensaje": pregunta}, headers=headers)
        data = r.json()
        print(f"\n   👤 {pregunta}")
        print(f"   🤖 {data['respuesta'][:120]}{'...' if len(data['respuesta'])>120 else ''}")
        print(f"   📌 fuente: {data.get('fuente','?')} | tokens: {data.get('tokens_usados','?')}")


# ══════════════════════════════════════════════════════════════════
# 3. OPENAI-COMPATIBLE CHAT (con requests)
# ══════════════════════════════════════════════════════════════════

def ejemplo_openai_requests():
    print("\n" + "=" * 50)
    print("3. OPENAI-COMPATIBLE /v1/chat/completions")
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    payload = {
        "model":    "pako",
        "messages": [
            {"role": "system",    "content": "Eres un experto en programación. Responde de forma concisa."},
            {"role": "user",      "content": "qué es un decorador en Python?"},
        ],
        "stream": False,
    }
    r    = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, headers=headers)
    data = r.json()
    msg  = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(f"\n   Respuesta: {msg[:200]}{'...' if len(msg)>200 else ''}")
    print(f"   Tokens: prompt={usage.get('prompt_tokens','?')} | completion={usage.get('completion_tokens','?')}")


# ══════════════════════════════════════════════════════════════════
# 4. OPENAI SDK (si está instalado)
# ══════════════════════════════════════════════════════════════════

def ejemplo_openai_sdk():
    print("\n" + "=" * 50)
    print("4. OPENAI SDK (pip install openai)")
    try:
        from openai import OpenAI
        client = OpenAI(base_url=f"{BASE_URL}/v1", api_key=API_KEY)

        # Listar modelos
        models = client.models.list()
        print(f"   Modelos disponibles: {[m.id for m in models.data]}")

        # Chat
        response = client.chat.completions.create(
            model="pako",
            messages=[
                {"role": "user", "content": "qué es Kubernetes en una frase?"}
            ]
        )
        print(f"\n   Respuesta: {response.choices[0].message.content}")
        print(f"   Modelo:    {response.model}")
        print(f"   Tokens:    {response.usage.total_tokens}")

    except ImportError:
        print("   ⚠️  openai no instalado. Instala con: pip install openai")
    except Exception as ex:
        print(f"   ❌ Error: {ex}")


# ══════════════════════════════════════════════════════════════════
# 5. STREAMING
# ══════════════════════════════════════════════════════════════════

def ejemplo_streaming():
    print("\n" + "=" * 50)
    print("5. STREAMING /v1/chat/completions (stream: true)")
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    payload = {
        "model":    "pako",
        "messages": [{"role": "user", "content": "explícame qué es SOLID"}],
        "stream":   True,
    }
    print("   Respuesta: ", end="", flush=True)
    with requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, headers=headers, stream=True) as r:
        for line in r.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded == "data: [DONE]":
                break
            if decoded.startswith("data: "):
                try:
                    chunk = json.loads(decoded[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    print(content, end="", flush=True)
                except Exception:
                    pass
    print()  # newline final


# ══════════════════════════════════════════════════════════════════
# 6. ENSEÑAR CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════

def ejemplo_aprender():
    print("\n" + "=" * 50)
    print("6. ENSEÑAR CONOCIMIENTO /api/learn")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    conocimientos = [
        {"clave": "Mi empresa",          "valor": "Desarrollamos software de gestión para PYMEs en España"},
        {"clave": "Stack tecnológico",    "valor": "Python, FastAPI, PostgreSQL, React, Docker"},
        {"clave": "Horario de trabajo",  "valor": "Lunes a viernes, 9:00 a 18:00 CET"},
    ]
    for c in conocimientos:
        r = requests.post(f"{BASE_URL}/api/learn", json=c, headers=headers)
        data = r.json()
        print(f"   {'✅' if data['ok'] else '❌'} {c['clave']}: {data['mensaje']}")


# ══════════════════════════════════════════════════════════════════
# 7. BUSCAR EN MEMORIA
# ══════════════════════════════════════════════════════════════════

def ejemplo_buscar():
    print("\n" + "=" * 50)
    print("7. BUSCAR EN MEMORIA /api/search")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    queries = ["python framework", "docker", "empresa stack"]
    for q in queries:
        r    = requests.post(f"{BASE_URL}/api/search", json={"query": q, "limit": 3}, headers=headers)
        data = r.json()
        print(f"\n   🔍 '{q}' → {data['total']} resultado(s):")
        for res in data["results"]:
            conf = int(res['confianza'] * 100)
            print(f"      [{conf}%] {res['clave']}: {res['valor'][:80]}")


# ══════════════════════════════════════════════════════════════════
# 8. EMBEDDINGS
# ══════════════════════════════════════════════════════════════════

def ejemplo_embeddings():
    print("\n" + "=" * 50)
    print("8. EMBEDDINGS /v1/embeddings")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    r = requests.post(f"{BASE_URL}/v1/embeddings", json={
        "model": "pako-embed",
        "input": ["Docker es una plataforma de contenedores", "Python es un lenguaje de programación"],
    }, headers=headers)
    data = r.json()
    print(f"   Embeddings generados: {len(data['data'])}")
    for emb in data["data"]:
        vec = emb["embedding"]
        print(f"   [{emb['index']}] dimensiones={len(vec)}, primeros valores={vec[:5]}")


# ══════════════════════════════════════════════════════════════════
# 9. LISTA DE MODELOS
# ══════════════════════════════════════════════════════════════════

def ejemplo_modelos():
    print("\n" + "=" * 50)
    print("9. LISTA DE MODELOS /v1/models")
    headers = {"Authorization": f"Bearer {API_KEY}"}
    r    = requests.get(f"{BASE_URL}/v1/models", headers=headers)
    data = r.json()
    for model in data["data"]:
        print(f"   • {model['id']} (owned_by: {model.get('owned_by','?')})")


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n🧠 PAKO API — Ejemplos de uso")
    print(f"   Base URL: {BASE_URL}")
    print(f"   API Key:  {API_KEY}")

    # Verificar que el servidor está activo
    try:
        requests.get(f"{BASE_URL}/health", timeout=3)
    except Exception:
        print(f"\n❌ No se puede conectar a {BASE_URL}")
        print("   Asegúrate de que el servidor está activo:")
        print("   python pako_api_server.py\n")
        exit(1)

    ejemplo_health()
    ejemplo_chat_nativo()
    ejemplo_openai_requests()
    ejemplo_openai_sdk()
    ejemplo_streaming()
    ejemplo_aprender()
    ejemplo_buscar()
    ejemplo_embeddings()
    ejemplo_modelos()

    print("\n\n✅ Todos los ejemplos completados.")
    print("   Visita http://localhost:11434/api/docs para la documentación interactiva.\n")
