# SALUS — Documentación Técnica

**Proyecto:** Chatbot de atención al cliente y ventas para **Nature's Green** (tienda/farmacia naturista)  
**Tipo:** Aplicación web Flask con IA conversacional multi-fase (Saludo → Atención → Asesoría → Producto, con componentes futuros de tratamiento, venta e historial)  
**Entorno de ejecución:** Python 3.11 (Windows / Linux)  
**Despliegue:** Render — https://salus-ctix.onrender.com  
**Tienda en línea:** https://www.naturesgreenec.com  
**Base de datos:** Turso (SQLite serverless) mediante `libsql-client`  
**Estado de conversación:** Flask `session` (cookie firmada con `SECRET_KEY`)  
**Control de versiones:** Git / GitHub (`Leecsito/Salus`) — https://github.com/Leecsito/Salus

---

## 1. Stack Tecnológico

| Capa | Tecnología | Propósito |
|------|------------|-----------|
| **Lenguaje base** | Python 3.11 | Núcleo del servidor y de los módulos de IA |
| **Framework web** | Flask 3.x | Rutas HTTP, sesiones, renderizado de plantillas |
| **Servidor de producción** | Gunicorn | `Procfile`: `web: gunicorn app:app --workers 1 --threads 8 --timeout 120` (Render) |
| **IA / LLM** | GPT-OSS 20B (API de **Groq**, SDK `groq`) | Clasificación de intenciones, diálogo de asesoría, extracción del término y generación de respuestas |
| **Base de datos** | **Turso** (SQLite serverless) vía `libsql-client` | Catálogo de productos de Nature's Green |
| **Búsqueda web** | **Tavily** (REST con `httpx`) | Respaldo cuando la DB no alcanza (datos puntuales o 0 resultados), con filtro de producto exacto y caché en memoria |
| **Configuración** | `python-dotenv` + variables de entorno | Credenciales y secretos (única fuente: `core/config.py`) |
| **Estado de sesión** | Flask `session` (cookie cifrada con `SECRET_KEY`) | Guarda `fase` actual e `historial` de mensajes entre peticiones HTTP |
| **Frontend** | HTML5, CSS3 vanilla, JavaScript (Fetch API) | Interfaz de chat minimalista |
| **Protección** | Flask-Limiter | Límite de peticiones por IP en `/api/chat` (protege la cuota de Groq) |
| **Observabilidad** | `logging` estándar + buffer en memoria + panel en el frontend | Traza cada petición: módulo, prompt/modelo, key usada, tiempos, decisiones y errores |
| **Hosting** | **Render** (plan gratuito) | Despliegue desde Git con Gunicorn |

Modelo Groq usado en el diálogo (saludo, atención, asesoría, vendedor y repregunta): `openai/gpt-oss-20b` (`GROQ_MODEL`). El **extractor** usa un modelo propio (`GROQ_MODEL_EXTRACCION`, default `openai/gpt-oss-120b`) para repartir la cuota diaria de tokens (cada modelo tiene su propio TPD en Groq).

---

## 2. Estructura de Directorios

```
Salus/
│
├── app.py                       # Solo rutas Flask: validación, despacho a flujo.py y JSON
├── flujo.py                     # Orquestador: registro de fases y despacho de transiciones
├── Procfile                     # Instrucción de arranque para Render (gunicorn con timeout/workers)
├── requirements.txt             # Dependencias Python del proyecto (versiones fijadas)
├── .env.example                 # Plantilla de variables de entorno para desarrollo local
├── DOCUMENTACION.md             # Documentación técnica central (este archivo)
├── enrich_products.py           # Herramienta offline: limpia/enriquece la tabla productos (Tavily + Groq)
│
├── core/                        # Infraestructura compartida (sin lógica de negocio)
│   ├── config.py                # Configuración central: único lugar que lee variables de entorno
│   ├── groq_cliente.py          # Cliente Groq único: fallback de API Keys ante 401/429
│   └── logs.py                  # Logging: consola + buffer en memoria para /api/logs
│
├── saludo/                      # FASE 0 — Saludo inicial generado por LLM
│   └── saludo.py                # Saludo humano y variado; pasa a la fase atención
│
├── atencion/                    # FASE 1 — Atención (antes main.py): clasifica la intención
│   └── atencion.py
│
├── asesoria/                    # FASE 2 — Asesor de salud
│   └── asesoria.py              # Prompt del asesor + orquestación de la conversación
│
├── producto/                    # FASE 3 — Búsqueda y venta de productos
│   ├── producto.py              # Orquestador del componente + responder() estándar
│   ├── contexto.py              # Últimos N turnos como transcript para extractor/vendedor
│   ├── extractor.py             # Extrae término, necesidad, intención y requiere_web (con contexto)
│   ├── database.py              # Consulta el catálogo en Turso (LIMITE_PRODUCTOS filas)
│   ├── vendedor.py              # Respuesta de ventas conversacional (sin ficha)
│   └── buscador.py              # Respaldo web (Tavily): filtro de producto exacto + caché
│
├── tratamiento/                 # FASE 4 — Tratamiento (ESQUELETO, pendiente)
│   └── tratamiento.py
├── venta/                       # FASE 5 — Pago y cierre (ESQUELETO, pendiente)
│   └── venta.py
├── historial/                   # FASE 6 — Historial clínico (ESQUELETO, pendiente)
│   └── historial.py
│
├── templates/
│   └── index.html               # Interfaz web del chat
│
└── static/
    ├── style.css                # Estilos (tema verde, burbujas, animaciones)
    └── script.js                # Lógica cliente: Fetch API, indicador de escritura, reset
```

> Cada paquete (`core/`, `saludo/`, `atencion/`, `asesoria/`, `producto/`, `tratamiento/`, `venta/`, `historial/`) incluye un `__init__.py` vacío.

### Convenciones de nombres

| Patrón | Significado |
|--------|-------------|
| `app.py` | Único punto de entrada web. Solo valida peticiones y serializa JSON; **no conoce fases**. |
| `flujo.py` | Orquestador central: mapa `FASES`, `FASE_INICIAL` y `despachar()`. Único lugar con transiciones. |
| `core/` | Infraestructura compartida (config, cliente Groq, logging). Sin lógica de negocio. |
| `<componente>/<componente>.py` | Componente de fase. Expone `responder(mensaje, historial) -> (respuesta, siguiente_fase, historial)`. |
| `producto/<verbo>or.py` (`extractor`, `vendedor`, `buscador`) | Helpers con una única responsabilidad dentro del componente producto. |
| `__init__.py` | Presente (y vacío) en cada paquete; solo marca el paquete. |

### Cómo agregar un componente nuevo

1. Crear el paquete `nuevo/` con `__init__.py` y `nuevo/nuevo.py` que exponga `responder(mensaje, historial) -> (respuesta, siguiente_fase, historial)` (documentar en la docstring si internamente es `async`).
2. Registrarlo en `FASES` de `flujo.py`. `app.py` **no se toca**.
3. Actualizar esta documentación (directiva obligatoria).

---

## 3. Arquitectura del Sistema

### A. Máquina de estados de fases (`session['fase']`)

El estado de la conversación vive en la **sesión de Flask**, lo que permite que cada petición HTTP sea independiente (el servidor no guarda estado en memoria, requisito para Gunicorn/Render).

```
                    ┌─────────────────────────────────────┐
                    │           session['fase']           │
                    │    (saludo por defecto al inicio)   │
                    └──────────────────┬──────────────────┘
                                       │  flujo.despachar()
        ┌──────────────┬───────────────┼───────────────┬──────────────────┐
        ▼              ▼               ▼               ▼                  │
   ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   ┌──────────────┐
   │  saludo  │  │  atencion  │  │  asesoria  │  │  producto  │   │ tratamiento /│
   │saludo.py │  │atencion.py │  │asesoria.py │  │producto.py │   │ venta /      │
   │ LLM:     │  │ clasifica  │  │ indaga y   │  │extractor→  │   │ historial    │
   │ saluda   │  │ intención  │  │ recomienda │  │database→   │   │ (esqueletos) │
   └────┬─────┘  └─────┬──────┘  └─────┬──────┘  │vendedor    │   └──────────────┘
        │              │               │         └────────────┘
        │ siempre      │ intención ∈   │ estado ==
        │ → atención   │ {producto,    │ "producto_encontrado"
        │              │  asesoria,    │ (busca y concatena)
        │              │  historial,   │
        │              │  tratamiento  │
        │              │   → historial}│
         ▼              ▼               ▼
      pasa a        cambia fase +   cambia fase
      atención      limpia historial

                         POST /api/reset → session.clear() (vuelve a saludo)
```

> [!IMPORTANT]
> La fase `tratamiento` **nunca se alcanza directo**: una petición explícita de tratamiento se deriva a `historial` (modo recopilación de antecedentes) y solo `historial` puede pasar a `tratamiento` (guarda central en `flujo.py`). Regla de negocio vigente.

### B. Flujo de una petición `POST /api/chat`

1. **Validación:** `app.py` exige JSON con el campo `mensaje` no vacío (400 si falla).
2. **Inicialización:** si no existe `session['fase']`, se inicializa en `saludo` con `historial = []`.
3. **Despacho:** `app.py` llama a `flujo.despachar(fase, mensaje, historial)`, que busca el componente en el mapa `FASES` y ejecuta su `responder`. El componente devuelve `(respuesta, siguiente_fase, historial)`; `app.py` persiste ambos valores en la sesión y devuelve el JSON.
4. **Comportamiento por componente:**
   - `saludo` → genera un saludo con LLM (solo al inicio) y devuelve `siguiente_fase="atencion"` con historial vacío.
   - `atencion` → clasifica la intención. Si es `pendiente`/error permanece en `atencion` conservando el historial; si el cliente pide producto, asesoría o historial, **vacía el historial** y cambia a esa fase; si pide un **tratamiento**, vacía el historial y lo deriva a `historial` (nunca directo a `tratamiento`).
   - `asesoria` → si el asesor confirma `producto_encontrado`, ejecuta de inmediato la búsqueda del producto sugerido, concatena el resultado comercial y pasa a `producto`; si sigue indagando, permanece en `asesoria`.
   - `producto` → cada mensaje dispara una nueva búsqueda (fase terminal hasta reset). Si el cliente pide un dato puntual del producto (`requiere_web`) o Turso no devuelve resultados, consulta Tavily como respaldo y solo usa los fragmentos que corresponden al producto exacto. Si el extractor detecta una petición explícita de **tratamiento**, responde una transición y deriva a `historial` (nunca a `tratamiento`). Si hace una pregunta (sin término), la fase no cambia.
   - `tratamiento`, `venta`, `historial` → esqueletos: responden un placeholder y permanecen en su fase (ver TODO en cada archivo). Mientras `historial` no implemente el intake, la fase `tratamiento` queda inaccesible.
   - **Fase desconocida** → `flujo` reinicia a `saludo` con historial vacío.
5. **Respuesta:** JSON `{ "respuesta", "fase" }`.
6. **Errores:** cualquier excepción se captura y se devuelve como JSON (nunca HTML), con un mensaje genérico al usuario; el detalle queda solo en los logs del servidor.
7. **Rate limiting:** `/api/chat` está limitado a 30 peticiones/minuto y 500/día por IP. Al superarlo se devuelve `429` en JSON.

### C. Tabla de transiciones

