"""
extractor.py — Extracción del término de búsqueda.
Responsabilidad: usar IA para extraer el sustantivo principal (singular) del
mensaje del usuario, descartando frases de síntomas o verbos de acción.
"""
import json
import logging
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.extractor")

PROMPT_EXTRACCION = """Analiza el mensaje del usuario y extrae ÚNICAMENTE el sustantivo principal del producto que está buscando, en SINGULAR y sin frases adicionales.
IGNORA descripciones de síntomas o frases como 'para aliviar el dolor', 'que tengan', 'busco'.
Devuelve un JSON válido con la clave "termino".
Ejemplo 1: "Quiero comprar un frasco de colágeno" -> {"termino": "colágeno"}
Ejemplo 2: "¿Tienen pomadas para aliviar el dolor?" -> {"termino": "pomada"}
Ejemplo 3: "Me duele la cabeza, tienen aspirinas?" -> {"termino": "aspirina"}"""

def extraer_termino(mensaje: str) -> str:
    """
    Devuelve el término de búsqueda extraído del mensaje.
    Retorna string vacío si no se pudo identificar ningún producto.
    """
    logger.info("Extractor | prompt=PROMPT_EXTRACCION | mensaje=%r", recortar(mensaje))
    respuesta = llamar_groq(
        messages=[
            {"role": "system", "content": PROMPT_EXTRACCION},
            {"role": "user",   "content": mensaje}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    termino = json.loads(respuesta.choices[0].message.content).get("termino", "")
    logger.info("Extractor | término=%r", termino)
    return termino
