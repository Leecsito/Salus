from flask import Flask, render_template, request, jsonify, session
import os
import secrets
import asyncio
import sys

# Agregar la ruta actual para las importaciones
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import responder_recepcion
from asesoria.FASE1 import responder_asesoria
from producto.FASE1 import ejecutar_fase_2 as ejecutar_producto

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

@app.route("/")
def index():
    # Inicializar estado si no existe
    if 'fase' not in session:
        session['fase'] = 'recepcion'
        session['historial'] = []
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
async def chat():
    data = request.get_json()
    mensaje_usuario = data.get("mensaje", "")
    
    if not mensaje_usuario:
        return jsonify({"respuesta": "Mensaje vacío"}), 400

    fase_actual = session.get('fase', 'recepcion')
    historial = session.get('historial', [])
    
    try:
        if fase_actual == 'recepcion':
            respuesta_ia, intencion, nuevo_historial = responder_recepcion(mensaje_usuario, historial)
            
            # Guardamos el nuevo historial
            session['historial'] = nuevo_historial
            
            # Verificamos si cambió de intención
            if intencion != "pendiente":
                session['fase'] = intencion
                # Reiniciamos el historial para la nueva fase
                session['historial'] = []
                
                # Si el usuario pidió asesoría o producto y la IA solo dio una transición, podemos enviarla
                # O si es automático, pasamos a la siguiente fase y la ejecutamos de una vez
                if intencion == "asesoria":
                    # Forzamos un primer mensaje oculto en la nueva fase o enviamos la transición
                    pass
                elif intencion == "producto":
                    # Ejecutamos búsqueda del producto directamente con el mismo mensaje si es necesario
                    # Pero en la respuesta de transición de Fase 1 ya le decimos "dame un momento..."
                    pass
                    
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})
            
        elif fase_actual == 'asesoria':
            respuesta_ia, estado, producto_sugerido, nuevo_historial = responder_asesoria(mensaje_usuario, historial)
            session['historial'] = nuevo_historial
            
            if estado == "producto_encontrado" and producto_sugerido:
                session['fase'] = 'producto'
                session['historial'] = []
                
                # Opcional: Podríamos ejecutar la búsqueda de una vez y enviarla
                # Para simplificar, enviamos la recomendación y el frontend hará la transición
                return jsonify({
                    "respuesta": f"{respuesta_ia} [SISTEMA: Pasando a buscar {producto_sugerido}...]", 
                    "fase": "producto"
                })
                
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})
            
        elif fase_actual == 'producto':
            # La fase de producto usa await porque hace llamadas a la BD
            respuesta_ia = await ejecutar_producto(mensaje_usuario)
            return jsonify({"respuesta": respuesta_ia, "fase": session['fase']})
            
        elif fase_actual == 'historial':
            return jsonify({"respuesta": "[SISTEMA: El módulo de historial no está implementado en esta versión.]", "fase": session['fase']})
            
    except Exception as e:
        print(f"Error en endpoint chat: {e}")
        return jsonify({"respuesta": "Ocurrió un error en el servidor."}), 500

@app.route("/api/reset", methods=["POST"])
def reset():
    session.clear()
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
