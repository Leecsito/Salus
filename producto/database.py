"""
database.py — Consulta a la base de datos Turso.
Responsabilidad: conectarse a Turso (SQLite serverless) y buscar productos
por nombre o descripción. Devuelve una lista de diccionarios con los datos.

Ranking de resultados: primero por relevancia (coincidencia en el nombre >
marca > descripción) y luego por "calidad" del producto — cuantos más campos
prioritarios tenga (foto_url, video_url, info_completada, categoria_id,
star/superstar), mejor posición. Así, al buscar "magnesio", los productos que
SON magnesio aparecen antes que los que solo lo mencionan en su descripción.
La búsqueda ignora acentos ('vitamagnésio' encuentra 'VITAMAGNESIO PLUS') y
espacios raros de la DB (\u202f, \xa0): el término se normaliza y las columnas
se comparan con REPLACE en SQL.
Si no hay coincidencias exactas, hay un reintento tolerante a erratas leves
(p. ej. 'vitamagensio' → 'VITAMAGNESIO PLUS') por prefijo + similitud.
El stock NO influye en el orden. Los productos ocultos (oculto = 1) se
excluyen siempre.
"""
import difflib
import logging
import re
import unicodedata
import libsql_client

# Importa las credenciales y parámetros desde el módulo central de configuración (core)
from core.config import TURSO_URL, TURSO_TOKEN, LIMITE_PRODUCTOS
from core.logs import recortar

logger = logging.getLogger("salus.turso")

_ACENTOS = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n"),
            ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ü", "U"), ("Ñ", "N"))

def _sin_acentos(texto: str) -> str:
    """Minúsculas, sin diacríticos y con espacios simples (la DB usa \u202f y \xa0)."""
    plano = "".join(c for c in unicodedata.normalize("NFKD", texto)
                    if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", plano.replace("\u202f", " ").replace("\xa0", " ")).strip()

def _columna_sin_acentos(columna: str) -> str:
    """
    Expresión SQL que quita tildes/ñ y unifica espacios raros de la DB (\u202f,
    \xa0), igual que `_sin_acentos` hace con el término (Turso no trae unaccent).
    """
    expr = columna
    for acentuada, plana in _ACENTOS:
        expr = f"REPLACE({expr}, '{acentuada}', '{plana}')"
    return f"REPLACE(REPLACE({expr}, '\u202f', ' '), '\xa0', ' ')"

_NOMBRE_N = _columna_sin_acentos("nombre_producto")
_DESCRIPCION_N = _columna_sin_acentos("descripcion")
_MARCA_N = _columna_sin_acentos("marca")

# Similitud mínima (difflib) para aceptar un candidato del reintento por erratas,
# y filas que se piden a Turso para puntuar ese reintento.
UMBRAL_APROXIMADO = 0.85
_CANDIDATOS_LIMITE = 50

# Muletillas que no cuentan como palabras clave en la segunda pasada de búsqueda.
_STOPWORDS = {"de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas",
              "para", "con", "sin", "por", "y", "o", "al", "en", "mas", "más"}

_COLUMNAS = """nombre_producto, marca, descripcion, precio1, slug,
       para_que_sirve, como_tomar, dosis, via_administracion,
       edad_recomendada, contraindicaciones, advertencias, recomendaciones,
       (stock > 0) AS disponible"""

# `prioridad` = suma de campos clave presentes (0-5); solo se usa para ordenar.
_PRIORIDAD_SQL = """((foto_url IS NOT NULL AND foto_url <> '')
   + (video_url IS NOT NULL AND video_url <> '')
   + (IFNULL(info_completada, 0) > 0)
   + (IFNULL(categoria_id, 0) > 0)
   + (IFNULL(star, 0) > 0 OR IFNULL(superstar, 0) > 0))"""

# Orden: `coincidencia` (0 = nombre, 1 = marca, 2 = descripción) y luego prioridad.
CONSULTA_SQL = f"""
SELECT {_COLUMNAS}
FROM productos
WHERE ({_NOMBRE_N} LIKE ? OR {_DESCRIPCION_N} LIKE ? OR {_MARCA_N} LIKE ?) AND oculto = 0
ORDER BY
    CASE
        WHEN {_NOMBRE_N} LIKE ? THEN 0
        WHEN {_MARCA_N} LIKE ? THEN 1
        ELSE 2
    END,
    {_PRIORIDAD_SQL} DESC
LIMIT ?
"""

# Candidatos para el reintento por erratas: solo nombre/marca que empiezan igual.
CONSULTA_CANDIDATOS_SQL = f"""
SELECT {_COLUMNAS}
FROM productos
WHERE ({_NOMBRE_N} LIKE ? OR {_MARCA_N} LIKE ?) AND oculto = 0
ORDER BY {_PRIORIDAD_SQL} DESC
LIMIT ?
"""

def _fila_a_dict(fila) -> dict:
    """Convierte una fila de Turso al contrato de dict del proyecto."""
    slug = fila[4]
    return {
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
    }

async def _consultar(sql: str, parametros: list) -> list:
    """Ejecuta una consulta contra Turso y devuelve las filas ya normalizadas."""
    async with libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN) as db:
        resultado = await db.execute(sql, parametros)
        return [_fila_a_dict(fila) for fila in resultado.rows]

