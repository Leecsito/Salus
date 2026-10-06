"""
saludo.py — Componente de saludo inicial de SALUS.

Genera con el LLM un saludo natural y distinto cada vez, con tono humano de
una persona real de Nature's Green (sin sonar a bot ni repetir fórmulas).
Tras el saludo, la conversación pasa a la fase "atencion".
"""
import logging
import random
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.saludo")

PROMPT_SISTEMA_SALUDO = """Eres una persona real del equipo de Nature's Green, una tienda de productos naturales. Atiendes el chat de la tienda y acabas de recibir el primer mensaje de un cliente.

Escribe una bienvenida breve (máximo 2 frases), cálida y natural, como si la dijeras en voz alta en el mostrador.

Reglas:
- Es solo la bienvenida inicial: no asumas que el cliente ya sabe qué quiere ni que busca un producto. Nunca preguntes "¿qué producto buscas?" ni nombres productos concretos.
- Ofrece ayuda de forma abierta y amable; puedes usar expresiones como "muy buenas tardes", "¿qué se le ofrece?", "¿en qué le podemos ayudar?", "¿qué necesita?", "cuéntame, ¿en qué puedo ayudarte?".
- Varía siempre la forma de saludar: nunca repitas la misma fórmula ni uses plantillas fijas entre conversaciones.
- Nada de presentarte como asistente virtual, bot o IA, ni frases robóticas o corporativas.
- Ten en cuenta lo que la persona escribió y respóndele con naturalidad, sin ignorarlo.
- No hagas más de una pregunta y no prometas nada que no puedas cumplir.
- Español cercano y relajado, pero profesional. Sin emojis en exceso (máximo uno, o ninguno).
"""

# Enfoques que se sortean en cada bienvenida para forzar variedad real entre
# conversaciones (el modelo tiende a repetir la misma estructura).
ENFOQUES = (
    "saludo corto y un ofrecimiento abierto de ayuda",
    "saludo cálido y una pregunta distinta a '¿en qué podemos ayudarte?' (p. ej. '¿qué se le ofrece?', '¿qué necesita?', '¿en qué le puedo servir?')",
    "saludo espontáneo y muy breve, sin pregunta, invitando a contar lo que necesita",
    "saludo + una frase de bienvenida a la tienda + ofrecimiento de ayuda",
    "saludo con un detalle cálido ('qué gusto saludarle', 'bienvenido/a') + ofrecimiento abierto",
)

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    No usa el historial: el saludo depende solo del primer mensaje. Siempre
    devuelve siguiente_fase="atencion" con historial vacío, para que la fase de
    atención arranque con su propio prompt de sistema.
    """
    enfoque = random.choice(ENFOQUES)
    prompt_sistema = (
        PROMPT_SISTEMA_SALUDO
        + f"\n- Enfoque para esta bienvenida (varía la estructura, no repitas siempre la misma frase): {enfoque}."
    )
    logger.info("Saludo | prompt=PROMPT_SISTEMA_SALUDO | enfoque=%r | user=%r",
                enfoque, recortar(mensaje_usuario))
    try:
        respuesta_api = llamar_groq(
            messages=[
                {"role": "system", "content": prompt_sistema},
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
