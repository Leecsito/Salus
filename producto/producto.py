"""
producto.py — Orquestador del módulo de Productos.
Responsabilidad: coordinar el flujo completo de búsqueda:
  1. Extraer el término clave del mensaje (extractor.py)
  2. Consultar la base de datos Turso (database.py)
  3. Generar la respuesta final orientada a ventas (vendedor.py)
"""
from producto.extractor import extraer_termino
from producto.database  import buscar_producto
from producto.vendedor   import generar_respuesta_vendedor

async def ejecutar_busqueda_producto(mensaje_usuario: str) -> str:
    """
    Función principal del módulo de productos.
    Recibe el mensaje del usuario y devuelve la respuesta final como string.
    """
    # Paso 1: Extraer el término de búsqueda
    termino = extraer_termino(mensaje_usuario)
    if not termino:
        return "No pude identificar qué producto buscas. ¿Podrías ser más específico?"

    # Paso 2: Consultar la base de datos
    resultados_db = await buscar_producto(termino)

    # Paso 3: Generar la respuesta con IA
    respuesta_final = generar_respuesta_vendedor(mensaje_usuario, resultados_db)

    return respuesta_final