| Fase actual | Condición de salida | Nueva fase | Efecto adicional |
|-------------|---------------------|-----------|------------------|
| `saludo` | siempre | `atencion` | `historial = []`; el primer mensaje solo da contexto al saludo |
| `atencion` | `intencion == "producto"` | `producto` (o `venta` si producto lo detecta) | handoff: búsqueda en el mismo turno + resultado concatenado; conserva el historial de producto |
| `atencion` | `intencion ∈ {asesoria, historial}` | la intención | `historial = []` |
| `atencion` | `intencion == "tratamiento"` | `historial` | `historial = []`; frase de transición que avisa que revisará los antecedentes |
| `atencion` | `intencion ∈ {pendiente, error}` | `atencion` | se conserva el historial |
| `asesoria` | `estado == "producto_encontrado"` | `producto` | `historial = []`; se ejecuta la búsqueda y se concatena al mensaje |
| `asesoria` | `estado ∈ {consultando, error}` | `asesoria` | se conserva el historial |
| `producto` | `intencion == "tratamiento"` | `historial` | responde la transición (sin buscar) y limpia historial; **no** entra a `tratamiento` |
| `producto` | `intencion == "venta"` | `venta` | responde la búsqueda y limpia historial |
| `producto` | sin término (repregunta) | `producto` | pregunta sin cambiar de fase (evita saltar de módulo al preguntar) |
| `producto` | resto de mensajes | `producto` | mantiene el historial para resolver referencias ("y bueno?") |
| `tratamiento` | cada mensaje | `tratamiento` | placeholder (esqueleto); inaccesible hasta que `historial` implemente el intake |
| `venta` | cada mensaje | `venta` | placeholder (esqueleto) |
| `historial` | cada mensaje | `historial` | mensaje informativo (esqueleto); única fase que podrá derivar a `tratamiento` con intake validado |
| cualquiera distinto de `historial` | `siguiente_fase == "tratamiento"` | `historial` | guarda central de `flujo.py`: bloquea la transición, responde una transición y limpia el historial |
| cualquiera | `POST /api/reset` | sesión nueva → `saludo` | `session.clear()` |
| fase desconocida | siguiente petición | `saludo` | historial vacío (reinicio defensivo) |

---

## 4. Módulos en Detalle

### [Core] `core/config.py` — Configuración central

- **Propósito:** ÚNICO lugar del proyecto que lee variables de entorno. Todos los módulos hacen `from core.config import ...`.
- **Carga:** `load_dotenv()` para desarrollo local (en Render las variables se inyectan directo; `.env` no existe).
- **Variables exportadas:**

| Variable | Origen | Descripción |
|----------|--------|-------------|
| `API_KEYS` | `GROQ_API_KEYS` | Lista de keys de Groq separadas por coma (`"key1,key2,key3"`). Habilita el fallback ante HTTP 401 (key inválida) y 429 (rate limit). |
| `MODELO` | `GROQ_MODEL` | Modelo Groq del diálogo (saludo, atención, asesoría, vendedor, repregunta). Default: `openai/gpt-oss-20b`. |
| `MODELO_EXTRACCION` | `GROQ_MODEL_EXTRACCION` | Modelo del extractor (`producto/extractor.py`). Default: `openai/gpt-oss-120b`. Separado para repartir la cuota diaria de tokens (TPD por modelo). |
| `HISTORIAL_TURNOS` | `HISTORIAL_TURNOS` | Turnos recientes usados como contexto por extractor y vendedor. Default: `4`. |
| `LIMITE_PRODUCTOS` | `LIMITE_PRODUCTOS` | Máximo de productos que devuelve Turso y recibe el vendedor. Default: `6`. |
| `TAVILY_API_KEY` | `TAVILY_API_KEY` | Key de Tavily para el respaldo web. **Opcional**: sin ella la búsqueda web se omite y se responde solo con Turso. |
| `WEB_MAX_RESULTADOS` | `WEB_MAX_RESULTADOS` | Resultados pedidos a Tavily por consulta. Default: `4`. |
| `WEB_CACHE_TTL` | `WEB_CACHE_TTL` | TTL del caché de búsquedas web, en segundos. Default: `21600` (6 h). |
| `WEB_CACHE_MAX` | `WEB_CACHE_MAX` | Máximo de consultas guardadas en el caché web. Default: `200`. |
| `TURSO_URL` | `TURSO_URL` | URL de la base de datos Turso. |
| `TURSO_TOKEN` | `TURSO_TOKEN` | Token de autenticación de Turso. |
| `SECRET_KEY` | `SECRET_KEY` | Clave de firma de la cookie de sesión. **Obligatoria**, sin default. |

- **`validar_config()`:** lanza `EnvironmentError` con el detalle de las variables faltantes. **Se invoca al importar `app.py`**: si falta alguna variable crítica, el arranque falla con un error claro en logs.

### [Fase 1] `atencion/atencion.py` — Atención (clasificación de intención)

- **Propósito:** Primer contacto conversacional tras el saludo. Conversa con empatía y clasifica la necesidad del cliente.
- **Firma:** `responder(mensaje_usuario, historial) → (respuesta, siguiente_fase, historial)`. `siguiente_fase` es `"producto" | "asesoria" | "historial"` si la intención es explícita, o `"atencion"` si sigue `pendiente` o hubo error. Si la intención es `"tratamiento"`, devuelve `"historial"` (regla de negocio: todo tratamiento pasa primero por el historial clínico).
- **Prompt (`PROMPT_SISTEMA_RECEPCION`):** recepcionista cálido, respuestas de máximo 1-2 frases. Define las 4 rutas + estados:
  - `"pendiente"` — aún no hay petición explícita (saludos, síntomas narrados, temas ajenos, "no sé qué hacer").
  - `"producto"` — el cliente nombra un producto/marca/compuesto exacto.
  - `"asesoria"` — pide recomendación puntual para un síntoma, sin saber qué producto comprar.
  - `"tratamiento"` — pide explícitamente un tratamiento/plan/protocolo (p. ej. "quisiera un tratamiento natural para la próstata"); que mencione síntomas no basta. Se deriva a `historial`.
  - `"historial"` — pide explícitamente abrir/gestionar su expediente clínico.
- **Regla estructural clave:** si la respuesta del bot contiene una pregunta, la intención DEBE ser `pendiente`. Nunca se asume la intención por mencionar un síntoma.
- **Salida del modelo:** JSON estricto (`response_format={"type": "json_object"}`), `temperature=0.3`.
- **Handoff a producto:** si `intencion == "producto"`, ejecuta `producto.responder(mensaje_usuario, historial)` en el mismo turno (igual que asesoría hace con `producto_encontrado`), concatena el resultado a la frase de transición y conserva el historial que devuelve producto (contexto para turnos siguientes). La frase de transición **no adelanta información del producto** (el prompt prohíbe confirmar disponibilidad, variedades, precios o dosis), así no duplica ni contradice la respuesta comercial que se concatena. Si la búsqueda falla, se registra el error y se responde solo la frase de transición.
- **Transición:** al cambiar de fase (salvo el handoff) devuelve `historial = []` (cada fase arranca con su propio prompt de sistema); si permanece en `atencion` lo conserva.
- **Errores:** delegado en `core/groq_cliente.py`; el módulo registra el error y devuelve un mensaje genérico con `siguiente_fase="atencion"`.

### [Fase 2] `asesoria/asesoria.py` — Asesor de salud

- **Propósito:** Indagar síntomas y recomendar un **tipo genérico de producto** (p. ej. "pomada", "colágeno", "jarabe").
- **Firma:** `responder(mensaje_usuario, historial) → (respuesta, siguiente_fase, historial)`.
- **Estados internos:** `"consultando"` (sigue indagando → permanece en `asesoria`), `"producto_encontrado"` (ya recomendó → pasa a `producto`).
- **Búsqueda inmediata:** con `producto_encontrado`, el propio componente llama a `producto.producto.responder(producto_sugerido, [])`, concatena el resultado comercial (`respuesta + "\n\n" + resultado`) y devuelve `historial = []`. Si la búsqueda falla, se registra el error y se devuelve solo la recomendación (el error no se filtra al cliente).
- **Prompt (`PROMPT_SISTEMA`, sin cambios):** preguntas amables de máximo 2 oraciones; al tener claro el diagnóstico comunica la recomendación y avisa que revisará stock. Salida JSON estricta, `temperature=0.3`.
- **Delegación:** todas las llamadas al LLM pasan por `core/groq_cliente.py`.

### [Core] `core/groq_cliente.py` — Cliente Groq compartido

- **Propósito:** Único lugar que crea clientes Groq y maneja el fallback entre API keys. Lo consumen `saludo/`, `atencion/`, `asesoria/` y `producto/` (`extractor` y `vendedor`).
- **Función:** `llamar_groq(messages, model=MODELO, temperature=0.3, response_format=None)`. `MODELO` se define en `core/config.py` (default `openai/gpt-oss-20b`, configurable con `GROQ_MODEL`); el extractor pasa `MODELO_EXTRACCION` (`GROQ_MODEL_EXTRACCION`, default `openai/gpt-oss-120b`).
- **Comportamiento:** recorre `API_KEYS` en orden; ante `APIError` 401 (key inválida) o 429 (rate limit) espera 2 s y reintenta con la siguiente key. Si todas fallan, **relanza** la excepción (cada módulo de fase la captura, la registra en logs y devuelve un mensaje genérico con estado `error`). Los reintentos internos del SDK quedan desactivados (`max_retries=0`) para no duplicar esperas ocultas. Helper `es_limite_diario(error)`: detecta el 429 por tokens/día (TPD) para no reintentar lo que no se recupera hasta la renovación de cuota.
- **Trazabilidad:** registra en logs la key usada (enmascarada, nunca completa), el modelo, la temperatura, si pide JSON, la latencia de cada llamada y cada rotación de key (`WARNING`).

### [Core] `core/logs.py` — Logging y panel de depuración

- **Propósito:** trazar el recorrido de cada mensaje para pulir el chat: qué módulo entra, qué prompt y modelo actúan, qué decide la IA, cuánto tarda y dónde falla.
- **Destinos:** consola (Render) con formato `[hora] NIVEL módulo mensaje`, y un buffer circular en memoria (`deque`, últimas `LOGS_BUFFER` entradas, default 500) expuesto por `GET /api/logs`.
- **Módulos registrados:** `salus.app`, `salus.flujo`, `salus.saludo`, `salus.atencion`, `salus.asesoria`, `salus.producto`, `salus.extractor`, `salus.vendedor`, `salus.buscador`, `salus.turso`, `salus.tratamiento`, `salus.venta`, `salus.historial`, `salus.groq`.
- **Seguridad:** las API keys se enmascaran (`gsk_XXXXX…XXXX`); los textos se recortan a 160–200 caracteres; el buffer nunca se escribe a disco. `/api/logs` está **abierto sin token** (pensado para pruebas; ver pendiente en §8).
- **Niveles:** `INFO` para el flujo normal (prompt, key, decisión, tiempos), `WARNING` para rotaciones de key o búsquedas sin resultados, `ERROR` para excepciones con traceback en consola.
- **Limpieza:** el botón **Limpiar** del panel llama a `POST /api/logs/clear`, que vacía el buffer del servidor (no solo la vista); la siguiente consulta ya devuelve vacío.
- **Variables:** `LOG_LEVEL` (default `INFO`), `LOGS_BUFFER` (default `500`).

### [Orquestador] `flujo.py` — Registro de fases y transiciones

- **Propósito:** Único lugar que conoce el mapa de fases. `app.py` le delega el despacho y **no necesita cambios** al agregar componentes.
- **Mapa `FASES`:** `saludo`, `atencion`, `asesoria`, `producto`, `tratamiento`, `venta` e `historial` → `responder` de cada componente.
- **`FASE_INICIAL = "saludo"`:** fase con la que arranca toda conversación nueva (y a la que se reinicia ante una fase desconocida).
- **`despachar(fase, mensaje, historial)`:** busca el componente y ejecuta `responder(mensaje, historial)`. Si la fase no existe, registra un `WARNING` y devuelve `("Sesión reiniciada. ¿En qué te puedo ayudar?", "saludo", [])`.
- **Guarda central de tratamiento:** tras responder, si `siguiente_fase == "tratamiento"` y la fase actual no está en `ORIGENES_PERMITIDOS_A_TRATAMIENTO` (`("historial",)`), registra `WARNING`, bloquea la transición y devuelve la frase `TRANSICION_A_HISTORIAL` con fase `historial` e historial vacío. La regla "todo tratamiento pasa primero por historial" queda así garantizada **estructuralmente**, sin depender de que el LLM clasifique bien. TODO: cuando `historial` implemente el intake, exigir además la validación completa.
- **Contrato de componentes:** `responder(mensaje, historial) -> (respuesta, siguiente_fase, historial)`. Si un componente es `async`, debe documentarlo en su docstring (hoy todos son síncronos; `producto` envuelve una corrutina con `asyncio.run`).

