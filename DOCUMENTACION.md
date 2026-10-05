# SALUS — Documentación Técnica

**Proyecto:** Chatbot de atención al cliente y ventas para **Nature's Green** (tienda/farmacia naturista)  
**Tipo:** Aplicación web Flask con IA conversacional multi-fase (Recepción → Asesoría → Búsqueda de productos)  
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
| **Servidor de producción** | Gunicorn | `Procfile`: `web: gunicorn app:app` (Render) |
| **IA / LLM** | Llama 3.1 8B Instant (API de **Groq**, SDK `groq`) | Clasificación de intenciones, diálogo de asesoría, extracción del término y generación de respuestas |
| **Base de datos** | **Turso** (SQLite serverless) vía `libsql-client` | Catálogo de productos de Nature's Green |
| **Configuración** | `python-dotenv` + variables de entorno | Credenciales y secretos (única fuente: `config.py`) |
| **Estado de sesión** | Flask `session` (cookie cifrada con `SECRET_KEY`) | Guarda `fase` actual e `historial` de mensajes entre peticiones HTTP |
| **Frontend** | HTML5, CSS3 vanilla, JavaScript (Fetch API) | Interfaz de chat con banner de debug |
| **Hosting** | **Render** (plan gratuito) | Despliegue desde Git con Gunicorn |

Modelo Groq usado en todo el proyecto: `llama-3.1-8b-instant`.

---

## 2. Estructura de Directorios

```
Salus/
│
├── app.py                       # Servidor Flask: rutas, sesiones y máquina de estados de fases
├── main.py                      # Fase Recepción: recepcionista virtual (clasifica intención)
├── config.py                    # Configuración central: único lugar que lee variables de entorno
├── Procfile                     # Instrucción de arranque para Render (gunicorn app:app)
├── requirements.txt             # Dependencias Python del proyecto
├── .env.example                 # Plantilla de variables de entorno para desarrollo local
├── DOCUMENTACION.md             # Documentación técnica central (este archivo)
│
├── asesoria/                    # FASE 2 — Asesor de salud
│   ├── asesoria.py              # Prompt del asesor + orquestación de la conversación
│   ├── groq_cliente.py          # Cliente Groq compartido con fallback de API Keys (429)
│   └── FASE1.py                 # [LEGACY] versión monolítica anterior (NO usada por app.py)
│
├── producto/                    # FASE 3 — Búsqueda y venta de productos
│   ├── producto.py              # Orquestador: extractor → database → vendedor
│   ├── extractor.py             # Extrae el sustantivo clave del mensaje con IA
│   ├── database.py              # Consulta el catálogo de productos en Turso
│   ├── vendedor.py              # Genera la respuesta final de ventas con IA
│   ├── groq_cliente.py          # Cliente Groq compartido con fallback de API Keys (429)
│   └── FASE1.py                 # [LEGACY] versión monolítica anterior (NO usada por app.py)
│
├── templates/
│   └── index.html               # Interfaz web del chat + banner de debug
│
└── static/
    ├── style.css                # Estilos (tema verde, burbujas, animaciones, banner debug)
    └── script.js                # Lógica cliente: Fetch API, indicador de escritura, reset
```

### Convenciones de nombres

| Patrón | Significado |
|--------|-------------|
| `app.py` | Único punto de entrada web y orquestador de fases. No contiene prompts. |
| `main.py` | Módulo de la Fase Recepción (raíz del proyecto). |
| `asesoria/asesoria.py`, `producto/producto.py` | Módulos de fase. Contienen el prompt del sistema y coordinan sus helpers. |
| `producto/<verbo>or.py` (`extractor`, `vendedor`) | Helpers con una única responsabilidad dentro de la fase. |
| `*/groq_cliente.py` | Cliente HTTP de Groq con fallback automático de API Keys. Duplicado por paquete (ver §8). |
| `*/FASE1.py` | **Legacy.** Versiones monolíticas previas a la refactorización modular. No las importa `app.py`. |

---

## 3. Arquitectura del Sistema

### A. Máquina de estados de fases (`session['fase']`)

