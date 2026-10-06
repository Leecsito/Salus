"""
saludo.py — Componente de saludo inicial de SALUS.

Genera con el LLM un saludo natural y distinto cada vez, con tono humano de
una persona real de Nature's Green (sin sonar a bot ni repetir fórmulas).
Tras el saludo, la conversación pasa a la fase "atencion".
"""
import logging
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.saludo")

PROMPT_SISTEMA_SALUDO = """Eres una persona real del equipo de Nature's Green, una tienda de productos naturales. Atiendes el chat de la tienda y acabas de recibir el primer mensaje de un cliente.

Escribe un saludo breve (máximo 2 frases), cálido y natural, como si lo dijeras en voz alta en el mostrador.

Reglas:
- Varía siempre la forma de saludar: nunca repitas la misma fórmula ni uses plantillas fijas entre conversaciones.
- Nada de presentarte como asistente virtual, bot o IA, ni frases robóticas o corporativas.
- Ten en cuenta lo que la persona escribió y respóndele con naturalidad, sin ignorarlo.
- No hagas más de una pregunta y no prometas nada que no puedas cumplir.
- Español cercano y relajado, pero profesional. Sin emojis en exceso (máximo uno, o ninguno).
"""

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    No usa el historial: el saludo depende solo del primer mensaje. Siempre
    devuelve siguiente_fase="atencion" con historial vacío, para que la fase de
    atención arranque con su propio prompt de sistema.
    """
    logger.info("Saludo | prompt=PROMPT_SISTEMA_SALUDO | user=%r", recortar(mensaje_usuario))
    try:
        respuesta_api = llamar_groq(
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA_SALUDO},
                {"role": "user", "content": mensaje_usuario},
            ],
            temperature=0.9,
        )
        texto = (respuesta_api.choices[0].message.content or "").strip()
        if not texto:
            logger.warning("Saludo | el modelo devolvió texto vacío")
            texto = "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos."
    except Exception as e:
        logger.error("Saludo falló: %s", e, exc_info=True)
        texto = "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos."

    logger.info("Saludo resuelto | respuesta=%r", recortar(texto, 200))
    return texto, "atencion", []
