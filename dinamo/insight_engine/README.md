# Insight Engine (Fase 2 — responsable: Samuel)

Recibe: `list[Evidencia]` + `Plan`  ->  Devuelve: `list[Insight]` ordenados por `puntaje`.
Prioriza hallazgos con reglas determinísticas (magnitud del cambio, valores extremos,
fuerza de asociación, tamaño de muestra). No llama al LLM. Ver el plan del equipo.
