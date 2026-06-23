from flask import Flask, render_template, request, jsonify, session
import os
import asyncio
import sys

# Agregar la ruta actual para las importaciones
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import responder_recepcion
from asesoria.FASE1 import responder_asesoria
from producto.FASE1 import ejecutar_fase_2 as ejecutar_producto

app = Flask(__name__)
# Clave secreta fija para que las sesiones no se rompan entre reinicios
app.secret_key = os.environ.get("SECRET_KEY", "natures-green-secret-2026")

@app.route("/")
def index():
    # Inicializar estado si no existe
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Endpoint síncrono. La parte async de 'producto' se corre con asyncio.run().
    Flask con Gunicorn sync workers NO soporta 'async def' directamente.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"respuesta": "Solicitud inválida."}), 400

    mensaje_usuario = data.get("mensaje", "").strip()
    if not mensaje_usuario:
        return jsonify({"respuesta": "Mensaje vacío."}), 400

    # Inicializar sesión si viene sin datos (ej. sesión expirada)
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []

    fase_actual = session.get('fase', 'recepcion')
    historial = session.get('historial', [])

    try:
        if fase_actual == 'recepcion':
            respuesta_ia, intencion, nuevo_historial = responder_recepcion(mensaje_usuario, historial)
            session['historial'] = nuevo_historial

            if intencion not in ("pendiente", "error"):
                # Cambiar de fase y limpiar historial para la nueva
                session['fase'] = intencion
                session['historial'] = []

            # Forzar que Flask guarde los cambios en la sesión
            session.modified = True
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})

        elif fase_actual == 'asesoria':
            respuesta_ia, estado, producto_sugerido, nuevo_historial = responder_asesoria(mensaje_usuario, historial)
            session['historial'] = nuevo_historial

            if estado == "producto_encontrado" and producto_sugerido:
                session['fase'] = 'producto'
                session['historial'] = []
                # Ejecutamos la búsqueda del producto inmediatamente y la enviamos junto con la recomendación
                try:
                    resultado_producto = asyncio.run(ejecutar_producto(producto_sugerido))
                    respuesta_completa = f"{respuesta_ia}\n\n{resultado_producto}"
                except Exception as e_prod:
                    respuesta_completa = respuesta_ia

                session.modified = True
                return jsonify({"respuesta": respuesta_completa, "fase": "producto"})

            session.modified = True
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})

        elif fase_actual == 'producto':
            # asyncio.run() ejecuta la corrutina async de forma síncrona
            respuesta_ia = asyncio.run(ejecutar_producto(mensaje_usuario))
            session.modified = True
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})

        elif fase_actual == 'historial':
            return jsonify({
                "respuesta": "El módulo de historial clínico aún está en desarrollo. ¿Puedo ayudarte con algo más?",
                "fase": session['fase']
            })

        else:
            session.clear()
            return jsonify({"respuesta": "Sesión reiniciada. ¿En qué te puedo ayudar?", "fase": "recepcion"})

    except Exception as e:
        print(f"[ERROR en /api/chat]: {e}")
        return jsonify({"respuesta": "Ocurrió un error interno. Por favor intenta de nuevo."}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