El estado de la conversación vive en la **sesión de Flask**, lo que permite que cada petición HTTP sea independiente (el servidor no guarda estado en memoria, requisito para Gunicorn/Render).

```
                    ┌─────────────────────────────────────┐
                    │        session['fase']              │
                    │  (recepcion por defecto al inicio)  │
                    └──────────────────┬──────────────────┘
                                       │
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼               ▼              │
   ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌───────────┐         │
   │recepcion │  │ asesoria  │  │  producto  │  │ historial │         │
   │ main.py  │  │asesoria.py│  │producto.py │  │ placeholder│         │
   │          │  │           │  │extractor→  │  │ en app.py │         │
   │ clasifica│  │ indaga y  │  │database→   │  │(pendiente)│         │
   │ intención│  │ recomienda│  │vendedor    │  │           │         │
   └────┬─────┘  └─────┬─────┘  └────────────┘  └───────────┘         │
        │              │                                               │
        │ intención ∈  │ estado ==                                     │
        │ {producto,   │ "producto_encontrado"                         │
        │  asesoria,   │                                               │
        │  historial}  │                                               │
        ▼              ▼                                               │
   cambia fase +  cambia fase + ejecuta búsqueda      POST /api/reset  │
   limpia historial  y concatena resultado            session.clear()──┘
```

### B. Flujo de una petición `POST /api/chat`

1. **Validación:** `app.py` exige JSON con el campo `mensaje` no vacío (400 si falla).
2. **Inicialización:** si no existe `session['fase']`, se inicializa en `recepcion` con `historial = []`.
3. **Despacho por fase:**
   - `recepcion` → `main.responder_recepcion(mensaje, historial)` devuelve `(respuesta, intencion, historial)`. Si la intención deja de ser `pendiente`/`error`, se guarda como nueva fase y **se vacía el historial** (cada fase arranca con su propio prompt de sistema).
   - `asesoria` → `asesoria.responder_asesoria(mensaje, historial)` devuelve `(respuesta, estado, producto_sugerido, historial)`. Si `estado == "producto_encontrado"`, se cambia a fase `producto`, se ejecuta la búsqueda de inmediato con `asyncio.run(...)` y el resultado se concatena a la respuesta de asesoría.
   - `producto` → cada mensaje del usuario dispara una nueva búsqueda (`asyncio.run(ejecutar_busqueda_producto(mensaje))`); esta fase no usa historial ni vuelve a recepción.
   - `historial` → placeholder inline en `app.py` (el módulo de expediente clínico aún no existe).
4. **Respuesta:** JSON `{ "respuesta", "fase", "debug": { "fase", "modulo", "carpeta" } }`. El banner de debug del frontend se alimenta de `debug`.
5. **Errores:** cualquier excepción se captura y se devuelve como JSON (nunca HTML), evitando que el frontend falle al parsear.

### C. Tabla de transiciones

| Fase actual | Condición de salida | Nueva fase | Efecto adicional |
|-------------|---------------------|-----------|------------------|
| `recepcion` | `intencion ∈ {producto, asesoria, historial}` | la intención | `historial = []` |
| `recepcion` | `intencion ∈ {pendiente, error}` | `recepcion` | se conserva el historial |
| `asesoria` | `estado == "producto_encontrado"` | `producto` | `historial = []`; se ejecuta la búsqueda y se concatena al mensaje |
| `asesoria` | `estado ∈ {consultando, error}` | `asesoria` | se conserva el historial |
| `producto` | cada mensaje | `producto` | nueva búsqueda independiente (sin historial) |
| `historial` | cada mensaje | `historial` | mensaje informativo; sin módulo real aún |
| cualquiera | `POST /api/reset` | `recepcion` | `session.clear()` |
| fase desconocida | siguiente petición | `recepcion` | `session.clear()` defensivo |

---

## 4. Módulos en Detalle

### [Raíz] `config.py` — Configuración central

