from flask import Flask, render_template, request, jsonify, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
import os
import asyncio
import sys
import traceback

# Agregar la ruta actual para las importaciones
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import SECRET_KEY, validar_config
from main import responder_recepcion
from asesoria.asesoria import responder_asesoria
from producto.producto import ejecutar_busqueda_producto as ejecutar_producto

# Falla al arrancar si faltan variables críticas (mejor que fallar en la primera petición)
validar_config()

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Cookies de sesión: no accesibles por JS y solo por HTTPS en producción (Render)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

# Límite de peticiones por IP para proteger la cuota gratuita de Groq
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ── Handlers globales de error: SIEMPRE devuelven JSON, nunca HTML ──────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"respuesta": "Ruta no encontrada."}), 404

@app.errorhandler(429)
def rate_limit(e):
    return jsonify({"respuesta": "Estás enviando mensajes muy rápido. Espera un momento e intenta de nuevo."}), 429

@app.errorhandler(500)
def server_error(e):
    return jsonify({"respuesta": "Error interno del servidor."}), 500

@app.errorhandler(Exception)
def unhandled_exception(e):
    if isinstance(e, HTTPException):
        return jsonify({"respuesta": f"Error {e.code}: {e.name}"}), e.code
    print(f"[EXCEPCIÓN NO MANEJADA]:\n{traceback.format_exc()}")
    return jsonify({"respuesta": "Error inesperado. Intenta de nuevo."}), 500
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute;500 per day")
def chat():
    """
    Endpoint síncrono principal del chatbot.
    La corrutina async de producto/producto.py se ejecuta con asyncio.run().
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
        return jsonify({"respuesta": respuesta, "fase": fase})

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

    except Exception:
        print(f"[ERROR en /api/chat]:\n{traceback.format_exc()}")
        return jsonify({"respuesta": "Lo siento, ocurrió un error al procesar tu mensaje. Intenta de nuevo."}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
