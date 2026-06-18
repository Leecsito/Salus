# Documentación del Proyecto: Chatbot "Nature's Green"

## Descripción General
Este proyecto es un chatbot de atención al cliente y ventas para una tienda/farmacia llamada **"Nature's Green"**. Utiliza inteligencia artificial (modelos Llama 3.1 alojados en Groq) para mantener una conversación natural con el usuario, identificar su necesidad y realizar acciones específicas como buscar productos en una base de datos remota (Turso).

## Arquitectura y Flujo de Ejecución

El chatbot está dividido en **fases lógicas**. Actualmente, el flujo de ejecución arranca desde `main.py` (Fase 1) y delega la responsabilidad a submódulos según lo que el cliente necesite.

### 1. Fase 1: Recepcionista Virtual (`main.py`)
- **Propósito:** Actúa como el primer punto de contacto. Su objetivo es mantener una charla empática con el usuario hasta descubrir explícitamente qué necesita.
- **Lógica de Intenciones:** Clasifica la necesidad del usuario en una de las siguientes categorías:
  - `"pendiente"`: Aún no está clara la necesidad. Sigue conversando.
  - `"producto"`: El usuario quiere comprar, cotizar o saber si hay disponibilidad de un artículo específico.
  - `"asesoria"`: El usuario pide una recomendación médica para un dolor, síntoma o situación, pero aún no sabe qué producto comprar.
  - `"historial"`: El usuario quiere abrir o gestionar su expediente clínico.
- **Enrutamiento:** Cuando la intención deja de ser `"pendiente"`, la Fase 1 termina y el flujo se envía al módulo correspondiente.

### 2. Fase 2: Asesoría de Salud (`asesoria/FASE1.py`)
- **Propósito:** Atiende a los clientes cuya intención es `"asesoria"`. Actúa como un profesional de la salud o farmacéutico.
- **Proceso:**
  1. **Diagnóstico:** Indaga brevemente sobre los síntomas del usuario.
  2. **Recomendación:** Determina qué tipo de producto (ej. "pomada", "colágeno") le vendría bien al usuario y se lo recomienda.
  3. **Transición Automática:** Una vez determinado el producto ideal, termina su ejecución y devuelve el control a `main.py` junto con el nombre del producto sugerido. `main.py` entonces enruta automáticamente a la **Fase 3 (Producto)**.

### 3. Fase 3: Módulo de Productos (`producto/FASE1.py`)
- **Propósito:** Atiende directamente las solicitudes con intención `"producto"` (cuando el cliente sabe qué quiere) o recibe las recomendaciones de la **Fase 2**.
- **Proceso:**
  1. **Extracción:** Usa IA para extraer únicamente el sustantivo principal (singular) del producto a buscar.
  2. **Consulta a BD:** Se conecta a una base de datos SQLite remota en **Turso** usando `libsql-client` (protocolo `https://`). Busca el término y trae coincidencias (nombre, precio, stock, descripción, slug, etc.).
  3. **Respuesta Final:** Pasa los resultados de la BD a la IA para que genere una respuesta natural, directa y orientada a la venta, informando disponibilidad, precio y un enlace web.

#### Módulos Pendientes de Implementación
- **Historial:** Deberá encargarse del CRUD (Crear, Leer, Actualizar, Borrar) de historiales clínicos.

## Stack Tecnológico y Detalles Técnicos
- **Lenguaje:** Python 3 + `asyncio`.
- **IA (LLM):** Modelos `llama-3.1-8b-instant` vía la API de **Groq**.
- **Base de Datos:** **Turso** (SQLite serverless) interactuando con la librería `libsql-client`.
- **Manejo de Rate Limits (429):** Dado que la capa gratuita de Groq puede lanzar errores HTTP 429 por límite de peticiones, **ambos módulos** (`main.py` y `producto/FASE1.py`) cuentan con un sistema de respaldo (`fallback`) que itera automáticamente entre un arreglo de múltiples `API_KEYS` si la primera falla, garantizando estabilidad en el servicio.

---
*Nota para el Asistente de IA: Al retomar este proyecto, lee este archivo para entender la estructura de carpetas, el estado de las integraciones (Groq + Turso) y la lógica de enrutamiento basada en las intenciones de la Fase 1.*
