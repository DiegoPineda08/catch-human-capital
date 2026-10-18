"""
RESÚMENES DE CONTEXTO: cuando una conversación crece, los mensajes antiguos se resumen para que el
LLM los tenga presentes sin repetirlos completos.

Regla: el resumen conserva hechos, cifras y fuentes. Si lo escribe un LLM, se verifica que
TODAS sus cifras y citas existan en el texto original; si no, se usa el resumen determinístico.
"""
from __future__ import annotations

import re

from dinamo.llm import LLMFalso, LLMNoDisponible

NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
CITA = re.compile(r"\[(?:E|C|W):[^\]]+\]")

SISTEMA_RESUMEN = """Resume la conversación para que un asistente pueda continuarla.
Conserva EXACTAMENTE: cifras, nombres de archivos, países, indicadores, decisiones del usuario,
hechos que pidió recordar y las citas entre corchetes ([E:..], [C:..], [W:..]).
No agregues nada que no esté en la conversación. Máximo 12 viñetas en español."""


def _frases(texto: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+|\n+", texto) if f.strip()]


def resumen_deterministico(mensajes: list[dict]) -> str:
    lineas = []
    for m in mensajes:
        if m["rol"] == "usuario":
            lineas.append(f"• Usuario preguntó: {m['texto'][:200]}")
        elif m["rol"] == "asistente":
            clave = [f for f in _frases(m["texto"]) if NUMERO.search(f) or CITA.search(f)][:3]
            if clave:
                lineas.append("• DINAMO respondió: " + " ".join(clave)[:400])
            for f in (m.get("fuentes") or [])[:3]:
                lineas.append(f"• Fuente consultada: {f.get('titulo', '')[:100]} ({f.get('url', '')})")
    return "\n".join(lineas[-40:])


def es_fiel(resumen: str, original: str) -> bool:
    numeros_orig = set(NUMERO.findall(original))
    citas_orig = set(CITA.findall(original))
    return set(NUMERO.findall(resumen)) <= numeros_orig and set(CITA.findall(resumen)) <= citas_orig


def resumir(mensajes: list[dict], resumen_previo: str = "", llm=None) -> tuple[str, str]:
    """Devuelve (resumen, método). Método: 'llm' (verificado) o 'determinístico'."""
    original = resumen_previo + "\n" + "\n".join(f"{m['rol']}: {m['texto']}" for m in mensajes)
    if llm is not None and not isinstance(llm, LLMFalso):
        try:
            texto = llm.generar(SISTEMA_RESUMEN, original[-12000:]).strip()
            if texto and es_fiel(texto, original):
                return texto, "llm"
        except LLMNoDisponible:
            pass
    previo = (resumen_previo + "\n") if resumen_previo else ""
    return previo + resumen_deterministico(mensajes), "determinístico"