async def _consultar_crudo(sql: str, parametros: list) -> list:
    """Ejecuta una consulta contra Turso y devuelve las filas sin normalizar."""
    async with libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN) as db:
        resultado = await db.execute(sql, parametros)
        return resultado.rows

async def buscar_producto(termino: str) -> list:
    """
    Consulta Turso con el término dado (hasta LIMITE_PRODUCTOS filas, las más
    relevantes). Si no hay coincidencias exactas, reintenta tolerando erratas
    leves del término. Devuelve lista de dicts o lista vacía.
    """
    termino_normalizado = _sin_acentos(termino)
    termino_sql = f"%{termino_normalizado}%"
    logger.info("Turso → consulta productos LIKE %r (normalizado, sin acentos) | limite=%d | ranking=relevancia(nombre>marca>descripción)+prioridad",
                recortar(termino_normalizado, 80), LIMITE_PRODUCTOS)
    productos = await _consultar(CONSULTA_SQL, [termino_sql, termino_sql, termino_sql,
                                                termino_sql, termino_sql, LIMITE_PRODUCTOS])

    # Segunda pasada por palabras clave: "glicinato de magnesio" también debe
    # traer "Magnesio Glicinato 600 mg" (mismas palabras en otro orden).
    palabras = _palabras_clave(termino_normalizado)
    if len(palabras) >= 2 and len(productos) < LIMITE_PRODUCTOS:
        extra = await _buscar_por_palabras(palabras, excluir={p["nombre"] for p in productos})
        if extra:
            logger.info("Turso | búsqueda por palabras añadió %d fila(s) para %r",
                        len(extra), recortar(termino_normalizado, 80))
            productos.extend(extra[:LIMITE_PRODUCTOS - len(productos)])

    if not productos:
        productos = await _buscar_aproximado(termino_normalizado)
    logger.info("Turso ← %d fila(s)", len(productos))
    return productos

def _palabras_clave(termino_normalizado: str) -> list:
    """Palabras significativas (>= 3 letras, sin muletillas) del término."""
    return [p for p in re.split(r"\W+", termino_normalizado)
            if len(p) >= 3 and p not in _STOPWORDS]

# Palabras de pregunta/conversación que no pueden ser nombre o marca de producto.
_PALABRAS_IGNORADAS = _STOPWORDS | {
    "como", "hora", "toma", "tomar", "tomarlo", "tomo", "dosis", "cada", "cuanto",
    "cuantas", "sirve", "recomienda", "recomiendas", "recomiendan", "diferencia",
    "precio", "cuesta", "puedo", "debo", "antes", "despues", "efervescente",
    "contraindicaciones", "advertencias", "efectos", "secundarios", "modo", "uso",
    "solo", "tienen", "hay", "mas", "esta", "estan", "cual", "cuales", "mejor",
    "bueno", "otro", "mismo", "disponible", "stock", "manana", "noche", "dia",
    "capsulas", "tabletas", "sobres", "sachets", "unidades", "envase", "frasco",
    "cuando", "donde", "quien", "algo", "algun", "alguna", "tengo", "quiero",
    "necesito", "busco", "venden", "disponen", "gracias", "hola", "buenas", "favor",
    "puede", "sabe", "saben", "dormir", "tomarse", "tomas", "dias", "veces",
}

