"""
database.py — Consulta a la base de datos Turso.
Responsabilidad: conectarse a Turso (SQLite serverless) y buscar productos
por nombre o descripción. Devuelve una lista de diccionarios con los datos.
"""
import logging
import os
import sys
import libsql_client

# Importa las credenciales desde el módulo central de configuración
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import TURSO_URL, TURSO_TOKEN
from logs import recortar

logger = logging.getLogger("salus.turso")

CONSULTA_SQL = """
SELECT nombre_producto, marca, descripcion, precio1, slug,
       para_que_sirve, como_tomar, dosis, via_administracion,
       edad_recomendada, contraindicaciones, advertencias, recomendaciones,
       (stock > 0) AS disponible
FROM productos
WHERE (nombre_producto LIKE ? OR descripcion LIKE ?) AND oculto = 0
LIMIT 1
"""

async def buscar_producto(termino: str) -> list:
    """
    Consulta Turso con el término dado.
    Devuelve lista de dicts con los campos del producto, o lista vacía si no hay resultados.
    """
    termino_sql = f"%{termino}%"
    logger.info("Turso → consulta productos LIKE %r", recortar(termino, 80))
    async with libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN) as db:
        resultado = await db.execute(CONSULTA_SQL, [termino_sql, termino_sql])

        productos = []
        for fila in resultado.rows:
            slug = fila[4]
            productos.append({
                "nombre":            fila[0],
                "marca":             fila[1],
                "descripcion":       fila[2],
                "precio":            fila[3],
                "enlace":            f"https://naturesgreenec.com/producto/{slug}" if slug else None,
                "para_que_sirve":    fila[5],
                "como_tomar":        fila[6],
                "dosis":             fila[7],
                "via_administracion":fila[8],
                "edad_recomendada":  fila[9],
                "contraindicaciones":fila[10],
                "advertencias":      fila[11],
                "recomendaciones":   fila[12],
                "disponible":        bool(fila[13]),
            })
        logger.info("Turso ← %d fila(s)", len(productos))
        return productos
