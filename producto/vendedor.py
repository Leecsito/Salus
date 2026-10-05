"""
vendedor.py — Generación de respuesta de ventas con IA.
Responsabilidad: tomar los resultados de la BD y generar una respuesta
natural, directa y orientada a la venta usando el modelo de Groq.
"""
import json
from groq_cliente import llamar_groq

PROMPT_VENDEDOR = """Eres el vendedor de Nature's Green.
El cliente busca: "{termino}".

Resultado de la base de datos: {resultados}

Reglas:
- Si la lista está vacía, di cortésmente que no encontraste ese producto y sugiere reformular.
- Si hay resultado, responde ÚNICAMENTE con: nombre del producto, para qué sirve (1 sola frase corta), precio y si está disponible o no, y el enlace al final.
- Nada más. Sin contraindicaciones, sin dosis, sin listas largas. Solo lo esencial.
- Sé directo y natural. Máximo 3-4 líneas.
"""

def generar_respuesta_vendedor(termino: str, resultados_db: list) -> str:
    """
    Recibe el término buscado y los resultados de la BD.
    Devuelve una respuesta natural lista para mostrar al cliente.
    """
    prompt = PROMPT_VENDEDOR.format(
        termino=termino,
        resultados=json.dumps(resultados_db, ensure_ascii=False)
    )
    respuesta = llamar_groq(
        model="openai/gpt-oss-20b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3
    )
    return respuesta.choices[0].message.content
