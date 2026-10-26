"""
tratamiento.py — Componente de tratamiento de SALUS (ESQUELETO).

Objetivo futuro: recomendar un conjunto de productos para un malestar
concreto. Por ahora solo devuelve una respuesta placeholder.
"""
import logging

logger = logging.getLogger("salus.tratamiento")

def responder(mensaje: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    TODO: definir el flujo de negocio del tratamiento (prompt del sistema,
    criterios de recomendación, transiciones y datos que necesite) antes de
    implementarlo. Debe ser defensivo: sin datos clínicos validados debe
    redirigir a "historial" (la guarda central vive en flujo.py).
    """
    logger.warning("Tratamiento | componente sin implementar (esqueleto)")
    return "El módulo de tratamiento aún no está disponible.", "tratamiento", historial
