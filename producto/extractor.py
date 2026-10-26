"""
extractor.py — Extracción del término, la necesidad y la intención.

Responsabilidad: usar IA para interpretar el mensaje del cliente con ayuda de
la conversación reciente, resolviendo referencias ("ese", "el otro",
"y bueno?", "y solo tienen ese?") y devolviendo un JSON estricto con:
  - termino:     sustantivo principal del producto (singular, sin frases extra
    ni dosis/tamaños, salvo que el cliente pregunte por una presentación
    concreta; en comparaciones usa el nombre común de la familia)
  - necesidad:   uso, síntoma o motivo mencionado (ej. "estrés")
  - intencion:   "producto" | "tratamiento" | "venta"
  - requiere_web: true solo si pide un dato puntual que la ficha del catálogo
    no suele traer (presentación o formato: efervescente, polvo, tableta,
    cápsula, sobre, líquido; cómo se toma o se consume; unidades del envase,
    contenido neto, ingredientes, sabor, origen, certificaciones): dispara la
    búsqueda web de respaldo.

Usa un modelo propio (`GROQ_MODEL_EXTRACCION`, default openai/gpt-oss-120b)
para repartir la cuota diaria de tokens de Groq con el vendedor (20b). Si el
429 es por tokens/día no reintenta: devuelve `fallo=True` para que producto.py
reutilice el último término de la conversación.
"""
import json
import logging
from core.config import MODELO_EXTRACCION
from core.groq_cliente import llamar_groq, es_limite_diario
from core.logs import recortar

logger = logging.getLogger("salus.extractor")

