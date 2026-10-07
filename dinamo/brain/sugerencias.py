"""
SUGERENCIAS: las siguientes preguntas que DINAMO propone al usuario.

Esto vuelve la conversación interactiva: el usuario no necesita saber qué preguntar.
Las sugerencias son determinísticas (no las inventa el LLM) y sólo proponen lo que el
sistema PUEDE responder con la base cargada: si la base no tiene tiempo, no sugiere
"¿cómo ha evolucionado...?"; si todavía no existe la Skill de comparar, no sugiere comparar.
Cada sugerencia está escrita para que el Intérprete la entienda (hay un test que lo verifica).
"""
from __future__ import annotations

from typing import Any

from dinamo.core.contracts import PerfilDataset, Plan

MAX_SUGERENCIAS = 3

# Qué conviene preguntar después de cada intención (en orden de preferencia).
SIGUIENTES = {
    "describir_datos": ("tendencia", "ranking", "comparar_grupos", "relaciones", "ranking_otra"),
    "desconocida": ("describir_datos", "tendencia", "ranking"),
    "tendencia": ("ranking", "comparar_grupos", "relaciones", "tendencia_otra"),
    "ranking": ("perfil_entidad", "comparar_grupos", "tendencia", "ranking_inverso", "ranking_otra"),
    "comparar_grupos": ("relaciones", "tendencia", "ranking", "tendencia_otra"),
    "relaciones": ("tendencia_otra", "comparar_grupos", "ranking", "ranking_otra"),
    "perfil_entidad": ("ranking", "tendencia", "comparar_grupos", "tendencia_otra"),
}
# Si las preferidas no se pueden responder con esta base, se completan con estas.
COMODINES = ("ranking_otra", "ranking_inverso", "describir_datos")


def sugerir(perfil: PerfilDataset, plan: Plan, disponibles: set[str],
            datos: dict[str, tuple[dict[str, Any], ...]] | None = None) -> tuple[str, ...]:
    metricas = perfil.por_rol("metrica")
    if not metricas:
        return ("¿Qué datos tienes?",) if "describir_datos" in disponibles else ()
    principal = perfil.columna(plan.metrica) if plan.metrica else metricas[0]
    if principal.rol != "metrica":
        principal = metricas[0]
    m = f"«{principal.nombre_visible}»"
    otra = next((c for c in metricas if c.nombre != principal.nombre), None)
    grupo = (perfil.por_rol("dimension") + perfil.por_rol("binaria") or (None,))[0]
    plural = perfil.entidad_plural
    primera_en_ranking = (datos or {}).get("ranking", ())

    plantillas = {
        "describir_datos": lambda: "¿Qué datos tienes?",
        "tendencia": lambda: f"¿Cómo ha evolucionado {m}?",
        "tendencia_otra": lambda: f"¿Cómo ha evolucionado «{otra.nombre_visible}»?" if otra else None,
        "ranking_otra": lambda: f"¿Qué {plural} tienen mayor «{otra.nombre_visible}»?" if otra else None,
        "ranking": lambda: f"¿Qué {plural} tienen mayor {m}?",
        "ranking_inverso": lambda: f"¿Qué {plural} tienen menor {m}?" if perfil.tiene("entidad") else None,
        "comparar_grupos": lambda: f"Compara {m} por «{grupo.nombre_visible}»" if grupo else None,
        "relaciones": lambda: f"¿Qué factores se relacionan con {m}?",
        "perfil_entidad": lambda: (f"Cuéntame de {primera_en_ranking[0]['nombre']}"
                                   if primera_en_ranking and perfil.tiene("entidad") else None),
    }
    salida = []
    for clave in SIGUIENTES.get(plan.intencion, SIGUIENTES["describir_datos"]) + COMODINES:
        intencion = clave.replace("_otra", "").replace("_inverso", "")
        if clave == plan.intencion:
            continue
        if intencion not in disponibles:
            continue
        texto = plantillas[clave]()
        if texto and texto not in salida:
            salida.append(texto)
        if len(salida) == MAX_SUGERENCIAS:
            break
    return tuple(salida)
