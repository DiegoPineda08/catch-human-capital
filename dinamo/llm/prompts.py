"""
Construcción de prompts. El LLM INTERPRETA; no calcula.

Por eso:
- los valores llegan ya formateados por código (p.ej. 0.0925 -> "9.3%");
- cada evidencia lleva un id que el LLM debe citar como [E:id];
- cada fragmento de documento lleva su fuente, que el LLM cita como [C:fuente];
- `citas_invalidas` detecta citas inventadas para que el Brain lo advierta;
- el perfil del usuario cambia el TONO de la respuesta, nunca los números.
"""
from __future__ import annotations

import re

from dinamo.core.contracts import Contexto, Evidencia

SISTEMA = """Eres DINAMO, un analista de datos que explica resultados a personas sin formación técnica.
Reglas obligatorias:
1. Usa SOLO las evidencias y el contexto que se te entregan. No inventes cifras.
2. No hagas cálculos nuevos: copia los valores tal como aparecen en la evidencia.
3. Cita cada cifra con su id entre corchetes, por ejemplo [E:tendencia:1a2b3c4d].
4. Si usas un fragmento de un documento, cítalo con su fuente, por ejemplo [C:informe.pdf#p2].
5. Una correlación NO es causalidad: usa "se asocia con", nunca "causa" o "provoca".
6. Si la evidencia y el contexto no alcanzan para responder, dilo claramente.
7. Adapta el tono a la persona que pregunta (ver PERSONA), pero nunca cambies las cifras.
8. Responde en español, en máximo 6 frases, claro y sin tecnicismos."""


def _moneda(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def formatear_valor(e: Evidencia) -> str:
    """Convierte el número en texto listo para leer, así el LLM nunca tiene que calcular."""
    v = e.valor
    if isinstance(v, str):
        return v
    formatos = {
        "proporcion": lambda x: f"{x * 100:.1f}%",
        "diferencia_proporcion": lambda x: f"{x * 100:+.1f} puntos porcentuales",
        "cambio_relativo": lambda x: f"{x * 100:+.1f}%",
        "rho": lambda x: f"{x:+.2f}",
        "moneda": _moneda,
        "conteo": lambda x: f"{x:,.0f}",
        "dias": lambda x: f"{x:,.1f} días",
        "escala": lambda x: f"{x:.2f}",
    }
    return formatos.get(e.unidad, lambda x: f"{x:,.4g}" if abs(x) < 1e6 else f"{x:,.0f}")(v)


def construir_mensajes(pregunta: str, contexto: list[Contexto], evidencias: list[Evidencia],
                       advertencias: list[str] | None = None, sobre_la_base: str = "",
                       usuario: str = "") -> tuple[str, str]:
    """Arma los dos mensajes del LLM: el de sistema (reglas) y el de usuario (todo el material)."""
    bloque_ctx = "\n".join(f"- [C:{c.fuente}] " + " ".join(c.texto.split()) for c in contexto) or "(sin contexto)"
    bloque_ev = "\n".join(f"- [E:{e.id}] {_de_tabla(e)}{e.descripcion}: {formatear_valor(e)} (n={e.n}; {e.metodo})"
                          for e in evidencias) or "(sin evidencia)"
    bloque_adv = "\n".join(f"- {a}" for a in (advertencias or [])) or "(ninguna)"
    mensaje = (f"PERSONA:\n{usuario or '(sin datos del usuario)'}\n\n"
               f"FUENTES:\n{sobre_la_base or '(sin descripción)'}\n\n"
               f"PREGUNTA:\n{pregunta}\n\nCONTEXTO RECUPERADO:\n{bloque_ctx}\n\n"
               f"EVIDENCIA:\n{bloque_ev}\n\nADVERTENCIAS:\n{bloque_adv}\n\n"
               "Responde la pregunta siguiendo las reglas.")
    return SISTEMA, mensaje


def _de_tabla(e: Evidencia) -> str:
    tabla = e.filtros.get("tabla")
    return f"({tabla}) " if tabla else ""


def citas_invalidas(texto: str, ids_validos: set[str], fuentes_validas: set[str] | None = None) -> list[str]:
    """Citas del LLM que NO existen: ids de evidencia [E:..] o fuentes de contexto [C:..] inventados."""
    malas = {c for c in re.findall(r"\[E:([^\]]+)\]", texto) if c not in ids_validos}
    if fuentes_validas is not None:
        malas |= {f"C:{c}" for c in re.findall(r"\[C:([^\]]+)\]", texto) if c not in fuentes_validas}
    return sorted(malas)
