"""
asesoria.py — Asesor de salud de SALUS.
Responsabilidad: mantener la conversación con el cliente para diagnosticar
su necesidad y recomendar un tipo de producto específico.
"""
import json
from groq_cliente import llamar_groq

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

def responder_asesoria(mensaje_usuario: str, historial: list):
    """
    Recibe un mensaje del usuario y el historial acumulado.
    Devuelve: (respuesta_ia, estado, producto_sugerido, historial_actualizado)
    - estado: "consultando" | "producto_encontrado" | "error"
    - producto_sugerido: string con el tipo de producto si estado == "producto_encontrado"
    """
    if not historial:
        historial = [{"role": "system", "content": PROMPT_SISTEMA}]

    historial.append({"role": "user", "content": mensaje_usuario})

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

        return respuesta_ia, estado, producto_sugerido, historial

    except Exception as e:
        print(f"[asesoria/asesoria.py] Error: {e}")
        return "Lo siento, tuve un problema para responder. Intenta de nuevo en unos segundos.", "error", "", historial