### [Fase 0] `saludo/saludo.py` — Saludo inicial (LLM)

- **Propósito:** generar un saludo natural y distinto cada vez, con tono humano de una persona real de Nature's Green.
- **Firma:** `responder(mensaje_usuario, historial) → (saludo, "atencion", [])`.
- **Prompt (`PROMPT_SISTEMA_SALUDO`):** máximo 2 frases, cálido y natural; es **solo bienvenida**: no asume que el cliente busca un producto ni pregunta "¿qué producto buscas?"; ofrece ayuda abierta ("¿qué se le ofrece?", "¿en qué le podemos ayudar?", "¿qué necesita?"). Prohíbe presentarse como bot/IA y las fórmulas repetidas.
- **Variedad forzada:** en cada llamada se sortea un `enfoque` de la tupla `ENFOQUES` y se añade al prompt (p. ej. "sin pregunta", "con detalle cálido", "pregunta distinta a la habitual"); así la estructura no se repite entre conversaciones. El enfoque elegido queda registrado en los logs.
- **Parámetros:** `temperature=0.9` (favorece la variedad), sin `response_format` (texto libre).
- **Particularidad:** al ser la `FASE_INICIAL`, el primer mensaje del cliente solo da contexto al saludo y no se clasifica; siempre devuelve `historial = []` para que `atencion` arranque con su propio prompt de sistema.

### [Fase 3] `producto/producto.py` — Componente de productos

- **Propósito:** Conversar sobre productos manteniendo el contexto entre turnos.
- **Firma estándar:** `responder(mensaje_usuario, historial) → (respuesta, siguiente_fase, historial)`. **Nota (async):** la búsqueda real es la corrutina `ejecutar_busqueda_producto(mensaje, contexto, ultimo)`, que devuelve `(respuesta, siguiente_fase, termino, necesidad)`; `responder` la ejecuta con `asyncio.run` porque el orquestador Flask es síncrono.
- **Estado interno (ahorro de cuota):** tras resolver un término, `responder` guarda `{termino, necesidad}` en un mensaje `system` marcado con `__salus_estado__` al final del historial (un único mensaje, se reemplaza; `formatear_contexto` lo ignora). Si el extractor falla (`fallo=True`), se reutiliza ese término/necesidad en vez de repreguntar; si además el mensaje parece un dato puntual (lista local de palabras: "cómo se toma", "a qué hora", "dosis", "cuántas"…), se activa `requiere_web`. Si no hay estado previo y el fallo es por TPD, responde `MENSAJE_SIN_CUOTA` sin llamar al LLM.
- **Respaldo sin LLM:** si `generar_respuesta_vendedor` falla (p. ej. cuota TPD del modelo de diálogo agotada), `producto.py` responde con `_respuesta_sin_llm`, un texto determinista armado con los datos reales de Turso (un producto: nombre/marca/precio/enlace y, con `requiere_web`, el `como_tomar` literal; varios: hasta 4 opciones con precio y enlace; sin resultados: mensaje de no encontrado). El turno no se pierde (antes propagaba un 500 o dejaba solo la frase de transición de atención sin contexto) y el estado interno queda guardado para el siguiente mensaje.
- **Extractor omitido en seguimientos (dieta de tokens):** si existe estado previo y el mensaje es un seguimiento claro (`_es_seguimiento`: "cómo se toma", "a qué hora", "cuál me recomienda", "qué diferencia", "y bueno"…), se comprueba contra Turso si menciona otro producto (`menciona_producto`, consulta local sin LLM); si no lo menciona y no pide tratamiento ni compra (`_PALABRAS_NO_SEGUIMIENTO`), se usan el término/necesidad del estado y **no se llama al extractor** (~1,800 tokens menos por turno). Con mención de otro producto, tratamiento o compra, el extractor corre normal.
- **Pasos:**
  1. `extraer_termino(mensaje, contexto)` (`extractor.py`) → término, necesidad, intención y `requiere_web`.
  2. `await buscar_producto(termino)` (`database.py`) contra Turso (hasta `LIMITE_PRODUCTOS` filas).
  2b. **Respaldo web:** si hay `TAVILY_API_KEY` y (`requiere_web` o Turso devolvió 0 filas), `buscar_en_web(consulta_web(termino, necesidad, mensaje), termino, nombre_db)` (`buscador.py`), donde `nombre_db` es el nombre del primer producto de Turso (si lo hay); `consulta_web` arma "término + necesidad + pregunta del cliente" (la pregunta aporta el contexto del dato, p. ej. "efervescente"; el filtro exacto usa el término y el nombre del catálogo).
  3. `generar_respuesta_vendedor(mensaje, termino, necesidad, resultados, contexto, resultados_web, requiere_web)` (`vendedor.py`).
- **Contexto:** `formatear_contexto(historial, HISTORIAL_TURNOS)` (`producto/contexto.py`) construye un transcript plano de los últimos N turnos para extractor y vendedor; así "y bueno?" o "y solo tienen ese?" se resuelven contra el producto del que se venía hablando. `responder` devuelve el historial actualizado con el intercambio del turno.
- **Sin término:** en vez de un texto fijo, `generar_repregunta(mensaje, contexto)` produce con el LLM una repregunta natural usando la conversación (`temperature=0.3`). El prompt prohíbe **nombrar o recomendar productos, marcas, opciones, precios o propiedades** y prohíbe volver a preguntar qué producto busca si eso ya se habló en el contexto; si retoma el tema, debe usar solo lo que aparece **literalmente** en la conversación (sin añadir variantes, ingredientes ni atributos) y sin listar opciones. Los **saludos o cortesías** ("hola", "gracias") se devuelven con calidez sin ofrecer productos. Si hace una pregunta, **la fase no cambia** (se queda en `producto`), evitando saltar de módulo tras preguntar. La ruta solo se alcanza cuando el extractor no logró término y no hay estado previo reutilizable (con estado previo se usa el fallback de término; con cuota diaria agotada se responde `MENSAJE_SIN_CUOTA` sin llamar al LLM).
- **Tratamiento explícito:** si el extractor devuelve `intencion="tratamiento"`, responde la constante `TRANSICION_HISTORIAL` y devuelve `"historial"` **sin buscar productos ni pasar por `tratamiento`**.
- **Siguiente fase:** `"producto"` normalmente; `"venta"` si el cliente quiere comprar; `"historial"` si pide un tratamiento (regla de negocio; `flujo.py` bloquea igualmente cualquier salto directo a `tratamiento`). Al salir de `producto` el historial se limpia.

### [Helper] `producto/contexto.py` — Contexto conversacional

- **Función:** `formatear_contexto(historial, turnos) → str`. Devuelve los últimos `turnos*2` mensajes como transcript plano (`Cliente:` / `Bot:`), ignorando los mensajes de sistema. Si un mensaje del asistente es el JSON interno de atención (`{"respuesta": ...}`), muestra solo la respuesta.

### [Helper] `producto/extractor.py` — Término, necesidad, intención y requiere_web

- **Función:** `extraer_termino(mensaje, contexto="") → dict` con contrato JSON estricto:
  - `termino` — sustantivo principal en singular (p. ej. `"citrato de magnesio"`); `""` si no se identifica. **Sin dosis ni tamaños** ("600 mg", "2000 UI", "100 cápsulas") salvo que el cliente pregunte por esa presentación concreta ("¿el de 600 mg?", "¿la de 2000 UI?"). En comparaciones o elecciones entre variantes ya mostradas ("el de $20 vs el de $30", "el otro", "cuál me conviene") usa el **nombre común de la familia** (p. ej. `"magnesio glicinato"`) para que Turso devuelva todas las variantes; en recomendaciones ("¿cuál me recomendaría?") usa la categoría discutida en el contexto (p. ej. `"magnesio"`) aunque el mensaje no la repita.
  - `necesidad` — uso, síntoma o motivo mencionado (p. ej. `"estrés"`); `""` si no hay.
  - `intencion` — `"producto"` | `"tratamiento"` | `"venta"` (cualquier otro valor se normaliza a `"producto"`). `"tratamiento"` es **restrictiva**: solo si el cliente pide explícitamente un tratamiento/plan/protocolo (p. ej. "quiero un tratamiento para la próstata"); comparar o preguntar por productos ya mostrados ("cuál de los dos es mejor para dormir?", "y el de $30?") y mencionar síntomas son siempre `"producto"`; ante duda, `"producto"`.
  - `requiere_web` — `true` solo si el cliente pide un dato puntual que la ficha no suele traer: **presentación o formato** (efervescente, polvo, tableta, cápsula, sobre, líquido; cómo se toma o se consume), unidades/cápsulas/sachets del envase, contenido neto, ingredientes, sabor, origen o certificaciones. Incluye ejemplos textuales de las preguntas "¿es efervescente o se traga con agua?" y "¿cómo se toma?" para estabilizar el flag. Se normaliza desde `"true"`/`"1"`/`"sí"`.
- **IA:** modelo `MODELO_EXTRACCION` (`GROQ_MODEL_EXTRACCION`, default `openai/gpt-oss-120b`, separado del diálogo para repartir el TPD de Groq), `temperature=0`, `response_format={"type": "json_object"}`. El prompt incluye ejemplos few-shot, reglas para resolver referencias ("ese", "el otro", "y bueno?") usando el contexto, la prohibición de meter síntomas dentro de `termino`, la regla de **copiar el nombre tal cual aparece en la conversación** (evita erratas como "vitamagnésio"/"vitamagensio" que el catálogo no encontraría) y las reglas de dosis/comparación/recomendación descritas arriba (con un ejemplo para cada caso).
- **Contrato de salida ampliado:** además de las 4 claves, devuelve `fallo` (True si ninguna llamada logró datos) y `limite_diario` (True si el 429 fue por TPD). `producto.py` usa `fallo` para reutilizar el último término/necesidad y `limite_diario` para no llamar al LLM sin cuota.
- **Reintento distinto + degradación segura:** si la llamada o el parseo fallan (p. ej. Groq responde 400 `json_validate_failed` con generación vacía en modo JSON estricto), hace **un segundo intento con el mismo contexto pero sin `response_format`**, y `_parsear_json` tolera cercas de markdown o texto alrededor. Si el primer fallo es un **429 por tokens/día (TPD)** no reintenta (helper `es_limite_diario`): la cuota no se recupera y solo se perdería tiempo. Si el reintento también falla, registra el error y devuelve el dict vacío con `fallo=True` **sin propagar la excepción** (antes llegaba un 500 y el turno quedaba sin respuesta); `producto.py` degrada al fallback de término o a la repregunta contextual. Así el fallo de Groq nunca tira el turno.

### [Helper] `producto/database.py` — Consulta a Turso

- **Función:** `async buscar_producto(termino) → list[dict]`.
- **Consulta SQL** (`CONSULTA_SQL`), con parámetros `%termino%` (filtro por nombre/descripción/marca y desempate de relevancia) y `LIMITE_PRODUCTOS` (default 6, configurable en `core/config.py`):

```sql
SELECT nombre_producto, marca, descripcion, precio1, slug,
       para_que_sirve, como_tomar, dosis, via_administracion,
       edad_recomendada, contraindicaciones, advertencias, recomendaciones,
       (stock > 0) AS disponible
FROM productos
WHERE (nombre_producto LIKE ? OR descripcion LIKE ? OR marca LIKE ?) AND oculto = 0
ORDER BY
    CASE
        WHEN nombre_producto LIKE ? THEN 0
        WHEN marca LIKE ? THEN 1
        ELSE 2
    END,
    ((foto_url IS NOT NULL AND foto_url <> '')
   + (video_url IS NOT NULL AND video_url <> '')
   + (IFNULL(info_completada, 0) > 0)
   + (IFNULL(categoria_id, 0) > 0)
   + (IFNULL(star, 0) > 0 OR IFNULL(superstar, 0) > 0)) DESC
LIMIT ?
```

