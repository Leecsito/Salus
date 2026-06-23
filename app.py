# pyrefly: ignore [missing-import]
from flask import Flask, render_template, request, jsonify, session
import os
import asyncio
import sys
import traceback

# Agregar la ruta actual para las importaciones
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import responder_recepcion
from asesoria.asesoria import responder_asesoria
from producto.producto import ejecutar_busqueda_producto as ejecutar_producto

# Mapa de fases -> info de debug (carpeta y módulo activo)
FASE_INFO = {
    "recepcion": {"carpeta": "/ (raíz)",  "modulo": "main.py"},
    "asesoria":  {"carpeta": "asesoria/", "modulo": "asesoria/asesoria.py"},
    "producto":  {"carpeta": "producto/", "modulo": "producto/producto.py → extractor.py → database.py → vendedor.py"},
    "historial": {"carpeta": "historial/","modulo": "historial/historial.py (pendiente)"},
}

app = Flask(__name__)
# Clave secreta fija para que las sesiones sobrevivan reinicios del servidor
app.secret_key = os.environ.get("SECRET_KEY", "natures-green-secret-2026")

# ── Handlers globales de error: SIEMPRE devuelven JSON, nunca HTML ──────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"respuesta": f"Ruta no encontrada: {e}"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"respuesta": f"Error interno del servidor: {e}"}), 500

@app.errorhandler(Exception)
def unhandled_exception(e):
    tb = traceback.format_exc()
    print(f"[EXCEPCIÓN NO MANEJADA]:\n{tb}")
    return jsonify({"respuesta": f"Error inesperado: {str(e)}"}), 500
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Endpoint síncrono principal del chatbot.
    La corrutina async de producto/FASE1.py se ejecuta con asyncio.run().
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"respuesta": "Solicitud inválida. Envía un JSON con el campo 'mensaje'."}), 400

    mensaje_usuario = data.get("mensaje", "").strip()
    if not mensaje_usuario:
        return jsonify({"respuesta": "El mensaje no puede estar vacío."}), 400

    # Inicializar sesión si está vacía (ej. primera visita o sesión expirada)
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []

    fase_actual = session.get('fase', 'recepcion')
    historial = session.get('historial', [])

    def ok(respuesta, fase):
        """Helper: construye la respuesta JSON con info de debug."""
        info = FASE_INFO.get(fase, {"carpeta": "?", "modulo": "?"})
        return jsonify({
            "respuesta": respuesta,
            "fase": fase,
            "debug": {
                "fase":    fase,
                "modulo":  info["modulo"],
                "carpeta": info["carpeta"],
            }
        })

    try:
        if fase_actual == 'recepcion':
            respuesta_ia, intencion, nuevo_historial = responder_recepcion(mensaje_usuario, historial)
            session['historial'] = nuevo_historial

            if intencion not in ("pendiente", "error"):
                session['fase'] = intencion
                session['historial'] = []

            session.modified = True
            return ok(respuesta_ia, session['fase'])

        elif fase_actual == 'asesoria':
            respuesta_ia, estado, producto_sugerido, nuevo_historial = responder_asesoria(mensaje_usuario, historial)
            session['historial'] = nuevo_historial

            if estado == "producto_encontrado" and producto_sugerido:
                session['fase'] = 'producto'
                session['historial'] = []
                try:
                    resultado_producto = asyncio.run(ejecutar_producto(producto_sugerido))
                    respuesta_completa = f"{respuesta_ia}\n\n{resultado_producto}"
                except Exception as e_prod:
                    print(f"[ERROR al buscar producto tras asesoría]: {e_prod}")
                    respuesta_completa = respuesta_ia

                session.modified = True
                return ok(respuesta_completa, "producto")

            session.modified = True
            return ok(respuesta_ia, session['fase'])

        elif fase_actual == 'producto':
            respuesta_ia = asyncio.run(ejecutar_producto(mensaje_usuario))
            session.modified = True
            return ok(respuesta_ia, session['fase'])

        elif fase_actual == 'historial':
            return jsonify({
                "respuesta": "El módulo de historial clínico está en desarrollo. ¿Puedo ayudarte con algo más?",
                "fase": session['fase']
            })

        else:
            session.clear()
            return jsonify({"respuesta": "Sesión reiniciada. ¿En qué te puedo ayudar?", "fase": "recepcion"})

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR en /api/chat]:\n{tb}")
        return jsonify({"respuesta": f"Error al procesar tu mensaje: {str(e)}"}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
