"""
producto.py — Componente de productos de SALUS.

Responsabilidad: coordinar el flujo completo de búsqueda:
  1. Extraer el término clave del mensaje (extractor.py)
  2. Consultar la base de datos Turso (database.py)
  3. Generar la respuesta final orientada a ventas (vendedor.py)
"""
import asyncio
import logging
import time
from producto.extractor import extraer_termino
from producto.database  import buscar_producto
from producto.vendedor   import generar_respuesta_vendedor
from core.logs import recortar

logger = logging.getLogger("salus.producto")

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    NOTA: la búsqueda real es async (`ejecutar_busqueda_producto`); se ejecuta con
    asyncio.run porque el orquestador (Flask) es síncrono.
    Fase terminal: siempre devuelve "producto" y conserva el historial tal cual.
    """
    respuesta = asyncio.run(ejecutar_busqueda_producto(mensaje_usuario))
    return respuesta, "producto", historial

async def ejecutar_busqueda_producto(mensaje_usuario: str) -> str:
    """
    Búsqueda completa de un producto (corrutina).
    Recibe el mensaje del usuario y devuelve la respuesta final como string.
    """
    inicio = time.perf_counter()
    logger.info("Producto | mensaje=%r", recortar(mensaje_usuario))

    # Paso 1: Extraer el término de búsqueda
    termino = extraer_termino(mensaje_usuario)
    if not termino:
        logger.warning("Producto | no se pudo extraer término de búsqueda")
        return "No pude identificar qué producto buscas. ¿Podrías ser más específico?"

    # Paso 2: Consultar la base de datos
    resultados_db = await buscar_producto(termino)
    if resultados_db:
        logger.info("Producto | %d resultado(s) en Turso para %r", len(resultados_db), termino)
    else:
        logger.warning("Producto | sin resultados en Turso para %r", termino)

    # Paso 3: Generar la respuesta con IA
    respuesta_final = generar_respuesta_vendedor(termino, resultados_db)
    logger.info("Producto resuelto | %.0f ms | respuesta=%r",
                (time.perf_counter() - inicio) * 1000, recortar(respuesta_final, 200))

    return respuesta_final