- **Conexión:** `libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)` como context manager async (helper `_consultar`).
- **Acentos y espacios:** el término se normaliza (minúsculas, sin tildes, espacios simples: la DB usa `\u202f` y `\xa0`) y las columnas se comparan con una cadena de `REPLACE(...)` en SQL (Turso no trae `unaccent`) que ahora también **unifica `\u202f` y `\xa0` a espacio** (antes solo el término se normalizaba: `'magnesio glicinato 600 mg'` no encontraba `'Magnesio Glicinato 600\u202fmg'` y dependía de la pasada por palabras); así "vitamagnésio" encuentra "VITAMAGNESIO PLUS" y la presentación exacta se encuentra por frase completa.
- **Segunda pasada por palabras clave:** para términos con 2+ palabras significativas (≥ 3 letras, sin muletillas) se exige que TODAS aparezcan en nombre o marca; así "glicinato de magnesio" también devuelve "Magnesio Glicinato 600 mg" (mismas palabras en otro orden). Se fusiona con la frase exacta sin duplicar y no mira descripciones, para no diluir.
- **Reintento por erratas:** si la consulta exacta y la de palabras devuelven 0 filas, `_buscar_aproximado` trae hasta 50 candidatos por el prefijo (5 letras) de la palabra más larga del término y conserva los que superan `UMBRAL_APROXIMADO` (0.85) de similitud `difflib` contra nombre/marca; si ninguno supera el umbral, devuelve lista vacía (evita falsos positivos). Cubre erratas del extractor como "vitamagensio".
- **Chequeo de mención (`menciona_producto`):** consulta local (sin LLM) que devuelve True si alguna palabra significativa del mensaje (≥4 letras, sin muletillas de `_PALABRAS_IGNORADAS`) aparece en el nombre o la marca de un producto visible; usa `_consultar_crudo` (filas sin normalizar) y ante error de DB devuelve True (conservador: se usará el extractor). Lo usa `producto.py` para decidir si puede omitir el extractor en un seguimiento.
- **Normalización de filas:** cada fila se convierte en dict con claves `nombre`, `marca`, `descripcion`, `precio`, `enlace`, `para_que_sirve`, `como_tomar`, `dosis`, `via_administracion`, `edad_recomendada`, `contraindicaciones`, `advertencias`, `recomendaciones`, `disponible`.
- **Enlace:** se construye como `https://www.naturesgreenec.com/producto/{slug}` (o `None` si no hay slug).
- **Ranking:** primero por **relevancia** (coincidencia en `nombre_producto` > `marca` > `descripcion`) y luego por prioridad = número de campos clave presentes (`foto_url`, `video_url`, `info_completada`, `categoria_id`, `star`/`superstar`). Así, al buscar "magnesio", los productos que **son** magnesio aparecen antes que los que solo lo mencionan en su descripción (p. ej. un multivitamínico completo ya no desplaza al cloruro de magnesio). El stock **no** influye en el orden (solo informa `disponible`).
- **Límites:** `oculto = 0` excluye productos ocultos; `LIMIT ?` devuelve hasta `LIMITE_PRODUCTOS` coincidencias (default 6), ya ordenadas por relevancia+prioridad. No se filtra por marca en SQL: todas las variantes llegan al LLM para que identifique la específica.

### [Helper] `producto/vendedor.py` — Respuesta de ventas conversacional

- **Función:** `generar_respuesta_vendedor(mensaje_usuario, termino, necesidad, resultados_db, contexto="", resultados_web=None) → str`.
- **Prompt (`PROMPT_VENDEDOR`):** conversacional y breve (2-4 frases), sin ficha, MAYÚSCULAS, markdown ni viñetas. Reglas clave:
  - **Pregunta antes de volcar opciones:** si el cliente solo nombra el producto (p. ej. "magnesio") sin tipo, formato ni marca, confirma que lo hay, agrupa los tipos o presentaciones que muestran los datos (p. ej. citrato, cloruro, glicinato; polvo, cápsulas, líquido) y pregunta cuál prefiere o para qué lo necesita; **si el cliente ya dijo para qué lo necesita, no repite esa pregunta**: recomienda la variante que mejor encaje con los datos (p. ej. para dormir, el glicinato). No lidera con productos que solo mencionan el término (multivitamínico, colágeno) cuando hay productos cuyo nombre coincide. Si pide ver las opciones ("¿cuáles tienen?"), las lista breve (nombre, presentación, precio, enlace; máximo 3-4).
  - **Respeta la preferencia**: si la marca/formato pedido está en los datos, lo confirma con precio y enlace ANTES de cualquier alternativa — incluso si pregunta en negativo ("¿no tienen de X?"). Si no está, lo dice y ofrece la más parecida.
  - Al comparar, **menciona precio y enlace de cada producto** que nombre; el precio ya viene formateado con `$` desde `database.py`. En respuestas de un dato puntual (cómo se toma, dosis, presentación, unidades) no repite precio ni enlace si ya se dieron antes en la conversación.
  - Cita `descripcion`/`para_que_sirve` sin cambiar palabras; usa la presentación (tamaño, formato) si está en los datos.
  - Si `marca` viene sucia (POLVO, CAPS, EXCLUSIVO, TV, tamaños…), no la presenta como marca.
  - No menciona dosis, cantidades, frecuencia ni modos de uso **por iniciativa propia**; solo los cita si el cliente los pide explícitamente (`requiere_web`), y en ese caso recibe los campos `como_tomar`, `dosis`, `via_administracion`, `edad_recomendada`, `contraindicaciones` y `advertencias` de la ficha: reproduce **literalmente** el modo de uso/dosis para el producto exacto (sin mezclar, sumar ni recalcular) y menciona también, de forma breve y literal, las contraindicaciones, advertencias y edad recomendada cuando existan. Si el cliente **repregunta** sobre el mismo tema ("¿a qué hora?", "¿cuándo?", "¿cada cuánto?", "¿antes o después de comer?"), retoma lo que ya dijo —repite dosis y modo de la ficha— y recién añade el dato nuevo, sin responder un dato aislado que parezca olvidar lo anterior. La ficha del catálogo manda; la web solo complementa lo que la ficha no diga (p. ej. el momento del día), presentado como recomendación general si viene de una fuente no oficial, sin contradecirla ni sustituirla.
  - **Sin flexibilidad inventada:** no confirma con un simple "sí/no" un modo de uso que la ficha no respalde (p. ej. "¿me tomo las dos antes de dormir?") ni agrega horarios, comidas concretas o repartos aunque parezcan compatibles; si la ficha dice "con una comida" y preguntan "¿mañana o después del almuerzo?", responde solo lo que la ficha indica y que no especifica más.
  - **Consistencia:** nunca contradice ni cambia un dato ya dado en la conversación (dosis, frecuencia, horario, precio); si la información nueva o la web ofrece otra cifra, mantiene lo dicho o da un rango único compatible. El momento del día que no está en la ficha se presenta como recomendación general y **separado** de la indicación de la ficha, sin fusionarlos (caso real: decía "30 a 60 min" y luego "1 o 2 h").
  - No promete acciones inexistentes (carrito, reservar, enviar) y varía el cierre (sin repetir "¿Te gustaría…?").
  - Con lista vacía: lo dice y pregunta qué busca. `temperature=0.3`.
  - **Respaldo web:** si el catálogo no alcanza, recibe fragmentos de Tavily (`resultados_web`) y los usa **solo** como verificación interna para el dato puntual que pidió el cliente (p. ej. presentación, cómo se toma o cuántas unidades trae el envase), verificando que hablen del **producto exacto** y priorizando la ficha de naturesgreenec.com; los fragmentos **jamás se citan, mencionan ni enlazan** en la respuesta. Si no confirman el dato, lo dice sin inventar. La web puede confirmar el **modo de uso** del producto exacto (así responde "cómo se toma" cuando Turso no trae el campo), pero no sirve para recomendar productos fuera del catálogo ni para indicaciones médicas, contraindicaciones o advertencias.
  - **Enlaces solo de la tienda (regla dura):** prohibido citar o enlazar cualquier sitio que no sea el catálogo (marca, competencia, otras tiendas), ni sus precios, disponibilidad o contenido; si la variante pedida no está en el catálogo, lo dice y ofrece la más parecida sin mencionar que la marca sí la tiene. Además del prompt, `_filtrar_enlaces` elimina en código cualquier URL que no sea `naturesgreenec.com` (descarta la oración completa si solo contiene URLs externas; si el filtrado deja la respuesta vacía, responde con datos del catálogo) y registra un `WARNING`.
  - **Presentación no deducible:** regla dura del prompt: si preguntan presentación/formato (efervescente, polvo, tableta, cápsula, sobre, líquido, cómo se consume) y no está **textualmente** en los datos del catálogo ni en la web, responde que no tiene ese detalle confirmado. Está prohibido **afirmar o negar** por deducción ("no es efervescente porque venga en sobres", "se disuelve en agua porque es lo habitual") y reforzar suposiciones previas de la conversación (caso real: Triple C Advance es polvo efervescente en sobres y el modelo afirmaba "tabletas sólidas" o "no son efervescentes"). Cuando no hay fragmentos web, el prompt recibe el texto "(sin resultados: la búsqueda web no encontró información confirmada)" en lugar de `[]`.
  - **Stock pausado (pruebas):** `disponible` no se incluye en `CAMPOS_VENDEDOR` y la regla de "no disponible" está comentada en el código con `##`, para centrar las pruebas en la calidad de las respuestas; re-activar ambos al terminar.
- **Datos:** recibe hasta `LIMITE_PRODUCTOS` resultados reales de Turso (default 6), pero con una **vista reducida** (`CAMPOS_VENDEDOR`: nombre, marca, descripción, para qué sirve, precio y enlace; `disponible` pausado en pruebas) y, opcionalmente, hasta `WEB_MAX_RESULTADOS` fragmentos web del `buscador`. `descripcion` y `para_que_sirve` se **recortan a 200 caracteres** con `…` antes de enviarse (dieta de tokens; el log del vendedor indica `recortados=N`). Cuando `requiere_web` es `True`, la vista añade `como_tomar`, `dosis`, `via_administracion`, `edad_recomendada`, `contraindicaciones` y `advertencias` para citarlos literalmente al explicar el modo de uso. Solo `recomendaciones` (estilo de vida) queda fuera siempre.

### [Helper] `producto/buscador.py` — Respaldo web (Tavily)

- **Función:** `buscar_en_web(consulta, termino="", nombre_producto="") → list[dict]` con `[{"titulo", "url", "contenido"}]`.
- **Cuándo se invoca:** solo si hay `TAVILY_API_KEY` y `producto.py` detecta que la DB no alcanza: el extractor marcó `requiere_web` (dato puntual) o Turso devolvió 0 filas (antes del reintento por erratas no aplica: ver flujo en `producto.py`).
- **API:** `POST https://api.tavily.com/search` con `httpx` (timeout 8 s), `search_depth="basic"`, sin respuesta generada por Tavily. Se piden `WEB_MAX_RESULTADOS + 2` resultados (mismo crédito) y se recorta a `WEB_MAX_RESULTADOS` **después** de filtrar: la ficha oficial no siempre viene en el top.
- **Filtro de producto exacto (`_es_producto_exacto`):** acepta el resultado si contiene **todas** las palabras significativas del término (≥ 3 letras, sin tildes) **o**, como alternativa, las 3 primeras palabras del nombre del producto en el catálogo (`nombre_producto`). Esa alternativa cubre fichas oficiales que no repiten el término completo (p. ej. la misma ficha devuelta en otro idioma: "ENVELOPES / 10 sachets" sin "vitamina 1000"). Los parecidos se descartan antes de llegar al vendedor.
- **Caché en memoria:** clave `termino|nombre_producto|consulta`, TTL `WEB_CACHE_TTL` (default 6 h) y poda al superar `WEB_CACHE_MAX` entradas (default 200); las consultas repetidas no gastan créditos.
- **Errores:** si falta la key, Tavily falla o expira el timeout, registra `WARNING` y devuelve lista vacía; la conversación continúa con los datos de Turso (el error nunca llega al cliente).

