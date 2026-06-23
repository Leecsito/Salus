"""
extractor.py — Extracción del término de búsqueda.
Responsabilidad: usar IA para extraer el sustantivo principal (singular) del
mensaje del usuario, descartando frases de síntomas o verbos de acción.
"""
import json
from producto.groq_cliente import llamar_groq

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
    respuesta = llamar_groq(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": PROMPT_EXTRACCION},
            {"role": "user",   "content": mensaje}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(respuesta.choices[0].message.content).get("termino", "")
