"""
groq_cliente.py — Cliente compartido de Groq para todo el proyecto SALUS.

Único lugar que crea clientes Groq y maneja el fallback entre API keys:
- HTTP 401 (key inválida o revocada) → salta a la siguiente key
- HTTP 429 (rate limit)               → salta a la siguiente key
Si todas las keys fallan, relanza la excepción.
"""
import os
import sys
import time
from groq import Groq, APIError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import API_KEYS, MODELO

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key])

def llamar_groq(messages, model=MODELO, temperature=0.3, response_format=None):
    """
    Llama a la API de Groq con fallback automático entre API keys.
    Lanza excepción si todas las keys fallan.
    """
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
            return cliente.chat.completions.create(**kwargs)
        except APIError as e:
            if getattr(e, 'status_code', None) in (401, 429) and intento < len(API_KEYS) - 1:
                time.sleep(2)
                continue
            raise e
