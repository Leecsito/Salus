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
    """
    responder = FASES.get(fase)
    if responder is None:
        logger.warning("Fase desconocida %r → reiniciando a %s", fase, FASE_INICIAL)
        return "Sesión reiniciada. ¿En qué te puedo ayudar?", FASE_INICIAL, []
    return responder(mensaje, historial)
