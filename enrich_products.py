"""
enrich_products.py — Limpieza y enriquecimiento de la tabla `productos` (Turso).

Herramienta independiente del chatbot (no forma parte de las fases de `flujo.py`):
recorre la tabla `productos` en orden de `id`, busca cada producto en la web
(Tavily como fuente principal y, si falta la key o Tavily responde 432 de cuota
agotada, `ddgs` —DuckDuckGo gratis, sin API key— como respaldo) y pide a Groq una
ficha estructurada. Solo escribe en Turso cuando la confianza del modelo es
"alta" o "media"; si es "baja", la fila no se toca.

Campos que puede modificar (únicamente estos):
    descripcion, categoria, subcategoria, nombre_producto, marca,
    para_que_sirve, como_tomar, dosis, via_administracion, edad_recomendada,
    contraindicaciones, advertencias, recomendaciones, slug, info_completada

Los campos que Groq devuelve en null NO se escriben (no se borra información
existente); `descripcion` es NOT NULL en Turso y por eso se respeta esa regla.
El `slug` se calcula en el script como `nombre-del-producto-marca` y
`info_completada` se pone en 1 en cada fila actualizada.

Uso:
    python enrich_products.py --reset    # marca TODAS las filas con info_completada = 0 (pasada completa desde cero) y sale
    python enrich_products.py            # procesa solo las pendientes (info_completada = 0), en orden de id
    python enrich_products.py --test     # simulación: 10 pendientes, sin escribir en Turso

Es reanudable: cada fila escrita queda con `info_completada = 1`, así que se
puede parar (Ctrl+C) y volver a ejecutar cuando se quiera — continúa con las
pendientes. Las filas saltadas (`SKIPPED`) quedan en 0 y se reintentan en la
siguiente ejecución.

Variables de entorno (se leen del .env en la raíz del proyecto). Se aceptan
ambos juegos de nombres, priorizando el primero:
    Turso:  TURSO_DATABASE_URL / TURSO_AUTH_TOKEN  (o TURSO_URL / TURSO_TOKEN)
    Groq:   GROQ_API_KEY                           (o la primera de GROQ_API_KEYS)
    Tavily: TAVILY_API_KEY  (opcional; si falta o la cuota da HTTP 432 se usa
             `ddgs`, que busca en DuckDuckGo gratis y sin API key)

El token de Turso debe tener permiso de ESCRITURA: al arrancar el script hace
una comprobación (UPDATE no-op) y, si el servidor la bloquea, aborta antes de
gastar cuota de Tavily/Groq. El `TURSO_TOKEN` del chatbot es de solo lectura:
agrega un token de escritura como `TURSO_AUTH_TOKEN` (el script lo prefiere).

Acceso a Turso: API HTTP v2 (pipeline) con `httpx`. Se descartó `libsql-client`
para este script porque el endpoint legacy `v1/execute` no propaga el error de
escritura bloqueada (lo convierte en un `KeyError: 'result'` sin contexto).

Modelo Groq: se usa `llama-3.1-8b-instant` si la cuenta tiene acceso; si no,
se degrada a `qwen/qwen3.8-27b` (modelo aparte para no gastar la cuota diaria
de los modelos del chatbot).

Rate limiting: sleep(2) entre productos y sleep(1) entre la búsqueda web y Groq
del mismo producto. Ante un 429 de Groq se distingue el tipo: si es TPD (tokens
por día, cuota agotada) la key se bloquea y se rota a la siguiente — las keys
pueden ser de cuentas distintas, cada una con su propia cuota —; si TODAS están
bloqueadas, el run se **pausa solo** (espera al `retry-after` de Groq) y
**reanuda automáticamente** cuando alguna key libera cuota, sin relanzar el
script (tope de 6 h por producto). Si es TPM (por minuto), espera lo que indique
Groq (mínimo 60 s) y reintenta hasta 3 veces. `ddgs` ante rate limit reintenta
hasta 3 veces con esperas crecientes (10/20/30 s). Cada producto deja una línea
en `enrich_log.txt` (mismo directorio).
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx
from ddgs import DDGS
from ddgs.exceptions import RatelimitException, TimeoutException
from dotenv import load_dotenv
from groq import Groq, RateLimitError

# ── Constantes ────────────────────────────────────────────────────────────────
RAIZ_PROYECTO = Path(__file__).resolve().parent
RUTA_LOG = RAIZ_PROYECTO / "enrich_log.txt"

MODELO_GROQ_PREFERIDO = "llama-3.1-8b-instant"
MODELO_GROQ_ALTERNATIVO = "qwen/qwen3.8-27b"
MODELO_GROQ = MODELO_GROQ_PREFERIDO  # se resuelve al arrancar (resolver_modelo)
TEMPERATURA = 0.3
MAX_TOKENS = 3000

URL_TAVILY = "https://api.tavily.com/search"
TAVILY_PROFUNDIDAD = "advanced"
TAVILY_RESULTADOS = 3
TIMEOUT_TAVILY = 15.0
TIMEOUT_TURSO = 30.0
# ddgs: respaldo gratuito y sin API key. Región Ecuador en español para
# priorizar fichas locales; ante rate limit, esperas crecientes.
DDGS_REGION = "ec-es"
DDGS_RESULTADOS = 3
MAX_INTENTOS_DDGS = 3
ESPERA_DDGS_RATE_LIMIT = 10
# Fragmentos de Tavily recortados: alargan el prompt (y el gasto del TPD de Groq)
# sin aportar apenas: dosis/contraindicaciones suelen estar en los primeros párrafos.
MAX_CHARS_FRAGMENTO = 1500

ESPERA_ENTRE_PRODUCTOS = 2
ESPERA_TAVILY_GROQ = 1
MAX_INTENTOS_429 = 3
# Tope de espera automática por producto cuando TODAS las keys agotan TPD
# (el run se pausa solo y reanuda al liberarse cuota; esto evita quedar
# colgado para siempre si algo raro pasa con las keys).
ESPERA_CUOTA_MAXIMA = 6 * 3600
LIMITE_TEST = 10

# Campos que el modelo devuelve en su JSON (sin `confianza`, de control).
CAMPOS_GROQ = (
    "descripcion", "categoria", "subcategoria", "nombre_producto", "marca",
    "para_que_sirve", "como_tomar", "dosis", "via_administracion",
    "edad_recomendada", "contraindicaciones", "advertencias", "recomendaciones",
)

SYSPROMPT_FICHAS = """Eres un asistente que enriquece fichas de productos naturales y suplementos para una base de datos de farmacia natural en Ecuador.
Se te darán resultados de búsqueda web sobre un producto. Tu tarea es extraer información verificada y estructurada.
Responde ÚNICAMENTE con un JSON válido con los campos solicitados, sin texto adicional.
Si un campo no puede determinarse con seguridad desde los resultados, usa null.
Si los resultados no son del producto correcto o son de otra marca diferente, usa null en todos los campos.
NUNCA inventes datos médicos. NUNCA pongas "no reportado por el fabricante" ni frases similares.
NUNCA menciones los resultados de búsqueda ni la ausencia de datos: si un dato no está, se omite en silencio (o null). Está prohibido escribir "no se especifica", "no se detalla en los resultados", "no disponible", "no figura" o similares.
Para contraindicaciones: si el fabricante no las reporta, infiere desde los ingredientes activos del producto basándote en conocimiento farmacológico establecido."""

ESQUEMA_JSON = (
    '{"descripcion": "...", "categoria": "...", "subcategoria": "...", '
    '"nombre_producto": "...", "marca": "...", "para_que_sirve": "...", '
    '"como_tomar": "...", "dosis": "...", "via_administracion": "...", '
    '"edad_recomendada": "...", "contraindicaciones": "...", "advertencias": "...", '
    '"recomendaciones": "...", "confianza": "alta|media|baja"}'
)

REGLAS_FORMATO = """- descripcion: un solo párrafo (máximo ~400 caracteres) útil para la venta y para un asistente virtual. Debe incluir marca, formato/presentación, ingredientes activos, indicaciones principales y registro sanitario si aparece en los resultados. Si el registro sanitario no aparece, simplemente no lo menciones: prohibido escribir comentarios sobre datos ausentes o sobre la búsqueda ("no se especifica", "no detallado en resultados", etc.).
- categoria y subcategoria: en español, Title Case, descriptivas (ej.: "Suplementos", "Salud Ósea y Articular").
- nombre_producto: nombre canónico con formato/tamaño incluido, en Title Case (ej.: "Osteolan Pack 2 Frascos x 60 Cápsulas").
- marca: solo el nombre real de la marca, sin formato, tamaños ni números.
- para_que_sirve: indicaciones clínicas reales, máximo 300 caracteres.
- como_tomar: instrucción concreta con horario y forma si los resultados la describen (ej.: "Tomar 1 cápsula 2 veces al día, en el desayuno y en la cena, con un vaso de agua."). Si los resultados no la describen, usa null: nada de instrucciones genéricas inventadas.
- dosis: solo la dosis exacta del producto según los resultados (ej.: "1 cápsula al día", "2 veces al día, 1 cápsula de cada frasco"). Si no figura, usa null. Nunca pongas dosis genéricas de nutrientes (rangos tipo "310-420 mg"), equivalencias aproximadas ni "ajustar según la concentración".
- via_administracion: vía de administración (ej.: "Oral", "Tópica").
- edad_recomendada: rango de edad o condición (ej.: "Mayores de 18 años").
- contraindicaciones: SIEMPRE llenar este campo. Si el fabricante no las reporta, infierelas desde los ingredientes activos con base farmacológica establecida. Nunca escribas "no reportadas" ni frases similares.
- advertencias: precauciones de uso breves (no superar la dosis, mantener fuera del alcance de niños, conservar en lugar fresco y seco, etc.).
- recomendaciones: recomendaciones de estilo de vida que complementen el producto.
- confianza: "alta" si los resultados confirman el producto exacto y la mayoría de los campos son fiables; "media" si el producto es correcto pero la información es parcial; "baja" si no hay datos fiables.
- Nunca inventes valores: si un dato no puede determinarse, usa null (excepto contraindicaciones, que se infieren cuando el fabricante no las reporta). Nunca escribas frases sobre la ausencia de datos o sobre la búsqueda web."""

# ── Estado global (resuelto en `resolver_entorno`) ───────────────────────────
TURSO_URL = ""
TURSO_TOKEN = ""
TAVILY_API_KEY = ""
TAVILY_AGOTADO = False   # True tras un HTTP 432 de Tavily (cuota/plan agotado)
FUENTES_ENV = {}
CLAVES_GROQ = []        # todas las keys disponibles (GROQ_API_KEY + GROQ_API_KEYS)
CLIENTES_GROQ = {}      # key -> cliente Groq
BLOQUEO_CLAVES = {}     # key -> timestamp hasta el que está bloqueada por TPD (cuota diaria)


# ── Arranque ──────────────────────────────────────────────────────────────────
def _variable_entorno(*nombres):
    """Primer valor no vacío entre los nombres dados; devuelve (valor, nombre)."""
    for nombre in nombres:
        valor = os.environ.get(nombre, "").strip()
        if valor:
            return valor, nombre
    return "", ""


def resolver_entorno():
    """Carga y valida las credenciales; termina con un error claro si faltan."""
    global TURSO_URL, TURSO_TOKEN, TAVILY_API_KEY, CLAVES_GROQ, CLIENTES_GROQ, BLOQUEO_CLAVES
    TURSO_URL, fuente_url = _variable_entorno("TURSO_DATABASE_URL", "TURSO_URL")
    TURSO_URL = TURSO_URL.replace("libsql://", "https://", 1).rstrip("/")
    TURSO_TOKEN, fuente_token = _variable_entorno("TURSO_AUTH_TOKEN", "TURSO_TOKEN")
    TAVILY_API_KEY, fuente_tavily = _variable_entorno("TAVILY_API_KEY")

    claves = []
    unica, _ = _variable_entorno("GROQ_API_KEY")
    if unica:
        claves.append(unica)
    for parte in _variable_entorno("GROQ_API_KEYS")[0].split(","):
        llave = parte.strip()
        if llave and llave not in claves:
            claves.append(llave)
    CLAVES_GROQ = claves
    CLIENTES_GROQ = {llave: Groq(api_key=llave, max_retries=0) for llave in claves}
    BLOQUEO_CLAVES = {}
    FUENTES_ENV.update({"turso_url": fuente_url, "turso_token": fuente_token,
                        "tavily": fuente_tavily,
                        "groq": f"{len(claves)} key(s) (GROQ_API_KEY/GROQ_API_KEYS)"})

    faltantes = []
    if not TURSO_URL:
        faltantes.append("TURSO_DATABASE_URL (o TURSO_URL)")
    if not TURSO_TOKEN:
        faltantes.append("TURSO_AUTH_TOKEN (o TURSO_TOKEN)")
    if not CLAVES_GROQ:
        faltantes.append("GROQ_API_KEY (o GROQ_API_KEYS)")
    if faltantes:
        print("ERROR: faltan variables de entorno:\n  - " + "\n  - ".join(faltantes))
        sys.exit(1)
    if not TAVILY_API_KEY:
        print("AVISO: TAVILY_API_KEY no configurada; la búsqueda web usará ddgs (DuckDuckGo, sin API key).")


def resolver_modelo():
    """Usa el modelo preferido si la cuenta tiene acceso; si no, el alternativo."""
    global MODELO_GROQ
    try:
        disponibles = {modelo.id for modelo in CLIENTES_GROQ[CLAVES_GROQ[0]].models.list().data}
    except Exception as error:
        print(f"AVISO: no pude listar los modelos de Groq ({type(error).__name__}: {error}); uso {MODELO_GROQ_PREFERIDO}")
        return
    if MODELO_GROQ_PREFERIDO in disponibles:
        MODELO_GROQ = MODELO_GROQ_PREFERIDO
    else:
        MODELO_GROQ = MODELO_GROQ_ALTERNATIVO
        print(f"AVISO: {MODELO_GROQ_PREFERIDO} no está disponible en estas keys; uso {MODELO_GROQ}")


# ── Turso (API HTTP v2 con httpx) ─────────────────────────────────────────────
class ErrorTurso(Exception):
    """Error devuelto por Turso: mensaje + código (p. ej. `BLOCKED`)."""

    def __init__(self, mensaje, codigo="UNKNOWN"):
        super().__init__(f"{mensaje} (code={codigo})")
        self.codigo = codigo


def _valor_turso(valor):
    """Convierte un valor del protocolo de Turso a un valor de Python."""
    tipo = (valor or {}).get("type")
    if tipo == "null":
        return None
    if tipo == "text":
        return str(valor.get("value"))
    if tipo == "integer":
        return int(valor.get("value"))
    if tipo == "float":
        return float(valor.get("value"))
    if tipo == "blob":
        return valor.get("base64")
    raise ErrorTurso(f"tipo de valor desconocido: {tipo!r}")


def _ejecutar_sql(sql, argumentos=None):
    """Ejecuta una sentencia en el pipeline v2 de Turso y devuelve su `result`."""
    cuerpo = {"requests": [{"type": "execute", "stmt": {
        "sql": sql,
        "args": [{"type": "integer", "value": str(a)} if isinstance(a, int)
                 else {"type": "text", "value": str(a)} for a in (argumentos or [])],
        "want_rows": True}}]}
    try:
        respuesta = httpx.post(
            f"{TURSO_URL}/v2/pipeline",
            headers={"authorization": f"Bearer {TURSO_TOKEN}"},
            json=cuerpo,
            timeout=TIMEOUT_TURSO,
        )
        respuesta.raise_for_status()
        resultado = (respuesta.json().get("results") or [{}])[0]
    except httpx.HTTPError as error:
        raise ErrorTurso(f"fallo de red contra Turso: {type(error).__name__}: {error}")
    if resultado.get("type") == "error":
        error = resultado.get("error") or {}
        raise ErrorTurso(error.get("message", "error de Turso"), error.get("code", "UNKNOWN"))
    return (resultado.get("response") or {}).get("result") or {}


def obtener_productos():
    """Filas pendientes (info_completada = 0 o NULL) en orden de `id`."""
    resultado = _ejecutar_sql(
        "SELECT id, nombre_producto, marca FROM productos "
        "WHERE IFNULL(info_completada, 0) = 0 ORDER BY id")
    return [{"id": _valor_turso(fila[0]),
             "nombre_producto": _valor_turso(fila[1]),
             "marca": _valor_turso(fila[2])}
            for fila in resultado.get("rows", [])]


def contar_pendientes():
    """Cuántas filas quedan por procesar (info_completada = 0 o NULL)."""
    resultado = _ejecutar_sql("SELECT COUNT(*) FROM productos WHERE IFNULL(info_completada, 0) = 0")
    filas = resultado.get("rows") or [[{"type": "integer", "value": "0"}]]
    return _valor_turso(filas[0][0])


def reiniciar_pendientes():
    """Marca TODAS las filas con info_completada = 0 (pasada completa desde cero)."""
    resultado = _ejecutar_sql("UPDATE productos SET info_completada = 0")
    return resultado.get("affected_row_count", 0)


def actualizar_producto(id_producto, campos):
    """UPDATE solo de los campos dados + info_completada = 1. Devuelve filas afectadas."""
    asignaciones = ", ".join(f"{campo} = ?" for campo in campos)
    sql = f"UPDATE productos SET {asignaciones}, info_completada = 1 WHERE id = ?"
    resultado = _ejecutar_sql(sql, [*campos.values(), id_producto])
    filas = resultado.get("affected_row_count", 0)
    if not filas:
        raise ErrorTurso(f"el UPDATE no afectó ninguna fila (id={id_producto})")
    return filas


def obtener_producto(id_producto):
    """Fila puntual (aunque no esté pendiente), para reprocesar con --id."""
    resultado = _ejecutar_sql(
        "SELECT id, nombre_producto, marca FROM productos WHERE id = ?", [id_producto])
    filas = resultado.get("rows") or []
    if not filas:
        return None
    f = filas[0]
    return {"id": _valor_turso(f[0]), "nombre_producto": _valor_turso(f[1]), "marca": _valor_turso(f[2])}


def verificar_escritura(id_producto, campos):
    """
    Relee la fila y compara los campos escritos (más `info_completada`). Devuelve
    la lista de discrepancias; vacía si la escritura quedó reflejada. Sirve para
    detectar que otro proceso (p. ej. un guardado del panel de administración)
    revirtió la fila inmediatamente después del UPDATE.
    """
    columnas = list(campos.keys()) + ["info_completada"]
    sql = f"SELECT {', '.join(columnas)} FROM productos WHERE id = ?"
    resultado = _ejecutar_sql(sql, [id_producto])
    filas = resultado.get("rows") or []
    if not filas:
        return ["la fila ya no existe"]
    discrepancias = []
    for indice, campo in enumerate(columnas):
        leido = _valor_turso(filas[0][indice])
        esperado = campos.get(campo) if campo != "info_completada" else 1
        if str(leido) != str(esperado):
            discrepancias.append(f"{campo}: esperado={esperado!r} leído={leido!r}")
    return discrepancias


def verificar_permiso_escritura():
    """
    True si el token puede escribir. Usa un UPDATE no-op (`id = -1` no existe:
    no toca ninguna fila) y detecta el bloqueo por token de solo lectura.
    """
    try:
        _ejecutar_sql("UPDATE productos SET info_completada = info_completada WHERE id = -1")
        return True
    except ErrorTurso as error:
        if error.codigo == "BLOCKED" or "forbidden" in str(error).lower():
            return False
        raise


# ── Tavily ────────────────────────────────────────────────────────────────────
def construir_consulta(nombre, marca):
    partes = [nombre, marca, "Ecuador ficha técnica dosis contraindicaciones"]
    return " ".join(parte for parte in partes if parte)


def buscar_tavily(consulta):
    """Devuelve hasta 3 resultados [{"titulo", "url", "contenido"}]; [] si falla.

    Un HTTP 432 (cuota o plan agotado) marca `TAVILY_AGOTADO`: los siguientes
    productos ya no llaman a Tavily y van directo a ddgs.
    """
    global TAVILY_AGOTADO
    if TAVILY_AGOTADO or not TAVILY_API_KEY:
        return []
    try:
        respuesta = httpx.post(
            URL_TAVILY,
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={
                "query": consulta,
                "search_depth": TAVILY_PROFUNDIDAD,
                "max_results": TAVILY_RESULTADOS,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=TIMEOUT_TAVILY,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 432:
            TAVILY_AGOTADO = True
            print("    Tavily: 432 (cuota/plan agotado); el resto del run usará ddgs")
        else:
            print(f"    Tavily: error ({type(error).__name__}: {error}); pruebo ddgs")
        return []
    except Exception as error:
        print(f"    Tavily: error ({type(error).__name__}: {error}); pruebo ddgs")
        return []
    return [{
        "titulo": (fila.get("title") or "").strip(),
        "url": (fila.get("url") or "").strip(),
        "contenido": (fila.get("content") or "").strip()[:MAX_CHARS_FRAGMENTO],
    } for fila in (datos.get("results") or [])[:TAVILY_RESULTADOS]]


def buscar_ddgs(consulta):
    """Respaldo gratuito sin API key (DuckDuckGo/Bing/Google vía `ddgs`); [] si falla."""
    for intento in range(1, MAX_INTENTOS_DDGS + 1):
        try:
            with DDGS() as buscador:
                filas = list(buscador.text(consulta, region=DDGS_REGION,
                                           safesearch="moderate", max_results=DDGS_RESULTADOS))
            return [{
                "titulo": (fila.get("title") or "").strip(),
                "url": (fila.get("href") or "").strip(),
                "contenido": (fila.get("body") or "").strip()[:MAX_CHARS_FRAGMENTO],
            } for fila in filas[:DDGS_RESULTADOS]]
        except (RatelimitException, TimeoutException) as error:
            if intento >= MAX_INTENTOS_DDGS:
                print(f"    ddgs: {type(error).__name__} persistente; sin respaldo web")
                return []
            espera = ESPERA_DDGS_RATE_LIMIT * intento
            print(f"    ddgs: {type(error).__name__} (intento {intento}/{MAX_INTENTOS_DDGS}); espero {espera}s…")
            time.sleep(espera)
        except Exception as error:
            print(f"    ddgs: error ({type(error).__name__}: {error}); sin respaldo web")
            return []
    return []


def buscar_web(consulta):
    """Tavily como fuente principal; ddgs (gratis, sin API key) como respaldo."""
    if not TAVILY_AGOTADO and TAVILY_API_KEY:
        print(f"    Tavily → {consulta!r}")
        resultados = buscar_tavily(consulta)
        if resultados:
            print(f"    Tavily ← {len(resultados)} resultado(s)")
            time.sleep(ESPERA_TAVILY_GROQ)
            return resultados
        print("    Tavily ← 0 resultados; pruebo ddgs (DuckDuckGo, sin API key)…")
    print(f"    ddgs → {consulta!r}")
    resultados = buscar_ddgs(consulta)
    if resultados:
        print(f"    ddgs ← {len(resultados)} resultado(s)")
    else:
        print("    ddgs ← 0 resultados")
    time.sleep(ESPERA_TAVILY_GROQ)
    return resultados


# ── Groq ──────────────────────────────────────────────────────────────────────
def _parsear_json(texto):
    if not texto:
        raise ValueError("respuesta vacía de Groq")
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```[a-zA-Z]*\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)
    datos = json.loads(limpio)
    if not isinstance(datos, dict):
        raise ValueError("la respuesta de Groq no es un objeto JSON")
    return datos


def _pedir_json(clave, mensajes, json_mode):
    parametros = {}
    if json_mode:
        parametros["response_format"] = {"type": "json_object"}
    respuesta = CLIENTES_GROQ[clave].chat.completions.create(
        model=MODELO_GROQ, messages=mensajes, temperature=TEMPERATURA,
        max_tokens=MAX_TOKENS, **parametros)
    return _parsear_json(respuesta.choices[0].message.content)


def _es_429(error):
    return isinstance(error, RateLimitError) or getattr(error, "status_code", None) == 429


def _es_tpd(error):
    """True si el 429 es por tokens/día (cuota diaria agotada, no recuperable ya)."""
    return "tokens per day" in str(error).lower() or "(tpd)" in str(error).lower()


def _retry_after(error):
    """Segundos sugeridos por el servidor (`retry-after`), con mínimo de 60 s."""
    try:
        segundos = int(float(error.response.headers.get("retry-after", "60")))
    except Exception:
        segundos = 60
    return max(segundos, 60)


def claves_libres():
    """Keys no bloqueadas por TPD en este momento."""
    ahora = time.time()
    return [clave for clave in CLAVES_GROQ if BLOQUEO_CLAVES.get(clave, 0) <= ahora]


def esperar_cuota():
    """
    Pausa el run hasta que Groq libere cuota TPD en alguna key (según el
    `retry-after` que devolvió el servidor) y reanuda solo. Duerme en tramos
    cortos para informar el progreso y poder cortar con Ctrl+C. Devuelve los
    segundos esperados; si supera `ESPERA_CUOTA_MAXIMA`, regresa para no quedar
    colgado indefinidamente (el siguiente intento volverá a evaluar).
    """
    total = 0.0
    while not claves_libres():
        desbloqueo = min(BLOQUEO_CLAVES.values())
        espera = max(30.0, desbloqueo - time.time()) + 5.0
        hora = time.strftime("%H:%M:%S", time.localtime(desbloqueo))
        print(f"    Cuota TPD agotada en todas las keys; pauso hasta ~{hora} "
              f"({int(espera)}s) y reanudo solo…")
        restante = espera
        while restante > 0 and not claves_libres():
            tramo = min(restante, 120.0)
            time.sleep(tramo)
            restante -= tramo
            total += tramo
            if restante > 0 and not claves_libres():
                print(f"    … esperando cuota (faltan ~{int(restante)}s)")
        ahora = time.time()
        for clave in list(BLOQUEO_CLAVES):
            if BLOQUEO_CLAVES[clave] <= ahora:
                del BLOQUEO_CLAVES[clave]
        if total >= ESPERA_CUOTA_MAXIMA:
            print(f"    AVISO: espera máxima ({ESPERA_CUOTA_MAXIMA // 3600} h) alcanzada sin cuota; "
                  "se pasa al siguiente producto.")
            return total
    return total


def llamar_groq(mensajes):
    """
    Llama a Groq esperando un JSON, rotando entre todas las keys disponibles.
    Devuelve (datos, "") o (None, razón de fallo). Reglas:
    - 429 por TPD (cuota diaria): la key se bloquea hasta su `retry-after` y se
      pasa a la siguiente; si TODAS están bloqueadas, el run se pausa solo y
      reanuda cuando alguna libere cuota (no se pierde el producto).
    - 429 por TPM (por minuto): espera lo que indique Groq (mínimo 60 s) y
      reintenta, hasta 3 intentos.
    - Otros errores: un único reintento sin `response_format`.
    """
    razon = "Groq: error desconocido"
    intentos_tpm = 0
    while True:
        if not claves_libres():
            esperar_cuota()
            if not claves_libres():
                return None, "Groq TPD: cuota agotada (espera máxima alcanzada)"
        clave = claves_libres()[0]
        try:
            return _pedir_json(clave, mensajes, json_mode=True), ""
        except Exception as error:
            if _es_429(error) and _es_tpd(error):
                BLOQUEO_CLAVES[clave] = time.time() + _retry_after(error)
                razon = f"Groq 429 TPD (key bloqueada, reintento tras ~{_retry_after(error)}s)"
                print(f"    Groq 429 TPD en una key; paso a la siguiente (quedan {len(claves_libres())} libre/s)")
                continue
            if _es_429(error):
                intentos_tpm += 1
                razon = "Groq 429 TPM sin recuperación"
                if intentos_tpm >= MAX_INTENTOS_429:
                    return None, razon
                espera = _retry_after(error)
                print(f"    Groq 429 por minuto (intento {intentos_tpm}/{MAX_INTENTOS_429}); espero {espera}s…")
                time.sleep(espera)
                continue
            razon = f"Groq {type(error).__name__}: {error}"
            try:
                return _pedir_json(clave, mensajes, json_mode=False), ""
            except Exception as reintento:
                return None, f"Groq {type(reintento).__name__}: {reintento}"


def _mensaje_usuario(nombre, marca, resultados):
    lineas = [
        "Producto a enriquecer:",
        f"- nombre_producto actual: {nombre}",
        f"- marca actual: {marca or 'desconocida'}",
        "",
    ]
    if resultados:
        lineas.append("Resultados de búsqueda web:")
        for indice, resultado in enumerate(resultados, 1):
            lineas.append(f"\n[Resultado {indice}] {resultado['titulo']}\n"
                          f"URL: {resultado['url']}\n"
                          f"Contenido: {resultado['contenido']}")
    else:
        lineas.append("No hay resultados de búsqueda web disponibles; completa la ficha "
                      "usando únicamente el nombre y la marca del producto.")
    lineas += ["", "Devuelve exactamente este JSON, sin texto adicional:", ESQUEMA_JSON,
               "", "Reglas de formato obligatorias:", REGLAS_FORMATO]
    return "\n".join(lineas)


def _mensajes(nombre, marca, resultados):
    return [
        {"role": "system", "content": SYSPROMPT_FICHAS},
        {"role": "user", "content": _mensaje_usuario(nombre, marca, resultados)},
    ]


# ── Utilidades de datos ───────────────────────────────────────────────────────
def _texto(valor):
    """Normaliza a texto sin espacios extremos; null/vacío -> None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _todos_null(datos):
    return all(_texto(datos.get(campo)) is None for campo in CAMPOS_GROQ)


