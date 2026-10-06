# SALUS — Documentación Técnica

**Proyecto:** Chatbot de atención al cliente y ventas para **Nature's Green** (tienda/farmacia naturista)  
**Tipo:** Aplicación web Flask con IA conversacional multi-fase (Saludo → Atención → Asesoría → Producto, con componentes futuros de tratamiento, venta e historial)  
**Entorno de ejecución:** Python 3.11 (Windows / Linux)  
**Despliegue:** Render — https://salus-ctix.onrender.com  
**Tienda en línea:** https://naturesgreenec.com  
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
| **Configuración** | `python-dotenv` + variables de entorno | Credenciales y secretos (única fuente: `core/config.py`) |
| **Estado de sesión** | Flask `session` (cookie cifrada con `SECRET_KEY`) | Guarda `fase` actual e `historial` de mensajes entre peticiones HTTP |
| **Frontend** | HTML5, CSS3 vanilla, JavaScript (Fetch API) | Interfaz de chat minimalista |
| **Protección** | Flask-Limiter | Límite de peticiones por IP en `/api/chat` (protege la cuota de Groq) |
| **Observabilidad** | `logging` estándar + buffer en memoria + panel en el frontend | Traza cada petición: módulo, prompt/modelo, key usada, tiempos, decisiones y errores |
| **Hosting** | **Render** (plan gratuito) | Despliegue desde Git con Gunicorn |

Modelo Groq usado en todo el proyecto: `openai/gpt-oss-20b`.

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
│   ├── extractor.py             # Extrae el sustantivo clave del mensaje con IA
│   ├── database.py              # Consulta el catálogo de productos en Turso
│   └── vendedor.py              # Genera la respuesta final de ventas con IA
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
| `producto/<verbo>or.py` (`extractor`, `vendedor`) | Helpers con una única responsabilidad dentro del componente producto. |
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
        │              │  historial}   │
        ▼              ▼               ▼
     pasa a        cambia fase +   cambia fase
     atención      limpia historial

                        POST /api/reset → session.clear() (vuelve a saludo)
