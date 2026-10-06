"""Guardia del LLM: genera, valida, reintenta una vez con correcciones y, si no queda bien, usa la plantilla.

Samuel la llama desde Brain.responder en lugar de llamar al LLM directamente:

    r = responder_con_guardia(self.llm, pregunta, evidencias, contexto, advertencias=plan_avisos)
    respuesta = Respuesta(texto=r.texto, ..., advertencias=r.advertencias)

Garantías:
  * Con LLM apagado, lento o con una respuesta rara, el usuario SIEMPRE recibe un texto válido.
  * Ninguna cifra sin respaldo ni cita inventada llega al usuario (reglas 1, 6 y 7).
  * Funciona con cualquier objeto que tenga generar(sistema, usuario): LLMOllama, LLMFalso, etc.
  * Si no hay evidencias ni contexto, NI SIQUIERA llama al LLM: no hay con qué responder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from dinamo.core.contracts import Contexto, Evidencia

from .prompts import (SISTEMA, citas_invalidas, cifras_sin_cita, cifras_sin_respaldo,
                      construir_prompt_usuario, plantilla_respaldo)

try:  # algunos modelos (qwen, deepseek) escriben <think>…</think> antes de responder
    from .ollama_http import limpiar_respuesta
except Exception:  # pragma: no cover
    def limpiar_respuesta(t: str) -> str:
        return t.strip()


@dataclass(frozen=True)
class ResultadoGuardia:
    texto: str
    advertencias: tuple[str, ...] = ()
    intentos: int = 0            # llamadas al LLM realizadas
    uso_plantilla: bool = False  # True si el texto es el de respaldo, no el del LLM


def revisar(texto: str, evidencias: Sequence[Evidencia], contexto: Sequence[Contexto] = (),
            pregunta: str = "", exigir_citas: bool = True) -> list[str]:
    """Problemas encontrados en el texto del LLM (lista vacía = texto aceptable)."""
    if not texto.strip():
        return ["La respuesta llegó vacía."]
    problemas = []
    if (ids := citas_invalidas(texto, evidencias)):
        problemas.append(f"Citaste ids de evidencia que no existen: {', '.join(ids)}. Usa sólo los ids dados.")
    if (nums := cifras_sin_respaldo(texto, evidencias, contexto, pregunta)):
        problemas.append(f"Escribiste cifras que no están en las evidencias: {', '.join(nums)}. "
                         "Usa sólo cifras de las evidencias, sin calcular ni redondear.")
    if exigir_citas and evidencias and (frases := cifras_sin_cita(texto)):
        problemas.append(f"Estas frases tienen cifras sin cita [E:id]: «{frases[0][:80]}»")
    return problemas


def responder_con_guardia(llm, pregunta: str, evidencias: Sequence[Evidencia],
                          contexto: Sequence[Contexto] = (), advertencias: Iterable[str] = (),
                          *, max_intentos: int = 2, sistema: str = SISTEMA,
                          exigir_citas: bool = True) -> ResultadoGuardia:
    avisos = list(advertencias)

    if not evidencias and not contexto:                      # nada que explicar -> no hay riesgo que correr
        return ResultadoGuardia(plantilla_respaldo((), ()), tuple(avisos), 0, True)

    correcciones: list[str] = []
    intento = 0
    for intento in range(1, max_intentos + 1):
        usuario = construir_prompt_usuario(pregunta, evidencias, contexto, avisos, correcciones)
        try:
            texto = limpiar_respuesta(str(llm.generar(sistema, usuario)))
        except Exception as e:                               # Ollama apagado, tiempo agotado, modelo ausente…
            avisos.append(f"El modelo de lenguaje no está disponible ({type(e).__name__}); "
                          "se muestra una respuesta basada sólo en las evidencias.")
            break
        correcciones = revisar(texto, evidencias, contexto, pregunta, exigir_citas)
        if not correcciones:
            return ResultadoGuardia(texto, tuple(avisos), intento, False)
    else:
        avisos.append("La redacción del modelo no pasó la validación de cifras y citas; "
                      "se muestra una respuesta basada sólo en las evidencias.")

    # Las advertencias viajan aparte (la interfaz las muestra con st.warning): no se repiten en el texto.
    return ResultadoGuardia(plantilla_respaldo(evidencias, contexto), tuple(avisos), intento, True)