### ~~[Helper] `producto/groq_cliente.py`~~ (unificado)

> [!NOTE]
> Este helper fue eliminado: todas las fases usan el `core/groq_cliente.py`. La fase producto pasa `temperature=0` explícitamente (es factual, no conversacional).

### [Fase 4] `tratamiento/tratamiento.py` — Tratamiento (ESQUELETO)

- **Estado:** sin implementar. `responder` devuelve `("El módulo de tratamiento aún no está disponible.", "tratamiento", historial)` y registra un `WARNING`. **Inaccesible mientras `historial` no implemente el intake**: la guarda de `flujo.py` bloquea toda transición que no venga de `historial`.
- **TODO:** definir el flujo de negocio (prompt del sistema, criterios de recomendación por malestar, transiciones y datos necesarios) antes de implementarlo. Debe ser defensivo: sin datos clínicos validados, redirigir a `historial`.

### [Fase 5] `venta/venta.py` — Venta (ESQUELETO)

- **Estado:** sin implementar. `responder` devuelve `("El módulo de venta aún no está disponible.", "venta", historial)` y registra un `WARNING`.
- **TODO:** definir el flujo de negocio (método de pago, cierre de la venta, transiciones y datos necesarios) antes de implementarlo.

### [Fase 6] `historial/historial.py` — Historial clínico (ESQUELETO)

- **Estado:** sin implementar. `responder` conserva el mensaje informativo que antes vivía inline en `app.py`: `"El módulo de historial clínico está en desarrollo. ¿Puedo ayudarte con algo más?"`, permaneciendo en `historial`.
- **Entradas actuales:** petición explícita del cliente (intención `historial` en atención) y derivación automática cuando se pide un tratamiento (atención o producto).
- **Rol en la regla de negocio:** es la **única fase autorizada a derivar a `tratamiento`** (ver guarda en `flujo.py`). Deberá distinguir el motivo de ingreso: consulta/gestión del expediente vs recopilación de antecedentes previa a un tratamiento, y cerrar el intake con una validación.
- **TODO:** definir el flujo de negocio (fuente de datos del expediente, datos a recopilar, validación, prompt del sistema y transiciones) antes de implementarlo. Requiere persistir los datos clínicos en sesión (clave propia, distinta del historial conversacional) y subir `VERSION_SESION`; hasta entonces, `tratamiento` queda inaccesible.

### [Herramienta] `enrich_products.py` — Limpieza y enriquecimiento del catálogo

- **Propósito:** script **independiente del chatbot** (no es una fase de `flujo.py`) que limpia y completa los campos de venta de la tabla `productos`: recorre las filas **pendientes** (`IFNULL(info_completada, 0) = 0`) en orden de `id`, busca cada producto en la web (Tavily) y pide a Groq una ficha estructurada. Es **reanudable**: cada fila escrita queda con `info_completada = 1`, así que se puede parar con Ctrl+C y continuar después (solo procesa los `0` que queden). Modos: `python enrich_products.py` (procesa pendientes y escribe en Turso), `python enrich_products.py --id N` (procesa solo ese producto, aunque ya tenga `info_completada = 1`; útil para reprocesar o diagnosticar una fila), `python enrich_products.py --test` (simulación con las 10 primeras pendientes: imprime el JSON que se escribiría, **no** toca Turso y resume OK/SKIPPED/ERROR) y `python enrich_products.py --reset` (marca **todas** las filas con `info_completada = 0` — pasada completa desde cero — y sale). Al terminar (o con Ctrl+C) muestra los contadores y cuántos pendientes quedan; las filas `SKIPPED` quedan en 0 y se reintentan en la siguiente ejecución.
- **Variables de entorno (`.env`):** acepta `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN`, `TAVILY_API_KEY` y, para Groq, usa **todas las keys** disponibles (`GROQ_API_KEY` + todas las de `GROQ_API_KEYS`, sin duplicados). Si faltan las de Turso, cae a los nombres del proyecto (`TURSO_URL`/`TURSO_TOKEN`). Faltando credenciales termina con un error claro.
- **Acceso a Turso (HTTP v2 + comprobación de escritura):** consulta y escribe mediante la API HTTP v2 (pipeline) con `httpx`, no con `libsql-client`: el endpoint legacy `v1/execute` del SDK no propaga los errores de escritura y un token de solo lectura revienta como `KeyError: 'result'` sin contexto. Al arrancar hace un UPDATE no-op (`id = -1`, no toca filas) para comprobar el permiso: si el token no puede escribir, el run real **aborta antes de gastar cuota** de Tavily/Groq (y `--test` solo avisa). El `TURSO_TOKEN` del chatbot es de solo lectura: para enriquecer hay que agregar un token de escritura (`turso db tokens create <base-de-datos>`) como `TURSO_AUTH_TOKEN`, que el script prefiere.
- **Modelo Groq:** `llama-3.1-8b-instant` si la cuenta tiene acceso; si no (en las keys actuales devuelve 404 `model_not_found`), degrada a `qwen/qwen3.8-27b` — un modelo distinto de los del chatbot para no gastar su cuota diaria (TPD).
- **Flujo por producto:** (1) Tavily con `"{nombre_producto} {marca} Ecuador ficha técnica dosis contraindicaciones"` (la marca se omite si es null/vacía), `search_depth="advanced"` y `max_results=3`; (2) los resultados pasan a Groq con el system prompt de fichas (JSON estricto con `confianza`; el prompt prohíbe escribir frases sobre datos ausentes o sobre la búsqueda — "no se especifica", "no detallado en resultados"… — y exige que `dosis`/`como_tomar` sean del producto o `null`); (3) si Groq devuelve **todos** los campos `null` (resultados de otro producto o marca), se repite la llamada solo con nombre y marca; (4) decisión: `confianza` alta/media → se actualiza la fila con `info_completada = 1`; baja o todo `null` → la fila no se toca y se loguea `SKIPPED`. Cada fila OK imprime en consola el JSON completo de los campos escritos (en `--test` y en modo real). Tras cada UPDATE el script **verifica la escritura releyendo la fila** (y exige `affected_row_count > 0`): si la fila no quedó como se escribió (p. ej. un guardado del panel de administración la revirtió), lo loguea como `ERROR … la fila fue revertida/mismatch tras escribir`. La URL de la base usada se imprime al arrancar.
- **Campos que puede escribir (únicamente estos):** `descripcion`, `categoria`, `subcategoria`, `nombre_producto`, `marca`, `para_que_sirve`, `como_tomar`, `dosis`, `via_administracion`, `edad_recomendada`, `contraindicaciones`, `advertencias`, `recomendaciones`, `slug`, `info_completada`. Los campos que Groq devuelve en `null` **no se escriben** (no borra datos existentes; además `descripcion` es NOT NULL en Turso) y el `slug` lo calcula el script en código (`nombre-del-producto-marca`, minúsculas, sin tildes ni caracteres especiales).
- **Rate limiting y cuota Groq:** `sleep(2)` entre productos y `sleep(1)` entre Tavily y Groq del mismo producto. Ante un 429 se distingue el tipo: **TPD** (tokens/día agotados — el plan gratuito de `qwen/qwen3.8-27b` da ~200k/día por cuenta, unos 40-70 productos) → bloquea esa key hasta su `retry-after` y **rota a la siguiente** (las keys de `GROQ_API_KEYS` pueden ser de cuentas distintas, cada una con su propia cuota); **TPM** (por minuto) → `sleep(15)` hasta 3 intentos. Si **todas** las keys están bloqueadas por TPD, el run **se pausa solo** (espera al `retry-after` de Groq, informando hora de reanudación y avance cada 2 min) y **reanuda automáticamente** al liberarse cuota — no hay que relanzar el script; hay un tope de seguridad de 6 h de espera por producto (si se alcanza, el producto queda en 0 y se pasa al siguiente). El chequeo se hace antes de cada producto y también dentro de la llamada a Groq. Los fragmentos de Tavily se recortan a 1500 chars para alargar la cuota. Ante otros fallos de JSON hace un único reintento sin `response_format` (mismo patrón que el extractor).
- **Log:** una línea por producto en `enrich_log.txt` (raíz del proyecto; excluido en `.gitignore`, igual que `*.log`):
  `[OK]      id=15 | nombre | confianza=alta` · `[SKIPPED] id=23 | nombre | razón: confianza baja` · `[ERROR]   id=67 | nombre | razón: Groq 429 sin recuperación`.

### [Servidor] `app.py` — Aplicación Flask

- **Propósito:** Punto de entrada web: valida la petición, delega en `flujo.despachar` y serializa JSON. **No contiene lógica de fases.**
- **Arranque:** `validar_config()` se ejecuta al importar el módulo; si faltan credenciales, la app no arranca (error claro en logs, en lugar de fallar en la primera petición).
- **Rate limiting:** Flask-Limiter limita `/api/chat` a 30 req/minuto y 500/día por IP, y `/api/logs` a 60 req/minuto (almacenamiento en memoria; con 1 worker los contadores y el buffer de logs son coherentes).
- **Seguridad de sesión:** cookies `HttpOnly`, `SameSite=Lax` y `Secure` activado en Render (`RENDER` presente en el entorno).
- **Observabilidad:** registra el inicio y fin de cada petición (`fase`, mensaje recortado, latencia total, respuesta recortada), los rechazos 400 y las excepciones con traceback.
- **Rutas:**

| Método y ruta | Descripción |
|---------------|-------------|
| `GET /` | Inicializa la sesión si está vacía y renderiza `templates/index.html`. |
| `POST /api/chat` | Recibe `{"mensaje": "..."}`, despacha según `session['fase']`. Limitado a 30 req/min y 500/día por IP. |
| `GET /api/logs` | Devuelve las últimas entradas del buffer (`?limit=1..500`). **Abierto, sin token.** |
| `POST /api/logs/clear` | Vacía el buffer de logs del servidor (botón Limpiar del panel). |
| `POST /api/reset` | `session.clear()`; devuelve `{"status": "ok"}`. |

- **Sesión:** `app.secret_key = core.config.SECRET_KEY` (única fuente). Al ser obligatoria, `validar_config()` garantiza que nunca se firme con un default público.
- **Versión de sesión (`VERSION_SESION = 2`):** si la cookie no trae la versión actual (`_v`), la sesión se reinicia a `saludo`. Evita que una fase antigua (p. ej. `producto`) siga activa tras un despliegue.
- **Handlers globales (`@app.errorhandler`):** `404`, `429`, `500` y `Exception` genérico devuelven siempre JSON con clave `respuesta`. Al usuario se le muestra un mensaje genérico; el traceback se imprime en logs con el prefijo `[EXCEPCIÓN NO MANEJADA]` o `[ERROR en /api/chat]`.
- **Delegación:** entrega `(fase, mensaje, historial)` a `flujo.despachar` y guarda `(respuesta, siguiente_fase, historial)` en la sesión. Las reglas de transición viven en los componentes y en `flujo.py`, no aquí.

### [Frontend] `templates/index.html` + `static/`