```

### B. Flujo de una petición `POST /api/chat`

1. **Validación:** `app.py` exige JSON con el campo `mensaje` no vacío (400 si falla).
2. **Inicialización:** si no existe `session['fase']`, se inicializa en `saludo` con `historial = []`.
3. **Despacho:** `app.py` llama a `flujo.despachar(fase, mensaje, historial)`, que busca el componente en el mapa `FASES` y ejecuta su `responder`. El componente devuelve `(respuesta, siguiente_fase, historial)`; `app.py` persiste ambos valores en la sesión y devuelve el JSON.
4. **Comportamiento por componente:**
   - `saludo` → genera un saludo con LLM (solo al inicio) y devuelve `siguiente_fase="atencion"` con historial vacío.
   - `atencion` → clasifica la intención. Si es `pendiente`/error permanece en `atencion` conservando el historial; si el cliente pide producto, asesoría o historial, **vacía el historial** y cambia a esa fase.
   - `asesoria` → si el asesor confirma `producto_encontrado`, ejecuta de inmediato la búsqueda del producto sugerido, concatena el resultado comercial y pasa a `producto`; si sigue indagando, permanece en `asesoria`.
   - `producto` → cada mensaje dispara una nueva búsqueda (fase terminal hasta reset).
   - `tratamiento`, `venta`, `historial` → esqueletos: responden un placeholder y permanecen en su fase (ver TODO en cada archivo).
   - **Fase desconocida** → `flujo` reinicia a `saludo` con historial vacío.
5. **Respuesta:** JSON `{ "respuesta", "fase" }`.
6. **Errores:** cualquier excepción se captura y se devuelve como JSON (nunca HTML), con un mensaje genérico al usuario; el detalle queda solo en los logs del servidor.
7. **Rate limiting:** `/api/chat` está limitado a 30 peticiones/minuto y 500/día por IP. Al superarlo se devuelve `429` en JSON.

### C. Tabla de transiciones

| Fase actual | Condición de salida | Nueva fase | Efecto adicional |
|-------------|---------------------|-----------|------------------|
| `saludo` | siempre | `atencion` | `historial = []`; el primer mensaje solo da contexto al saludo |
| `atencion` | `intencion ∈ {producto, asesoria, historial}` | la intención | `historial = []` |
| `atencion` | `intencion ∈ {pendiente, error}` | `atencion` | se conserva el historial |
| `asesoria` | `estado == "producto_encontrado"` | `producto` | `historial = []`; se ejecuta la búsqueda y se concatena al mensaje |
| `asesoria` | `estado ∈ {consultando, error}` | `asesoria` | se conserva el historial |
| `producto` | cada mensaje | `producto` | nueva búsqueda independiente (sin historial) |
| `tratamiento` | cada mensaje | `tratamiento` | placeholder (esqueleto) |
| `venta` | cada mensaje | `venta` | placeholder (esqueleto) |
| `historial` | cada mensaje | `historial` | mensaje informativo (esqueleto) |
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
| `MODELO` | `GROQ_MODEL` | Modelo Groq usado en todo el proyecto. Default: `openai/gpt-oss-20b`. |
| `TURSO_URL` | `TURSO_URL` | URL de la base de datos Turso. |
| `TURSO_TOKEN` | `TURSO_TOKEN` | Token de autenticación de Turso. |
| `SECRET_KEY` | `SECRET_KEY` | Clave de firma de la cookie de sesión. **Obligatoria**, sin default. |

- **`validar_config()`:** lanza `EnvironmentError` con el detalle de las variables faltantes. **Se invoca al importar `app.py`**: si falta alguna variable crítica, el arranque falla con un error claro en logs.

### [Fase 1] `atencion/atencion.py` — Atención (clasificación de intención)

- **Propósito:** Primer contacto conversacional tras el saludo. Conversa con empatía y clasifica la necesidad del cliente.
- **Firma:** `responder(mensaje_usuario, historial) → (respuesta, siguiente_fase, historial)`. `siguiente_fase` es `"producto" | "asesoria" | "historial"` si la intención es explícita, o `"atencion"` si sigue `pendiente` o hubo error.
- **Prompt (`PROMPT_SISTEMA_RECEPCION`, sin cambios):** recepcionista cálido, respuestas de máximo 1-2 frases. Define las 3 rutas + estados:
  - `"pendiente"` — aún no hay petición explícita (saludos, síntomas narrados, temas ajenos, "no sé qué hacer").
  - `"producto"` — el cliente nombra un producto/marca/compuesto exacto.
  - `"asesoria"` — pide recomendación para un síntoma, sin saber qué producto comprar.
  - `"historial"` — pide explícitamente abrir/gestionar su expediente clínico.
- **Regla estructural clave:** si la respuesta del bot contiene una pregunta, la intención DEBE ser `pendiente`. Nunca se asume la intención por mencionar un síntoma.
- **Salida del modelo:** JSON estricto (`response_format={"type": "json_object"}`), `temperature=0.3`.
- **Transición:** al cambiar de fase devuelve `historial = []` (cada fase arranca con su propio prompt de sistema); si permanece en `atencion` lo conserva.
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
- **Función:** `llamar_groq(messages, model=MODELO, temperature=0.3, response_format=None)`. `MODELO` se define en `core/config.py` (default `openai/gpt-oss-20b`, configurable con `GROQ_MODEL`).
- **Comportamiento:** recorre `API_KEYS` en orden; ante `APIError` 401 (key inválida) o 429 (rate limit) espera 2 s y reintenta con la siguiente key. Si todas fallan, **relanza** la excepción (cada módulo de fase la captura, la registra en logs y devuelve un mensaje genérico con estado `error`).
- **Trazabilidad:** registra en logs la key usada (enmascarada, nunca completa), el modelo, la temperatura, si pide JSON, la latencia de cada llamada y cada rotación de key (`WARNING`).

### [Core] `core/logs.py` — Logging y panel de depuración

- **Propósito:** trazar el recorrido de cada mensaje para pulir el chat: qué módulo entra, qué prompt y modelo actúan, qué decide la IA, cuánto tarda y dónde falla.
- **Destinos:** consola (Render) con formato `[hora] NIVEL módulo mensaje`, y un buffer circular en memoria (`deque`, últimas `LOGS_BUFFER` entradas, default 500) expuesto por `GET /api/logs`.
- **Módulos registrados:** `salus.app`, `salus.flujo`, `salus.saludo`, `salus.atencion`, `salus.asesoria`, `salus.producto`, `salus.extractor`, `salus.vendedor`, `salus.turso`, `salus.tratamiento`, `salus.venta`, `salus.historial`, `salus.groq`.
- **Seguridad:** las API keys se enmascaran (`gsk_XXXXX…XXXX`); los textos se recortan a 160–200 caracteres; el buffer nunca se escribe a disco. `/api/logs` está **abierto sin token** (pensado para pruebas; ver pendiente en §8).
- **Niveles:** `INFO` para el flujo normal (prompt, key, decisión, tiempos), `WARNING` para rotaciones de key o búsquedas sin resultados, `ERROR` para excepciones con traceback en consola.
- **Variables:** `LOG_LEVEL` (default `INFO`), `LOGS_BUFFER` (default `500`).

### [Orquestador] `flujo.py` — Registro de fases y transiciones

- **Propósito:** Único lugar que conoce el mapa de fases. `app.py` le delega el despacho y **no necesita cambios** al agregar componentes.
- **Mapa `FASES`:** `saludo`, `atencion`, `asesoria`, `producto`, `tratamiento`, `venta` e `historial` → `responder` de cada componente.
- **`FASE_INICIAL = "saludo"`:** fase con la que arranca toda conversación nueva (y a la que se reinicia ante una fase desconocida).
- **`despachar(fase, mensaje, historial)`:** busca el componente y ejecuta `responder(mensaje, historial)`. Si la fase no existe, registra un `WARNING` y devuelve `("Sesión reiniciada. ¿En qué te puedo ayudar?", "saludo", [])`.
- **Contrato de componentes:** `responder(mensaje, historial) -> (respuesta, siguiente_fase, historial)`. Si un componente es `async`, debe documentarlo en su docstring (hoy todos son síncronos; `producto` envuelve una corrutina con `asyncio.run`).

### [Fase 0] `saludo/saludo.py` — Saludo inicial (LLM)

- **Propósito:** generar un saludo natural y distinto cada vez, con tono humano de una persona real de Nature's Green.
- **Firma:** `responder(mensaje_usuario, historial) → (saludo, "atencion", [])`.
- **Prompt (`PROMPT_SISTEMA_SALUDO`):** máximo 2 frases, cálido y variado; prohíbe presentarse como bot/IA y las fórmulas repetidas; ordena reaccionar con naturalidad al primer mensaje del cliente.
- **Parámetros:** `temperature=0.9` (favorece la variedad), sin `response_format` (texto libre).
- **Particularidad:** al ser la `FASE_INICIAL`, el primer mensaje del cliente solo da contexto al saludo y no se clasifica; siempre devuelve `historial = []` para que `atencion` arranque con su propio prompt de sistema.

### [Fase 3] `producto/producto.py` — Componente de productos

- **Propósito:** Coordinar el flujo completo de búsqueda de un producto.
- **Firma estándar:** `responder(mensaje_usuario, historial) → (respuesta, "producto", historial)`. **Nota (async):** la búsqueda real es la corrutina `ejecutar_busqueda_producto`; `responder` la ejecuta con `asyncio.run` porque el orquestador Flask es síncrono.
- **Corrutina principal:** `async ejecutar_busqueda_producto(mensaje_usuario) → str`.
- **Pasos:**
  1. `extraer_termino(mensaje)` (`extractor.py`). Si no hay término → mensaje pidiendo más precisión.
  2. `await buscar_producto(termino)` (`database.py`) contra Turso.
  3. `generar_respuesta_vendedor(termino, resultados)` (`vendedor.py`).

### [Helper] `producto/extractor.py` — Extracción del término

- **Función:** `extraer_termino(mensaje) → str` (sustantivo principal en singular, p. ej. `"colágeno"`, `"pomada"`, `"aspirina"`).
- **IA:** prompt con 3 ejemplos few-shot; ignora síntomas y frases como "que tengan" o "busco". `temperature=0`, salida JSON (`{"termino": "..."}`). Devuelve `""` si no identifica producto.

### [Helper] `producto/database.py` — Consulta a Turso

- **Función:** `async buscar_producto(termino) → list[dict]`.
- **Consulta SQL** (`CONSULTA_SQL`), con parámetros `%termino%` duplicados:

```sql
SELECT nombre_producto, marca, descripcion, precio1, slug,
       para_que_sirve, como_tomar, dosis, via_administracion,
       edad_recomendada, contraindicaciones, advertencias, recomendaciones,
       (stock > 0) AS disponible
