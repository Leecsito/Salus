"""
contexto.py — Contexto conversacional para el componente producto.

Convierte el historial de sesión (formato OpenAI) en un transcript plano de
los últimos N turnos, para que el extractor y el vendedor puedan resolver
referencias como "ese", "el otro", "y bueno?" o "y solo tienen ese?".

Detalles:
- Ignora los mensajes de sistema (prompts de fases anteriores).
- Si un mensaje del asistente es un JSON con clave "respuesta" (p. ej. el de
  la fase de atención), usa esa respuesta en lugar del JSON crudo.
"""
import json

def formatear_contexto(historial: list, turnos: int) -> str:
    """
    Devuelve un transcript plano con los últimos `turnos` intercambios.
    Si no hay mensajes utilizables, devuelve cadena vacía.
    """
    if not historial or turnos <= 0:
        return ""

    mensajes = [m for m in historial if m.get("role") in ("user", "assistant")]
    mensajes = mensajes[-(turnos * 2):]

    lineas = []
    for m in mensajes:
        contenido = m.get("content", "") or ""
        if m.get("role") == "assistant":
            try:
                datos = json.loads(contenido)
                if isinstance(datos, dict) and "respuesta" in datos:
                    contenido = str(datos["respuesta"])
            except (ValueError, TypeError):
                pass
            lineas.append(f"Bot: {contenido}")
        else:
            lineas.append(f"Cliente: {contenido}")

    return "\n".join(lineas)
