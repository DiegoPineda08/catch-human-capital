"""
CATÁLOGO DE INTEGRACIONES con su estado REAL.

Estados: disponible · sin comprobar · sin configurar · sin conexión · limitada · error.
"disponible" sólo se muestra después de una comprobación real que respondió bien.
Ninguna clave se devuelve nunca: sólo si está configurada o no.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from dinamo.llm.proveedores import proveedores_configurados

from . import buscadores as bus

_CACHE: dict[str, tuple[float, str, str]] = {}
VIGENCIA = 300

SERVICIOS = [
    # id, nombre, categoría, variable de clave (None = no necesita), envía la consulta fuera, costo/límite
    ("tavily", "Tavily (búsqueda web y noticias)", "Investigación web", "TAVILY_API_KEY", True,
     "Sin clave: modo keyless con límite de uso. Con clave gratuita: 1.000 créditos/mes."),
    ("brave", "Brave Search", "Investigación web", "BRAVE_API_KEY", True, "Opcional. Plan gratuito con cuota mensual."),
    ("wikipedia", "Wikipedia", "Investigación web", None, True, "Gratuito, sin clave."),
    ("gdelt", "GDELT (noticias)", "Noticias", None, True, "Gratuito, sin clave."),
    ("openalex", "OpenAlex", "Artículos científicos", None, True, "Gratuito; OPENALEX_API_KEY opcional amplía el límite diario."),
    ("crossref", "Crossref", "Artículos científicos", None, True, "Gratuito, sin clave."),
    ("semantic_scholar", "Semantic Scholar", "Artículos científicos", None, True, "Gratuito con límite de frecuencia."),
    ("pubmed", "PubMed", "Artículos científicos", None, True, "Gratuito, sin clave."),
    ("banco_mundial", "Banco Mundial (indicadores)", "Estadísticas oficiales", None, True, "Gratuito, sin clave."),
]

PRUEBAS = {
    "tavily": lambda: bus.tavily("human resources employee turnover", 1),
    "brave": lambda: bus.brave("employee turnover", 1),
    "wikipedia": lambda: bus.wikipedia("rotación de personal", 1),
    "gdelt": lambda: bus.gdelt("employment", 1),
    "openalex": lambda: bus.openalex("employee turnover", 1),
    "crossref": lambda: bus.crossref("employee turnover", 1),
    "semantic_scholar": lambda: bus.semantic_scholar("employee turnover", 1),
    "pubmed": lambda: bus.pubmed("occupational burnout", 1),
    "banco_mundial": lambda: requests.get("https://api.worldbank.org/v2/country/MX/indicator/SL.UEM.TOTL.ZS",
                                          params={"format": "json", "per_page": 1}, timeout=(5, 10)).raise_for_status(),
}


def _probar(sid: str) -> tuple[str, str]:
    try:
        PRUEBAS[sid]()
        if sid == "tavily" and not os.getenv("TAVILY_API_KEY"):
            return "limitada", "Responde en modo sin clave (con límite de uso)."
        return "disponible", "Respondió correctamente."
    except bus.ErrorBuscador as exc:
        texto = str(exc)
        if "límite" in texto:
            return "limitada", texto
        if "sin conexión" in texto:
            return "sin conexión", texto
        return "error", texto
    except requests.RequestException as exc:
        return "sin conexión", type(exc).__name__
    except Exception as exc:
        return "error", type(exc).__name__


def integraciones(comprobar: bool = False) -> list[dict]:
    ahora = time.time()
    if comprobar:
        pendientes = [s[0] for s in SERVICIOS if not (s[3] and not os.getenv(s[3]) and s[0] != "tavily")]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for sid, (estado, detalle) in zip(pendientes, ex.map(_probar, pendientes)):
                _CACHE[sid] = (ahora, estado, detalle)
    filas = []
    for sid, nombre, cat, var, sale, costo in SERVICIOS:
        tiene_clave = bool(var and os.getenv(var, "").strip())
        if var and not tiene_clave and sid != "tavily":
            estado, detalle = "sin configurar", f"Agrega {var} al archivo .env para activarlo."
        elif sid in _CACHE and ahora - _CACHE[sid][0] < VIGENCIA:
            estado, detalle = _CACHE[sid][1], _CACHE[sid][2]
        else:
            estado, detalle = "sin comprobar", "Pulsa «Comprobar» para verificar la conexión."
        filas.append({"id": sid, "nombre": nombre, "categoria": cat, "estado": estado, "detalle": detalle,
                      "clave": var, "clave_configurada": tiene_clave, "envia_datos_fuera": sale, "costo": costo})
    for p in proveedores_configurados():
        filas.append({"id": f"llm_{p['proveedor']}", "nombre": p["etiqueta"], "categoria": "Modelo de lenguaje",
                      "estado": {"configurado": "sin comprobar"}.get(p["estado"], p["estado"]),
                      "detalle": f"Modelo: {p['modelo']}" if p["modelo"] else p["requisito"],
                      "clave": None if not p["nube"] else p["requisito"].split()[1], "clave_configurada": p["estado"] != "sin configurar",
                      "envia_datos_fuera": p["nube"], "costo": "Local, gratuito" if not p["nube"] else "Según el plan del proveedor"})
    filas.append({"id": "llm_navegador", "nombre": "IA en el navegador (WebLLM)", "categoria": "Modelo de lenguaje",
                  "estado": "sin comprobar", "detalle": "Descarga un modelo pequeño al navegador la primera vez (requiere WebGPU).",
                  "clave": None, "clave_configurada": False, "envia_datos_fuera": False, "costo": "Gratuito"})
    filas.append({"id": "avatar_labios", "nombre": "Avatar con sincronización labial (D-ID / HeyGen)", "categoria": "Avatar",
                  "estado": "sin configurar", "detalle": "No implementado: el avatar actual es una imagen con voz del navegador, "
                  "sin sincronización labial.", "clave": None, "clave_configurada": False, "envia_datos_fuera": True,
                  "costo": "De pago"})
    filas.append({"id": "supabase", "nombre": "Supabase (usuarios y sesiones)", "categoria": "Autenticación",
                  "estado": "sin configurar", "detalle": "Planificado para la Fase 2.", "clave": "SUPABASE_URL",
                  "clave_configurada": bool(os.getenv("SUPABASE_URL")), "envia_datos_fuera": True, "costo": "Plan gratuito"})
    return filas