FROM productos
WHERE (nombre_producto LIKE ? OR descripcion LIKE ?) AND oculto = 0
LIMIT 1
```

- **Conexión:** `libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)` como context manager async.
- **Normalización:** cada fila se convierte en dict con claves `nombre`, `marca`, `descripcion`, `precio`, `enlace`, `para_que_sirve`, `como_tomar`, `dosis`, `via_administracion`, `edad_recomendada`, `contraindicaciones`, `advertencias`, `recomendaciones`, `disponible`.
- **Enlace:** se construye como `https://naturesgreenec.com/producto/{slug}` (o `None` si no hay slug).
- **Límites:** `oculto = 0` excluye productos ocultos; `LIMIT 1` devuelve solo el primer producto coincidente (ver §6 y §8).

### [Helper] `producto/vendedor.py` — Respuesta de ventas

- **Función:** `generar_respuesta_vendedor(termino, resultados_db) → str`.
- **Prompt (`PROMPT_VENDEDOR`):** inyecta el mensaje completo del cliente (el parámetro se llama `termino`, pero `producto.py` le pasa el mensaje original) y el JSON de resultados. Reglas: si la lista está vacía → disculpa cordial y sugerencia de reformular; si hay resultado → **solo** nombre, para qué sirve (1 frase), precio, disponibilidad y enlace; máximo 3-4 líneas; nada de dosis, contraindicaciones ni listas largas.
- **Nota:** aunque la BD entrega dosis/contraindicaciones al prompt (viajan en el JSON), el prompt ordena no mostrarlas. `temperature=0.3`.

