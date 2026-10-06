"""
config.py — Configuración centralizada del proyecto SALUS (core).

Este es el ÚNICO lugar donde se leen las variables de entorno.
Todos los demás módulos importan desde aquí:

    from core.config import API_KEYS, TURSO_URL, TURSO_TOKEN

Para desarrollo local: crea un archivo .env en la raíz del proyecto (ver .env.example).
Para producción (Render): define las variables en el dashboard de Render → Environment.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # No hace nada en producción (Render inyecta las vars directamente)

# ── Groq ──────────────────────────────────────────────────────────────────────
# Múltiples keys separadas por coma: "key1,key2,key3"
_raw_keys = os.environ.get("GROQ_API_KEYS", "")
API_KEYS: list[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Modelo usado en todo el proyecto (se puede cambiar sin tocar código con GROQ_MODEL)
MODELO: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

# ── Producto ──────────────────────────────────────────────────────────────────
# Turnos recientes que se pasan como contexto al extractor y al vendedor
HISTORIAL_TURNOS: int = int(os.environ.get("HISTORIAL_TURNOS", "4"))
# Máximo de productos que devuelve Turso y recibe el vendedor
LIMITE_PRODUCTOS: int = int(os.environ.get("LIMITE_PRODUCTOS", "3"))

# ── Turso ─────────────────────────────────────────────────────────────────────
TURSO_URL: str = os.environ.get("TURSO_URL", "")
TURSO_TOKEN: str = os.environ.get("TURSO_TOKEN", "")

# ── Flask ─────────────────────────────────────────────────────────────────────
# Sin default inseguro: es obligatoria (ver validar_config).
SECRET_KEY: str = os.environ.get("SECRET_KEY", "")

# ── Validación al arrancar ────────────────────────────────────────────────────
def validar_config():
    """Lanza un error claro si faltan variables críticas."""
    errores = []
    if not API_KEYS:
        errores.append("GROQ_API_KEYS no está definida o está vacía.")
    if not TURSO_URL:
        errores.append("TURSO_URL no está definida.")
    if not TURSO_TOKEN:
        errores.append("TURSO_TOKEN no está definida.")
    if not SECRET_KEY:
        errores.append("SECRET_KEY no está definida (genera una aleatoria, ver .env.example).")
    if errores:
        raise EnvironmentError(
            "Faltan variables de entorno requeridas:\n" + "\n".join(f"  - {e}" for e in errores)
        )