PROMPT_EXTRACCION = """Eres el extractor de productos de Nature's Green. Analiza el mensaje del cliente junto con la conversación reciente y devuelve SOLO un JSON válido con estas claves:

- "termino": el sustantivo principal del producto del que se habla o que se busca, en SINGULAR y sin frases adicionales (ej. "colágeno", "pomada", "citrato de magnesio"). Si no puedes identificar ningún producto, usa "".
- "necesidad": el uso, síntoma o motivo que menciona el cliente (ej. "estrés", "dolor de cabeza"). Usa "" si no menciona ninguno.
- "intencion": "producto" si pregunta por un producto, sus opciones, precios, comparaciones o detalles de algo que ya se le mostró; "tratamiento" SOLO si pide explícitamente un tratamiento, plan o protocolo para un malestar (p. ej. "quiero un tratamiento para la próstata"), sin referirse a productos ya mostrados; "venta" si quiere comprar, pagar o recibir el producto.
- "requiere_web": true SOLO si el cliente pide un dato puntual del producto que una ficha de catálogo no suele traer: presentación o formato (si es efervescente, polvo, tableta, cápsula, sobre, líquido; cómo se toma o se consume), cuántas unidades/cápsulas/sachets/tabletas trae el envase, contenido neto, ingredientes, sabor, origen o certificaciones. false para precio, disponibilidad, para qué sirve, comparaciones, referencias ("y bueno?") o conversación general.

REGLAS:
- Usa la conversación reciente para resolver referencias como "ese", "el otro", "y bueno?", "y solo tienen ese?": en esos casos el término es el producto del que se venía hablando.
- Si el producto ya aparece escrito en la conversación reciente, COPIA su nombre tal cual está ahí (no lo reescribas de memoria ni cambies letras u orden): el catálogo lo busca por coincidencia de texto.
- "termino" no debe llevar dosis, concentración ni tamaño del envase ("600 mg", "2000 UI", "100 cápsulas") salvo que el cliente pregunte por una presentación concreta (p. ej. "¿el de 600 mg?", "¿la de 2000 UI?"): en ese caso consérvala tal cual.
- Si el cliente compara o elige entre variantes ya mostradas ("el de $20", "el de $30", "el otro", "cuál me conviene", "qué diferencia tiene con..."), usa el nombre común de la familia sin dosis ni tamaños (p. ej. "magnesio glicinato") para que el catálogo devuelva todas las variantes.
- Si el cliente pide una recomendación o elección ("¿cuál me recomendaría?") y el producto o categoría del que se venía hablando está en la conversación, usa ese nombre (p. ej. "magnesio") aunque el mensaje no lo repita.
- No incluyas síntomas, usos ni frases como "para el estrés" dentro de "termino".
- Conserva los nombres compuestos completos (p. ej. "citrato de magnesio", "omega 3", "vitamina c"): no los recortes a una sola palabra.
- Ignora verbos y frases como "busco", "tienen", "cuáles dispone".
- "requiere_web" no cambia "intencion" ni "termino": solo marca que hace falta un dato extra.
- Comparar o elegir entre productos ya mostrados ("cuál de los dos es mejor para dormir?", "cuál me conviene?", "y el de $30?", "cuál trae más?") es SIEMPRE "producto", aunque mencione un síntoma o uso.
- Mencionar un síntoma, uso o beneficio ("mejor para dormir", "para el estrés", "para la próstata") NO convierte la intención en "tratamiento": eso solo ocurre si pide un tratamiento/plan como tal.
- Ante la duda entre "producto" y "tratamiento", elige "producto".

EJEMPLOS:
- Mensaje: "Quiero comprar un frasco de colágeno" -> {"termino": "colágeno", "necesidad": "", "intencion": "producto", "requiere_web": false}
- Mensaje: "¿Tienen pomadas para aliviar un dolor muscular?" -> {"termino": "pomada", "necesidad": "dolor muscular", "intencion": "producto", "requiere_web": false}
- Conversación: el cliente venía preguntando por "citrato de magnesio" para el estrés. Mensaje: "y bueno?" -> {"termino": "citrato de magnesio", "necesidad": "estrés", "intencion": "producto", "requiere_web": false}
- Conversación: se acaba de mostrar un producto. Mensaje: "y solo tienen ese?" -> {"termino": "<el producto del contexto>", "necesidad": "", "intencion": "producto", "requiere_web": false}
- Conversación: se acaba de mostrar "vitamagnesio plus". Mensaje: "y cuántas cápsulas trae?" -> {"termino": "vitamagnesio plus", "necesidad": "", "intencion": "producto", "requiere_web": true}
- Conversación: se acaba de mostrar "triple c advance vitamina c 1000 mg". Mensaje: "¿y esas tabletitas son efervescentes o se tragan con agua?" -> {"termino": "triple c advance vitamina c 1000 mg", "necesidad": "", "intencion": "producto", "requiere_web": true}
- Conversación: se acaba de recomendar el "glicinato de magnesio" de VITAHEALTH. Mensaje: "¿cómo se toma?" -> {"termino": "glicinato de magnesio de VITAHEALTH", "necesidad": "", "intencion": "producto", "requiere_web": true}
- Conversación: se mostraron el glicinato de $20 y el de $30. Mensaje: "y cuál de los dos es mejor para dormir?" -> {"termino": "glicinato de magnesio", "necesidad": "dormir", "intencion": "producto", "requiere_web": false}
- Conversación: se mostraron "Magnesio Glicinato 600 mg" ($30) y "GLICINATO DE MAGNESIO" de VITAHEALTH ($20). Mensaje: "Ah, entonces el de $30 trae 100 cápsulas. ¿Y qué diferencia tiene con el de $20? ¿Cuál me conviene más?" -> {"termino": "magnesio glicinato", "necesidad": "", "intencion": "producto", "requiere_web": false}
- Conversación: se acaba de mostrar "Magnesio Glicinato 600 mg". Mensaje: "¿ese de 600 mg cuántas cápsulas trae?" -> {"termino": "magnesio glicinato 600 mg", "necesidad": "", "intencion": "producto", "requiere_web": true}
- Conversación: el cliente venía preguntando por magnesio para el cansancio y el bot le mostró citrato, glicinato y cloruro. Mensaje: "Lo necesito porque me siento cansado, aunque duermo bien. ¿Cuál me recomendaría?" -> {"termino": "magnesio", "necesidad": "cansancio", "intencion": "producto", "requiere_web": false}
- Mensaje: "quiero un tratamiento para el estrés" -> {"termino": "", "necesidad": "estrés", "intencion": "tratamiento", "requiere_web": false}
- Mensaje: "quiero un tratamiento para la inflamación de la próstata" -> {"termino": "", "necesidad": "inflamación de la próstata", "intencion": "tratamiento", "requiere_web": false}
- Mensaje: "cómo hago para comprar el citrato?" -> {"termino": "citrato", "necesidad": "", "intencion": "venta", "requiere_web": false}

Salida ESTRICTA en JSON con las cuatro claves."""