### ~~[Helper] `producto/groq_cliente.py`~~ (unificado)

> [!NOTE]
> Este helper fue eliminado: todas las fases usan el `core/groq_cliente.py`. La fase producto pasa `temperature=0` explícitamente (es factual, no conversacional).

### [Fase 4] `tratamiento/tratamiento.py` — Tratamiento (ESQUELETO)

- **Estado:** sin implementar. `responder` devuelve `("El módulo de tratamiento aún no está disponible.", "tratamiento", historial)` y registra un `WARNING`.
- **TODO:** definir el flujo de negocio (prompt del sistema, criterios de recomendación por malestar, transiciones y datos necesarios) antes de implementarlo.

### [Fase 5] `venta/venta.py` — Venta (ESQUELETO)

- **Estado:** sin implementar. `responder` devuelve `("El módulo de venta aún no está disponible.", "venta", historial)` y registra un `WARNING`.
- **TODO:** definir el flujo de negocio (método de pago, cierre de la venta, transiciones y datos necesarios) antes de implementarlo.

### [Fase 6] `historial/historial.py` — Historial clínico (ESQUELETO)

- **Estado:** sin implementar. `responder` conserva el mensaje informativo que antes vivía inline en `app.py`: `"El módulo de historial clínico está en desarrollo. ¿Puedo ayudarte con algo más?"`, permaneciendo en `historial`.
- **TODO:** definir el flujo de negocio (fuente de datos del expediente, prompt del sistema y transiciones) antes de implementarlo.

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
  - Convierte cualquier URL de la respuesta en un enlace con texto `Ver Producto` (`target="_blank"`).
  - Botón de reset con `confirm()` → `POST /api/reset` y limpia el DOM.
  - Bloquea input y botón de envío durante la petición (evita dobles envíos).
  - **Panel de logs:** el botón de terminal abre un panel lateral oscuro que consulta `/api/logs?limit=200` cada 3 s; colorea por nivel (`INFO`/`WARNING`/`ERROR`), muestra hora/módulo/mensaje, auto-scroll configurable y botones **Copiar** (portapapeles con formato `[hora] NIVEL módulo: mensaje`) y **Limpiar** (solo visual). El texto se inserta con `textContent` (sin XSS).
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
| `precio1` | REAL/INTEGER | Precio que el vendedor comunica (clave `precio`). |
| `slug` | TEXT | Construye `https://naturesgreenec.com/producto/{slug}`. |
| `para_que_sirve` | TEXT | Contexto para el vendedor (1 frase en la respuesta). |
| `como_tomar` | TEXT | Contexto interno; el prompt prohíbe mostrarlo. |
| `dosis` | TEXT | Contexto interno; el prompt prohíbe mostrarlo. |
| `via_administracion` | TEXT | Contexto interno. |
| `edad_recomendada` | TEXT | Contexto interno. |
| `contraindicaciones` | TEXT | Contexto interno; el prompt prohíbe mostrarlo. |
| `advertencias` | TEXT | Contexto interno. |
| `recomendaciones` | TEXT | Contexto interno. |
| `stock` | INTEGER | Se transforma en `disponible = (stock > 0)`. |
| `oculto` | INTEGER | Filtro `oculto = 0` (productos visibles). |