- **Propósito:** ÚNICO lugar del proyecto que lee variables de entorno. Todos los módulos hacen `from config import ...`.
- **Carga:** `load_dotenv()` para desarrollo local (en Render las variables se inyectan directo; `.env` no existe).
- **Variables exportadas:**

| Variable | Origen | Descripción |
|----------|--------|-------------|
| `API_KEYS` | `GROQ_API_KEYS` | Lista de keys de Groq separadas por coma (`"key1,key2,key3"`). Habilita el fallback ante HTTP 429. |
| `TURSO_URL` | `TURSO_URL` | URL de la base de datos Turso. |
| `TURSO_TOKEN` | `TURSO_TOKEN` | Token de autenticación de Turso. |
| `SECRET_KEY` | `SECRET_KEY` | Clave de firma de la cookie de sesión (default inseguro `cambia-esto-en-produccion`). |

- **`validar_config()`:** lanza `EnvironmentError` con el detalle de las variables faltantes. **Actualmente nadie la invoca** (ver §8, deuda técnica).

### [Fase 1] `main.py` — Recepcionista virtual

- **Propósito:** Primer contacto. Conversa con empatía y clasifica la necesidad del cliente.
- **Función principal:** `responder_recepcion(mensaje_usuario, historial) → (respuesta_ia, intencion, historial_actualizado)`.
- **Prompt (`PROMPT_SISTEMA_RECEPCION`):** recepcionista cálido, respuestas de máximo 1-2 frases. Define las 3 rutas + estados:
  - `"pendiente"` — aún no hay petición explícita (saludos, síntomas narrados, temas ajenos, "no sé qué hacer").
  - `"producto"` — el cliente nombra un producto/marca/compuesto exacto.
  - `"asesoria"` — pide recomendación para un síntoma, sin saber qué producto comprar.
  - `"historial"` — pide explícitamente abrir/gestionar su expediente clínico.
- **Regla estructural clave:** si la respuesta del bot contiene una pregunta, la intención DEBE ser `pendiente`. Nunca se asume la intención por mencionar un síntoma.
- **Salida del modelo:** JSON estricto (`response_format={"type": "json_object"}`), `temperature=0.3`.
- **Fallback de keys:** itera `API_KEYS`; ante `APIError` 429 espera 2 s y prueba la siguiente. Si todas fallan devuelve `("Error de API: ...", "error", historial)` (la sesión no cambia de fase).

### [Fase 2] `asesoria/asesoria.py` — Asesor de salud

- **Propósito:** Indagar síntomas y recomendar un **tipo genérico de producto** (p. ej. "pomada", "colágeno", "jarabe").
- **Función principal:** `responder_asesoria(mensaje_usuario, historial) → (respuesta_ia, estado, producto_sugerido, historial_actualizado)`.
- **Estados:** `"consultando"` (sigue indagando), `"producto_encontrado"` (ya recomendó y entrega el sustantivo clave para la BD), `"error"`.
- **Prompt (`PROMPT_SISTEMA`):** preguntas amables de máximo 2 oraciones; al tener claro el diagnóstico comunica la recomendación y avisa que revisará stock. Salida JSON estricta, `temperature=0.3`.
- **Delegación:** todas las llamadas al LLM pasan por `asesoria/groq_cliente.py`.

### [Helper] `asesoria/groq_cliente.py` — Cliente Groq con fallback

- **Propósito:** Centralizar la llamada a Groq y el manejo de rate limits para el paquete `asesoria`.
- **Función:** `llamar_groq(messages, model="llama-3.1-8b-instant", temperature=0.3, response_format=None)`.
- **Comportamiento:** recorre `API_KEYS` en orden; con `APIError` 429 y keys restantes espera 2 s y reintenta con la siguiente. Si todas fallan, **relanza** la excepción (el módulo de fase la captura y devuelve estado `error`).

### [Fase 3] `producto/producto.py` — Orquestador de productos

- **Propósito:** Coordinar el flujo completo de búsqueda de un producto.
- **Función principal:** `async ejecutar_busqueda_producto(mensaje_usuario) → str`.
- **Pasos:**
  1. `extraer_termino(mensaje)` (`extractor.py`). Si no hay término → mensaje pidiendo más precisión.
  2. `await buscar_producto(termino)` (`database.py`) contra Turso.
  3. `generar_respuesta_vendedor(mensaje, resultados)` (`vendedor.py`).
