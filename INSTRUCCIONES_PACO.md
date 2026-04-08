# PACO — IA Propia desde cero

## Instalación (solo necesitas Python 3.10+, sin librerías externas)

```bash
# 1. Pon los 3 archivos en la misma carpeta:
#    paco.py · paco_brain.py · paco_server.py

# 2. Ejecuta:
python paco.py

# 3. Abre en el navegador:
#    http://localhost:8765
```

---

## Qué sabe hacer Paco

| Capacidad           | Ejemplo                                              |
|---------------------|------------------------------------------------------|
| Saludar / conversar | "Hola Paco", "¿cómo estás?"                         |
| Calcular            | "¿cuánto es 347 * 28?"  "15% de 200"                |
| Potencias / raíz    | "calcula 2 elevado a 10"                            |
| Estadísticas        | "analiza estos datos: 12, 45, 7, 89, 34"            |
| Hora y fecha        | "¿qué hora es?"  "¿qué día es hoy?"                 |
| Nº aleatorios       | "número aleatorio entre 1 y 100"                    |
| Chistes / curiosidades | "cuéntame un chiste"  "dato curioso"             |
| **Aprender**        | "aprende que X es Y"                                |
| **Recordar**        | Lo aprendido se guarda en `paco_aprendido.json`     |

---

## Cómo enseñarle cosas nuevas

```
aprende que Django es un framework web de Python
aprende que la velocidad de la luz es 299.792 km/s
aprende que mi nombre es Juan
aprende que el proyecto Alpha significa el proyecto secreto
```

Paco lo recordará aunque cierres y vuelvas a abrir el programa.

---

## Archivos del proyecto

```
paco.py          → Punto de entrada (ejecuta esto)
paco_brain.py    → Cerebro: lógica, NLP, aprendizaje, cálculo
paco_server.py   → Servidor web + interfaz de chat
paco_aprendido.json  → Se crea automáticamente con lo aprendido
```

---

## Cómo funciona por dentro (sin modelos externos)

1. **Tokenizador**: divide el texto en palabras, normaliza acentos
2. **Bag-of-Words**: convierte texto en vectores numéricos
3. **Similitud coseno**: mide cuánto se parece tu mensaje a cada patrón conocido
4. **Motor de intenciones**: clasifica el mensaje (saludo, cálculo, pregunta, etc.)
5. **Calculadora propia**: extrae y evalúa expresiones matemáticas del texto natural
6. **Aprendizaje persistente**: guarda lo que le enseñas en JSON
7. **Memoria conversacional**: recuerda el contexto de la sesión actual