- **`index.html`:** layout de chat (header con marca SALUS, botones de logs y reset, mensajes, formulario de entrada), panel lateral de logs y favicon inline (SVG ⚕️). Carga la fuente Outfit de Google Fonts.
- **`script.js`:**
  - Envía el mensaje con `fetch('/api/chat')` y renderiza la respuesta del bot.
  - Indicador de escritura animado (3 puntos) mientras espera.
  - Convierte cualquier URL de la respuesta en un enlace con texto `Ver Producto` (`target="_blank"`), limpiando la puntuación pegada (paréntesis, punto, coma) para que el enlace no salga roto.
  - Botón de reset con `confirm()` → `POST /api/reset` y limpia el DOM.
  - Bloquea input y botón de envío durante la petición (evita dobles envíos).
  - **Panel de logs:** el botón de terminal abre un panel lateral oscuro que consulta `/api/logs?limit=200` cada 3 s; colorea por nivel (`INFO`/`WARNING`/`ERROR`), muestra hora/módulo/mensaje, auto-scroll configurable y botones **Copiar** (portapapeles con formato `[hora] NIVEL módulo: mensaje`) y **Limpiar** (vacía el buffer del servidor vía `POST /api/logs/clear`). El texto se inserta con `textContent` (sin XSS).
- **`style.css`:** tema verde (`--primary: #10b981`), variables CSS en `:root`, glassmorphism suave (`rgba` + blur), animaciones `fadeIn` / `pulse` / `typing`, burbujas diferenciadas para usuario/bot/sistema, estilos del panel de logs (tema consola oscura, responsive) y scrollbar personalizada.

### ~~[Legacy] `*/FASE1.py`, `asesoria/groq_cliente.py`, `producto/groq_cliente.py`~~ (eliminados)

> [!NOTE]
> Los módulos monolíticos `FASE1.py` y los clientes Groq duplicados por paquete fueron **eliminados** del proyecto. La lógica vigente es la refactorizada (`asesoria/asesoria.py`, `producto/producto.py`, `core/groq_cliente.py`). Si se necesitan como referencia, siguen disponibles en el historial de Git.

---

## 5. Esquema de Datos

### A. Tabla Turso `productos`

Columnas consultadas por `producto/database.py` (el esquema completo de la tabla puede tener más columnas):

| Columna | Tipo lógico | Uso en SALUS |
|---------|-------------|--------------|
| `nombre_producto` | TEXT | Nombre mostrado y campo de búsqueda `LIKE`. |
| `marca` | TEXT | Se pasa al prompt del vendedor. |
| `descripcion` | TEXT | Campo de búsqueda `LIKE` y contexto para la IA. |
| `precio1` | REAL/INTEGER | Precio que el vendedor comunica; se formatea como `$12.00` (clave `precio`). |
| `slug` | TEXT | Construye `https://www.naturesgreenec.com/producto/{slug}`. |
| `para_que_sirve` | TEXT | Contexto para el vendedor (1 frase en la respuesta). |
| `como_tomar` | TEXT | Solo se envía al vendedor si `requiere_web` (el cliente pide cómo se toma); se cita literal. |
| `dosis` | TEXT | Solo se envía al vendedor si `requiere_web`; se cita literal. |
| `via_administracion` | TEXT | Solo se envía al vendedor si `requiere_web`; se cita literal. |
| `edad_recomendada` | TEXT | Solo se envía al vendedor si `requiere_web`; se cita al explicar el modo de uso. |
| `contraindicaciones` | TEXT | Solo se envía al vendedor si `requiere_web`; se cita literal al explicar el modo de uso. |
| `advertencias` | TEXT | Solo se envía al vendedor si `requiere_web`; se cita literal al explicar el modo de uso. |
| `recomendaciones` | TEXT | **No se envía al vendedor** (estilo de vida). |
| `stock` | INTEGER | Se transforma en `disponible = (stock > 0)` (informativo; no influye en el ranking). |
| `oculto` | INTEGER | Filtro `oculto = 0` (productos visibles). |
| `foto_url` | TEXT | Ranking: +1 si tiene foto. |
| `video_url` | TEXT | Ranking: +1 si tiene video. |
| `info_completada` | INTEGER | Ranking: +1 si la información está completa. |
| `categoria_id` | INTEGER | Ranking: +1 si pertenece a una categoría. |
| `star` / `superstar` | INTEGER | Ranking: +1 si es destacado (`star` o `superstar` > 0). |

> [!NOTE]
> La consulta devuelve hasta `LIMITE_PRODUCTOS` coincidencias (default 6, configurable) **ordenadas por relevancia** (coincidencia en nombre > marca > descripción) y luego por prioridad (campos clave completos). El vendedor las recibe todas (vista reducida) y compara/recomienda; con lista vacía responde que no lo encontró y pregunta qué busca.

### B. Contrato del dict `producto` (salida de `buscar_producto`)

```json
{
  "nombre": "…", "marca": "…", "descripcion": "…", "precio": "$12.00",
  "enlace": "https://www.naturesgreenec.com/producto/slug",
  "para_que_sirve": "…", "como_tomar": "…", "dosis": "…",
  "via_administracion": "…", "edad_recomendada": "…",
  "contraindicaciones": "…", "advertencias": "…", "recomendaciones": "…",
  "disponible": true
}
```

### C. Formato de respuesta HTTP de `/api/chat`

```json
{
  "respuesta": "Texto que se muestra al usuario",
  "fase": "saludo | atencion | asesoria | producto | tratamiento | venta | historial"
}
```

> [!NOTE]
> Todas las ramas de `app.py` devuelven exactamente el mismo formato (`respuesta` + `fase`). El banner de debug se eliminó en la sesión de endurecimiento.

### D. Estado de sesión (`session`)

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `fase` | str | Fase activa: `saludo` (default), `atencion`, `asesoria`, `producto`, `tratamiento`, `venta` o `historial`. |
| `historial` | list[dict] | Mensajes en formato OpenAI (`role`/`content`), incluyendo el prompt de sistema. Se **vacía** al cambiar de fase. En fase `producto` incluye además un mensaje `system` interno con el marcador `__salus_estado__` (último término/necesidad) para el fallback del extractor. |
| `_v` | int | Versión del esquema de sesión (`VERSION_SESION`). Si no coincide, la sesión se reinicia a `saludo`. |

> [!NOTE]
> El historial crece dentro de una misma fase; no hay truncado por longitud. El prompt de sistema se reinyecta al reconstruirlo cuando la lista está vacía.

---

## 6. Particularidades y Reglas de Negocio

1. **Clasificación de intenciones conservadora (Fase Atención):** el bot nunca asume que el cliente quiere comprar algo solo por mencionar un síntoma. Mientras la petición no sea explícita, la intención es `pendiente`. Si el bot hace una pregunta, la intención también es `pendiente` (regla estructural). Esto evita transiciones de fase prematuras.
2. **Aislamiento por fase:** al cambiar de fase se descarta el historial anterior. Recepción, Asesoría y Producto usan prompts de sistema distintos; mezclarlos degradaría la calidad de la conversación.
3. **Asesoría con búsqueda inmediata:** cuando el asesor confirma `producto_encontrado`, el propio componente de asesoría llama a `producto.responder(producto_sugerido, [])` sin esperar un mensaje adicional y **concatena** la recomendación + el resultado comercial en una sola burbuja (`respuesta + "\n\n" + resultado`). Si la búsqueda falla, se devuelve solo la recomendación (el error no se filtra al cliente).
4. **Venta conversacional y minimalista:** el vendedor conversa en 2-4 frases; cuando el cliente solo nombra el producto, pregunta el tipo, presentación o marca agrupando las variantes que muestran los datos (p. ej. citrato/cloruro/glicinato) y no lidera con productos que solo mencionan el término; respeta la preferencia, compara opciones y recomienda una; menciona el precio (ya formateado con `$`) y el enlace de cada producto que nombre al presentarlo/compararlo/recomendarlo (en respuestas de un dato puntual no repite precio ni enlace si ya se dieron). Dosis, cantidades, contraindicaciones y advertencias **no** se muestran por iniciativa propia; solo si el cliente lo pide expresamente (`requiere_web`, p. ej. "¿cómo se toma?") el vendedor recibe `como_tomar`/`dosis`/`via_administracion`/`edad_recomendada`/`contraindicaciones`/`advertencias` de la ficha y cita el modo de uso **literalmente** para el producto exacto, mencionando también de forma breve las contraindicaciones, advertencias y edad. En repreguntas sobre lo mismo ("¿a qué hora?", "¿cada cuánto?") retoma lo ya dicho y lo complementa: la ficha es la fuente principal y la web solo añade lo que la ficha no dice, sin contradecirla ni sustituirla. No confirma con un simple "sí/no" un uso que la ficha no respalde ni agrega horarios, comidas concretas o repartos inventados ("con una comida" no autoriza "mañana o tarde", "con la cena" ni "como te resulte más cómodo"). Solo `recomendaciones` (estilo de vida) no se le envía nunca. Tampoco promete acciones que no existen (carrito, reservas). Mientras se prueban las respuestas, la verificación de stock está **pausada** (`disponible` no viaja al LLM).
5. **Rotación de API Keys ante 401/429:** el cliente único `core/groq_cliente.py` recorre `API_KEYS` en orden y espera 2 s entre intentos. El 401 (key inválida o revocada) también dispara el salto a la siguiente key, no solo el 429 (rate limit). Garantiza estabilidad en la capa gratuita de Groq.
6. **Salida JSON estricta:** recepción, asesoría y extracción usan `response_format={"type": "json_object"}` y parsean con `json.loads`. El contrato de cada prompt es parte del código: cambiarlo exige actualizar el parseo en el mismo commit.
7. **Errores siempre en JSON:** los handlers globales de `app.py` impiden que Flask devuelva HTML de error, lo que rompería el `response.json()` del frontend.
8. **Protección de cuota:** el endpoint público `/api/chat` está limitado por IP (30 req/min, 500/día) y los errores internos nunca se muestran al usuario; ambos cambios protegen la cuota gratuita de Groq y evitan filtrar detalles internos.
9. **Logs efímeros y con datos recortados:** el buffer vive en memoria (no se escribe a disco), guarda las últimas `LOGS_BUFFER` entradas y recorta los textos. Las API keys siempre van enmascaradas. El panel `/api/logs` queda abierto (sin token) para pruebas; si el chat se abre a usuarios reales, conviene restringirlo (ver §8).
10. **Producto ya no es terminal:** mantiene contexto entre turnos y puede derivar a `tratamiento` o `venta` cuando el cliente muestra esas intenciones; `POST /api/reset` (botón ↺) sigue volviendo al saludo.
11. **Historial, tratamiento y venta pendientes:** existen como esqueletos en sus carpetas (`historial/`, `tratamiento/`, `venta/`) con `responder` placeholder y TODO; aún no tienen lógica de negocio.
12. **Saludo inicial:** la conversación arranca en `saludo`; el LLM genera una bienvenida variada (enfoques aleatorios) sin asumir productos, y el primer mensaje del cliente solo se usa como contexto (no se clasifica). A partir del siguiente turno, todo pasa por `atencion`.
13. **Contexto en producto:** extractor y vendedor reciben los últimos `HISTORIAL_TURNOS` turnos (default 4) mediante `producto/contexto.py`; por eso las referencias ("y bueno?", "y solo tienen ese?", "ese") se resuelven sin repetir el producto. Si el extractor no logra un término, la repregunta también la genera el LLM con ese contexto (nada de texto fijo) y con reglas anti-alucinación: no nombra ni recomienda productos ni opciones, no añade variantes/atributos que no estén literalmente en el contexto, ante saludos solo devuelve la cortesía sin ofrecer productos y no repregunta lo que el cliente ya explicó. El vendedor, por su parte, no repite "¿para qué lo necesitas?" si el motivo ya viene en los datos y no contradice datos ya dados en la conversación. El extractor solo llega a ese fallback si fallaron sus dos llamadas a Groq (la segunda sin modo JSON).
14. **Ranking de productos:** la búsqueda cubre nombre, descripción y marca; ordena primero por relevancia (coincidencia en nombre > marca > descripción) y luego prioriza productos con `foto_url`, `video_url`, `info_completada`, `categoria_id` y `star`/`superstar` (más campos completos = mejor posición); el stock no influye en el orden y los ocultos nunca se muestran. Los enlaces de producto se construyen siempre con `www`: `https://www.naturesgreenec.com/producto/{slug}`.
15. **Respaldo web con verificación (Tavily):** la web solo se consulta cuando la DB no alcanza (el extractor marcó `requiere_web` o Turso devolvió 0 filas); la consulta incluye la pregunta del cliente como contexto (p. ej. "efervescente"), se piden 2 resultados extra y el filtro de producto exacto acepta todas las palabras del término **o** las primeras palabras del nombre del catálogo (cubre fichas oficiales devueltas en otro idioma). El vendedor los usa solo si confirman el dato puntual pedido — incluido el **modo de uso** ("cómo se toma"), que la web puede confirmar cuando Turso no trae el campo —, usándolos **solo como verificación interna** (jamás se citan, mencionan ni enlazan: ver regla 19); si no, responde que no tiene el detalle confirmado. Está **prohibido afirmar o negar la presentación/formato** (efervescente, tableta, cápsula, sobre, líquido) cuando no aparece textualmente en datos o web, y reforzar suposiciones previas de la conversación. Las consultas se cachean en memoria (`WEB_CACHE_TTL`, `WEB_CACHE_MAX`), la web nunca habilita recomendar productos fuera del catálogo ni dar indicaciones médicas, contraindicaciones o advertencias, y la respuesta pasa por `_filtrar_enlaces` para eliminar cualquier URL externa.
16. **Tratamiento solo bajo pedido explícito:** comparar productos ya mostrados, preguntar por precios/cantidades o narrar un síntoma **no** cambia la intención a `tratamiento`; el extractor solo la marca cuando el cliente pide un tratamiento/plan como tal y, ante duda, elige `producto`. Así "¿cuál de los dos es mejor para dormir?" se responde dentro de `producto` y no cae en el esqueleto de tratamiento.
17. **Todo tratamiento pasa primero por el historial clínico:** una petición explícita de tratamiento se detecta en atención (ruta propia) o en producto (extractor) y se deriva a `historial`, nunca directo a `tratamiento`. La guarda central de `flujo.py` bloquea a nivel estructural cualquier transición a `tratamiento` cuya fase de origen no sea `historial` (defensa que no depende del LLM). Mientras `historial` sea esqueleto, `tratamiento` queda inaccesible; y si el bot hace una pregunta, no cambia de fase.
18. **Ahorro de cuota Groq (TPD):** medido con datos reales, un mensaje de producto costaba ~5,600 tokens (69% reglas de prompts, 26% datos de la DB, 4% contexto; la web añade ~400). Dieta aplicada: extractor en modelo propio (`openai/gpt-oss-120b`, otro TPD), extractor **omitido** en seguimientos claros (~-1,800 tok; un "¿a qué hora?" pasa de ~5,600 a ~3,200), `LIMITE_PRODUCTOS` 8→6 y `descripcion`/`para_que_sirve` recortadas a 200 chars (~-560 tok), 429 por TPD sin reintento (`es_limite_diario`) y `max_retries=0`; si el extractor falla se reutiliza el estado `__salus_estado__`, si el vendedor falla se responde un texto determinista (`_respuesta_sin_llm`) y sin estado ni cuota se responde `MENSAJE_SIN_CUOTA`. El TPD es por **organización**, no por key: varias keys de la misma cuenta no suman cuota.
19. **Enlaces únicamente de naturesgreenec.com (regla dura):** el chat nunca comparte ni menciona enlaces, precios, disponibilidad ni contenido de otras webs (la marca, la competencia u otras tiendas). Los fragmentos de Tavily son **solo verificación interna** y jamás se citan. Toda respuesta del vendedor pasa por `_filtrar_enlaces` (`producto/vendedor.py`): las URLs externas se eliminan (la oración completa si solo contiene URLs externas) antes de mostrarse, con `WARNING` en logs; si el filtrado deja la respuesta vacía, se responde con datos del catálogo. Si el cliente pide una variante que no está en el catálogo, se dice con claridad y se ofrece la más parecida, sin señalar que otra tienda o la marca sí la tiene. Caso real que originó la regla: "¿no tiene en polvo?" respondió citando la página oficial de Only Natural y su precio.

