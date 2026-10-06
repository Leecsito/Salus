"""
venta.py — Componente de venta de SALUS (ESQUELETO).

Objetivo futuro: gestionar el método de pago y el cierre de la venta.
Por ahora solo devuelve una respuesta placeholder.
"""
import logging

logger = logging.getLogger("salus.venta")

def responder(mensaje: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    TODO: definir el flujo de negocio de la venta (métodos de pago, cierre,
    transiciones y datos que necesite) antes de implementarlo.
    """
    logger.warning("Venta | componente sin implementar (esqueleto)")
    return "El módulo de venta aún no está disponible.", "venta", historial
