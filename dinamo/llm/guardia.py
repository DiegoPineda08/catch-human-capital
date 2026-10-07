"""Guardia del LLM: genera, valida y reintenta; devuelve siempre texto seguro.

Flujo:
  1. Llama al LLM.
  2. Valida: ¿hay citas inventadas? ¿números sin respaldo?
  3. Si falla, reintenta UNA vez con retroalimentación.
  4. Si vuelve a fallar, usa la plantilla determinista.

Nunca expone texto no validado al usuario.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from dinamo.core.contracts import Contexto, Evidencia
from dinamo.llm.prompts import (
    SISTEMA,
    citas_invalidas,
    construir_mensajes,
    formatear_valor,
)


@dataclass(frozen=True)
class ResultadoGuardia:
    texto: str
    advertencias: tuple[str, ...]
    intentos: int
    uso_plantilla: bool


def _plantilla(evidencias: list[Evidencia], contexto: list[Contexto],
               advertencias: list[str]) -> str:
    """Respuesta determinista cuando el LLM no pasa la validación."""
    partes: list[str] = []
    if evidencias:
        partes.append("Resultados disponibles:")
        for e in evidencias:
            partes.append(f"- {e.descripcion}: {formatear_valor(e)} [E:{e.id}]")
    if contexto:
        partes.append("Contexto relevante:")
        for c in contexto[:3]:
            partes.append(f"- [{c.fuente}] {c.texto[:200]}")
    if advertencias:
        partes.append("Nota: " + "; ".join(advertencias))
    return "\n".join(partes) if partes else "No hay evidencia suficiente para responder."


def _numeros_en_texto(texto: str) -> list[str]:
    """Extrae números (incluye decimales con coma o punto y porcentajes)."""
    return re.findall(r"\b\d[\d.,]*%?\b", texto)


def revisar(texto: str, evidencias: list[Evidencia], contexto: list[Contexto],
            pregunta: str = "") -> list[str]:
    """Devuelve lista de problemas encontrados (vacía = texto OK)."""
    problemas: list[str] = []

    # 1. Citas de evidencias inventadas
    ids_validos = {e.id for e in evidencias}
    fuentes_validas = {c.fuente for c in contexto}
    inventadas = citas_invalidas(texto, ids_validos, fuentes_validas)
    if inventadas:
        problemas.append(f"Citas inventadas: {inventadas}")

    # 2. Números en el texto que no aparecen en ninguna evidencia ni contexto
    if evidencias:
        valores_en_evidencia: set[str] = set()
        for e in evidencias:
            v = formatear_valor(e)
            valores_en_evidencia.update(re.findall(r"\d[\d.,]*%?", v))
        for ctx in contexto:
            valores_en_evidencia.update(re.findall(r"\d[\d.,]*%?", ctx.texto))

        numeros_respuesta = _numeros_en_texto(texto)
        sin_respaldo = [n for n in numeros_respuesta
                        if not any(n.replace(",", ".") in v.replace(",", ".") or v.replace(",", ".") in n.replace(",", ".")
                                   for v in valores_en_evidencia)]
        if sin_respaldo:
            problemas.append(f"Números sin respaldo en evidencia: {sin_respaldo[:5]}")

    return problemas


def responder_con_guardia(
    llm,
    pregunta: str,
    evidencias: list[Evidencia],
    contexto: list[Contexto],
    advertencias: list[str] | None = None,
    max_intentos: int = 2,
    sistema: str | None = None,
    exigir_citas: bool = True,
    perfil: dict | None = None,
) -> ResultadoGuardia:
    """Genera una respuesta validada.

    Args:
        llm: cualquier objeto con .generar(sistema, usuario) -> str
        pregunta: texto de la pregunta del usuario
        evidencias: lista de Evidencia calculadas por las Skills
        contexto: fragmentos del RAC
        advertencias: advertencias ya conocidas antes de llamar al LLM
        max_intentos: máximo de llamadas al LLM (1 = sin reintento)
        sistema: override del prompt de sistema (None = usa SISTEMA de prompts.py)
        exigir_citas: si True, falla cuando hay números sin cita
        perfil: dict con nombre/cargo/nivel_detalle del usuario (para instruccion_perfil)
    """
    advertencias = list(advertencias or [])
    sistema_llm = sistema or SISTEMA

    # Sin material, devuelve plantilla directamente
    if not evidencias and not contexto:
        return ResultadoGuardia(
            texto=_plantilla(evidencias, contexto, advertencias),
            advertencias=tuple(advertencias),
            intentos=0,
            uso_plantilla=True,
        )

    # Añade instrucción de perfil al sistema si hay perfil
    if perfil:
        try:
            from dinamo.llm.prompts import instruccion_perfil as _ip
            sistema_llm = sistema_llm + "\n" + _ip(perfil)
        except (ImportError, AttributeError):
            pass

    correcciones: list[str] = []
    for intento in range(1, max_intentos + 1):
        _, mensaje_usuario = construir_mensajes(
            pregunta, contexto, evidencias, advertencias,
        )
        if correcciones:
            mensaje_usuario += "\n\nCORRECCIONES NECESARIAS:\n" + "\n".join(f"- {c}" for c in correcciones)

        try:
            texto = llm.generar(sistema_llm, mensaje_usuario)
        except Exception as exc:
            advertencias.append(f"LLM no disponible: {exc}")
            break

        problemas = revisar(texto, evidencias, contexto, pregunta) if exigir_citas else []
        if not problemas:
            return ResultadoGuardia(
                texto=texto,
                advertencias=tuple(advertencias),
                intentos=intento,
                uso_plantilla=False,
            )
        correcciones = problemas

    # Agota intentos -> plantilla
    advertencias.append(f"El LLM no pasó la validación tras {max_intentos} intento(s); se usa plantilla.")
    return ResultadoGuardia(
        texto=_plantilla(evidencias, contexto, advertencias),
        advertencias=tuple(advertencias),
        intentos=max_intentos,
        uso_plantilla=True,
    )