---

## 7. Instalación y Guía de Uso

### A. Preparación del entorno

```bash
# 1. Clonar el repositorio
git clone https://github.com/Leecsito/Salus.git
cd Salus

# 2. Crear y activar entorno virtual (Windows)
python -m venv venv
.\venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

### B. Variables de entorno

1. Copiar `.env.example` a `.env`.
2. Completar: `GROQ_API_KEYS` (una o más keys separadas por coma), `TURSO_URL`, `TURSO_TOKEN` y `SECRET_KEY` (obligatoria; genera una con `python -c "import secrets; print(secrets.token_hex(32))"`). Opcionales: `GROQ_MODEL`, `HISTORIAL_TURNOS`, `LIMITE_PRODUCTOS`, `TAVILY_API_KEY` (habilita el respaldo web), `WEB_MAX_RESULTADOS`, `WEB_CACHE_TTL`, `WEB_CACHE_MAX`, `LOG_LEVEL` y `LOGS_BUFFER`.

> [!TIP]
> **Cómo ver los logs:** abre el botón de terminal (⎡>_⎦) del header → panel en vivo (con botones Copiar y Limpiar). No requiere token ni URL especial.

> [!IMPORTANT]
> `.env` está en `.gitignore`: nunca se sube al repositorio. En **Render**, definir las mismas variables en *Dashboard → Environment*.

| Variable | Requerida | Ejemplo | Descripción |
|----------|-----------|---------|-------------|
| `GROQ_API_KEYS` | Sí | `gsk_abc,gsk_def` | Keys separadas por coma; se rotan ante 401/429. |
| `GROQ_MODEL` | No | `openai/gpt-oss-20b` | Modelo Groq del diálogo. Si se omite, usa el default. |
| `GROQ_MODEL_EXTRACCION` | No | `openai/gpt-oss-120b` | Modelo del extractor (reparte la cuota diaria de tokens con el diálogo). Si se omite, usa el default. |
| `HISTORIAL_TURNOS` | No | `4` | Turnos recientes que extractor y vendedor usan como contexto. |
| `LIMITE_PRODUCTOS` | No | `6` | Máximo de productos que devuelve Turso y recibe el vendedor. |
| `TAVILY_API_KEY` | No | `tvly-…` | Key de Tavily para el respaldo web. Sin ella, la búsqueda web se omite. |
| `WEB_MAX_RESULTADOS` | No | `4` | Fragmentos web pedidos a Tavily por consulta. |
| `WEB_CACHE_TTL` | No | `21600` | TTL del caché de búsquedas web, en segundos (6 h). |
| `WEB_CACHE_MAX` | No | `200` | Entradas máximas del caché de búsquedas web. |
| `TURSO_URL` | Sí | `https://tu-db.turso.io` | URL de la base Turso. |
| `TURSO_TOKEN` | Sí | `eyJhbGci…` | Token de Turso. |
| `SECRET_KEY` | Sí | `token_hex(32)` | Firma de la cookie de sesión. Sin ella la app no arranca. |
| `LOG_LEVEL` | No | `INFO` | Nivel mínimo de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `LOGS_BUFFER` | No | `500` | Entradas conservadas en memoria para el panel de logs. |

### C. Ejecución local

```bash
python app.py
# → http://127.0.0.1:5000  (debug=True)
```

### D. Ejecución en producción (Render)

- El `Procfile` ya define el comando: `web: gunicorn app:app --workers 1 --threads 8 --timeout 120` (el timeout amplio evita cortes cuando el LLM tarda o la instancia despierta; 1 worker mantiene coherentes el buffer de logs y los límites por IP).
- Render inyecta las variables de entorno; `load_dotenv()` no encuentra `.env` y no hace nada. Para el respaldo web, definir también `TAVILY_API_KEY` (y opcionalmente `WEB_*`) en *Dashboard → Environment*.
- El plan gratuito puede **dormir** la instancia: la primera petición tras inactividad tarda unos segundos.
- **Despliegue automático:** el servicio de Render está conectado al repositorio GitHub (`Leecsito/Salus`). Con *Auto-Deploy* en **On Commit** (Dashboard → servicio → Settings → Build & Deploy), cada `git push` a la rama `main` dispara un redespliegue: **no hace falta ningún archivo adicional ni desplegar a mano**.

### E. Prueba de la API con `curl`

La conversación depende de la cookie de sesión; usar un cookie jar:

```bash
# Turno 1 — saludo
curl -c cookies.txt -X POST http://127.0.0.1:5000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"mensaje\": \"Hola, me duele la cabeza\"}"

# Turno 2 — misma sesión
curl -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:5000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"mensaje\": \"¿Qué me recomiendas?\"}"

# Reset
curl -b cookies.txt -X POST http://127.0.0.1:5000/api/reset
```

---

## 8. Deuda Técnica y Buenas Prácticas

**Resueltas en la sesión de endurecimiento (2026-10):**

