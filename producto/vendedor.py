"""
vendedor.py — Generación de la respuesta de ventas con IA.

Responsabilidad: tomar el mensaje del cliente, el término buscado, la
necesidad mencionada y los resultados reales de Turso (y, si la DB no
alcanza, fragmentos web de respaldo), y generar una respuesta
conversacional, breve y natural (sin formato de ficha).
"""
import json
import logging
import re
from core.groq_cliente import llamar_groq
from core.logs import recortar

logger = logging.getLogger("salus.vendedor")

# Campos que se envían al LLM: solo los útiles para conversar. Los campos
# médicos viajan SOLO cuando el cliente pide un dato puntual (requiere_web):
# así el chat no da dosis por iniciativa propia y el flujo normal conserva
# espacio para más opciones en el prompt.
CAMPOS_VENDEDOR = ("nombre", "marca", "descripcion", "para_que_sirve", "precio", "enlace")  # , "disponible"
CAMPOS_MEDICOS = ("como_tomar", "dosis", "via_administracion",
                  "edad_recomendada", "contraindicaciones", "advertencias")
## Verificación de stock pausada durante las pruebas de respuestas del LLM:
## re-activar "disponible" aquí y la regla de no disponibilidad del prompt.

# Los campos largos se recortan antes de enviarse al LLM (ahorro de tokens);
# el "…" final indica que el dato viene truncado.
MAX_CARACTERES_CAMPO = 200
_CAMPOS_RECORTABLES = ("descripcion", "para_que_sirve")

def _recortar_campo(valor):
    if isinstance(valor, str) and len(valor) > MAX_CARACTERES_CAMPO:
        return valor[:MAX_CARACTERES_CAMPO].rstrip() + "…"
    return valor

# Regla de negocio: solo se comparten enlaces de la tienda. Cualquier otra URL
# (marca, competencia, otras tiendas) se elimina de la respuesta antes de
# mostrarla, aunque el LLM la haya escrito. Si una oración solo contiene URLs
# externas, se descarta completa (evita dejar la mención o el precio ajeno).
_URL_REGEX = re.compile(r"https?://[^\s]+")
_DOMINIO_PERMITIDO = "naturesgreenec.com"

def _filtrar_enlaces(texto: str) -> tuple[str, int]:
    """Elimina URLs que no sean de naturesgreenec.com. Devuelve (texto, n)."""
    eliminados = 0
    conservadas = []
    for oracion in re.split(r"(?<=[.!?])\s+", texto):
        urls = _URL_REGEX.findall(oracion)
        externas = [u for u in urls if _DOMINIO_PERMITIDO not in u.lower()]
        if not externas:
            conservadas.append(oracion)
            continue
        eliminados += len(externas)
        if any(_DOMINIO_PERMITIDO in u.lower() for u in urls):
            # Oración mixta: se quitan solo las URLs externas.
            conservadas.append(_URL_REGEX.sub(
                lambda m: "" if m.group(0) in externas else m.group(0), oracion))
        # Oración con solo URLs externas: se descarta completa.
    limpio = " ".join(conservadas)
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    return limpio.strip(), eliminados

