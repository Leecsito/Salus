"""
logs.py — Sistema de logging profesional de SALUS.

Dos destinos:
  1. Consola (Render): formato clásico con hora, nivel y módulo.
  2. Buffer en memoria (últimas LOGS_BUFFER entradas): se expone en /api/logs
     y se visualiza en el panel de logs del frontend.

Nunca escribe a disco: en Render el filesystem es efímero y el buffer en
memoria es suficiente para depurar conversaciones en vivo.

Variables de entorno:
  LOG_LEVEL   — nivel mínimo (default INFO)
  LOGS_BUFFER — número de entradas conservadas en memoria (default 500)
"""
import logging
import os
from collections import deque
from datetime import datetime
from threading import Lock

def recortar(texto, limite: int = 160) -> str:
    """Acota el texto para que los logs no se saturen."""
    if texto is None:
        return ""
    texto = str(texto).replace("\n", " ")
    return texto if len(texto) <= limite else texto[:limite] + "…"

def mascara_key(api_key: str) -> str:
    """Muestra solo un fragmento de una API key (nunca la key completa)."""
    if not api_key:
        return "(vacía)"
    return f"{api_key[:9]}…{api_key[-4:]}" if len(api_key) > 15 else "…"

class BufferLogs(logging.Handler):
    """Handler que conserva las últimas N entradas en memoria (thread-safe)."""

    def __init__(self, max_entradas: int = 500):
        super().__init__()
        self._entradas = deque(maxlen=max_entradas)
        self._lock = Lock()

    def emit(self, record):
        try:
            with self._lock:
                self._entradas.append({
                    "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                    "nivel": record.levelname,
                    "modulo": record.name,
                    "mensaje": record.getMessage(),
                })
        except Exception:
            self.handleError(record)

    def ultimas(self, limite: int = 100) -> list:
        with self._lock:
            return list(self._entradas)[-limite:]

    def limpiar(self):
        """Vacía el buffer de logs (usado por POST /api/logs/clear)."""
        with self._lock:
            self._entradas.clear()

buffer_logs = BufferLogs(int(os.environ.get("LOGS_BUFFER", "500")))

_configurado = False

def configurar_logging():
    """Configura consola + buffer una sola vez. Idempotente."""
    global _configurado
    if _configurado:
        return

    raiz = logging.getLogger()
    raiz.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    formato = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-7s %(name)-20s %(message)s",
        datefmt="%H:%M:%S",
    )
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)
    raiz.addHandler(buffer_logs)

    for ruidoso in ("werkzeug", "httpx", "httpcore", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    _configurado = True
