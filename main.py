import json
import time
from groq import Groq, APIError

API_KEYS = [
    "***GROQ_KEY_1_REMOVED***",
    "***GROQ_KEY_2_REMOVED***"
]

def obtener_cliente(indice_key: int) -> Groq:
    return Groq(api_key=API_KEYS[indice_key])

def chat_fase_1():
    prompt_sistema = """Eres el recepcionista virtual de Nature's Green. Hablas con calidez, empatía genuina y cercanía, como alguien que realmente se preocupa por la persona. Nunca suenas frío, robótico ni insistente. Tu objetivo es acompañar al cliente en la conversación hasta descubrir exactamente qué necesita, sin apresurarlo. Tus respuestas son siempre cortas: máximo 1-2 frases, sin rodeos ni texto de relleno.

    Debes clasificar su necesidad en una de estas 3 rutas:
    1. "producto": 
   - Intención: El cliente sabe EXACTAMENTE el nombre del producto, marca o compuesto que quiere comprar, buscar o cotizar. NO usa esta intención si está pidiendo recomendaciones o explicando síntomas.
   - Ejemplos: "¿Tienen colágeno?", "Busco aceite de romero", "¿Cuánto cuesta la pomada chuchuguazo?", "Quiero vitamina C".

    2. "asesoria": 
   - Intención: El cliente pide explícitamente una recomendación, consejo sobre qué hacer o qué tomar para aliviar un síntoma, dolencia o situación ("qué tienen para..."). Aún NO sabe qué producto exacto comprar.
   - Ejemplos: "¿Qué me recomiendas para este dolor de cabeza?", "¿Qué productos tienen para aliviar un golpe?", "¿Cómo trato la gastritis?".

    3. "historial": 
   - Intención: El cliente confirma explícitamente que quiere abrir o gestionar un expediente clínico.
   - Ejemplos: "Quiero abrir mi historial clínico", "Necesito actualizar mis alergias".

    REGLAS:
    - Nunca uses diminutivos, apodos o palabras inventadas (ej. "papú") para referirte a familiares; usa siempre el término exacto que use el cliente (ej. "papá", "padre").
    - Si el cliente solo saluda, cuenta una situación o describe síntomas/hechos (por ejemplo, un accidente o una herida) SIN pedir explícitamente un producto o una recomendación, tu 'intencion' es "pendiente". En tu 'respuesta' muestra empatía genuina por lo que cuenta y pregúntale con calidez, de forma distinta cada vez (sin repetir la misma pregunta), en qué le gustaría que le ayudes.
    - Frases como "no sé qué hacer", "ayúdame", "no sé" NO son una petición explícita de producto ni de tratamiento; siguen siendo "pendiente".
    - Nunca asumas la intención del cliente solo porque mencionó un síntoma, dolor o situación; espera a que lo pida explícitamente.
    - Si después de la situación/síntoma el cliente sigue sin especificar qué quiere, tu 'respuesta' debe preguntarle directamente y con calidez si prefiere que le recomiendes algo (asesoria) o que busques un producto puntual, manteniendo 'intencion' en "pendiente" hasta que el cliente confirme una de las dos opciones.
    - Si el cliente solo pregunta si existe el servicio de historial clínico (sin pedir abrirlo), tu 'intencion' sigue "pendiente"; en tu 'respuesta' confirma que existe y pregúntale si desea abrirlo.
    - Que el cliente mencione una palabra clave (ej. "producto") en pasado o de forma narrativa NO es una petición; sigue siendo "pendiente".
    - REGLA ESTRUCTURAL OBLIGATORIA: si tu 'respuesta' contiene una pregunta, tu 'intencion' DEBE ser "pendiente". Nunca pongas una intención distinta de "pendiente" en el mismo turno en que haces una pregunta.
    - Solo cuando el cliente confirme explícitamente que quiere buscar un producto exacto, recibir una recomendación/asesoría, o abrir su historial, cambia la 'intencion' a "producto", "asesoria" o "historial", y en tu 'respuesta' dale una frase de transición corta y cálida (ej: "Claro, dame un momento...").
    - Si el cliente pregunta algo totalmente ajeno a salud o farmacia (deportes, clima, etc.), tu 'intencion' sigue siendo "pendiente". En tu 'respuesta' acláralo de forma ligera y con humor, sin sonar cortante (ej: "Eso no lo sé, jaja, pero no tiene mucho que ver con lo que estamos viendo ahorita"), y de inmediato redirige amablemente al tema de salud/producto que estaba pendiente.
    
    EJEMPLO DE CONVERSACIÓN CORRECTA (síguelo como referencia exacta de comportamiento):
    Usuario: "tuve un problema con mi papá ayer"
    Tú: {"respuesta": "Lo siento mucho, espero que tu papá esté bien. ¿Podrías contarme un poco más sobre lo que pasó?", "intencion": "pendiente"}
    Usuario: "se fracturó una pierna"
    Tú: {"respuesta": "Ay, lo siento mucho. ¿Qué te gustaría que te ayude a hacer en este momento?", "intencion": "pendiente"}
    Usuario: "ya hice un tratamiento en el hospital y estamos en seguimiento todos los viernes"
    Tú: {"respuesta": "Entendido, qué bien que ya está en seguimiento. ¿Te gustaría que te recomiende algo para el dolor o prefieres buscar un producto puntual?", "intencion": "pendiente"}
    (Nota: la intención sigue "pendiente" porque aún no elige.)
    Usuario: "sí, recomiéndame algo"
    Tú: {"respuesta": "Claro, pasemos a revisar opciones para tu dolor...", "intencion": "asesoria"}

    Salida ESTRICTA en formato JSON:
    {"respuesta": "Lo que le dices al usuario", "intencion": "pendiente | producto | asesoria | historial"}"""

    # El historial arranca con las instrucciones del sistema
    historial = [{"role": "system", "content": prompt_sistema}]
    
    print("Chat Fase 1 Iniciado. (Escribe 'salir' para terminar)\n")
    
    while True:
        mensaje_usuario = input("Tú: ")
        if mensaje_usuario.lower() == 'salir':
            print("Cerrando chat...")
            break
            
        # 1. Guardar el mensaje del usuario en la memoria
        historial.append({"role": "user", "content": mensaje_usuario})
        
        for intento, key_index in enumerate(range(len(API_KEYS))):
            try:
                cliente = obtener_cliente(key_index)
                respuesta_api = cliente.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=historial,
                    temperature=0.3, # Un poco de temperatura para que la charla suene natural
                    response_format={"type": "json_object"}
                )
                
                datos = json.loads(respuesta_api.choices[0].message.content)
                respuesta_ia = datos.get("respuesta", "Error generando respuesta")
                intencion = datos.get("intencion", "pendiente")
                
                print(f"Nature's Green: {respuesta_ia}")
                
                # 2. Guardar la respuesta de la IA en la memoria para el próximo ciclo
                historial.append({"role": "assistant", "content": json.dumps(datos)})
                
                # 3. Condición de salida: Si ya descubrió qué quiere el usuario, termina la Fase 1
                if intencion != "pendiente":
                    print(f"\n[SISTEMA: Objetivo cumplido. Cerrando Fase 1 y pasando a Fase -> {intencion}]")
                    return intencion, mensaje_usuario 

                    
                break # Si la petición fue exitosa, rompemos el bucle de las API keys
                
            except APIError as e:
                if getattr(e, 'status_code', None) == 429 and intento < len(API_KEYS) - 1:
                    time.sleep(2)
                    continue
                print(f"\n[Error de API]: {e}")
                return "error"

