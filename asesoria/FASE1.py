import json
import os
import sys
import time
from groq import Groq, APIError

# Importa credenciales desde el módulo central — sólo hay que cambiarlas en config.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import API_KEYS

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key])

def llamar_groq_completions(messages, model="openai/gpt-oss-20b", temperature=0.3, response_format=None):
    for intento, key_index in enumerate(range(len(API_KEYS))):
        try:
            cliente = obtener_cliente(key_index)
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            respuesta = cliente.chat.completions.create(**kwargs)
            return respuesta
        except APIError as e:
            if getattr(e, 'status_code', None) in (401, 429) and intento < len(API_KEYS) - 1:
                time.sleep(2)
                continue
            raise e

PROMPT_SISTEMA_ASESORIA = """Eres el asesor de salud naturista de Nature's Green.
Tu objetivo es diagnosticar el problema del cliente haciendo preguntas breves y precisas sobre sus síntomas.
Una vez que tengas claro qué tipo de dolencia tiene, recomiéndale un TIPO DE PRODUCTO ESPECÍFICO (ej. pomada antiinflamatoria, té relajante, jarabe para la tos, colágeno).

Reglas:
- Haz preguntas amables y cortas (máximo 2 oraciones).
- Cuando ya sepas qué recomendar, dile al cliente tu recomendación y dile que vas a revisar si hay stock de eso.
- La respuesta debe seguir estrictamente este JSON:
  {"respuesta": "Lo que dices al cliente", "estado": "consultando | producto_encontrado", "producto_sugerido": "nombre del producto si estado es producto_encontrado"}
- "estado" debe ser "consultando" mientras indagas.
- Cambia "estado" a "producto_encontrado" solo cuando ya sepas qué recomendar y se lo hayas comunicado en la "respuesta". En ese caso, en "producto_sugerido" pon un sustantivo genérico clave (ej. "pomada", "colágeno", "jarabe") para buscar en la base de datos.
"""

def responder_asesoria(mensaje_usuario: str, historial: list):
    if not historial:
        historial = [
            {"role": "system", "content": PROMPT_SISTEMA_ASESORIA}
        ]
    
    historial.append({"role": "user", "content": mensaje_usuario})
    
    try:
        respuesta_api = llamar_groq_completions(
            messages=historial,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        datos = json.loads(respuesta_api.choices[0].message.content)
        respuesta_ia = datos.get("respuesta", "Error generando respuesta")
        estado = datos.get("estado", "consultando")
        producto_sugerido = datos.get("producto_sugerido", "")
        
        historial.append({"role": "assistant", "content": json.dumps(datos)})
        
        # Devolvemos la respuesta, el estado para que Flask sepa si cambiar de fase, el producto si lo hay, y el historial
        return respuesta_ia, estado, producto_sugerido, historial
        
    except Exception as e:
        return f"Error en Asesoría: {e}", "error", "", historial