> [!NOTE]
> La consulta aplica `LIMIT 1`: SALUS muestra **un solo producto** por búsqueda. El prompt del vendedor, en cambio, está escrito para manejar una lista (lista vacía → mensaje de "no encontrado"), por lo que ampliar el límite no requeriría cambios en el prompt.

### B. Contrato del dict `producto` (salida de `buscar_producto`)

```json
{
  "nombre": "…", "marca": "…", "descripcion": "…", "precio": 0,
  "enlace": "https://naturesgreenec.com/producto/slug",
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
| `historial` | list[dict] | Mensajes en formato OpenAI (`role`/`content`), incluyendo el prompt de sistema. Se **vacía** al cambiar de fase. |
| `_v` | int | Versión del esquema de sesión (`VERSION_SESION`). Si no coincide, la sesión se reinicia a `saludo`. |

> [!NOTE]
> El historial crece dentro de una misma fase; no hay truncado por longitud. El prompt de sistema se reinyecta al reconstruirlo cuando la lista está vacía.

---

## 6. Particularidades y Reglas de Negocio

1. **Clasificación de intenciones conservadora (Fase Atención):** el bot nunca asume que el cliente quiere comprar algo solo por mencionar un síntoma. Mientras la petición no sea explícita, la intención es `pendiente`. Si el bot hace una pregunta, la intención también es `pendiente` (regla estructural). Esto evita transiciones de fase prematuras.
2. **Aislamiento por fase:** al cambiar de fase se descarta el historial anterior. Recepción, Asesoría y Producto usan prompts de sistema distintos; mezclarlos degradaría la calidad de la conversación.
3. **Asesoría con búsqueda inmediata:** cuando el asesor confirma `producto_encontrado`, el propio componente de asesoría llama a `producto.responder(producto_sugerido, [])` sin esperar un mensaje adicional y **concatena** la recomendación + el resultado comercial en una sola burbuja (`respuesta + "\n\n" + resultado`). Si la búsqueda falla, se devuelve solo la recomendación (el error no se filtra al cliente).
4. **Venta directa y minimalista:** el vendedor solo expone nombre, utilidad, precio, disponibilidad y enlace. Dosis, contraindicaciones y advertencias **no** se muestran en el chat (aunque la IA las recibe como contexto), lo que reduce el riesgo de dar indicaciones médicas erróneas.
5. **Rotación de API Keys ante 401/429:** el cliente único `core/groq_cliente.py` recorre `API_KEYS` en orden y espera 2 s entre intentos. El 401 (key inválida o revocada) también dispara el salto a la siguiente key, no solo el 429 (rate limit). Garantiza estabilidad en la capa gratuita de Groq.
6. **Salida JSON estricta:** recepción, asesoría y extracción usan `response_format={"type": "json_object"}` y parsean con `json.loads`. El contrato de cada prompt es parte del código: cambiarlo exige actualizar el parseo en el mismo commit.
7. **Errores siempre en JSON:** los handlers globales de `app.py` impiden que Flask devuelva HTML de error, lo que rompería el `response.json()` del frontend.
8. **Protección de cuota:** el endpoint público `/api/chat` está limitado por IP (30 req/min, 500/día) y los errores internos nunca se muestran al usuario; ambos cambios protegen la cuota gratuita de Groq y evitan filtrar detalles internos.
9. **Logs efímeros y con datos recortados:** el buffer vive en memoria (no se escribe a disco), guarda las últimas `LOGS_BUFFER` entradas y recorta los textos. Las API keys siempre van enmascaradas. El panel `/api/logs` queda abierto (sin token) para pruebas; si el chat se abre a usuarios reales, conviene restringirlo (ver §8).
10. **Fase Producto terminal:** una vez en `producto`, cada mensaje se interpreta como una nueva búsqueda; la única forma de volver al saludo es `POST /api/reset` (botón ↺) o una sesión nueva.
11. **Historial, tratamiento y venta pendientes:** existen como esqueletos en sus carpetas (`historial/`, `tratamiento/`, `venta/`) con `responder` placeholder y TODO; aún no tienen lógica de negocio.
12. **Saludo inicial:** la conversación arranca en `saludo`; el LLM genera un saludo variado y el primer mensaje del cliente solo se usa como contexto (no se clasifica). A partir del siguiente turno, todo pasa por `atencion`.

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
2. Completar: `GROQ_API_KEYS` (una o más keys separadas por coma), `TURSO_URL`, `TURSO_TOKEN` y `SECRET_KEY` (obligatoria; genera una con `python -c "import secrets; print(secrets.token_hex(32))"`). Opcionales: `GROQ_MODEL`, `LOG_LEVEL` y `LOGS_BUFFER`.

> [!TIP]
> **Cómo ver los logs:** abre el botón de terminal (⎡>_⎦) del header → panel en vivo (con botones Copiar y Limpiar). No requiere token ni URL especial.

> [!IMPORTANT]
> `.env` está en `.gitignore`: nunca se sube al repositorio. En **Render**, definir las mismas variables en *Dashboard → Environment*.

| Variable | Requerida | Ejemplo | Descripción |
|----------|-----------|---------|-------------|
| `GROQ_API_KEYS` | Sí | `gsk_abc,gsk_def` | Keys separadas por coma; se rotan ante 401/429. |
| `GROQ_MODEL` | No | `openai/gpt-oss-20b` | Modelo Groq a usar. Si se omite, usa el default. |
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
- Render inyecta las variables de entorno; `load_dotenv()` no encuentra `.env` y no hace nada.
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

**Pendientes:**

1. **Componentes tratamiento, venta e historial sin implementar:** son esqueletos con placeholder y TODO (el historial antes era un inline en `app.py`). Acción sugerida: definir y programar cada flujo de negocio.
2. **`LIMIT 1` en la búsqueda:** el usuario solo ve el primer producto que coincide con el término; si el primero no es el que esperaba, no hay alternativas. Acción sugerida: parametrizar el límite y dejar que el vendedor liste 2-3 opciones.
3. **Historial sin truncado:** en conversaciones largas, `session['historial']` crece sin límite (límite práctico: tamaño de la cookie de sesión, ~4 KB). Acción sugerida: recortar a los últimos N turnos.
4. **Sin pruebas automatizadas ni CI:** no hay tests unitarios de los prompts/parseos ni pipeline de verificación. Acción sugerida: tests de contrato para `atencion.responder`, `asesoria.responder`, `flujo.despachar` y `buscar_producto` con mocks de Groq/Turso.
5. **Fallback 429 sin backoff exponencial:** se espera un `time.sleep(2)` fijo por key. Es aceptable en la capa gratuita, pero un backoff creciente sería más robusto.
6. **Panel de logs abierto:** `/api/logs` no pide credenciales y muestra (recortados) los mensajes de los usuarios. Acción sugerida: protegerlo antes de abrir el chat al público.

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