def _slug(nombre, marca):
    """`nombre-del-producto-marca`: minúsculas, sin tildes ni caracteres especiales."""
    texto = f"{nombre or ''} {marca or ''}".strip()
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(caracter for caracter in plano if not unicodedata.combining(caracter)).lower()
    return re.sub(r"[^a-z0-9]+", "-", plano).strip("-")


def _construir_campos(datos, producto):
    """Solo campos con valor (no se escribe null encima de datos existentes)."""
    campos = {}
    for campo in CAMPOS_GROQ:
        valor = _texto(datos.get(campo))
        if valor is not None:
            campos[campo] = valor
    nombre_slug = _texto(campos.get("nombre_producto")) or _texto(producto.get("nombre_producto"))
    marca_slug = _texto(campos.get("marca")) or _texto(producto.get("marca"))
    slug = _slug(nombre_slug, marca_slug)
    if slug:
        campos["slug"] = slug
    return campos


# ── Flujo por producto ────────────────────────────────────────────────────────
def procesar_producto(producto, escribir):
    """
    Devuelve (estado, nombre, detalle, fila) donde estado ∈ {OK, SKIPPED, ERROR}
    y `fila` es el JSON que se escribiría (solo en OK).
    """
    nombre = _texto(producto.get("nombre_producto")) or f"(sin nombre, id={producto['id']})"
    marca = _texto(producto.get("marca")) or ""

    consulta = construir_consulta(nombre, marca)
    resultados = buscar_web(consulta)

    if resultados:
        datos, razon = llamar_groq(_mensajes(nombre, marca, resultados))
        if datos is None:
            return "ERROR", nombre, f"razón: {razon}", None
        if _todos_null(datos):
            print("    Groq: resultados irrelevantes (todos los campos null); consulto sin web")
            datos, razon = llamar_groq(_mensajes(nombre, marca, []))
            if datos is None:
                return "ERROR", nombre, f"razón: {razon}", None
    else:
        print("    Sin resultados web; consulto directo a Groq")
        datos, razon = llamar_groq(_mensajes(nombre, marca, []))
        if datos is None:
            return "ERROR", nombre, f"razón: {razon}", None

    if _todos_null(datos):
        return "SKIPPED", nombre, "razón: sin resultados", None
    confianza = (_texto(datos.get("confianza")) or "baja").lower()
    if confianza not in ("alta", "media"):
        return "SKIPPED", nombre, "razón: confianza baja", None

    campos = _construir_campos(datos, producto)
    if escribir:
        actualizar_producto(producto["id"], campos)
        discrepancias = verificar_escritura(producto["id"], campos)
        if discrepancias:
            print(f"    AVISO: la escritura no quedó reflejada: {'; '.join(discrepancias)}")
            return "ERROR", nombre, "razón: la fila fue revertida/mismatch tras escribir", None
    print(f"    Groq ← confianza={confianza} | campos={len(campos)}")
    fila = dict(campos)
    fila["info_completada"] = 1
    return "OK", nombre, f"confianza={confianza}", fila


