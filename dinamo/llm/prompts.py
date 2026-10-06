"""Prompts del LLM y validadores de sus respuestas.

El LLM interpreta; nunca calcula (reglas 1 y 6). Este archivo hace cumplir eso en tres frentes:
  1. SISTEMA le dice cómo responder (con un ejemplo de formato, few-shot).
  2. citas_invalidas / cifras_sin_respaldo / cifras_sin_cita detectan cuando se salió del guion.
  3. plantilla_respaldo produce una respuesta segura sin LLM cuando no hay forma de validar su texto.

Nada aquí menciona un tema concreto: el mismo prompt sirve para rotación, ventas o cualquier
Skill futura, porque el contenido llega siempre en las Evidencias.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

from dinamo.core.contracts import Contexto, Evidencia

# ---------------------------------------------------------------- prompt de sistema
SISTEMA = """Eres DINAMO, un analista de datos que explica resultados a personas que no son técnicas.

REGLAS (no tienen excepciones):
1. Usa SÓLO las EVIDENCIAS que recibes. Cada cifra que escribas debe copiarse tal cual de una evidencia.
2. Después de cada cifra, cita su evidencia con el formato [E:id], copiando el id exacto.
3. No calcules, no redondees, no conviertas unidades y no compares cifras restándolas. Si hace falta una diferencia que no está en las evidencias, no la menciones.
4. Habla de asociación ("se asocia con", "tiende a"); nunca de causa ("causa", "provoca", "por culpa de").
5. Si las evidencias no alcanzan para responder, dilo con claridad y di qué dato faltaría. No rellenes con suposiciones.
6. El CONTEXTO sirve sólo para explicar qué significa un término o cómo se calculó algo. No saques cifras del contexto que no estén también en las evidencias.
7. Si la pregunta no tiene relación con las evidencias ni con el contexto, responde que no tienes información sobre eso.
8. Responde en el mismo idioma de la pregunta, en 3 frases como máximo, sin títulos, listas ni viñetas.
9. Si hay ADVERTENCIAS, menciona la más importante en una frase corta.

