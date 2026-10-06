"""
extractor.py — Extracción del término, la necesidad y la intención.

Responsabilidad: usar IA para interpretar el mensaje del cliente con ayuda de
la conversación reciente, resolviendo referencias ("ese", "el otro",
"y bueno?", "y solo tienen ese?") y devolviendo un JSON estricto con:
  - termino:   sustantivo principal del producto (singular, sin frases extra)
  - necesidad: uso, síntoma o motivo mencionado (ej. "estrés")
  - intencion: "producto" | "tratamiento" | "venta"
"""
import json
import logging
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.extractor")

PROMPT_EXTRACCION = """Eres el extractor de productos de Nature's Green. Analiza el mensaje del cliente junto con la conversación reciente y devuelve SOLO un JSON válido con estas claves:

- "termino": el sustantivo principal del producto del que se habla o que se busca, en SINGULAR y sin frases adicionales (ej. "colágeno", "pomada", "citrato de magnesio"). Si no puedes identificar ningún producto, usa "".
- "necesidad": el uso, síntoma o motivo que menciona el cliente (ej. "estrés", "dolor de cabeza"). Usa "" si no menciona ninguno.
- "intencion": "producto" si pregunta por un producto, sus opciones o precios; "tratamiento" si muestra interés en un tratamiento para un malestar; "venta" si quiere comprar, pagar o recibir el producto.

REGLAS:
- Usa la conversación reciente para resolver referencias como "ese", "el otro", "y bueno?", "y solo tienen ese?": en esos casos el término es el producto del que se venía hablando.
- No incluyas síntomas, usos ni frases como "para el estrés" dentro de "termino".
- Conserva los nombres compuestos completos (p. ej. "citrato de magnesio", "omega 3", "vitamina c"): no los recortes a una sola palabra.
- Ignora verbos y frases como "busco", "tienen", "cuáles dispone".

EJEMPLOS:
- Mensaje: "Quiero comprar un frasco de colágeno" -> {"termino": "colágeno", "necesidad": "", "intencion": "producto"}
- Mensaje: "¿Tienen pomadas para aliviar un dolor muscular?" -> {"termino": "pomada", "necesidad": "dolor muscular", "intencion": "producto"}
- Conversación: el cliente venía preguntando por "citrato de magnesio" para el estrés. Mensaje: "y bueno?" -> {"termino": "citrato de magnesio", "necesidad": "estrés", "intencion": "producto"}
- Conversación: se acaba de mostrar un producto. Mensaje: "y solo tienen ese?" -> {"termino": "<el producto del contexto>", "necesidad": "", "intencion": "producto"}
- Mensaje: "quiero un tratamiento para el estrés" -> {"termino": "", "necesidad": "estrés", "intencion": "tratamiento"}
- Mensaje: "cómo hago para comprar el citrato?" -> {"termino": "citrato", "necesidad": "", "intencion": "venta"}

Salida ESTRICTA en JSON con las tres claves."""

def extraer_termino(mensaje: str, contexto: str = "") -> dict:
    """
    Devuelve {"termino": str, "necesidad": str, "intencion": str}.
    `contexto` es el transcript de los últimos turnos (ver producto/contexto.py).
    Si algo falla en el parseo, devuelve valores vacíos con intencion "producto".
    """
    logger.info("Extractor | prompt=PROMPT_EXTRACCION | mensaje=%r | contexto=%r",
                recortar(mensaje), recortar(contexto, 120))
    respuesta = llamar_groq(
        messages=[
            {"role": "system", "content": PROMPT_EXTRACCION},
            {"role": "user", "content": f"Conversación reciente:\n{contexto or '(sin contexto previo)'}\n\nMensaje del cliente: {mensaje}"}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    datos = json.loads(respuesta.choices[0].message.content)
    termino = str(datos.get("termino", "")).strip()
    necesidad = str(datos.get("necesidad", "")).strip()
    intencion = str(datos.get("intencion", "producto")).strip().lower()
    if intencion not in ("producto", "tratamiento", "venta"):
        intencion = "producto"

    logger.info("Extractor | término=%r | necesidad=%r | intencion=%s",
                termino, recortar(necesidad, 80), intencion)
    return {"termino": termino, "necesidad": necesidad, "intencion": intencion}