- **Ejecución:** es `async`; `app.py` la invoca con `asyncio.run(...)` en cada petición (el worker WSGI es síncrono).

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

### [Helper] `producto/groq_cliente.py` — Cliente Groq del paquete producto

- Idéntico a `asesoria/groq_cliente.py` salvo que su `temperature` por defecto es `0` (la fase producto es factual, no conversacional). Misma estrategia de fallback 429 y de relanzar la excepción si todas las keys fallan.

### [Servidor] `app.py` — Aplicación Flask

- **Propósito:** Punto de entrada web, máquina de estados por sesión y serialización JSON.
- **`FASE_INFO`:** mapa fase → `{carpeta, modulo}` usado por el banner de debug. La fase `producto` reporta la cadena `producto/producto.py → extractor.py → database.py → vendedor.py`; `historial` apunta a un módulo inexistente (deuda §8).
- **Rutas:**

| Método y ruta | Descripción |
|---------------|-------------|
| `GET /` | Inicializa la sesión si está vacía y renderiza `templates/index.html`. |
| `POST /api/chat` | Recibe `{"mensaje": "..."}`, despacha según `session['fase']` y devuelve la respuesta + `debug`. |
| `POST /api/reset` | `session.clear()`; devuelve `{"status": "ok"}`. |

- **Sesión:** `app.secret_key = os.environ.get("SECRET_KEY", "natures-green-secret-2026")`. **No** importa `config.SECRET_KEY` (default distinto al de `config.py`; ver §8).
- **Handlers globales (`@app.errorhandler`):** `404`, `500` y `Exception` genérico devuelven siempre JSON con clave `respuesta`. El handler genérico imprime el traceback en consola con el prefijo `[EXCEPCIÓN NO MANEJADA]`.
- **Timing del cambio de fase:** en asesoría, `session['fase'] = 'producto'` se fija **antes** de ejecutar la búsqueda; así el siguiente mensaje del usuario ya entra directo a la fase producto aunque la búsqueda falle.

### [Frontend] `templates/index.html` + `static/`

- **`index.html`:** layout de chat (header con marca SALUS, botón de reset, mensajes, formulario de entrada) y **banner de debug** fijo arriba con `Fase`, `Módulo` y `Carpeta` (ids `debug-fase`, `debug-modulo`, `debug-carpeta`). Carga la fuente Outfit de Google Fonts.
- **`script.js`:**
  - Envía el mensaje con `fetch('/api/chat')` y renderiza la respuesta del bot.
  - Indicador de escritura animado (3 puntos) mientras espera.
  - Convierte cualquier URL de la respuesta en un enlace con texto `Ver Producto` (`target="_blank"`).
  - Actualiza el banner de debug con `data.debug` de cada respuesta.
  - Botón de reset con `confirm()` → `POST /api/reset` y limpia el DOM.
  - Bloquea input y botón de envío durante la petición (evita dobles envíos).
- **`style.css`:** tema verde (`--primary: #10b981`), variables CSS en `:root`, glassmorphism suave (`rgba` + blur), animaciones `fadeIn` / `pulse` / `typing`, burbujas diferenciadas para usuario/bot/sistema, estilos del banner de debug y scrollbar personalizada.

### [Legacy] `asesoria/FASE1.py` y `producto/FASE1.py`

