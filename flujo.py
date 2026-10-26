"""
flujo.py — Orquestador central de fases de SALUS.

Único lugar que conoce el mapa de fases y aplica las transiciones. Para
agregar un componente nuevo basta con:
  1. Crear su paquete con un módulo que exponga `responder(mensaje, historial)`
     con firma: (respuesta, siguiente_fase, historial).
  2. Registrarlo en el diccionario FASES (y ajustar FASE_INICIAL si aplica).
`app.py` no necesita cambios.
"""
import logging

from saludo import saludo as comp_saludo
from atencion import atencion as comp_atencion
from asesoria import asesoria as comp_asesoria
from producto import producto as comp_producto
from tratamiento import tratamiento as comp_tratamiento
from venta import venta as comp_venta
from historial import historial as comp_historial

logger = logging.getLogger("salus.flujo")

# Fase con la que arranca toda conversación nueva.
FASE_INICIAL = "saludo"

# Regla de negocio: SOLO el historial clínico puede derivar a tratamiento
# (y, cuando implemente el intake, solo con la validación completa). La guarda
# es estructural: no depende de que el LLM clasifique bien la intención.
ORIGENES_PERMITIDOS_A_TRATAMIENTO = ("historial",)

TRANSICION_A_HISTORIAL = ("Para recomendarte un tratamiento necesito primero revisar tus "
                          "antecedentes de salud. Empecemos por tu historial clínico.")

# Registro de fases → función de entrada del componente.
FASES = {
    "saludo":      comp_saludo.responder,
    "atencion":    comp_atencion.responder,
    "asesoria":    comp_asesoria.responder,
    "producto":    comp_producto.responder,
    "tratamiento": comp_tratamiento.responder,
    "venta":       comp_venta.responder,
    "historial":   comp_historial.responder,
}

def despachar(fase: str, mensaje: str, historial: list):
    """
    Envía el mensaje al componente de la fase actual.
    Devuelve (respuesta, siguiente_fase, historial).
    Si la fase no existe, reinicia la conversación en FASE_INICIAL.
    Guarda central: si un componente intenta derivar a "tratamiento" desde una
    fase que no es "historial", la transición se bloquea y se redirige al
    historial clínico.
    """
    responder = FASES.get(fase)
    if responder is None:
        logger.warning("Fase desconocida %r → reiniciando a %s", fase, FASE_INICIAL)
        return "Sesión reiniciada. ¿En qué te puedo ayudar?", FASE_INICIAL, []

    respuesta, siguiente_fase, historial_actualizado = responder(mensaje, historial)

    if siguiente_fase == "tratamiento" and fase not in ORIGENES_PERMITIDOS_A_TRATAMIENTO:
        # TODO: al implementar historial, exigir además que el intake esté validado.
        logger.warning("Transición a tratamiento bloqueada desde %r → historial clínico", fase)
        return TRANSICION_A_HISTORIAL, "historial", []

    return respuesta, siguiente_fase, historial_actualizado
