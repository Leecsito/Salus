"""
database.py — Consulta a la base de datos Turso.
Responsabilidad: conectarse a Turso (SQLite serverless) y buscar productos
por nombre o descripción. Devuelve una lista de diccionarios con los datos.

Ranking de resultados: se ordenan por "calidad" del producto — cuantos más
campos prioritarios tenga (foto_url, video_url, info_completada, categoria_id,
star/superstar), mejor posición. El stock NO influye en el orden. Los
productos ocultos (oculto = 1) se excluyen siempre.
"""
import logging
import libsql_client

# Importa las credenciales y parámetros desde el módulo central de configuración (core)
from core.config import TURSO_URL, TURSO_TOKEN, LIMITE_PRODUCTOS
from core.logs import recortar

logger = logging.getLogger("salus.turso")

# `prioridad` = suma de campos clave presentes (0-5); se usa solo para ordenar.
CONSULTA_SQL = """
SELECT nombre_producto, marca, descripcion, precio1, slug,
       para_que_sirve, como_tomar, dosis, via_administracion,
       edad_recomendada, contraindicaciones, advertencias, recomendaciones,
       (stock > 0) AS disponible
FROM productos
WHERE (nombre_producto LIKE ? OR descripcion LIKE ? OR marca LIKE ?) AND oculto = 0
ORDER BY
    ((foto_url IS NOT NULL AND foto_url <> '')
   + (video_url IS NOT NULL AND video_url <> '')
   + (IFNULL(info_completada, 0) > 0)
   + (IFNULL(categoria_id, 0) > 0)
   + (IFNULL(star, 0) > 0 OR IFNULL(superstar, 0) > 0)) DESC
LIMIT ?
"""

async def buscar_producto(termino: str) -> list:
    """
    Consulta Turso con el término dado (hasta LIMITE_PRODUCTOS filas, las de
    mejor prioridad). Devuelve lista de dicts o lista vacía si no hay resultados.
    """
    termino_sql = f"%{termino}%"
    logger.info("Turso → consulta productos LIKE %r (nombre/descripción/marca) | limite=%d | ranking=prioridad",
                recortar(termino, 80), LIMITE_PRODUCTOS)
    async with libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN) as db:
        resultado = await db.execute(CONSULTA_SQL, [termino_sql, termino_sql, termino_sql, LIMITE_PRODUCTOS])

        productos = []
        for fila in resultado.rows:
            slug = fila[4]
            productos.append({
                "nombre":            fila[0],
                "marca":             fila[1],
                "descripcion":       fila[2],
                "precio":            f"${fila[3]:.2f}" if isinstance(fila[3], (int, float)) else fila[3],
                "enlace":            f"https://www.naturesgreenec.com/producto/{slug}" if slug else None,
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
