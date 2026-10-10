"""Guardia del LLM: genera, valida y reintenta; devuelve siempre texto seguro.

Flujo:
  1. Llama al LLM.
  2. Valida: ¿hay citas inventadas ([E:id] o [C:fuente])? ¿cifras sin respaldo? ¿cifras sin cita?
  3. Si falla, reintenta UNA vez con retroalimentación.
  4. Si vuelve a fallar, usa la plantilla determinista.

Nunca expone texto no validado al usuario.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from dinamo.core.contracts import Contexto, Evidencia
from dinamo.llm.ollama_http import limpiar_respuesta
from dinamo.llm.prompts import (
    SISTEMA,
    cifras_sin_cita,
    cifras_sin_respaldo,
    citas_invalidas,
    construir_mensajes,
    formatear_valor,
    instruccion_perfil,
)


_RE_SIN_INFO = re.compile(r"\bno tengo\b|\bno hay informaci", re.IGNORECASE)     # «no tengo información…»


@dataclass(frozen=True)
class ResultadoGuardia:
    texto: str
    advertencias: tuple[str, ...]
    intentos: int
    uso_plantilla: bool


def _plantilla(evidencias: list[Evidencia], contexto: list[Contexto],
               advertencias: list[str]) -> str:
    """Respuesta determinista cuando el LLM no pasa la validación.

    Las advertencias viajan aparte (la interfaz las muestra por separado): no se repiten en el texto."""
    partes: list[str] = []
    if evidencias:
        partes.append("Resultados disponibles:")
        for e in evidencias:
            partes.append(f"- {e.descripcion}: {formatear_valor(e)} [E:{e.id}]")
    if contexto:
        partes.append("Contexto relevante:")
        for c in contexto[:3]:
            partes.append(f"- {' '.join(c.texto.split())[:200]} [C:{c.fuente}]")
    return "\n".join(partes) if partes else "No hay evidencia suficiente para responder."


def revisar(texto: str, evidencias: list[Evidencia], contexto: list[Contexto],
            pregunta: str = "", exigir_citas: bool = True, extras: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Devuelve la lista de problemas encontrados (vacía = texto OK).

    `extras`: textos que el LLM también ve (advertencias, descripción de las fuentes); sus números son válidos."""
    if not str(texto).strip():
        return ["La respuesta llegó vacía."]
    problemas: list[str] = []

    inventadas = citas_invalidas(texto, {e.id for e in evidencias}, {c.fuente for c in contexto})
    if inventadas:
        problemas.append(f"Citas inventadas: {inventadas}. Usa sólo los ids y fuentes que se te dieron.")

    sin_respaldo = cifras_sin_respaldo(texto, evidencias, contexto, pregunta, extras)
    if sin_respaldo:
        problemas.append(f"Cifras sin respaldo en las evidencias: {sin_respaldo[:5]}. "
                         "Usa sólo cifras de las evidencias, sin calcular ni redondear.")

    if exigir_citas and evidencias:
        frases = cifras_sin_cita(texto)
        if frases:
            problemas.append(f"Esta frase tiene cifras sin cita [E:id]: «{frases[0][:80]}»")

    # Respuesta apoyada en un documento y sin ninguna cita [C:…]: se pide citar la página (salvo que diga que no sabe)
    docs = [c for c in contexto if c.tipo == "documento"]
    if (exigir_citas and not evidencias and docs and "[C:" not in texto and not _RE_SIN_INFO.search(texto)):
        problemas.append(f"Lo que dices viene de un documento: cítalo con [C:fuente], por ejemplo [C:{docs[0].fuente}].")
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
    perfil=None,
    sobre_la_base: str = "",
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
        exigir_citas: si True, también exige que cada frase con cifras lleve su cita
                      (las citas inventadas y las cifras sin respaldo se revisan siempre)
        perfil: PerfilUsuario, dict o texto del usuario; cambia el tono, nunca las cifras
        sobre_la_base: descripción de las fuentes cargadas (va en el mensaje al LLM)
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

    persona = instruccion_perfil(perfil)
    extras = [*advertencias, sobre_la_base]
    correcciones: list[str] = []
    intentos = 0
    llm_caido = False
    for intento in range(1, max_intentos + 1):
        intentos = intento
        _, mensaje_usuario = construir_mensajes(
            pregunta, contexto, evidencias, advertencias, sobre_la_base, persona,
        )
        if correcciones:
            mensaje_usuario += "\n\nCORRECCIONES NECESARIAS:\n" + "\n".join(f"- {c}" for c in correcciones)

        try:
            texto = limpiar_respuesta(str(llm.generar(sistema_llm, mensaje_usuario)))
        except Exception as exc:
            advertencias.append(f"LLM no disponible: {exc}")
            llm_caido = True
            break

        problemas = revisar(texto, evidencias, contexto, pregunta, exigir_citas, extras)
        if not problemas:
            return ResultadoGuardia(
                texto=texto,
                advertencias=tuple(advertencias),
                intentos=intento,
                uso_plantilla=False,
            )
        correcciones = problemas

    if not llm_caido:
        advertencias.append(f"El LLM no pasó la validación tras {intentos} intento(s); se usa plantilla.")
    return ResultadoGuardia(
        texto=_plantilla(evidencias, contexto, advertencias),
        advertencias=tuple(advertencias),
        intentos=intentos,
        uso_plantilla=True,
    )