- Versiones **monolíticas** previas a la refactorización. Incluyen su propio cliente Groq (`llamar_groq_completions`) y toda la lógica en un solo archivo.
- **No son importadas por `app.py`** (este importa `asesoria.asesoria` y `producto.producto`). Se conservan como respaldo.
- `producto/FASE1.py` incluye un menú de prueba por consola (`python producto/FASE1.py`, escribe `salir` para terminar) con la lógica original de `ejecutar_fase_2`.
- **Recomendación:** eliminarlas o moverlas a una carpeta `legacy/` para evitar confusión (ver §8).

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
  "fase": "recepcion | asesoria | producto | historial",
  "debug": {
    "fase": "producto",
    "modulo": "producto/producto.py → extractor.py → database.py → vendedor.py",
    "carpeta": "producto/"
  }
}
```

> [!WARNING]
> La rama `historial` y la rama defensiva `else` de `app.py` **no incluyen** la clave `debug`, a diferencia del helper `ok()` usado por el resto de fases. El frontend tolera su ausencia (`if (!debug) return;`), pero es una inconsistencia conocida (ver §8).

### D. Estado de sesión (`session`)

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `fase` | str | Fase activa: `recepcion` (default), `asesoria`, `producto` o `historial`. |
| `historial` | list[dict] | Mensajes en formato OpenAI (`role`/`content`), incluyendo el prompt de sistema. Se **vacía** al cambiar de fase. |

> [!NOTE]
> El historial crece dentro de una misma fase; no hay truncado por longitud. El prompt de sistema se reinyecta al reconstruirlo cuando la lista está vacía.

---

## 6. Particularidades y Reglas de Negocio

1. **Clasificación de intenciones conservadora (Fase Recepción):** el bot nunca asume que el cliente quiere comprar algo solo por mencionar un síntoma. Mientras la petición no sea explícita, la intención es `pendiente`. Si el bot hace una pregunta, la intención también es `pendiente` (regla estructural). Esto evita transiciones de fase prematuras.
2. **Aislamiento por fase:** al cambiar de fase se descarta el historial anterior. Recepción, Asesoría y Producto usan prompts de sistema distintos; mezclarlos degradaría la calidad de la conversación.
3. **Asesoría con búsqueda inmediata:** cuando el asesor confirma `producto_encontrado`, SALUS ejecuta la búsqueda sin esperar un mensaje adicional y **concatena** la recomendación + el resultado comercial en una sola burbuja (`respuesta_ia + "\n\n" + resultado`). Si la búsqueda falla, se devuelve solo la recomendación (el error no se filtra al cliente).
4. **Venta directa y minimalista:** el vendedor solo expone nombre, utilidad, precio, disponibilidad y enlace. Dosis, contraindicaciones y advertencias **no** se muestran en el chat (aunque la IA las recibe como contexto), lo que reduce el riesgo de dar indicaciones médicas erróneas.
5. **Rotación de API Keys ante rate limit (429):** los tres clientes (`main.py`, `asesoria/groq_cliente.py`, `producto/groq_cliente.py`) recorren `API_KEYS` en orden y esperan 2 s entre intentos. Garantiza estabilidad en la capa gratuita de Groq.
6. **Salida JSON estricta:** recepción, asesoría y extracción usan `response_format={"type": "json_object"}` y parsean con `json.loads`. El contrato de cada prompt es parte del código: cambiarlo exige actualizar el parseo en el mismo commit.
7. **Errores siempre en JSON:** los handlers globales de `app.py` impiden que Flask devuelva HTML de error, lo que rompería el `response.json()` del frontend.
8. **Debug Banner en fase de pruebas:** cada respuesta informa fase, módulo y carpeta activos. Es información de desarrollo; al retirarlo debe eliminarse también `FASE_INFO` en `app.py` y el bloque HTML asociado.
9. **Fase Producto terminal:** una vez en `producto`, cada mensaje se interpreta como una nueva búsqueda; la única forma de volver a recepción es `POST /api/reset` (botón ↺) o una sesión nueva.
10. **Fase Historial pendiente:** responde con un mensaje informativo desde `app.py`. No existe carpeta `historial/` ni módulo `historial.py` todavía.

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
2. Completar: `GROQ_API_KEYS` (una o más keys separadas por coma), `TURSO_URL`, `TURSO_TOKEN` y `SECRET_KEY`.

> [!IMPORTANT]
> `.env` está en `.gitignore`: nunca se sube al repositorio. En **Render**, definir las mismas variables en *Dashboard → Environment*.

| Variable | Requerida | Ejemplo | Descripción |
|----------|-----------|---------|-------------|
| `GROQ_API_KEYS` | Sí | `gsk_abc,gsk_def` | Keys separadas por coma; se rotan ante 429. |
| `TURSO_URL` | Sí | `https://tu-db.turso.io` | URL de la base Turso. |
| `TURSO_TOKEN` | Sí | `eyJhbGci…` | Token de Turso. |
| `SECRET_KEY` | Recomendada | `frase-larga-y-secreta` | Firma de la cookie de sesión. Sin ella se usa un default inseguro. |

