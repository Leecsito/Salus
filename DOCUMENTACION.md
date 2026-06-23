# Documentación del Proyecto: SALUS (Chatbot de Nature's Green)

## Descripción General
**SALUS** es un chatbot de atención al cliente y ventas para **Nature's Green**, una tienda/farmacia naturista. Utiliza inteligencia artificial (modelos Llama 3.1 alojados en Groq) para mantener una conversación natural con el usuario, identificar su necesidad y realizar acciones específicas como buscar productos en una base de datos remota (Turso).

Está desplegado como aplicación web con Flask en **Render**: https://salus-ctix.onrender.com

---

## Arquitectura y Flujo de Ejecución

El chatbot está dividido en **fases lógicas**, cada una mapeada a una carpeta y un archivo `.py`. El estado de la conversación (historial de mensajes y fase actual) se guarda en la **sesión de Flask**, lo que permite que cada petición HTTP sea independiente.

```
chatbot/
├── app.py               ← Servidor Flask. Punto de entrada web.
├── main.py              ← Fase 1: Recepcionista virtual
├── asesoria/
│   └── FASE1.py         ← Fase 2: Asesor de salud
├── producto/
│   └── FASE1.py         ← Fase 3: Módulo de búsqueda de productos
├── templates/
│   └── index.html       ← Interfaz web del chat
├── static/
│   ├── style.css        ← Estilos CSS premium
│   └── script.js        ← Lógica de cliente (Fetch API)
├── Procfile             ← Instrucción de inicio para Gunicorn en Render
└── requirements.txt     ← Dependencias del proyecto
```

---

### 1. Servidor Flask (`app.py`)
- **Propósito:** Punto de entrada único de la aplicación web.
- **Rutas:**
  - `GET /` → Renderiza `templates/index.html`.
  - `POST /api/chat` → Recibe el mensaje del usuario como JSON, consulta el módulo correspondiente a la fase actual y devuelve la respuesta en JSON (incluyendo información de debug: fase, módulo, carpeta).
  - `POST /api/reset` → Limpia la sesión del usuario y reinicia el chat.
- **Gestión de estado:** Usa `session` de Flask para guardar `fase` e `historial` entre peticiones.
- **Error handling:** Handlers globales `@app.errorhandler` garantizan que cualquier error devuelva JSON (nunca HTML), lo que evita que el frontend crashee al parsear.

---

### 2. Fase 1: Recepcionista Virtual (`main.py`)
- **Propósito:** Primer punto de contacto. Mantiene una conversación empática para descubrir la intención del usuario.
- **Función principal:** `responder_recepcion(mensaje_usuario, historial)` → devuelve `(respuesta_ia, intencion, historial_actualizado)`.
- **Lógica de Intenciones:** Clasifica la necesidad en:
  - `"pendiente"`: Aún no está clara la necesidad. Sigue conversando.
  - `"producto"`: El usuario quiere un artículo específico.
  - `"asesoria"`: El usuario pide una recomendación para un síntoma.
  - `"historial"`: El usuario quiere gestionar su expediente clínico.
- **Enrutamiento:** Cuando la intención cambia de `"pendiente"`, `app.py` actualiza `session['fase']` y redirige al módulo correspondiente.

---

### 3. Fase 2: Asesoría de Salud (`asesoria/FASE1.py`)
- **Propósito:** Atiende a los clientes cuya intención es `"asesoria"`. Actúa como farmacéutico o asesor de salud.
- **Función principal:** `responder_asesoria(mensaje_usuario, historial)` → devuelve `(respuesta_ia, estado, producto_sugerido, historial_actualizado)`.
- **Proceso:**
  1. Indaga brevemente sobre síntomas con preguntas cortas y amables.
  2. Recomienda un tipo de producto genérico (ej. "pomada", "colágeno").
  3. Cuando `estado == "producto_encontrado"`, `app.py` pasa automáticamente a la Fase 3 y ejecuta la búsqueda.

---

### 4. Fase 3: Módulo de Productos (`producto/FASE1.py`)
- **Propósito:** Atiende solicitudes con intención `"producto"` o recibe recomendaciones de la Fase 2.
- **Función principal:** `ejecutar_fase_2(mensaje_usuario)` → corrutina `async` ejecutada con `asyncio.run()` desde `app.py`.
- **Proceso:**
  1. **Extracción:** Usa IA para extraer el sustantivo principal del producto (singular).
  2. **Consulta a BD:** Se conecta a **Turso** (SQLite serverless) vía `libsql-client` y busca coincidencias.
  3. **Respuesta Final:** La IA genera una respuesta natural con nombre, precio, disponibilidad y enlace web.

---

### 5. Módulos Pendientes de Implementación
- **Historial (`historial/FASE1.py`):** CRUD de historiales clínicos. Actualmente devuelve un mensaje informativo.

---

## Stack Tecnológico
| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11 |
| Framework Web | Flask 3.x |
| Servidor de Producción | Gunicorn |
| IA / LLM | Llama 3.1 8B Instant via API de **Groq** |
| Base de Datos | **Turso** (SQLite serverless) con `libsql-client` |
| Frontend | HTML5, CSS3 Vanilla, JavaScript (Fetch API) |
| Hosting | **Render** (plan gratuito) |
| Sesiones | Flask `session` (cookie cifrada con `SECRET_KEY`) |

## Manejo de Rate Limits (429)
Ambos módulos (`main.py` y `producto/FASE1.py`) iteran automáticamente sobre un array de `API_KEYS` si la key activa devuelve HTTP 429, garantizando estabilidad en la capa gratuita de Groq.

## Debug Banner (solo en fase de pruebas)
La interfaz web muestra un banner en tiempo real con:
- **Fase:** nombre de la fase actual (`recepcion`, `asesoria`, `producto`, `historial`)
- **Módulo:** archivo `.py` que está procesando la petición
- **Carpeta:** carpeta del proyecto donde vive ese módulo

Esta información la provee `app.py` en cada respuesta JSON bajo la clave `"debug"`.

---
*Nota para el Asistente de IA: Al retomar este proyecto, lee este archivo para entender la estructura de carpetas, el flujo de sesiones Flask, el estado de las integraciones (Groq + Turso) y la lógica de enrutamiento basada en las intenciones de la Fase 1.*
