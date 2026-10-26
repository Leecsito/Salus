"""
historial.py — Componente de historial clínico de SALUS (ESQUELETO).

Objetivo futuro: consultar y gestionar el expediente clínico del cliente.
Debe distinguir el motivo de ingreso:
  - consulta/gestión del expediente (petición explícita del cliente);
  - recopilación de antecedentes previa a un tratamiento (derivado desde
    atención o producto): al completar y validar el intake, es la ÚNICA fase
    que puede derivar a "tratamiento" (ver guarda en flujo.py).
Por ahora conserva el mensaje informativo que antes vivía en app.py.
"""
import logging

logger = logging.getLogger("salus.historial")

def responder(mensaje: str, historial: list):
    """
    Firma estándar de componente: (mensaje, historial) -> (respuesta, siguiente_fase, historial).

    TODO: definir el flujo de negocio del historial clínico (fuente de datos,
    datos a recopilar, validación, prompt del sistema y transiciones) antes de
    implementarlo. Hasta entonces, la fase "tratamiento" queda inaccesible.
    """
    logger.warning("Historial | componente sin implementar (esqueleto)")
    return "El módulo de historial clínico está en desarrollo. ¿Puedo ayudarte con algo más?", "historial", historial
