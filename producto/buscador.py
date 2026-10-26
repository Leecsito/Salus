"""
buscador.py — Búsqueda web de respaldo (Tavily).

Responsabilidad: cuando el catálogo de Turso no alcanza (el cliente pide un
dato puntual del producto o la búsqueda no devolvió resultados), consultar
Tavily y devolver fragmentos crudos de páginas web. El módulo NO interpreta
ni responde: filtra que TODAS las palabras del término aparezcan en el
resultado (así no confunde productos parecidos) y el vendedor decide si los
fragmentos confirman el dato exacto. Los fragmentos son insumo INTERNO: nunca
se citan, mencionan ni enlazan al cliente (regla de negocio: solo se comparten
enlaces de naturesgreenec.com); si no confirman el dato, el vendedor lo dice.

Incluye caché en memoria con TTL para no gastar créditos en consultas
repetidas (mismo patrón que el buffer de logs: 1 worker de Gunicorn).
Sin TAVILY_API_KEY el módulo queda inactivo y devuelve lista vacía.
"""
import logging
import re
import time
import unicodedata

import httpx

from core.config import TAVILY_API_KEY, WEB_MAX_RESULTADOS, WEB_CACHE_TTL, WEB_CACHE_MAX
from core.logs import recortar

logger = logging.getLogger("salus.buscador")

URL_TAVILY = "https://api.tavily.com/search"
TIMEOUT_SEGUNDOS = 8.0
MAX_CARACTERES_FRAGMENTO = 400
# Se piden 2 resultados extra a Tavily (mismo costo) y se filtra antes de
# recortar a WEB_MAX_RESULTADOS: la ficha oficial no siempre viene en el top.
SOLICITADOS_EXTRA = 2

# Caché en memoria: consulta normalizada -> (expira_ts, resultados)
_CACHE: dict = {}

def buscar_en_web(consulta: str, termino: str = "", nombre_producto: str = "") -> list:
    """
    Devuelve fragmentos como [{"titulo": str, "url": str, "contenido": str}].
    Solo los que corresponden al producto exacto: contienen todas las palabras
    de `termino` o, como alternativa, las primeras palabras del nombre del
    producto en el catálogo (`nombre_producto`) — cubre fichas oficiales que
    no repiten el término completo (p. ej. devueltas en otro idioma).
    Si falta la key, Tavily falla o expira el timeout, devuelve lista vacía
    (la conversación continúa con los datos de Turso).
    """
    if not TAVILY_API_KEY:
        logger.info("Web | sin TAVILY_API_KEY: búsqueda omitida | consulta=%r", recortar(consulta, 120))
        return []

    clave = f"{termino.strip().lower()}|{nombre_producto.strip().lower()}|{consulta.strip().lower()}"
    ahora = time.time()
    guardado = _CACHE.get(clave)
    if guardado and guardado[0] > ahora:
        logger.info("Web ← caché | %d resultado(s) | consulta=%r", len(guardado[1]), recortar(consulta, 120))
        return guardado[1]

    solicitados = WEB_MAX_RESULTADOS + SOLICITADOS_EXTRA
    logger.info("Web → Tavily | consulta=%r | max=%d", recortar(consulta, 120), solicitados)
    try:
        respuesta = httpx.post(
            URL_TAVILY,
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={
                "query": consulta,
                "max_results": solicitados,
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=TIMEOUT_SEGUNDOS,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except Exception as e:
        logger.warning("Web ✗ Tavily falló (%s): %s", type(e).__name__, e)
        return []

    fragmentos = [
        {
            "titulo": fila.get("title") or "",
            "url": fila.get("url") or "",
            "contenido": (fila.get("content") or "")[:MAX_CARACTERES_FRAGMENTO],
        }
        for fila in datos.get("results", [])[:solicitados]
    ]
    resultados = [f for f in fragmentos if _es_producto_exacto(f, termino, nombre_producto)]
    resultados = resultados[:WEB_MAX_RESULTADOS]
    if len(resultados) != len(fragmentos):
        logger.info("Web | descartados %d resultado(s) de otros productos", len(fragmentos) - len(resultados))
    _guardar_en_cache(clave, resultados, ahora)
    logger.info("Web ← %d resultado(s) | consulta=%r", len(resultados), recortar(consulta, 120))
    return resultados

def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar el término con los fragmentos."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c)).lower()

def _es_producto_exacto(fragmento: dict, termino: str, nombre_producto: str = "") -> bool:
    """
    Acepta el resultado si contiene TODAS las palabras significativas del
    término (>= 3 letras) o, como alternativa, las 3 primeras palabras del
    nombre del producto en el catálogo (cubre fichas oficiales que no repiten
    el término completo: p. ej. la misma ficha devuelta en otro idioma).
    Si no cumple ninguna, es otro producto y no se envía al vendedor.
    """
    palabras = [p for p in re.split(r"\W+", _normalizar(termino)) if len(p) >= 3]
    if not palabras:
        return True
    texto = _normalizar(" ".join((fragmento["titulo"], fragmento["url"], fragmento["contenido"])))
    if all(p in texto for p in palabras):
        return True
    if nombre_producto:
        clave = " ".join(re.split(r"\W+", _normalizar(nombre_producto))[:3]).strip()
        if len(clave) >= 5 and clave in texto:
            return True
    return False

def _guardar_en_cache(clave: str, resultados: list, ahora: float) -> None:
    """Guarda la consulta en caché y poda entradas vencidas si crece demasiado."""
    _CACHE[clave] = (ahora + WEB_CACHE_TTL, resultados)
    if len(_CACHE) <= WEB_CACHE_MAX:
        return
    for k in [k for k, (expira, _) in _CACHE.items() if expira <= ahora]:
        del _CACHE[k]
    while len(_CACHE) > WEB_CACHE_MAX:
        del _CACHE[next(iter(_CACHE))]
