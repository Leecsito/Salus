"""
asesoria.py — Componente de asesoría de salud de SALUS.

Responsabilidad: mantener la conversación con el cliente para diagnosticar
su necesidad y recomendar un tipo de producto específico.
"""
import json
import logging
from core.groq_cliente import llamar_groq
from core.logs import recortar
from producto.producto import responder as responder_producto

logger = logging.getLogger("salus.asesoria")

PROMPT_SISTEMA = """Eres el asesor de salud naturista de Nature's Green.
Tu objetivo es diagnosticar el problema del cliente haciendo preguntas breves y precisas sobre sus síntomas.
Una vez que tengas claro qué tipo de dolencia tiene, recomiéndale un TIPO DE PRODUCTO ESPECÍFICO (ej. pomada antiinflamatoria, té relajante, jarabe para la tos, colágeno).

Reglas:
- Haz preguntas amables y cortas (máximo 2 oraciones).
- Cuando ya sepas qué recomendar, dile al cliente tu recomendación y dile que vas a revisar si hay stock de eso.
- La respuesta debe seguir estrictamente este JSON:
  {"respuesta": "Lo que dices al cliente", "estado": "consultando | producto_encontrado", "producto_sugerido": "nombre del producto si estado es producto_encontrado"}
- "estado" debe ser "consultando" mientras indagas.
- Cambia "estado" a "producto_encontrado" solo cuando ya sepas qué recomendar y se lo hayas comunicado en la "respuesta".
  En ese caso, en "producto_sugerido" pon un sustantivo genérico clave (ej. "pomada", "colágeno", "jarabe") para buscar en la BD.
"""

def responder(mensaje_usuario: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    - Si el asesor confirma "producto_encontrado", ejecuta de inmediato la búsqueda
      del producto sugerido (componente producto), concatena el resultado comercial
      a la recomendación y devuelve siguiente_fase="producto" con historial vacío.
    - En cualquier otro caso permanece en "asesoria" conservando el historial.
    """
    if not historial:
        historial = [{"role": "system", "content": PROMPT_SISTEMA}]

    historial.append({"role": "user", "content": mensaje_usuario})

    logger.info("Asesoría | prompt=PROMPT_SISTEMA | user=%r", recortar(mensaje_usuario))
    try:
        respuesta_api = llamar_groq(
            messages=historial,
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        datos = json.loads(respuesta_api.choices[0].message.content)
        respuesta_ia      = datos.get("respuesta",        "Error generando respuesta")
        estado            = datos.get("estado",           "consultando")
        producto_sugerido = datos.get("producto_sugerido", "")

        historial.append({"role": "assistant", "content": json.dumps(datos)})

        logger.info(
            "Asesoría resuelta | estado=%s | producto_sugerido=%r | respuesta=%r",
            estado, producto_sugerido, recortar(respuesta_ia, 200)
        )

        if estado == "producto_encontrado" and producto_sugerido:
            try:
                resultado_producto, _, _ = responder_producto(producto_sugerido, [])
                respuesta_ia = f"{respuesta_ia}\n\n{resultado_producto}"
            except Exception as e:
                logger.error("Asesoría | falló la búsqueda tras recomendar: %s", e, exc_info=True)
            return respuesta_ia, "producto", []

        return respuesta_ia, "asesoria", historial

    except Exception as e:
        logger.error("Asesoría falló: %s", e, exc_info=True)
        return "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos.", "asesoria", historial