def _candidatos_producto(mensaje: str) -> list:
    """Palabras del mensaje que podrían ser nombre o marca de producto."""
    plano = _sin_acentos(mensaje)
    return [p for p in re.split(r"\W+", plano)
            if len(p) >= 4 and p not in _PALABRAS_IGNORADAS]

async def menciona_producto(mensaje: str) -> bool:
    """
    Chequeo local contra Turso (sin LLM): True si alguna palabra del mensaje
    coincide con el nombre o la marca de un producto visible. Permite decidir si
    un seguimiento puede resolverse con el estado previo (ahorro de tokens).
    Ante error de DB devuelve True (conservador: se usará el extractor).
    """
    palabras = _candidatos_producto(mensaje)
    if not palabras:
        return False
    condiciones = " OR ".join(f"({_NOMBRE_N} LIKE ? OR {_MARCA_N} LIKE ?)" for _ in palabras)
    parametros = []
    for palabra in palabras:
        parametros += [f"%{palabra}%", f"%{palabra}%"]
    sql = f"SELECT 1 FROM productos WHERE ({condiciones}) AND oculto = 0 LIMIT 1"
    try:
        filas = await _consultar_crudo(sql, parametros)
        return bool(filas)
    except Exception as e:
        logger.warning("Turso | falló el chequeo de mención (%s) → se usará el extractor", e)
        return True

async def _buscar_por_palabras(palabras: list, excluir: set) -> list:
    """
    Exige TODAS las palabras clave en nombre o marca (no en descripción, para
    no diluir con productos que solo las mencionan). Devuelve las filas nuevas.
    """
    condiciones = " AND ".join(f"({_NOMBRE_N} LIKE ? OR {_MARCA_N} LIKE ?)" for _ in palabras)
    parametros = []
    for palabra in palabras:
        parametros += [f"%{palabra}%", f"%{palabra}%"]
    sql = (f"SELECT {_COLUMNAS} FROM productos WHERE {condiciones} AND oculto = 0 "
           f"ORDER BY {_PRIORIDAD_SQL} DESC LIMIT ?")
    filas = await _consultar(sql, parametros + [LIMITE_PRODUCTOS + len(excluir)])
    return [fila for fila in filas if fila["nombre"] not in excluir]

async def _buscar_aproximado(termino_normalizado: str) -> list:
    """
    Reintento por erratas: busca candidatos por el prefijo de la palabra más
    larga del término y conserva los que se parecen al término completo
    (similitud difflib >= UMBRAL_APROXIMADO). Evita falsos positivos.
    """
    palabras = [p for p in re.split(r"\W+", termino_normalizado) if len(p) >= 5]
    if not palabras:
        return []
    prefijo = max(palabras, key=len)[:5]
    logger.info("Turso | sin coincidencias exactas para %r → reintento aproximado por prefijo %r",
                recortar(termino_normalizado, 80), prefijo + "%")
    candidatos = await _consultar(CONSULTA_CANDIDATOS_SQL,
                                  [f"%{prefijo}%", f"%{prefijo}%", _CANDIDATOS_LIMITE])

    def similitud(producto: dict) -> float:
        nombre = _sin_acentos(producto.get("nombre") or "")
        marca = _sin_acentos(producto.get("marca") or "")
        return max(difflib.SequenceMatcher(None, termino_normalizado, nombre).ratio(),
                   difflib.SequenceMatcher(None, termino_normalizado, marca).ratio())

    aproximados = [p for p in sorted(candidatos, key=similitud, reverse=True)
                   if similitud(p) >= UMBRAL_APROXIMADO][:LIMITE_PRODUCTOS]
    logger.info("Turso | aproximado: %d candidato(s), %d sobre el umbral %.2f",
                len(candidatos), len(aproximados), UMBRAL_APROXIMADO)
    return aproximados
