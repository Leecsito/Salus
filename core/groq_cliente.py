"""
groq_cliente.py — Cliente compartido de Groq para todo el proyecto SALUS (core).

Único lugar que crea clientes Groq y maneja el fallback entre API keys:
- HTTP 401 (key inválida o revocada) → salta a la siguiente key
- HTTP 429 (rate limit)               → salta a la siguiente key
Si todas las keys fallan, relanza la excepción.

Los reintentos internos del SDK quedan desactivados (`max_retries=0`): la
rotación de keys ya maneja el 429 y así se evitan esperas ocultas del SDK.
`es_limite_diario()` distingue el 429 por tokens/día (TPD) del 429 por minuto:
ante TPD, reintentar el mismo modelo no ayuda hasta que la cuota se renueve.
"""
import logging
import time
from groq import Groq, APIError

from core.config import API_KEYS, MODELO
from core.logs import mascara_key

logger = logging.getLogger("salus.groq")

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key], max_retries=0)

def es_limite_diario(error: Exception) -> bool:
    """True si el 429 es por límite de tokens por día (TPD): reintentar no ayuda."""
    texto = str(error).lower()
    return "per day" in texto or "tokens per day" in texto

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

            logger.info(
                "Groq → key#%d %s | modelo=%s | temp=%s | json=%s",
                key_index + 1, mascara_key(API_KEYS[key_index]),
                model, temperature, bool(response_format)
            )
            inicio = time.perf_counter()
            respuesta = cliente.chat.completions.create(**kwargs)
            logger.info("Groq ← OK en %.0f ms", (time.perf_counter() - inicio) * 1000)
            return respuesta

        except APIError as e:
            status = getattr(e, 'status_code', None)
            if status in (401, 429) and intento < len(API_KEYS) - 1:
                logger.warning("Groq key#%d falló (%s) → rotando a la siguiente key", key_index + 1, status)
                time.sleep(2)
                continue
            logger.error("Groq key#%d falló (%s): %s", key_index + 1, status, e)
            raise e