- Módulos legacy `*/FASE1.py` y clientes `groq_cliente.py` duplicados: **eliminados**; el cliente es único en `core/`.
- Reestructuración por componentes: `core/` (config, Groq, logs), una carpeta por fase y `flujo.py` como orquestador; `app.py` quedó sin lógica de fases.
- `.pyc` con credenciales eliminados del árbol y de Git; `__pycache__/` y `*.pyc` en `.gitignore`.
- `validar_config()`: ahora se invoca al arrancar `app.py`.
- `SECRET_KEY`: única fuente en `core/config.py`, obligatoria y sin default inseguro.
- Banner de debug: eliminado del frontend y de las respuestas JSON.
- Errores internos: ya no se exponen al usuario (solo mensajes genéricos; detalle en logs).
- Rate limiting por IP en `/api/chat` y timeout/workers de Gunicorn configurados.
- `requirements.txt` con versiones fijadas.
- Producto conversacional con contexto (sesión actual): historial reciente en extractor y vendedor, repregunta natural por LLM, handoff atención→producto en el mismo turno, `LIMITE_PRODUCTOS` configurable (hoy default 6), ranking por prioridad de campos, búsqueda por nombre/descripción/marca, enlaces con `www` y limpieza de puntuación, precio formateado con `$`, vista reducida sin campos médicos, vendedor que pregunta presentación/marca antes de volcar opciones, respeta preferencias, compara/recomienda sin ficha y deriva a `tratamiento`/`venta`.
- Relevancia de búsqueda y agrupación por tipo: el ranking ahora prioriza coincidencias en nombre > marca > descripción (un producto que solo menciona "magnesio" en su descripción ya no desplaza a los que son de magnesio), el vendedor agrupa las variantes (citrato/cloruro/glicinato…) y pregunta cuál prefiere antes de listar, y la frase de transición de atención ya no adelanta información del producto.
- Búsqueda tolerante y respaldo web: la consulta a Turso ignora acentos y reintenta ante erratas (`vitamagnésio`/`vitamagensio` → `VITAMAGNESIO PLUS`); cuando el cliente pide un dato puntual del producto (`requiere_web` del extractor) o Turso no devuelve nada, `producto/buscador.py` consulta Tavily con filtro de producto exacto y caché en memoria, y el vendedor solo responde si los fragmentos confirman el dato (sin inventar). Verificación de stock pausada durante las pruebas (marcada con `##` en `producto/vendedor.py`).
- Clasificación de intención corregida y recuperación por palabras: comparaciones de productos mostrados ya no derivan a `tratamiento` (que solo se activa con un pedido explícito), la segunda pasada trae "Magnesio Glicinato 600 mg" al buscar "glicinato de magnesio", y el extractor reintenta una vez ante fallos transitorios de JSON de Groq.
- Flujo clínico obligatorio (esta sesión): atención tiene ruta propia `tratamiento` → `historial`; producto deriva a `historial` cuando el extractor detecta tratamiento (sin buscar productos) y ya no cambia de fase si hace una pregunta; `flujo.py` incorpora la guarda central que impide llegar a `tratamiento` desde cualquier fase que no sea `historial`. `tratamiento` queda inaccesible hasta que se implemente el intake clínico.
- Antialucinación de presentación (caso Triple C Advance): `requiere_web` cubre preguntas de formato (efervescente, tableta, sobre, polvo, cápsula, líquido), la consulta a Tavily incluye la pregunta del cliente, el filtro acepta también las primeras palabras del nombre del catálogo (la ficha oficial volvía en inglés y se descartaba) y se piden 2 resultados extra. El vendedor tiene regla dura de no **afirmar ni negar** la presentación: antes inventaba "tabletas sólidas" o "no son efervescentes" y ahora responde con los sobres efervescentes confirmados o dice que no tiene el detalle.
- Comparaciones de variantes, presentaciones y fallos de JSON (caso magnesio glicinato $20/$30): el extractor ya no arrastra dosis al término en comparaciones (usa la familia `"magnesio glicinato"`, con lo que Turso devuelve VITAHEALTH $20 y Natural Factors $30) pero **sí conserva** la concentración cuando el cliente pregunta por una presentación concreta (`"magnesio glicinato 600 mg"`); las columnas de Turso ahora unifican `\u202f`/`\xa0` igual que el término, de modo que la frase exacta encuentra productos con espacios angostos; el fallo `400 json_validate_failed` se reintenta **sin `response_format`** y, si vuelve a fallar, `extraer_termino` devuelve un dict vacío en vez de propagar el 500 (el turno degrada a repregunta); y la repregunta tiene reglas anti-alucinación (no recomienda ni inventa, no repregunta lo ya explicado, `temperature=0.3`). Probado con los casos: comparación $20 vs $30, consulta específica 600 mg, "¿cuál me recomendaría?" tras magnesio, doble fallo JSON simulado y repregunta real.
- Modo de uso bajo pedido explícito ("¿cómo se toma?"): antes el vendedor nunca podía responder porque `como_tomar`/`dosis`/`via_administracion` no viajaban al LLM y el prompt prohibía modos de uso, aunque Turso sí tuviera el dato (caso GLICINATO DE MAGNESIO: "Tomar 2 cápsulas al día con agua, preferiblemente con una comida."). Ahora `producto/vendedor.py` expone `CAMPOS_MEDICOS` y los añade a la vista **solo** cuando el extractor marca `requiere_web`; el prompt obliga a citarlos **literalmente** y solo para el producto exacto (sin mezclar ni recalcular); la web puede confirmar el modo de uso cuando el catálogo no lo trae (se eliminó la contradicción extractor↔vendedor sobre "cómo se consume" y se añadió el ejemplo few-shot "¿cómo se toma?"). La dosis por iniciativa propia sigue prohibida y `contraindicaciones`/`advertencias`/`recomendaciones` siguen sin enviarse nunca. El log del vendedor ahora indica `medicos=True/False`. Segunda pasada (seguimiento "¿a qué hora?"): el prompt obliga a **retomar lo ya dicho** en repreguntas (repetir dosis y modo de la ficha y luego añadir el dato nuevo, con la ficha como fuente principal y la web solo como complemento), en lugar de responder un dato aislado que parezca olvidar lo anterior. Verificado en vivo: "Tomar 2 cápsulas al día con agua, preferiblemente con una comida. Para dormir, lo ideal es tomarlo 30-60 minutos antes de acostarse. El glicinato de magnesio de VITAHEALTH cuesta $20.00 y lo puedes ver aquí https://…".
- Revisión de conversación real (saludo inventado, repregunta ignorada y horario contradictorio): la repregunta ya no ofrece ni inventa opciones (caso "hola" → "la opción con magnesio o la que incluye vitamina"): ante saludos solo devuelve la cortesía sin productos y, si retoma el tema, se limita a lo literal del contexto; el vendedor no repite "¿para qué lo necesitas?" cuando el motivo ya viene del extractor (recomienda la variante que encaja: sueño → glicinato, con precio y enlace) y no contradice datos ya dados (decía 30-60 min y luego 1-2 h); el horario general se presenta separado de la ficha. Verificado en vivo: saludo → "¡Hola! ¿En qué puedo ayudarte hoy?"; "no sé cuál, para el sueño" → recomienda el glicinato sin repreguntar; "¿a qué hora?" → mantiene "2 cápsulas al día con agua, preferiblemente con una comida" + "30 a 60 minutos antes de acostarse" y el enlace.
- Revisión con ficha externa (Arcamia) del VITAHEALTH: se aclaró que la dosis "2 cápsulas al día con agua, preferiblemente con una comida" y "promoviendo un sueño reparador"/"ideal" **sí** vienen de la ficha de la tienda en Turso (no de otras marcas, como sugería el revisor); el "30-60 min antes de dormir" era el único aporte web (genérico). Se endureció el prompt: no confirmar con "sí/no" un uso que la ficha no respalde, no inventar horarios/comidas/repartos ("con una comida" no autoriza "mañana o tarde", "con la cena" ni "como te resulte más cómodo"), y al explicar el modo de uso se envían y citan también `edad_recomendada`/`contraindicaciones`/`advertencias` de la ficha (`CAMPOS_MEDICOS` ampliado); el precio/enlace ya no se repiten en respuestas de dato puntual. Verificado en vivo: "¿cómo debo tomarlo?" → modo de uso + contraindicaciones + advertencias + edad, sin precio/enlace; "¿me tomo las dos antes de dormir?" → "No menciona que se deban tomar antes de dormir"; "¿mañana o después del almuerzo?" → "La ficha no indica si es la mañana o después del almuerzo". **Pendiente de negocio:** la ficha de Turso difiere de la etiqueta de Arcamia (2 vs 1-2 cápsulas; contraindicaciones distintas: Turso habla de insuficiencia renal grave, corazón, hipertensión y medicamentos, y adultos >18; Arcamia de embarazo, insuficiencia renal y menores de 8): la tienda debe decidir cuál es la correcta y actualizar Turso si aplica.
- Ahorro de cuota Groq (revisión de consumo): el extractor pasó a `openai/gpt-oss-120b` (nuevo `GROQ_MODEL_EXTRACCION`; cada modelo tiene su TPD), `Groq(max_retries=0)` evita reintentos ocultos del SDK, `es_limite_diario()` detecta el 429 por tokens/día para no reintentar (extractor) y para responder `MENSAJE_SIN_CUOTA` sin LLM (producto, sin estado previo), y el nuevo estado interno `__salus_estado__` en el historial permite reutilizar el último término/necesidad cuando el extractor falla (con detección local de dato puntual para activar `requiere_web`). Verificado con mocks (sin gastar cuota): 1 sola llamada ante TPD, fallback sin repregunta, estado reemplazable e invisible al contexto, camino normal intacto. Medición: ~6-7k tokens por mensaje de producto → ~30 mensajes/día en el plan gratuito; alternativa definitiva: Dev Tier/pago (~$0.02/día con gpt-oss-20b). **Pendiente de verificar por el usuario:** si sus keys pertenecen a la misma organización (el TPD es por org y rotar no suma cuota). Además, si el vendedor falla (TPD del modelo de diálogo) responde un texto determinista con los datos reales (`_respuesta_sin_llm`): antes la excepción propagaba (500 o solo la frase de transición de atención, con el historial vacío) y el siguiente mensaje perdía el contexto; ahora el turno se conserva y el estado queda guardado. Verificado con mocks (varios productos, uno con `requiere_web`, sin resultados y error genérico).
- Dieta de tokens (medición + optimizaciones): medición real → 69% reglas de prompts, 26% datos DB, 4% contexto, ~400 tok la web; por mensaje ~5,600 tok. Se implementó: (A) extractor omitido en seguimientos claros usando `__salus_estado__` + chequeo local `menciona_producto` contra Turso (sin LLM), con guardas de tratamiento/compra — un "¿a qué hora?" baja de ~5,600 a ~3,200 tok (-44%); y (C) `LIMITE_PRODUCTOS` 8→6 y `descripcion`/`para_que_sirve` truncadas a 200 chars con `…` — el primer mensaje baja a ~4,900 tok (-14%); proyección: ~41-63 turnos/día según mezcla (antes ~35). Verificado con mocks y Turso real (8 casos de mención, skip del extractor, guardas, truncado), Groq: 0 llamadas. La mejora manual de la DB (descripciones concisas, campos médicos completos, marcas limpias) queda recomendada para evitar el respaldo web y mejorar exactitud.
- Regla de enlaces (caso "citrato en polvo de Only Natural"): el vendedor citó la web oficial de la marca con su precio. Se endureció el prompt (prohibido citar/enlazar cualquier sitio que no sea el catálogo; los fragmentos web son solo verificación interna, jamás citados) y se añadió `_filtrar_enlaces` en `producto/vendedor.py`: elimina URLs externas (descarta la oración completa si solo contiene URLs externas) con `WARNING`, y si la respuesta queda vacía responde con datos del catálogo. Verificado con mocks (oración externa descartada, oración mixta, fallback y reglas presentes en el prompt), Groq: 0 llamadas.

**Pendientes:**

1. **Componentes tratamiento, venta e historial sin implementar:** son esqueletos con placeholder y TODO (el historial antes era un inline en `app.py`). Orden sugerido: implementar **primero `historial`** (dos modos + intake + persistencia clínica en sesión + `VERSION_SESION`), porque es la única puerta hacia `tratamiento`; después `tratamiento`, y `venta` en paralelo. Acción sugerida: definir y programar cada flujo de negocio.
2. **Historial sin truncado:** en conversaciones largas, `session['historial']` crece sin límite (límite práctico: tamaño de la cookie de sesión, ~4 KB). `HISTORIAL_TURNOS` limita lo que se **envía** al LLM, no lo que se almacena. Acción sugerida: recortar lo persistido a los últimos N turnos.
3. **Sin pruebas automatizadas ni CI:** no hay tests unitarios de los prompts/parseos ni pipeline de verificación. Acción sugerida: tests de contrato para `atencion.responder`, `asesoria.responder`, `producto.responder`, `flujo.despachar` y `buscar_producto` con mocks de Groq/Turso.
4. **Fallback 429 sin backoff exponencial:** se espera un `time.sleep(2)` fijo por key. Es aceptable en la capa gratuita, pero un backoff creciente sería más robusto.
5. **Panel de logs abierto:** `/api/logs` no pide credenciales y muestra (recortados) los mensajes de los usuarios. Acción sugerida: protegerlo antes de abrir el chat al público.
6. **Verificación web perfeccionable:** el filtro de `buscador.py` exige que todas las palabras del término aparezcan en el resultado, pero no puntúa la fuente; si aparecen fragmentos ambiguos, conviene priorizar dominios oficiales (`naturesgreenec.com`, marca) y revisar `UMBRAL_APROXIMADO` con casos reales. Acción sugerida: anotar falsos positivos desde los logs (`Web | descartados…`) y ajustar.

---

## ⚠️ DIRECTIVA OBLIGATORIA DE MANTENIMIENTO DE DOCUMENTACIÓN

> [!IMPORTANT]
> **REGLA PERMANENTE DEL PROYECTO:**
>
> **Actualización obligatoria por cambios:** cada vez que se realice cualquier modificación, refactorización o ampliación en el proyecto (por ejemplo: cambios en prompts o en la máquina de fases, nuevas rutas o funciones, reorganización de archivos/carpetas, cambios en la consulta a Turso o en el contrato JSON de los endpoints), es **estrictamente obligatorio actualizar este archivo `DOCUMENTACION.md`**. Ningún cambio de código o arquitectura se considerará finalizado sin haber reflejado sus nuevos conceptos, funciones, esquemas o parámetros en esta documentación.
>
> **Corrección oportunista de inconsistencias:** si durante la implementación de un cambio encuentras explicaciones confusas, desactualizadas o incorrectas en la documentación directamente relacionada con lo que estás tocando, corrígelas en ese mismo momento. No realices auditorías completas del archivo para evitar consumo innecesario de tokens; únicamente subsana los errores puntuales que encuentres al paso.
>
> *"Con la idea de que la IA no tenga que revisar todo el proyecto, sino solo la documentación."*