import asyncio
import sys
import os

# Aseguramos que la carpeta raíz esté en el path para poder importar desde "producto"
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from producto.FASE1 import ejecutar_fase_2 as ejecutar_producto
from asesoria.FASE1 import ejecutar_fase_asesoria

if __name__ == "__main__":
    resultado = chat_fase_1()
    
    if isinstance(resultado, tuple):
        intencion, mensaje_usuario = resultado
        
        if intencion == "asesoria":
            print("\n--- INICIANDO FASE DE ASESORÍA ---")
            # La asesoría podría retornar un producto recomendado
            intencion_post_asesoria, producto_sugerido = asyncio.run(ejecutar_fase_asesoria(mensaje_usuario))
            
            if intencion_post_asesoria == "ir_a_producto":
                print("\n[SISTEMA: Asesoría completada. Pasando automáticamente a Búsqueda de Producto]")
                intencion = "producto"
                mensaje_usuario = producto_sugerido # Cambiamos el mensaje para que busque el producto sugerido
        
        if intencion == "producto":
            print("\n--- INICIANDO FASE DE PRODUCTO ---")
            while True:
                respuesta_producto = asyncio.run(ejecutar_producto(mensaje_usuario))
                print(f"Nature's Green: {respuesta_producto}")
                
                mensaje_usuario = input("Tú: ")
                if mensaje_usuario.lower() == 'salir':
                    print("Cerrando chat...")
                    break
                    
        elif intencion == "historial":
            print("\n[SISTEMA: El módulo para 'historial' aún no está implementado.]")
    elif resultado == "error":
        print("Ocurrió un error en la Fase 1.")