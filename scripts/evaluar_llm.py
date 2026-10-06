"""Evalúa modelos de Ollama con el banco de preguntas y escribe docs/evaluacion_llm.md (tarea C1 y C2).

    python scripts/evaluar_llm.py --modelos llama3.2:3b qwen2.5:7b
    python scripts/evaluar_llm.py --modelos llama3.2:3b --variantes con_ejemplo sin_ejemplo   # antes/después del few-shot
    python scripts/evaluar_llm.py --banco docs/banco_preguntas.txt                            # una pregunta por línea

Mide por modelo: segundos por respuesta, citas inventadas, cifras sin respaldo y frases con cifra sin cita.
La columna «Claridad (1 a 5)» se llena a mano leyendo las respuestas (el script guarda el detalle).

Las evidencias se obtienen UNA vez por pregunta con el sistema sin LLM, así todos los modelos redactan
sobre exactamente los mismos datos y la comparación es justa.
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import sys
import time
from typing import Callable, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dinamo.llm.prompts import (SISTEMA, citas_invalidas, cifras_sin_cita, cifras_sin_respaldo,  # noqa: E402
                                construir_prompt_usuario)

# Las 10 preguntas del banco del MVP (la 10 es de seguimiento: el orden importa).
BANCO_MVP = [
    "¿Cómo ha evolucionado la rotación en el último año?",
    "¿Cómo va el ausentismo de la compañía 7?",
    "¿Qué empresas tienen la mayor rotación?",
    "¿Qué empresas tuvieron más ausentismo en Julio-Agosto 2025?",
    "Compara la rotación de Tier 1 vs Tier 2",
    "¿Las empresas con sindicato tienen menos ausentismo?",
    "¿Qué factores se asocian con la rotación?",
    "¿Por qué se va la gente?",
    "Cuéntame de la compañía 12",
    "¿Y sólo en Tier 2?",
]

SISTEMA_SIN_EJEMPLO = SISTEMA.split("EJEMPLO (")[0].rstrip()
VARIANTES = {"con_ejemplo": SISTEMA, "sin_ejemplo": SISTEMA_SIN_EJEMPLO}


def evaluar_modelo(llm, preguntas: Sequence[str], evidencias_de: Callable[[str], tuple[list, list[str]]],
                   sistema: str = SISTEMA) -> dict:
    """Corre todas las preguntas. `evidencias_de(pregunta)` -> (evidencias, advertencias)."""
    filas = []
    for pregunta in preguntas:
        evidencias, avisos = evidencias_de(pregunta)
        usuario = construir_prompt_usuario(pregunta, evidencias, (), avisos)
        t0 = time.perf_counter()
        try:
            texto, error = str(llm.generar(sistema, usuario)), ""
        except Exception as e:                                   # un fallo no detiene la evaluación
            texto, error = "", f"{type(e).__name__}: {e}"
        seg = time.perf_counter() - t0
        filas.append({"pregunta": pregunta, "texto": texto, "error": error, "segundos": seg,
                      "citas": len(citas_invalidas(texto, evidencias)),
                      "cifras": len(cifras_sin_respaldo(texto, evidencias, (), pregunta)),
                      "sin_cita": len(cifras_sin_cita(texto)) if evidencias else 0})
    ok = [f for f in filas if not f["error"]]
    return {"filas": filas, "errores": len(filas) - len(ok),
            "segundos": statistics.mean(f["segundos"] for f in ok) if ok else float("nan"),
            "citas": sum(f["citas"] for f in ok), "cifras": sum(f["cifras"] for f in ok),
            "sin_cita": sum(f["sin_cita"] for f in ok)}


def tabla_markdown(resultados: dict[str, dict]) -> str:
    lineas = ["| Modelo | Segundos por respuesta | Citas inventadas | Cifras sin respaldo | Frases con cifra sin cita | Errores | Claridad (1 a 5) |",
              "|---|---|---|---|---|---|---|"]
    for nombre, r in resultados.items():
        lineas.append(f"| {nombre} | {r['segundos']:.1f} | {r['citas']} | {r['cifras']} | {r['sin_cita']} | "
                      f"{r['errores']} | _llenar_ |")
    return "\n".join(lineas)


def detalle_markdown(resultados: dict[str, dict]) -> str:
    partes = []
    for nombre, r in resultados.items():
        partes.append(f"### {nombre}")
        for f in r["filas"]:
            marca = f"ERROR {f['error']}" if f["error"] else (
                f"{f['segundos']:.1f}s · citas {f['citas']} · cifras {f['cifras']} · sin cita {f['sin_cita']}")
            partes.append(f"**{f['pregunta']}** ({marca})\n\n> {f['texto'].strip() or '—'}\n")
    return "\n".join(partes)


def main() -> None:                                              # pragma: no cover (necesita Ollama y el Excel)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", nargs="+", default=["llama3.2:3b"])
    ap.add_argument("--variantes", nargs="+", choices=list(VARIANTES), default=["con_ejemplo"])
    ap.add_argument("--banco", help="archivo de texto con una pregunta por línea")
    ap.add_argument("--salida", default="docs/evaluacion_llm.md")
    args = ap.parse_args()

    from dinamo.core.config import Config
    from dinamo.data_engine import DataEngine
    from dinamo.llm.ollama_http import LLMOllamaRobusto
    from dinamo.sistema import construir_sistema

    preguntas = BANCO_MVP if not args.banco else [
        l.strip() for l in pathlib.Path(args.banco).read_text(encoding="utf-8").splitlines() if l.strip()]
    brain = construir_sistema(datos=DataEngine.desde_excel(Config().ruta_datos))   # sin LLM: sólo para obtener evidencias
    cache: dict[str, tuple[list, list[str]]] = {}
    for p in preguntas:                                          # en orden: la pregunta 10 depende de la 1
        resp = brain.responder(p)
        cache[p] = (list(resp.evidencias), list(resp.advertencias))

    resultados = {}
    for modelo in args.modelos:
        llm = LLMOllamaRobusto(modelo=modelo, respaldo=())
        for variante in args.variantes:
            print(f"Evaluando {modelo} ({variante})…")
            resultados[f"{modelo} · {variante}"] = evaluar_modelo(llm, preguntas, lambda p: cache[p], VARIANTES[variante])

    salida = pathlib.Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("# Evaluación de modelos locales\n\n" + tabla_markdown(resultados)
                      + "\n\nEl modelo ganador se fija en `dinamo/core/config.py`.\n\n## Detalle\n\n"
                      + detalle_markdown(resultados), encoding="utf-8")
    print(f"Escrito {salida}")


if __name__ == "__main__":
    main()
