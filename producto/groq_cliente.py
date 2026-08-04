"""
groq_cliente.py — Cliente compartido de Groq para el módulo de Productos.
Maneja el fallback automático entre múltiples API Keys si se recibe error 429.
"""
import os
import sys
import time
from groq import Groq, APIError

# Importa las keys desde el módulo central de configuración
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import API_KEYS

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key])

def llamar_groq(messages, model="llama-3.1-8b-instant", temperature=0, response_format=None):
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
            if getattr(e, 'status_code', None) == 429 and intento < len(API_KEYS) - 1:
                time.sleep(2)
                continue
            raise e
