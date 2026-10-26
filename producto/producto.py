"""
producto.py — Componente de productos de SALUS.

Responsabilidad: coordinar el flujo completo de búsqueda:
  1. Extraer término, necesidad, intención y si requiere web (extractor.py)
  2. Consultar la base de datos Turso (database.py)
  2b. Si la DB no alcanza (dato puntual o 0 resultados), buscar en web (buscador.py)
  3. Generar la respuesta conversacional con IA (vendedor.py)

Mantiene contexto entre turnos: usa los últimos HISTORIAL_TURNOS del historial
de sesión y devuelve el historial actualizado con el intercambio de cada turno.
Guarda además un mensaje system interno (marcador `__salus_estado__`) con el
último término/necesidad resueltos: si el extractor falla (p. ej. cuota diaria
agotada), se reutiliza ese término en vez de repreguntar.
"""
import asyncio
import json
import logging
import time
import unicodedata
from core.config import HISTORIAL_TURNOS, TAVILY_API_KEY
from core.groq_cliente import llamar_groq, es_limite_diario
from core.logs import recortar
from producto.contexto import formatear_contexto
from producto.extractor import extraer_termino
from producto.database  import buscar_producto, menciona_producto
from producto.buscador  import buscar_en_web
from producto.vendedor   import generar_respuesta_vendedor

logger = logging.getLogger("salus.producto")

PROMPT_REPREGUNTA = """Eres una persona real del equipo de Nature's Green atendiendo el chat. El cliente acaba de escribir algo, pero no se pudo identificar un producto concreto para buscar en el catálogo.

Conversación reciente:
{contexto}

Responde de forma natural, cálida y breve (máximo 2 frases). Reglas:
- NO nombres ni recomiendes productos, marcas, opciones, precios ni propiedades, y no inventes información: en este turno no tienes los datos del catálogo y no puedes confirmar nada. Si te apoyas en la conversación reciente, usa solo lo que aparece LITERALMENTE en ella, sin añadir variantes, ingredientes ni atributos que no estén escritos ahí.
- Si el mensaje es un saludo o charla de cortesía ("hola", "gracias"), devuélvelo con calidez y no ofrezcas productos: pregunta si desea continuar con lo que estaba viendo o en qué puedes ayudar.
- Si en la conversación reciente ya se habló de un producto o categoría y el cliente quiere seguir, NO le preguntes qué producto busca: retoma el tema sin listar opciones (p. ej. "¿cuál de las opciones que viste te llama más la atención?" o pregúntale el dato concreto que necesita).
- Si falta el dato para poder buscar, pídelo (producto, tipo, marca o presentación) en una sola pregunta.
- No suenes a robot ni repitas siempre la misma pregunta."""

# Regla de negocio: todo tratamiento pasa primero por el historial clínico.
TRANSICION_HISTORIAL = ("Claro, para recomendarte un tratamiento primero necesito revisar tus "
                        "antecedentes de salud. Empecemos por tu historial clínico.")

# Estado interno en el historial (mensaje system, ignorado por formatear_contexto):
# guarda el último término/necesidad resueltos para el fallback del extractor.
_MARCADOR_ESTADO = "__salus_estado__"

MENSAJE_SIN_CUOTA = ("Estoy teniendo un problema técnico para procesar tu consulta. "
                     "Intenta de nuevo en unos minutos.")

# Palabras que marcan un dato puntual (dispara el respaldo web cuando el
# extractor falla y no pudo marcar `requiere_web`).
_PALABRAS_DATO_PUNTUAL = ("como se toma", "cómo se toma", "dosis", "cuantas", "cuántas",
                          "a que hora", "a qué hora", "antes de", "unidades", "capsulas",
                          "cápsulas", "tabletas", "sachets", "sobres", "efervescente",
                          "ingredientes", "sabor", "miligramos", "mg")

