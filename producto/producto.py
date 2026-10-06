"""
producto.py — Componente de productos de SALUS.

Responsabilidad: coordinar el flujo completo de búsqueda:
  1. Extraer término, necesidad e intención con contexto (extractor.py)
  2. Consultar la base de datos Turso (database.py)
  3. Generar la respuesta conversacional con IA (vendedor.py)

Mantiene contexto entre turnos: usa los últimos HISTORIAL_TURNOS del historial
de sesión y devuelve el historial actualizado con el intercambio de cada turno.
"""
import asyncio
import logging
import time
from core.config import HISTORIAL_TURNOS
from core.groq_cliente import llamar_groq
from core.logs import recortar
from producto.contexto import formatear_contexto
from producto.extractor import extraer_termino
from producto.database  import buscar_producto
from producto.vendedor   import generar_respuesta_vendedor

logger = logging.getLogger("salus.producto")

PROMPT_REPREGUNTA = """Eres una persona real del equipo de Nature's Green atendiendo el chat. El cliente acaba de escribir algo que no alcanza para identificar un producto.

Conversación reciente:
{contexto}

Pídele de forma natural, cálida y breve (máximo 2 frases) que te diga qué producto busca o qué necesita. No suenes a robot ni repitas siempre la misma pregunta; si el contexto permite intuir de qué venían hablando, retómalo con naturalidad."""

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    NOTA (async): la búsqueda real es la corrutina `ejecutar_busqueda_producto`;
    `responder` la ejecuta con asyncio.run porque el orquestador Flask es síncrono.

    - siguiente_fase: "producto" normalmente; "tratamiento" o "venta" si el
      cliente muestra interés en un tratamiento o en comprar. Al salir de
      "producto" el historial se devuelve vacío (transición estándar).
    - Contexto: usa los últimos HISTORIAL_TURNOS del historial y devuelve el
      historial actualizado para que los siguientes turnos resuelvan
      referencias como "y bueno?" o "y solo tienen ese?".
    """
    contexto = formatear_contexto(historial, HISTORIAL_TURNOS)
    respuesta, siguiente_fase = asyncio.run(ejecutar_busqueda_producto(mensaje_usuario, contexto))

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

    return respuesta, siguiente_fase, historial_actualizado

async def ejecutar_busqueda_producto(mensaje_usuario: str, contexto: str = ""):
    """
    Búsqueda completa de un producto (corrutina).
    Devuelve (respuesta, siguiente_fase).
    """
    inicio = time.perf_counter()
    logger.info("Producto | mensaje=%r | contexto=%r", recortar(mensaje_usuario), recortar(contexto, 120))

    # Paso 1: Extraer término, necesidad e intención (con contexto conversacional)
    datos = extraer_termino(mensaje_usuario, contexto)
    termino = datos["termino"]
    necesidad = datos["necesidad"]
    intencion = datos["intencion"]

    siguiente_fase = intencion if intencion in ("tratamiento", "venta") else "producto"

    # Sin término: repregunta natural generada por el LLM (nada de texto fijo)
    if not termino:
        logger.warning("Producto | sin término (intencion=%s) → repregunta con LLM", intencion)
        respuesta_repregunta = generar_repregunta(mensaje_usuario, contexto)
        logger.info("Producto resuelto | %.0f ms | siguiente=%s | respuesta=%r",
                    (time.perf_counter() - inicio) * 1000, siguiente_fase, recortar(respuesta_repregunta, 200))
        return respuesta_repregunta, siguiente_fase

    # Paso 2: Consultar la base de datos
    resultados_db = await buscar_producto(termino)
    if resultados_db:
        logger.info("Producto | %d resultado(s) en Turso para %r", len(resultados_db), termino)
    else:
        logger.warning("Producto | sin resultados en Turso para %r", termino)

    # Paso 3: Generar la respuesta conversacional con IA
    respuesta_final = generar_respuesta_vendedor(mensaje_usuario, termino, necesidad, resultados_db, contexto)
    logger.info("Producto resuelto | %.0f ms | termino=%r | necesidad=%r | siguiente=%s | respuesta=%r",
                (time.perf_counter() - inicio) * 1000, termino, recortar(necesidad, 80),
                siguiente_fase, recortar(respuesta_final, 200))

    return respuesta_final, siguiente_fase

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
            temperature=0.7,
        )
        texto = (respuesta.choices[0].message.content or "").strip()
        if texto:
            logger.info("Producto | repregunta lista=%r", recortar(texto, 200))
            return texto
        logger.warning("Producto | el modelo devolvió repregunta vacía")
    except Exception as e:
        logger.error("Producto | falló la repregunta: %s", e, exc_info=True)
    return "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos."