EJEMPLO (sólo muestra el formato; tu tema será otro):
Pregunta: ¿Cómo van las ventas de la sucursal Norte?
Evidencias:
[E:ventas:aa11bb22] Ventas del último mes, sucursal Norte = 120.5 miles de pesos (n=1, método: suma del mes)
[E:ventas:cc33dd44] Mediana de ventas entre sucursales = 98 miles de pesos (n=12, método: mediana)
Respuesta: La sucursal Norte vendió 120.5 miles de pesos en el último mes [E:ventas:aa11bb22]. La mediana de las 12 sucursales es de 98 miles de pesos [E:ventas:cc33dd44], así que Norte está por encima del centro del grupo. Son datos descriptivos: no explican por qué hay diferencia."""


def _valor(e: Evidencia) -> str:
    from dinamo.llm import formatear_valor   # import tardío: evita ciclo con dinamo/llm/__init__.py
    return formatear_valor(e)


def formatear_evidencias(evidencias: Sequence[Evidencia]) -> str:
    """Una línea por evidencia: [E:id] descripción = valor (n=…, método: …)."""
    return "\n".join(f"[E:{e.id}] {e.descripcion} = {_valor(e)} (n={e.n}, método: {e.metodo})"
                     for e in evidencias) or "(sin evidencias)"


def formatear_contexto(contexto: Sequence[Contexto], max_chars: int = 500) -> str:
    return "\n".join(f"- ({c.fuente}) {c.texto[:max_chars]}" for c in contexto) or "(sin contexto)"


def construir_prompt_usuario(pregunta: str, evidencias: Sequence[Evidencia],
                             contexto: Sequence[Contexto] = (), advertencias: Iterable[str] = (),
                             correcciones: Sequence[str] = ()) -> str:
    partes = [f"Pregunta: {pregunta}", f"Evidencias:\n{formatear_evidencias(evidencias)}",
              f"Contexto:\n{formatear_contexto(contexto)}"]
    avisos = list(advertencias)
    if avisos:
        partes.append("Advertencias:\n" + "\n".join(f"- {a}" for a in avisos))
    if correcciones:
        partes.append("Tu respuesta anterior tuvo estos problemas; corrígelos y responde de nuevo:\n"
                      + "\n".join(f"- {c}" for c in correcciones))
    partes.append("Respuesta:")
    return "\n\n".join(partes)


# ---------------------------------------------------------------- validadores
_RE_CITA = re.compile(r"\[E:([^\]]+)\]")
_RE_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?|\d+(?:,\d+)?")
NUM = r"\d+(?:\.\d+)?"          # compatibilidad con la guía


def citas_invalidas(texto: str, evidencias: Sequence[Evidencia]) -> list[str]:
    """Ids [E:…] que el LLM escribió y que no existen entre las evidencias."""
    validos = {e.id for e in evidencias}
    return sorted({i for i in _RE_CITA.findall(texto) if i not in validos})


def _canon(s: str) -> str | None:
    """'10,4' -> '10.4'; '35,200' -> '35200'; '10.40' -> '10.4'. None si no es un número."""
    s = s.strip().strip(",")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):      # miles con coma
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")                            # coma decimal (escritura en español)
    try:
        d = Decimal(s).normalize()
    except InvalidOperation:
        return None
    return format(d, "f")


def _numeros(texto: str) -> set[str]:
    """Números de un texto, ignorando [E:id], referencias de contexto y numeración de listas."""
    limpio = _RE_CITA.sub(" ", texto)
    limpio = re.sub(r"(?m)^\s*\d+[.)]\s+", " ", limpio)    # '1. ' al inicio de línea
    return {c for c in (_canon(m) for m in _RE_NUM.findall(limpio)) if c is not None}


def _numeros_permitidos(evidencias: Sequence[Evidencia], contexto: Sequence[Contexto],
                        pregunta: str) -> set[str]:
    texto = [pregunta]
    for e in evidencias:
        texto += [e.descripcion, _valor(e), str(e.n)]
        for extra in (getattr(e, "parametros", None), getattr(e, "contexto", None)):
            if isinstance(extra, dict):
                texto += [str(v) for v in extra.values()]
        v = float(e.valor)
        texto += [repr(v), f"{v:.4f}", f"{v:.2f}", f"{v * 100:.1f}", f"{v * 100:.2f}"]
        if e.unidad in ("proporcion", "porcentaje", "cambio_relativo"):
            texto.append(f"{abs(v) * 100:.1f}")   # el LLM puede omitir el signo
    texto += [c.texto for c in contexto]
    return _numeros(" ".join(texto))


def cifras_sin_respaldo(texto: str, evidencias: Sequence[Evidencia], contexto: Sequence[Contexto] = (),
                        pregunta: str = "") -> list[str]:
    """Cifras del texto que no aparecen en ninguna evidencia, en el contexto ni en la pregunta.

    Mejoras sobre la versión de la guía: acepta coma decimal (10,4), separador de miles (35,200),
    no se confunde con '[E:…]' ni con listas numeradas, y reconoce el valor crudo y en porcentaje."""
    permitidas = _numeros_permitidos(evidencias, contexto, pregunta)
    return sorted(_numeros(texto) - permitidas, key=lambda s: (len(s), s))


def cifras_sin_cita(texto: str) -> list[str]:
    """Frases que contienen una cifra pero ningún [E:id]. La regla 2 pide citar cada cifra."""
    frases = re.split(r"(?<=[.!?])\s+|\n+", texto)
    return [f.strip() for f in frases if _numeros(f) and not _RE_CITA.search(f)]


# ---------------------------------------------------------------- respaldo sin LLM
def plantilla_respaldo(evidencias: Sequence[Evidencia], contexto: Sequence[Contexto] = (),
                       advertencias: Iterable[str] = (), max_evidencias: int = 6) -> str:
    """Texto determinístico: sólo repite lo que dicen las evidencias. Nunca inventa nada."""
    lineas = []
    if evidencias:
        lineas.append("Esto es lo que muestran los datos:")
        lineas += [f"- {e.descripcion}: {_valor(e)} (n={e.n}) [E:{e.id}]" for e in evidencias[:max_evidencias]]
    elif contexto:
        lineas.append("No tengo cifras para esa pregunta, pero en la documentación encontré:")
        lineas += [f"- {c.texto[:300]} (fuente: {c.fuente})" for c in contexto[:2]]
    else:
        lineas.append("No tengo datos ni documentación para responder eso. "
                      "Puedes preguntarme por tendencias, rankings, comparaciones entre grupos o factores asociados.")
    lineas += [f"Aviso: {a}" for a in advertencias]
    return "\n".join(lineas)
