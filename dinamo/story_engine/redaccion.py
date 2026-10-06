"""Story Engine, fase 2 (tarea C5): una llamada al LLM por sección, con SÓLO las evidencias de esa sección.

Gabriela entrega la Historia con secciones (rol + ids de evidencia + texto de plantilla). Aquí cada
sección se redacta con el LLM y pasa por la misma guardia que las respuestas normales: si el texto
falla dos veces (cita o cifra inventada) se usa el texto de plantilla de Gabriela.

SUPUESTO A CONFIRMAR CON GABRIELA: el contrato `Historia` aún no está en esta guía. Se asume que cada
sección expone `rol`, `ids_evidencia` y `texto` (plantilla). Si los nombres difieren, sólo hay que
cambiar las tres constantes de abajo; el resto no se toca.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from dinamo.core.contracts import Contexto, Evidencia
from dinamo.llm.guardia import responder_con_guardia
from dinamo.llm.prompts import SISTEMA

ATRIBUTO_ROL, ATRIBUTO_IDS, ATRIBUTO_PLANTILLA = "rol", "ids_evidencia", "texto"

# Instrucción extra por tipo de sección (las 5 partes de la guía). Se suma al SISTEMA general.
GUIA_POR_ROL = {
    "contexto": "Esta sección sólo ubica al lector: de qué datos se habla (cuántas empresas, qué periodos).",
    "hallazgo": "Esta sección dice qué pasó: el cambio principal, con sus cifras citadas.",
    "tension": "Esta sección señala qué no cuadra o preocupa. Sé claro sin dramatizar.",
    "explicacion": "Esta sección habla de qué se asocia con el hallazgo. Usa 'se asocia con' o 'tiende a'; jamás 'causa'.",
    "recomendacion": "Esta sección propone qué revisar. Usa lenguaje condicional ('conviene revisar'), "
                     "no afirmes causas y no inventes cifras.",
}


@dataclass(frozen=True)
class SeccionRedactada:
    rol: str
    texto: str
    ids_evidencia: tuple[str, ...]
    advertencias: tuple[str, ...] = ()
    uso_plantilla: bool = False


def _clave_rol(rol: Any) -> str:
    from dinamo.rac.texto import quitar_acentos
    return quitar_acentos(str(rol)).lower().strip()


def redactar_seccion(llm, seccion: Any, evidencias_por_id: Mapping[str, Evidencia], pregunta: str = "",
                     contexto: Sequence[Contexto] = ()) -> SeccionRedactada:
    rol = str(getattr(seccion, ATRIBUTO_ROL))
    ids = tuple(getattr(seccion, ATRIBUTO_IDS, ()) or ())
    plantilla = str(getattr(seccion, ATRIBUTO_PLANTILLA, "") or "")
    evidencias = [evidencias_por_id[i] for i in ids if i in evidencias_por_id]   # sólo las de ESTA sección

    sistema = SISTEMA + "\n\nSECCIÓN QUE REDACTAS: " + GUIA_POR_ROL.get(_clave_rol(rol), "Redacta esta sección.")
    r = responder_con_guardia(llm, pregunta or f"Redacta la sección «{rol}».", evidencias, contexto, (),
                              sistema=sistema)
    if r.uso_plantilla and plantilla:       # falló la validación (o no hay LLM): texto de Gabriela
        return SeccionRedactada(rol, plantilla, ids, r.advertencias, True)
    return SeccionRedactada(rol, r.texto, ids, r.advertencias, r.uso_plantilla)


def redactar_historia(llm, secciones: Iterable[Any], evidencias: Iterable[Evidencia], pregunta: str = "",
                      contexto: Sequence[Contexto] = ()) -> list[SeccionRedactada]:
    """Redacta todas las secciones en orden. Una sección que falla no afecta a las demás."""
    por_id = {e.id: e for e in evidencias}
    return [redactar_seccion(llm, s, por_id, pregunta, contexto) for s in secciones]