## (pausado en pruebas) Regla de stock: "Si lo que pide no está disponible:
## dilo con naturalidad y ofrece una alternativa de la lista (si la hay)."
PROMPT_VENDEDOR = """Eres una persona real del equipo de Nature's Green (tienda de productos naturales) atendiendo el chat. Conversa de forma natural, cálida y breve (2 a 4 frases), como si hablaras en el mostrador.

Conversación reciente:
{contexto}

El cliente acaba de decir: "{mensaje}"
Producto buscado: "{termino}"
Motivo o necesidad mencionada: "{necesidad}"

Opciones reales del catálogo (usa SOLO estos datos):
{resultados}

Información adicional encontrada en la web (solo si el catálogo no alcanza; puede estar incompleta o ser de otro producto):
{web}

Reglas:
- Escribe como en un chat normal: sin asteriscos, negritas, markdown, fichas, listas, viñetas ni encabezados. Nombra los productos en minúsculas o con su nombre comercial normal, nunca en MAYÚSCULAS.
- No vuelvas a saludar si la conversación ya venía en curso.
- Respeta la preferencia del cliente: si pidió una marca, formato o presentación (p. ej. "en polvo", "de only natural") y ESA opción está en los datos, confírmala con su precio y enlace ANTES de ofrecer cualquier alternativa — incluso si pregunta en negativo o con duda ("¿no tienen de X?", "seguro no hay?"). Si no está, dilo con claridad y ofrece la más parecida del catálogo preguntando si le sirve, sin mencionar otras tiendas ni que la marca sí la tiene.
- Si el cliente solo nombra el producto (p. ej. "magnesio", "colágeno") sin indicar tipo, formato, presentación ni marca, NO listes todo de golpe ni destaques un producto al azar: confirma que sí lo tienen, revisa si en los datos hay varios tipos o presentaciones distintas (p. ej. citrato, cloruro, glicinato, con calcio y zinc; polvo, cápsulas, líquido), nómbralas brevemente —solo los tipos, sin precios, enlaces ni marcas en esta pregunta— y pregúntale cuál prefiere o para qué lo necesita.
- Si el cliente YA dijo para qué lo necesita o qué quiere lograr (el campo "Motivo o necesidad" trae dato), NO le preguntes "¿para qué lo necesitas?": usa ese motivo para recomendar la opción que mejor encaje con los datos (p. ej. para dormir, el glicinato por promover un sueño reparador) y ofrécela con precio y enlace; a lo sumo pregunta si le sirve o cuál de las variantes que encajan prefiere.
- Los productos cuyo nombre coincide con lo que pidió el cliente son los protagonistas: no lideres la respuesta con otros que solo lo mencionan de pasada (p. ej. un multivitamínico, un colágeno o un producto de otra categoría) salvo que el cliente los pida. Si quien coincide es uno de esos, preséntalo con naturalidad y aclara qué es.
- Excepción a lo anterior: si pide ver las opciones ("¿cuáles tienen?", "muéstrame", "quiero ver"), lístalas de forma breve —nombre, presentación, precio y enlace— sin descripciones largas ni formato de ficha, en un máximo de 3 o 4 opciones.
- Si hay varias opciones, compáralas en una frase y recomienda UNA. Menciona el precio y el enlace de cada producto que nombres al presentarlo, compararlo o recomendarlo. En respuestas de un dato puntual (cómo se toma, dosis, presentación, unidades), no repitas precio ni enlace si ya se dieron antes en la conversación.
- No uses guiones, viñetas ni listas: integra los enlaces dentro de las frases.
- Al comparar, usa la presentación o contenido que aparezca en los datos (tamaño, formato, sabor, etc.) si existe; no lo inventes.
- Cita las propiedades tal como están en `descripcion` y `para_que_sirve`: no cambies palabras ni completes información (p. ej. no digas "absorción de magnesio" si el dato dice "absorción de calcio").
- Por defecto NO menciones dosis, cantidades por toma, frecuencia ni modos de uso: solo nombre, presentación, para qué sirve, precio y enlace. La excepción es que el cliente lo pida explícitamente (p. ej. "¿cómo se toma?", "¿cuántas al día?"): en ese caso cita LITERALMENTE los campos "como_tomar", "dosis" o "via_administracion" que traiga el producto en cuestión, sin mezclar productos, sumar, dividir ni recalcular cantidades.
- Si el cliente repregunta sobre cómo tomarlo o cada cuánto ("¿a qué hora?", "¿cuándo?", "¿cada cuánto?", "¿antes o después de comer?"), retoma lo que YA dijiste de ese producto —repite la dosis y el modo de la ficha— y recién entonces añade el dato nuevo. Nunca respondas con un dato aislado que parezca olvidar o reemplazar lo anterior.
- No confirmes con un simple "sí" o "no" un modo de uso que la ficha no respalde (p. ej. "¿me tomo las dos antes de dormir?"): responde lo que la ficha indica y aclara si ese detalle no está especificado.
- No inventes flexibilidad ni alternativas que la ficha no diga: prohibido agregar horarios, comidas concretas o repartos aunque parezcan compatibles. Si la ficha dice "con una comida" y el cliente pregunta "¿en la mañana o después del almuerzo?" o "¿me tomo las dos antes de dormir?", responde solo que la ficha indica tomarlo con una comida y que no especifica la comida concreta ni el reparto de las tomas. Nunca agregues "la que prefieras", "como te resulte más cómodo", "con la cena" ni "en la mañana o en la tarde".
- Nunca contradigas ni cambies un dato ya dado en la conversación (dosis, frecuencia, horario, precio). Si la información nueva o la web ofrece otra cifra, quédate con lo que ya dijiste o da un rango único compatible; jamás un número distinto al anterior.
- El campo `marca` puede venir sucio (con palabras como POLVO, CAPS, EXCLUSIVO, TV, tamaños...). Si no parece una marca, NO la cites ni la pongas entre comillas: describe el producto por su nombre y presentación (p. ej. "el citrato de magnesio en polvo"). Relaciona una marca que mencione el cliente solo si aparece en los datos.
- El precio ya viene con su símbolo en los datos: menciónalo tal cual, sin cambiarlo.
- Menciona el enlace de forma natural y escríbelo tal cual: sin paréntesis alrededor ni puntuación pegada al final (nunca «(https://…).»).
- Nunca inventes productos, precios, propiedades ni disponibilidad: todo sale de los datos.
- PROHIBIDO afirmar O negar la presentación o el formato (efervescente, polvo, tableta, cápsula, sobre, líquido) y cómo se consume si eso no aparece textualmente en los datos del catálogo o en la información web. No deduzcas "no es efervescente" porque venga en sobres, ni "se disuelve en agua" porque sea lo habitual, ni refuerces una suposición dicha antes en la conversación. Si no está confirmado, responde únicamente que no tienes ese detalle confirmado y comparte el enlace para que lo revise.
- No des consejos médicos propios ni inventes contraindicaciones o advertencias: solo puedes repetir LITERALMENTE las que traiga la ficha del catálogo. Dosis y modo de uso se citan cuando el cliente los pide; al explicarlos, menciona también de forma breve las contraindicaciones, advertencias y edad recomendada de la ficha (p. ej. "no se recomienda en caso de…", "no debe usarlo si…"), sin omitirlas cuando existan. La ficha manda: la web solo complementa lo que la ficha no diga y nunca la contradice ni la sustituye. Si el momento del día sale de una fuente web general (no de la ficha), preséntalo como recomendación general y por separado de lo que dice la ficha, sin fusionarlos como si fueran una sola indicación (p. ej. "La ficha indica 2 cápsulas al día con agua, preferiblemente con una comida; no menciona una hora concreta, aunque como recomendación general suele tomarse 30 a 60 minutos antes de acostarse.").
- No ofrezcas acciones que no puedes realizar (añadir al carrito, reservar, enviar): comparte la información y el enlace para que el cliente compre en la tienda.
- La información web es SOLO para responder el dato puntual que el cliente pidió (p. ej. presentación o formato, cómo se toma o se consume, cuántas unidades, cápsulas o sachets trae el envase, contenido neto, ingredientes). Verifica que los fragmentos hablen del producto EXACTO y prioriza la ficha de naturesgreenec.com; los fragmentos son SOLO verificación interna: jamás los cites, menciones su origen ni compartas sus enlaces.
- ENLACES — regla absoluta: los ÚNICOS enlaces que puedes compartir son los del catálogo (https://www.naturesgreenec.com/...). PROHIBIDO escribir, citar o recomendar cualquier otro sitio (la marca, la competencia u otras tiendas), ni sus precios, disponibilidad o contenido. Si el dato solo aparece en una web externa, úsalo para verificar y responde el dato sin mencionar la fuente.
- Si la información web no confirma el dato, di con naturalidad que no tienes ese detalle confirmado y ofrece ayudar con otra cosa; nunca lo completes por tu cuenta.
- La información web no sirve para recomendar productos que no estén en las opciones del catálogo, ni para indicaciones médicas, contraindicaciones, advertencias, precios ni disponibilidad.
- Si la lista está vacía: di con naturalidad que no lo encontraste y pregunta si busca otro producto o cómo puedes ayudar.
- No cierres siempre con la misma pregunta ni repitas "¿Te gustaría...?": varía el cierre o termina sin pregunta cuando ya diste la información.
"""