# Frases de seguimiento sobre el producto en curso: si el mensaje no menciona
# otro producto del catálogo (chequeo local `menciona_producto`), se resuelve
# con el estado previo y se omite el extractor (ahorro de ~1.8k tokens/turno).
_PATRONES_SEGUIMIENTO = (
    "como se toma", "como debo tomar", "como lo tomo", "como tomarlo", "como se consume",
    "a que hora", "cada cuanto", "cuantas capsulas", "cuantas al dia", "cuantas tomas",
    "es efervescente", "son efervescentes", "se traga", "se disuelve", "en polvo",
    "antes o despues", "con o sin comida", "en ayunas", "con una comida",
    "contraindicaciones", "advertencias", "efectos secundarios",
    "para que sirve", "sirve para",
    "cuanto cuesta", "el precio", "su precio", "hay descuento",
    "cual me recomienda", "cual me recomiendas", "cual de los dos", "cual me conviene",
    "que diferencia", "diferencia tiene", "es mejor",
    "y bueno", "y ese", "el otro", "ese mismo", "solo tienen ese", "hay mas",
    "tienen otro", "esta disponible", "hay stock", "me tomo", "debo tomarlo",
    "lo tomo", "tomarlo antes", "tomarlo despues",
)

# Nunca se omite el extractor si el mensaje puede pedir tratamiento o compra.
_PALABRAS_NO_SEGUIMIENTO = ("tratamiento", "plan", "protocolo", "comprar", "pagar",
                            "pedido", "carrito", "factura", "receta")

def _normalizar(mensaje: str) -> str:
    """Minúsculas sin tildes, para comparar con los patrones de seguimiento."""
    return "".join(c for c in unicodedata.normalize("NFKD", mensaje.lower())
                   if not unicodedata.combining(c))

def _es_seguimiento(mensaje: str) -> bool:
    """True si el mensaje es un seguimiento claro sobre el producto en curso."""
    plano = _normalizar(mensaje)
    if any(p in plano for p in _PALABRAS_NO_SEGUIMIENTO):
        return False
    return any(p in plano for p in _PATRONES_SEGUIMIENTO)

def consulta_web(termino: str, necesidad: str, mensaje_usuario: str) -> str:
    """
    Consulta para Tavily: término + necesidad + pregunta del cliente. La pregunta
    aporta el contexto del dato buscado (p. ej. "efervescente"); el filtro de
    producto exacto del buscador sigue usando solo el término.
    """
    return " ".join(p for p in (termino, necesidad, mensaje_usuario) if p).strip()

def _leer_estado(historial: list) -> dict:
    """Devuelve el último estado interno guardado ({} si no hay)."""
    for m in reversed(historial):
        contenido = m.get("content", "") or ""
        if m.get("role") == "system" and contenido.startswith(_MARCADOR_ESTADO):
            try:
                return json.loads(contenido[len(_MARCADOR_ESTADO):])
            except ValueError:
                return {}
    return {}

def _guardar_estado(historial: list, termino: str, necesidad: str) -> list:
    """Reemplaza el estado interno (un único mensaje system al final)."""
    limpio = [m for m in historial
              if not (m.get("role") == "system"
                      and (m.get("content") or "").startswith(_MARCADOR_ESTADO))]
    limpio.append({"role": "system",
                   "content": _MARCADOR_ESTADO + json.dumps(
                       {"termino": termino, "necesidad": necesidad}, ensure_ascii=False)})
    return limpio

def _parece_dato_puntual(mensaje: str) -> bool:
    """Detección local barata de preguntas de dato puntual (fallback del extractor)."""
    texto = mensaje.lower()
    return any(p in texto for p in _PALABRAS_DATO_PUNTUAL)

