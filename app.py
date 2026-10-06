from flask import Flask, render_template, request, jsonify, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
import logging
import os
import time

from core.config import SECRET_KEY, validar_config
from core.logs import buffer_logs, configurar_logging, recortar
import flujo

configurar_logging()
logger = logging.getLogger("salus.app")

# Falla al arrancar si faltan variables críticas (mejor que fallar en la primera petición)
try:
    validar_config()
except EnvironmentError as e:
    logger.error("Configuración incompleta:\n%s", e)
    raise

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
    logger.error("Excepción no manejada: %s", e, exc_info=True)
    return jsonify({"respuesta": "Error inesperado. Intenta de nuevo."}), 500
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if 'fase' not in session:
        session['fase'] = flujo.FASE_INICIAL
        session['historial'] = []
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute;500 per day")
def chat():
    """
    Endpoint del chat: valida la petición, delega en el orquestador (flujo.py)
    y persiste la fase/historial resultantes en la sesión.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        logger.warning("Solicitud rechazada: sin JSON válido")
        return jsonify({"respuesta": "Solicitud inválida. Envía un JSON con el campo 'mensaje'."}), 400

    mensaje_usuario = data.get("mensaje", "").strip()
    if not mensaje_usuario:
        logger.warning("Solicitud rechazada: mensaje vacío")
        return jsonify({"respuesta": "El mensaje no puede estar vacío."}), 400

    # Inicializar sesión si está vacía (ej. primera visita o sesión expirada)
    if 'fase' not in session:
        session['fase'] = flujo.FASE_INICIAL
        session['historial'] = []

    fase_actual = session.get('fase', flujo.FASE_INICIAL)
    historial = session.get('historial', [])

    inicio = time.perf_counter()
    logger.info("→ POST /api/chat | fase=%s | mensaje=%r", fase_actual, recortar(mensaje_usuario))

    def ok(respuesta, fase):
        logger.info("← POST /api/chat | fase=%s | %.0f ms | respuesta=%r",
                    fase, (time.perf_counter() - inicio) * 1000, recortar(respuesta, 200))
        return jsonify({"respuesta": respuesta, "fase": fase})

    try:
        respuesta, nueva_fase, nuevo_historial = flujo.despachar(fase_actual, mensaje_usuario, historial)
        session['fase'] = nueva_fase
        session['historial'] = nuevo_historial
        session.modified = True
        return ok(respuesta, nueva_fase)

    except Exception as e:
        logger.error("Error procesando mensaje: %s", e, exc_info=True)
        return jsonify({"respuesta": "Lo siento, ocurrió un error al procesar tu mensaje. Intenta de nuevo."}), 500


@app.route("/api/logs")
@limiter.limit("60 per minute")
def ver_logs():
    """
    Expone las últimas entradas del buffer de logs para el panel de depuración.
    Abierto por defecto; si se define LOGS_TOKEN, exige ?token=... para verlo.
    """
    token = os.environ.get("LOGS_TOKEN", "")
    if token and request.args.get("token", "") != token:
        return jsonify({"respuesta": "Token de logs inválido."}), 403

    limite_arg = request.args.get("limit", "100")
    limite = int(limite_arg) if limite_arg.isdigit() else 100
    limite = max(1, min(limite, 500))
    return jsonify({"logs": buffer_logs.ultimas(limite)})


@app.route("/api/reset", methods=["POST"])
def reset():
    logger.info("↺ Sesión reiniciada por el usuario")
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