# ── Log y resumen ─────────────────────────────────────────────────────────────
def escribir_log(estado, id_producto, nombre, detalle):
    linea = f"[{estado}]".ljust(10) + f"id={id_producto} | {nombre} | {detalle}"
    with open(RUTA_LOG, "a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")
    print(linea)


def _argumentos():
    parser = argparse.ArgumentParser(
        description="Limpia y enriquece la tabla `productos` de Turso con Tavily y Groq.")
    parser.add_argument(
        "--test", action="store_true",
        help="Modo simulación: procesa las 10 primeras filas pendientes, imprime lo que se "
             "escribiría y no toca Turso.")
    parser.add_argument(
        "--reset", action="store_true",
        help="Marca TODAS las filas con info_completada = 0 (pasada completa desde cero) y "
             "sale, sin procesar nada. No se combina con --test.")
    parser.add_argument(
        "--id", type=int, metavar="N",
        help="Procesa solo el producto con ese id (aunque ya tenga info_completada = 1), "
             "útil para reprocesar o diagnosticar una fila puntual.")
    return parser.parse_args()


def main():
    argumentos = _argumentos()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if argumentos.reset and argumentos.test:
        print("ERROR: --reset no se combina con --test (el test no escribe y el reset solo reinicia).")
        sys.exit(2)

    load_dotenv(RAIZ_PROYECTO / ".env")
    resolver_entorno()
    resolver_modelo()
    print(f"Credenciales: turso_url={FUENTES_ENV['turso_url']} | turso_token={FUENTES_ENV['turso_token']} "
          f"| tavily={FUENTES_ENV['tavily']} | groq={FUENTES_ENV['groq']} | modelo={MODELO_GROQ}")
    print(f"Base de datos: {TURSO_URL}")

    if not verificar_permiso_escritura():
        print("AVISO: el token de Turso es de SOLO LECTURA (el servidor bloquea las escrituras).")
        if argumentos.reset or not argumentos.test:
            print("ERROR: no se puede escribir en la base; aborto para no gastar cuota de Tavily/Groq.\n"
                  "  Crea un token con permiso de escritura (turso db tokens create <base-de-datos>) y\n"
                  "  agrégalo al .env como TURSO_AUTH_TOKEN (o reemplaza el valor de TURSO_TOKEN).")
            sys.exit(1)
        print("       El modo --test continúa (no escribe en Turso).")

    if argumentos.reset:
        total = reiniciar_pendientes()
        print(f"RESET → {total} fila(s) marcadas con info_completada = 0.")
        print("       Ejecuta de nuevo sin --reset para procesarlas de 0 en 0 "
              "(Ctrl+C para parar y reanudar cuando quieras).")
        return

    if argumentos.id is not None:
        producto = obtener_producto(argumentos.id)
        if producto is None:
            print(f"ERROR: no existe un producto con id={argumentos.id} en {TURSO_URL}.")
            sys.exit(1)
        productos = [producto]
    else:
        productos = obtener_productos()
        if not productos:
            print("No hay productos pendientes: todas las filas tienen info_completada = 1.")
            print("       Usa --reset para marcarlas todas como pendientes y reprocesar desde cero.")
            return
    if argumentos.test:
        productos = productos[:LIMITE_TEST]
    if argumentos.id is not None:
        print(f"PRODUCTO ÚNICO — id={argumentos.id}, "
              + ("sin escribir en Turso" if argumentos.test else "se escribe en Turso"))
    else:
        print("MODO TEST — 10 primeras filas pendientes, sin escribir en Turso" if argumentos.test
              else f"MODO REAL — {len(productos)} pendiente(s) (info_completada = 0), se escribe en Turso")
    print("-" * 70)

    contadores = {"OK": 0, "SKIPPED": 0, "ERROR": 0}
    try:
        for indice, producto in enumerate(productos, 1):
            if not claves_libres():
                esperar_cuota()
            print(f"[{indice}/{len(productos)}] id={producto['id']} | {producto.get('nombre_producto')}")
            try:
                estado, nombre, detalle, fila = procesar_producto(producto, escribir=not argumentos.test)
            except Exception as error:
                estado, nombre = "ERROR", str(producto.get("nombre_producto") or "")
                detalle, fila = f"razón: {type(error).__name__}: {error}", None
            contadores[estado] += 1
            escribir_log(estado, producto["id"], nombre, detalle)
            if fila is not None:
                print(json.dumps(fila, ensure_ascii=False, indent=2))
            if indice < len(productos):
                time.sleep(ESPERA_ENTRE_PRODUCTOS)
    except KeyboardInterrupt:
        print("\nInterrumpido con Ctrl+C: lo ya escrito quedó guardado.")

    print("-" * 70)
    print(f"{'TEST' if argumentos.test else 'RESUMEN'} → OK={contadores['OK']} | "
          f"SKIPPED={contadores['SKIPPED']} | ERROR={contadores['ERROR']} "
          f"(total={len(productos)})")
    try:
        print(f"Pendientes restantes: {contar_pendientes()}")
    except Exception as error:
        print(f"Pendientes restantes: (no se pudo consultar: {type(error).__name__}: {error})")
    print(f"Log: {RUTA_LOG}")


if __name__ == "__main__":
    main()