def _respuesta_sin_llm(termino: str, resultados_db: list, requiere_web: bool) -> str:
    """
    Respaldo determinista si el vendedor no pudo usar el LLM (p. ej. cuota TPD):
    responde con los datos reales del catálogo, sin IA y sin inventar.
    """
    if not resultados_db:
        return (f"No encontré {termino} en el catálogo. "
                "¿Buscas otro producto o te ayudo con algo más?")
    if len(resultados_db) == 1:
        p = resultados_db[0]
        marca = f" de {p['marca']}" if p.get("marca") else ""
        partes = [f"Tenemos {p['nombre']}{marca} a {p['precio']}."]
        if requiere_web and p.get("como_tomar"):
            partes.append(p["como_tomar"])
        if p.get("enlace"):
            partes.append(f"Puedes verlo aquí {p['enlace']}")
        return " ".join(partes)
    lineas = [f"Sí, tenemos {termino} en varias presentaciones:"]
    for p in resultados_db[:4]:
        marca = f" ({p['marca']})" if p.get("marca") else ""
        enlace = f" {p['enlace']}" if p.get("enlace") else ""
        lineas.append(f"{p['nombre']}{marca}: {p['precio']}{enlace}".strip())
    lineas.append("¿Cuál te interesa o para qué lo necesitas?")
    return "\n".join(lineas)

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    NOTA (async): la búsqueda real es la corrutina `ejecutar_busqueda_producto`;
    `responder` la ejecuta con asyncio.run porque el orquestador Flask es síncrono.

    - siguiente_fase: "producto" normalmente; "venta" si el cliente quiere
      comprar, y "historial" si pide un tratamiento (regla de negocio: todo
      tratamiento pasa primero por el historial clínico). Al salir de
      "producto" el historial se devuelve vacío (transición estándar).
    - Contexto: usa los últimos HISTORIAL_TURNOS del historial y devuelve el
      historial actualizado para que los siguientes turnos resuelvan
      referencias como "y bueno?" o "y solo tienen ese?".
    - Estado: si el turno resuelve un término, guarda término/necesidad en el
      mensaje system interno para el fallback del extractor.
    """
    contexto = formatear_contexto(historial, HISTORIAL_TURNOS)
    ultimo = _leer_estado(historial)
    respuesta, siguiente_fase, termino, necesidad = asyncio.run(
        ejecutar_busqueda_producto(mensaje_usuario, contexto, ultimo))

    historial_actualizado = list(historial)
    ya_incluye_mensaje = (
        historial_actualizado
        and historial_actualizado[-1].get("role") == "user"
        and historial_actualizado[-1].get("content") == mensaje_usuario
    )
    if not ya_incluye_mensaje:
        historial_actualizado.append({"role": "user", "content": mensaje_usuario})
    historial_actualizado.append({"role": "assistant", "content": respuesta})

    if siguiente_fase != "producto":
        historial_actualizado = []
    elif termino:
        historial_actualizado = _guardar_estado(historial_actualizado, termino, necesidad)

    return respuesta, siguiente_fase, historial_actualizado

async def ejecutar_busqueda_producto(mensaje_usuario: str, contexto: str = "",
                                     ultimo: dict | None = None):
    """
    Búsqueda completa de un producto (corrutina).
    Devuelve (respuesta, siguiente_fase, termino, necesidad).
    `ultimo` es el estado interno previo (fallback si el extractor falla).
    """
    ultimo = ultimo or {}
    inicio = time.perf_counter()
    logger.info("Producto | mensaje=%r | contexto=%r", recortar(mensaje_usuario), recortar(contexto, 120))

    # Paso 1: Extraer término, necesidad e intención. Si es un seguimiento claro
    # sobre el producto en curso y no menciona otro producto del catálogo, se
    # omite el extractor (LLM) y se usa el estado previo (ahorro de tokens).
    seguimiento = False
    if (ultimo.get("termino") and _es_seguimiento(mensaje_usuario)
            and not await menciona_producto(mensaje_usuario)):
        seguimiento = True
        datos = {}
        termino = ultimo["termino"]
        necesidad = ultimo.get("necesidad", "")
        intencion = "producto"
        requiere_web = _parece_dato_puntual(mensaje_usuario)
        logger.info("Producto | seguimiento detectado → extractor omitido | termino=%r | necesidad=%r | requiere_web=%s",
                    recortar(termino, 80), recortar(necesidad, 80), requiere_web)
    else:
        datos = extraer_termino(mensaje_usuario, contexto)
        termino = datos["termino"]
        necesidad = datos["necesidad"]
        intencion = datos["intencion"]
        requiere_web = datos["requiere_web"]

    # Regla de negocio: un tratamiento nunca se salta a la fase tratamiento
    # desde producto; primero pasa por el historial clínico.
    if intencion == "tratamiento":
        logger.info("Producto | intencion=tratamiento → derivando a historial clínico")
        logger.info("Producto resuelto | %.0f ms | siguiente=historial | respuesta=%r",
                    (time.perf_counter() - inicio) * 1000, recortar(TRANSICION_HISTORIAL, 200))
        return TRANSICION_HISTORIAL, "historial", "", ""

    siguiente_fase = "venta" if intencion == "venta" else "producto"

    # Fallback: el extractor falló (p. ej. cuota diaria) → reutilizar el último
    # término/necesidad de la conversación en vez de perder el turno.
    if not termino and datos.get("fallo") and ultimo.get("termino"):
        termino = ultimo["termino"]
        necesidad = necesidad or ultimo.get("necesidad", "")
        requiere_web = requiere_web or _parece_dato_puntual(mensaje_usuario)
        logger.warning("Producto | extractor falló → reutilizando término=%r | necesidad=%r | requiere_web=%s",
                       recortar(termino, 80), recortar(necesidad, 80), requiere_web)

    # Sin término: repregunta natural generada por el LLM (nada de texto fijo).
    # Si la cuota diaria está agotada no se llama al LLM: respuesta de error.
    if not termino:
        if datos.get("limite_diario"):
            logger.error("Producto | sin término y cuota diaria agotada → respuesta sin LLM")
            return MENSAJE_SIN_CUOTA, "producto", "", ""
        logger.warning("Producto | sin término (intencion=%s) → repregunta con LLM", intencion)
        respuesta_repregunta = generar_repregunta(mensaje_usuario, contexto)
        logger.info("Producto resuelto | %.0f ms | siguiente=producto | respuesta=%r",
                    (time.perf_counter() - inicio) * 1000, recortar(respuesta_repregunta, 200))
        return respuesta_repregunta, "producto", "", ""

    # Paso 2: Consultar la base de datos
    resultados_db = await buscar_producto(termino)
    if resultados_db:
        logger.info("Producto | %d resultado(s) en Turso para %r", len(resultados_db), termino)
    else:
        logger.warning("Producto | sin resultados en Turso para %r", termino)

    # Paso 2b: Respaldo web (Tavily) si la DB no alcanza: el cliente pide un
    # dato puntual (requiere_web) o Turso no devolvió nada para el término.
    resultados_web = []
    if TAVILY_API_KEY and (requiere_web or not resultados_db):
        nombre_db = resultados_db[0]["nombre"] if resultados_db else ""
        resultados_web = buscar_en_web(consulta_web(termino, necesidad, mensaje_usuario), termino, nombre_db)

    # Paso 3: Generar la respuesta conversacional con IA. Si el vendedor no
    # puede usar el LLM (p. ej. cuota diaria agotada), responde un texto
    # determinista con los datos reales: el turno no se pierde y se guarda el
    # estado para el siguiente mensaje.
    try:
        respuesta_final = generar_respuesta_vendedor(mensaje_usuario, termino, necesidad,
                                                     resultados_db, contexto, resultados_web,
                                                     requiere_web=requiere_web)
    except Exception as e:
        if es_limite_diario(e):
            logger.error("Producto | cuota diaria agotada en el vendedor → respuesta determinista sin LLM")
        else:
            logger.error("Producto | falló el vendedor (%s) → respuesta determinista sin LLM", e, exc_info=True)
        respuesta_final = _respuesta_sin_llm(termino, resultados_db, requiere_web)
    logger.info("Producto resuelto | %.0f ms | termino=%r | necesidad=%r | siguiente=%s | respuesta=%r",
                (time.perf_counter() - inicio) * 1000, termino, recortar(necesidad, 80),
                siguiente_fase, recortar(respuesta_final, 200))

    return respuesta_final, siguiente_fase, termino, necesidad

def generar_repregunta(mensaje_usuario: str, contexto: str = "") -> str:
    """
    Genera con el LLM una repregunta natural usando el historial reciente.
    Si el LLM falla, devuelve el mensaje de error genérico del proyecto.
    """
    logger.info("Producto | repregunta | mensaje=%r", recortar(mensaje_usuario))
    try:
        respuesta = llamar_groq(
            messages=[
                {"role": "system", "content": PROMPT_REPREGUNTA.format(contexto=contexto or "(sin contexto previo)")},
                {"role": "user", "content": mensaje_usuario},
            ],
            temperature=0.3,
        )
        texto = (respuesta.choices[0].message.content or "").strip()
        if texto:
            logger.info("Producto | repregunta lista=%r", recortar(texto, 200))
            return texto
        logger.warning("Producto | el modelo devolvió repregunta vacía")
    except Exception as e:
        logger.error("Producto | falló la repregunta: %s", e, exc_info=True)
    return "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos."