def _parsear_json(texto: str) -> dict:
    """Parsea el JSON del modelo tolerando cercas de markdown o texto alrededor."""
    limpio = (texto or "").strip()
    try:
        return json.loads(limpio)
    except ValueError:
        inicio, fin = limpio.find("{"), limpio.rfind("}")
        if inicio == -1 or fin <= inicio:
            raise
        return json.loads(limpio[inicio:fin + 1])

def _sin_datos(limite_diario: bool = False) -> dict:
    """Degradación segura: `fallo` activa el respaldo de término en producto.py."""
    return {"termino": "", "necesidad": "", "intencion": "producto",
            "requiere_web": False, "fallo": True, "limite_diario": limite_diario}

def extraer_termino(mensaje: str, contexto: str = "") -> dict:
    """
    Devuelve {"termino", "necesidad", "intencion", "requiere_web", "fallo", "limite_diario"}.
    `fallo`=True cuando ninguna llamada logró datos: producto.py reutiliza el
    último término/necesidad de la conversación en vez de repreguntar.
    Si el 429 es por tokens/día (TPD) no se reintenta (la cuota no se recupera).
    `contexto` es el transcript de los últimos turnos (ver producto/contexto.py).
    """
    logger.info("Extractor | prompt=PROMPT_EXTRACCION | modelo=%s | mensaje=%r | contexto=%r",
                MODELO_EXTRACCION, recortar(mensaje), recortar(contexto, 120))
    mensajes = [
        {"role": "system", "content": PROMPT_EXTRACCION},
        {"role": "user", "content": f"Conversación reciente:\n{contexto or '(sin contexto previo)'}\n\nMensaje del cliente: {mensaje}"}
    ]
    try:
        respuesta = llamar_groq(messages=mensajes, model=MODELO_EXTRACCION, temperature=0,
                                response_format={"type": "json_object"})
        datos = _parsear_json(respuesta.choices[0].message.content)
    except Exception as e:
        if es_limite_diario(e):
            logger.error("Extractor | límite diario de Groq agotado (%s) → sin reintento", e)
            return _sin_datos(limite_diario=True)
        # Groq a veces responde 400 json_validate_failed con generación vacía en
        # modo JSON estricto. El reintento conserva el mismo contexto y prompt
        # pero SIN response_format (otro modo de generación esquiva el fallo).
        logger.warning("Extractor | falló la extracción (%s) → reintento sin modo JSON", e)
        try:
            respuesta = llamar_groq(messages=mensajes, model=MODELO_EXTRACCION, temperature=0)
            datos = _parsear_json(respuesta.choices[0].message.content)
        except Exception as e2:
            logger.error("Extractor | falló también el reintento (%s) → sin datos de extracción", e2)
            return _sin_datos(limite_diario=es_limite_diario(e2))
    termino = str(datos.get("termino", "")).strip()
    necesidad = str(datos.get("necesidad", "")).strip()
    intencion = str(datos.get("intencion", "producto")).strip().lower()
    if intencion not in ("producto", "tratamiento", "venta"):
        intencion = "producto"
    requiere_web = str(datos.get("requiere_web", "")).strip().lower() in ("true", "1", "sí", "si", "yes")

    logger.info("Extractor | término=%r | necesidad=%r | intencion=%s | requiere_web=%s",
                termino, recortar(necesidad, 80), intencion, requiere_web)
    return {"termino": termino, "necesidad": necesidad, "intencion": intencion,
            "requiere_web": requiere_web, "fallo": False, "limite_diario": False}
