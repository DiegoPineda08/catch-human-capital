"""
dinamo/presentation/servidor.py
--------------------------------
API web que expone el motor DINAMO como servicio HTTP.

Endpoints:
  POST /preguntar   → recibe texto del usuario, devuelve RespuestaNarrativa en JSON
  POST /usuario     → configura el perfil de usuario activo
  GET  /health      → comprueba que el servidor está vivo

Arrancar en desarrollo:
  pip install fastapi uvicorn
  uvicorn dinamo.presentation.servidor:app --reload --port 8000

El frontend (frontend/index.html) apunta a http://localhost:8000 por defecto.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Motor principal
from dinamo.sistema import construir_sistema

# Capa de narrativa
from dinamo.presentation.narrativa import enriquecer_respuesta, a_dict


# ---------------------------------------------------------------------------
# Instancia del motor (singleton por proceso)
# ---------------------------------------------------------------------------

_brain = None


def _obtener_brain():
    global _brain
    if _brain is None:
        _brain = construir_sistema()
    return _brain


# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DINAMO Analytics",
    description="Motor de análisis conversacional de datos de Capital Humano",
    version="1.0.0",
)

# CORS: permite que el frontend (mismo origen o localhost) llame a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # en producción, restringir al dominio real
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir el frontend estático desde /frontend (si existe la carpeta)
_FRONTEND = Path(__file__).parent.parent.parent / "frontend"
if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")


# ---------------------------------------------------------------------------
# Modelos de request / response (Pydantic)
# ---------------------------------------------------------------------------

class PreguntaRequest(BaseModel):
    texto: str
    datos: str | None = None      # nombre del archivo/dataset activo (opcional)


class UsuarioRequest(BaseModel):
    nombre: str
    rol: str
    intereses: list[str] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def raiz():
    """Sirve el frontend si existe, o devuelve info de la API."""
    index = _FRONTEND / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"mensaje": "DINAMO API activa. Usa POST /preguntar para consultar."}


@app.get("/health")
def health():
    return {"estado": "ok", "version": "1.0.0"}


@app.post("/usuario")
def configurar_usuario(req: UsuarioRequest):
    """
    Cambia el perfil del usuario activo en el motor.
    Llamar antes de la primera pregunta para personalizar respuestas.
    """
    brain = _obtener_brain()
    brain.cambiar_usuario(
        nombre=req.nombre,
        rol=req.rol,
        intereses=req.intereses,
    )
    return {"mensaje": f"Usuario '{req.nombre}' configurado correctamente."}


@app.post("/preguntar")
def preguntar(req: PreguntaRequest):
    """
    Recibe una pregunta en lenguaje natural y devuelve una respuesta enriquecida.

    Response JSON:
    {
      "narrativa": "En enero de 2024, ventas arrancó en $105,543...",
      "grafica": {
        "tipo": "linea",
        "titulo": "Evolución de ventas",
        "unidad": "$",
        "datos": [{"etiqueta": "2024-01", "valor": 105543}, ...]
      },
      "sugerencias": ["¿Qué tiendas tienen mayor ventas?", ...],
      "intencion": "tendencia",
      "metrica": "ventas",
      "confianza": 0.8
    }
    """
    brain = _obtener_brain()

    try:
        resp = brain.responder(req.texto)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el motor: {e}")

    # Extraer campos del objeto respuesta del motor
    # (los nombres exactos dependen de la dataclass Respuesta en brain.py)
    texto_tecnico = getattr(resp, 'texto', str(resp))
    intencion     = getattr(resp, 'intencion', 'desconocida')
    metrica       = _extraer_metrica(resp)
    sugerencias   = getattr(resp, 'sugerencias', [])
    confianza     = getattr(resp, 'confianza', 1.0)

    # Enriquecer con narrativa y datos de gráfica
    narrativa_obj = enriquecer_respuesta(
        texto_tecnico=texto_tecnico,
        intencion=intencion,
        metrica=metrica,
        sugerencias=sugerencias,
        confianza=confianza,
    )

    return a_dict(narrativa_obj)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extraer_metrica(resp) -> str:
    """Intenta sacar la métrica principal de la respuesta del motor."""
    # Primero desde el plan si existe
    plan = getattr(resp, 'plan', None)
    if plan:
        metricas = getattr(plan, 'metricas', [])
        if metricas:
            return metricas[0]
    # Desde el texto: busca la primera palabra en minúscula entre «»
    import re
    texto = getattr(resp, 'texto', '')
    m = re.search(r'«([^»]+)»', texto)
    if m:
        return m.group(1)
    return 'datos'


# ---------------------------------------------------------------------------
# Arranque directo (python -m dinamo.presentation.servidor)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import uvicorn
    puerto = int(os.environ.get('DINAMO_PORT', 8000))
    uvicorn.run('dinamo.presentation.servidor:app', host='0.0.0.0', port=puerto, reload=True)
