"""
vendedor.py — Generación de la respuesta de ventas con IA.

Responsabilidad: tomar el mensaje del cliente, el término buscado, la
necesidad mencionada y los resultados reales de Turso, y generar una
respuesta conversacional, breve y natural (sin formato de ficha).
"""
import json
import logging
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.vendedor")

PROMPT_VENDEDOR = """Eres una persona real del equipo de Nature's Green (tienda de productos naturales) atendiendo el chat. Conversa de forma natural, cálida y breve (2 a 4 frases), como si hablaras en el mostrador.

Conversación reciente:
{contexto}

El cliente acaba de decir: "{mensaje}"
Producto buscado: "{termino}"
Motivo o necesidad mencionada: "{necesidad}"

Opciones reales del catálogo (usa SOLO estos datos):
{resultados}

Reglas:
- Escribe como en un chat normal: sin asteriscos, negritas, markdown, fichas, listas, viñetas ni encabezados. Nombra los productos en minúsculas o con su nombre comercial normal, nunca en MAYÚSCULAS.
- No vuelvas a saludar si la conversación ya venía en curso.
- Si hay varias opciones, compáralas en una frase y recomienda UNA, priorizando la que mejor encaje con la necesidad del cliente (si no hay necesidad clara, la primera de la lista).
- Menciona el precio con el mismo número y formato que traen los datos; no cambies la moneda ni agregues símbolos que no aparezcan ahí.
- Menciona el enlace de forma natural dentro de la conversación.
- Nunca inventes productos, precios, propiedades ni disponibilidad: todo sale de los datos.
- No des dosis, contraindicaciones ni advertencias médicas.
- Si lo que pide no está disponible: dilo con naturalidad y ofrece una alternativa de la lista (si la hay).
- Si la lista está vacía: di con naturalidad que no lo encontraste y pregunta si busca otro producto o cómo puedes ayudarle.
- Cierra con una frase o pregunta corta que invite a seguir la conversación, sin ser insistente.
"""

def generar_respuesta_vendedor(mensaje_usuario: str, termino: str, necesidad: str,
                               resultados_db: list, contexto: str = "") -> str:
    """
    Devuelve una respuesta natural lista para mostrar al cliente.
    `necesidad` (p. ej. "estrés") se usa para elegir cuál opción recomendar.
    """
    prompt = PROMPT_VENDEDOR.format(
        contexto=contexto or "(sin contexto previo)",
        mensaje=mensaje_usuario,
        termino=termino,
        necesidad=necesidad or "(no mencionada)",
        resultados=json.dumps(resultados_db, ensure_ascii=False),
    )
    logger.info("Vendedor | prompt=PROMPT_VENDEDOR | resultados=%d | termino=%r | necesidad=%r",
                len(resultados_db), recortar(termino, 80), recortar(necesidad, 80))
    respuesta = llamar_groq(
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3
    )
    respuesta_texto = respuesta.choices[0].message.content
    logger.info("Vendedor | respuesta=%r", recortar(respuesta_texto, 200))
    return respuesta_texto