### C. Ejecución local

```bash
python app.py
# → http://127.0.0.1:5000  (debug=True)
```

### D. Ejecución en producción (Render)

- El `Procfile` ya define el comando: `web: gunicorn app:app`.
- Render inyecta las variables de entorno; `load_dotenv()` no encuentra `.env` y no hace nada.
- El plan gratuito puede **dormir** la instancia: la primera petición tras inactividad tarda unos segundos.
- **Despliegue automático:** el servicio de Render está conectado al repositorio GitHub (`Leecsito/Salus`). Con *Auto-Deploy* en **On Commit** (Dashboard → servicio → Settings → Build & Deploy), cada `git push` a la rama `main` dispara un redespliegue: **no hace falta ningún archivo adicional ni desplegar a mano**.

### E. Prueba de la API con `curl`

La conversación depende de la cookie de sesión; usar un cookie jar:

```bash
# Turno 1 — recepción
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

### F. Prueba aislada del módulo de productos (legacy)

```bash
python producto/FASE1.py
# Menú interactivo de consola; escribe 'salir' para terminar.
```

---

## 8. Deuda Técnica y Buenas Prácticas

1. **Módulos legacy duplicados:** `asesoria/FASE1.py` y `producto/FASE1.py` replican la lógica ya refactorizada y pueden confundir a futuros desarrolladores (¿cuál es la versión vigente?). Acción sugerida: eliminarlos o moverlos a `legacy/` conservando únicamente el menú de prueba si se desea.
2. **`groq_cliente.py` duplicado:** el mismo cliente con fallback existe en `asesoria/` y `producto/` (solo cambia el `temperature` por defecto). Acción sugerida: un único `groq_cliente.py` en la raíz.
3. **`validar_config()` sin uso:** `config.py` define la validación de variables críticas, pero nadie la llama al arrancar. Si faltan credenciales, el error aparece recién en la primera petición. Acción sugerida: invocarla en `app.py` (solo en el proceso servidor, nunca en el import de módulos de test).
4. **`SECRET_KEY` duplicada y desincronizada:** `app.py` lee `os.environ.get("SECRET_KEY", "natures-green-secret-2026")` con un default distinto al de `config.py` (`"cambia-esto-en-produccion"`). Acción sugerida: `from config import SECRET_KEY` en `app.py`.
5. **Rama `historial` incompleta:** no existe el módulo prometido por `FASE_INFO` (`historial/historial.py`). Además, sus respuestas no incluyen la clave `debug`, a diferencia del helper `ok()`. Acción sugerida: implementar el módulo o unificar el formato de respuesta.
6. **`LIMIT 1` en la búsqueda:** el usuario solo ve el primer producto que coincide con el término; si el primero no es el que esperaba, no hay alternativas. Acción sugerida: parametrizar el límite y dejar que el vendedor liste 2-3 opciones.
7. **Historial sin truncado:** en conversaciones largas, `session['historial']` crece sin límite (límite práctico: tamaño de la cookie de sesión, ~4 KB). Acción sugerida: recortar a los últimos N turnos.
8. **Sin pruebas automatizadas ni CI:** no hay tests unitarios de los prompts/parseos ni pipeline de verificación. Acción sugerida: tests de contrato para `responder_recepcion`, `responder_asesoria` y `buscar_producto` con mocks de Groq/Turso.
9. **Fallback 429 sin backoff exponencial:** se espera un `time.sleep(2)` fijo por key. Es aceptable en la capa gratuita, pero un backoff creciente sería más robusto.

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