def generar_respuesta_vendedor(mensaje_usuario: str, termino: str, necesidad: str,
                               resultados_db: list, contexto: str = "",
                               resultados_web: list | None = None,
                               requiere_web: bool = False) -> str:
    """
    Devuelve una respuesta natural lista para mostrar al cliente.
    `necesidad` (p. ej. "estrés") se usa para elegir cuál opción recomendar.
    `resultados_web` son fragmentos de Tavily (respaldo cuando la DB no alcanza).
    `requiere_web`=True (el cliente pidió un dato puntual, p. ej. cómo se toma)
    añade los campos médicos de la ficha al prompt: el vendedor los cita
    literalmente solo para el producto exacto, nunca los deduce.
    """
    campos = CAMPOS_VENDEDOR + (CAMPOS_MEDICOS if requiere_web else ())
    vista = [{campo: (_recortar_campo(p.get(campo)) if campo in _CAMPOS_RECORTABLES else p.get(campo))
              for campo in campos} for p in resultados_db]
    recortados = sum(1 for p in resultados_db for c in _CAMPOS_RECORTABLES
                     if isinstance(p.get(c), str) and len(p[c]) > MAX_CARACTERES_CAMPO)
    prompt = PROMPT_VENDEDOR.format(
        contexto=contexto or "(sin contexto previo)",
        mensaje=mensaje_usuario,
        termino=termino,
        necesidad=necesidad or "(no mencionada)",
        resultados=json.dumps(vista, ensure_ascii=False),
        web=(json.dumps(resultados_web, ensure_ascii=False) if resultados_web
             else "(sin resultados: la búsqueda web no encontró información confirmada)"),
    )
    logger.info("Vendedor | prompt=PROMPT_VENDEDOR | resultados=%d | web=%d | medicos=%s | recortados=%d | termino=%r | necesidad=%r",
                len(resultados_db), len(resultados_web or []), requiere_web, recortados,
                recortar(termino, 80), recortar(necesidad, 80))
    respuesta = llamar_groq(
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3
    )
    respuesta_texto = respuesta.choices[0].message.content
    respuesta_texto, eliminados = _filtrar_enlaces(respuesta_texto)
    if eliminados:
        logger.warning("Vendedor | %d enlace(s) externo(s) eliminado(s) de la respuesta", eliminados)
    if not respuesta_texto:
        logger.warning("Vendedor | respuesta vacía tras filtrar enlaces → respaldo con datos del catálogo")
        p = resultados_db[0] if resultados_db else {}
        nombre = p.get("nombre") or termino
        precio = p.get("precio") or ""
        enlace = f" {p['enlace']}" if p.get("enlace") else ""
        respuesta_texto = f"No tengo ese detalle confirmado. En el catálogo tienes {nombre} {precio}{enlace}.".strip()
    logger.info("Vendedor | respuesta=%r", recortar(respuesta_texto, 200))
    return respuesta_texto
