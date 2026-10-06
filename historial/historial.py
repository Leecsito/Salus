"""
historial.py — Componente de historial clínico de SALUS (ESQUELETO).

Objetivo futuro: consultar y gestionar el expediente clínico del cliente.
Por ahora conserva el mensaje informativo que antes vivía en app.py.
"""
import logging

logger = logging.getLogger("salus.historial")

def responder(mensaje: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    TODO: definir el flujo de negocio del historial clínico (fuente de datos,
    prompt del sistema y transiciones) antes de implementarlo.
    """
    logger.warning("Historial | componente sin implementar (esqueleto)")
    return "El módulo de historial clínico está en desarrollo. ¿Puedo ayudarte con algo más?", "historial", historial
