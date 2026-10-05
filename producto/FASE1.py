import os
import json
import asyncio
import sys
import time
import libsql_client
from groq import Groq, APIError

# Importa credenciales desde el módulo central — sólo hay que cambiarlas en config.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import API_KEYS, TURSO_URL, TURSO_TOKEN

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key])

def llamar_groq_completions(messages, model="openai/gpt-oss-20b", temperature=0, response_format=None):
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

def extraer_termino_busqueda(mensaje: str) -> str:
    prompt = """Analiza el mensaje del usuario y extrae ÚNICAMENTE el sustantivo principal del producto que está buscando, en SINGULAR y sin frases adicionales.
    IGNORA descripciones de síntomas o frases como 'para aliviar el dolor', 'que tengan', 'busco'.
    Devuelve un JSON válido con la clave "termino".
    Ejemplo 1: "Quiero comprar un frasco de colágeno" -> {"termino": "colágeno"}
    Ejemplo 2: "¿Tienen pomadas para aliviar el dolor?" -> {"termino": "pomada"}
    Ejemplo 3: "Me duele la cabeza, tienen aspirinas?" -> {"termino": "aspirina"}"""
    
    respuesta = llamar_groq_completions(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": mensaje}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(respuesta.choices[0].message.content).get("termino", "")

async def consultar_producto_turso(termino: str) -> list:
    termino_sql = f"%{termino}%"
    consulta = """
    SELECT nombre_producto, marca, descripcion, precio1, slug,
           para_que_sirve, como_tomar, dosis, via_administracion,
           edad_recomendada, contraindicaciones, advertencias, recomendaciones,
           (stock > 0) AS disponible
    FROM productos 
    WHERE (nombre_producto LIKE ? OR descripcion LIKE ?) AND oculto = 0
    LIMIT 1
    """
    
    async with libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN) as db:
        resultado = await db.execute(consulta, [termino_sql, termino_sql])
        
        productos_encontrados = []
        for fila in resultado.rows:
            slug = fila[4]
            productos_encontrados.append({
                "nombre": fila[0],
                "marca": fila[1],
                "descripcion": fila[2],
                "precio": fila[3],
                "enlace": f"https://naturesgreenec.com/producto/{slug}" if slug else None,
                "para_que_sirve": fila[5],
                "como_tomar": fila[6],
                "dosis": fila[7],
                "via_administracion": fila[8],
                "edad_recomendada": fila[9],
                "contraindicaciones": fila[10],
                "advertencias": fila[11],
                "recomendaciones": fila[12],
                "disponible": bool(fila[13])
            })
        return productos_encontrados

def generar_respuesta_vendedor(termino: str, resultados_db: list) -> str:
    prompt = f"""Eres el vendedor de Nature's Green.
    El cliente busca: "{termino}".
    
    Resultado de la base de datos: {json.dumps(resultados_db, ensure_ascii=False)}
    
    Reglas:
    - Si la lista está vacía, di cortésmente que no encontraste ese producto y sugiere reformular.
    - Si hay resultado, responde ÚNICAMENTE con: nombre del producto, para qué sirve (1 sola frase corta), precio y si está disponible o no, y el enlace al final.
    - Nada más. Sin contraindicaciones, sin dosis, sin listas largas. Solo lo esencial.
    - Sé directo y natural. Máximo 3-4 líneas.
    """
    
    respuesta = llamar_groq_completions(
        model="openai/gpt-oss-20b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3
    )
    return respuesta.choices[0].message.content

async def ejecutar_fase_2(mensaje_usuario: str):
    termino_busqueda = extraer_termino_busqueda(mensaje_usuario)
    
    if not termino_busqueda:
        return "No pude identificar qué producto buscas. ¿Podrías ser más específico?"
        
    resultados_db = await consultar_producto_turso(termino_busqueda)
    respuesta_final = generar_respuesta_vendedor(mensaje_usuario, resultados_db)
    
    return respuesta_final

if __name__ == "__main__":
    print("Fase 2: Búsqueda de Productos Iniciada. (Escribe 'salir' para terminar)\n")
    while True:
        mensaje = input("Tú: ")
        if mensaje.lower() == 'salir':
            print("Cerrando prueba de Fase 2...")
            break
        respuesta_ia = asyncio.run(ejecutar_fase_2(mensaje))
        print(f"Nature's Green: {respuesta_ia}\n")