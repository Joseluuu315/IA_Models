Quiero que desarrolles una IA llamada PACO (o PAKO) completamente funcional, partiendo de un sistema tipo chatbot ya existente basado en:

- Tokenización
- Bag of Words
- Similitud coseno
- Sistema de intenciones
- Memoria persistente en JSON

El objetivo es evolucionarlo a un sistema híbrido inteligente con aprendizaje automático controlado, navegación web y acceso a repositorios.

---

# 🧩 FUNCIONALIDADES PRINCIPALES

## 1. Chatbot base
- Mantener todas las funcionalidades actuales:
  - Conversación natural
  - Cálculos matemáticos
  - Estadísticas
  - Respuestas contextuales
  - Sistema de aprendizaje manual ("aprende que X es Y")

---

## 2. Aprendizaje automático desde GitHub

Implementar un módulo que:

- Permita login mediante OAuth de GitHub
- Acceda a los repositorios del usuario autenticado
- Lea automáticamente:
  - README.md
  - Código fuente (solo lectura)
- Extraiga conocimiento útil

El sistema debe:
- Analizar contenido
- Transformarlo en conocimiento estructurado tipo:
  - "X es Y"
  - "X sirve para Y"
- Filtrar contenido irrelevante o duplicado

IMPORTANTE:
- Nunca modificar repositorios
- Solo lectura
- No ejecutar código externo

---

## 3. Navegación y aprendizaje desde internet

Crear un agente que:

- Busque información en internet cuando no sepa algo
- Extraiga contenido relevante
- Lo procese y lo convierta en conocimiento útil

Flujo:
1. Detectar falta de conocimiento
2. Buscar información
3. Limpiar texto
4. Generar conocimiento estructurado
5. Validar antes de guardar

---

## 4. Sistema de autoaprendizaje CONTROLADO

- PACO debe poder aprender automáticamente, pero con reglas:
  - Validación obligatoria del conocimiento
  - Evitar duplicados
  - Evitar contradicciones
- Guardar conocimiento en base de datos local (JSON o DB)

---

## 5. Acceso a archivos locales (modo seguro)

Implementar módulo que:

- Permita leer archivos del usuario (solo lectura)
- Limitar a carpetas específicas configurables
- Extraer conocimiento útil de:
  - Documentos
  - Código
  - Notas

RESTRICCIONES:
- No borrar archivos
- No modificar archivos
- No ejecutar programas
- No acceder a datos sensibles

---

## 6. Motor híbrido de respuesta

Cuando el usuario pregunte:

1. Buscar en memoria local
2. Si no hay respuesta:
   - Buscar en internet o GitHub
3. Generar respuesta
4. Opcional: aprender del resultado

---

## 7. Interfaz moderna (MUY IMPORTANTE)

Desarrollar una UI moderna tipo ChatGPT:

- Frontend con React + Tailwind
- Diseño limpio, minimalista y profesional
- Animaciones suaves
- Chat en tiempo real
- Panel lateral con:
  - Memoria aprendida
  - Estado del sistema
  - Actividad de aprendizaje

Extras:
- Indicador de “aprendiendo…”
- Botón para activar/desactivar autoaprendizaje
- Botón para conectar con GitHub

---

## 8. Arquitectura del sistema

Separar en módulos:

- paco_brain.py → lógica principal
- paco_web_agent.py → navegación web
- paco_github_agent.py → integración GitHub
- paco_memory.py → almacenamiento
- paco_server.py → backend API
- frontend → React app

---

## 9. Seguridad y estabilidad

- Manejo de errores robusto
- Logs de actividad
- Sistema de validación de conocimiento
- Evitar aprendizaje de datos corruptos

---

## 10. Escalabilidad futura

Preparar el sistema para:

- Integrar embeddings en el futuro
- Integrar modelos tipo LLM
- Migrar a base de datos vectorial

---

# 🎯 OBJETIVO FINAL

Crear una IA local avanzada que:

- Aprende del usuario
- Aprende de internet
- Aprende de GitHub
- Mejora con el tiempo
- Mantiene control y estabilidad
- Tiene interfaz moderna

---

Entrega:

- Código completo funcional
- Estructura del proyecto
- Instrucciones de instalación
- Ejemplo de uso