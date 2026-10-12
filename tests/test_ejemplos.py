"""Los archivos de ejemplo del proyecto (CSV y PDF) deben cargarse y responder SIN configuración."""
from pathlib import Path

import pytest

from dinamo.core.config import RAIZ, Config
from dinamo.sistema import construir_sistema

EJEMPLOS = RAIZ / "ejemplos"


def sistema(*archivos):
    config = Config(archivos=tuple(EJEMPLOS / a for a in archivos), carpeta_perfiles=Path("no_existe"))
    return construir_sistema(config)


@pytest.mark.parametrize("archivo, pregunta, intencion", [
    ("ventas_tiendas.csv", "¿Cómo han evolucionado las ventas?", "tendencia"),
    ("empleados.csv", "¿Qué áreas tienen mayor salario?", "comparar_grupos"),
    ("informe_clima_laboral.pdf", "¿Cómo ha evolucionado la rotación trimestral?", "tendencia"),
])
def test_ejemplo_responde(archivo, pregunta, intencion):
    r = sistema(archivo).responder(pregunta)
    assert r.plan.intencion == intencion and r.evidencias


def test_varias_fuentes_a_la_vez_cada_pregunta_va_a_su_tabla():
    brain = sistema("ventas_tiendas.csv", "empleados.csv", "informe_clima_laboral.pdf")
    assert brain.responder("¿Cómo han evolucionado las ventas?").plan.tabla == "ventas_tiendas"
    assert brain.responder("¿Qué empleados tienen mayor salario?").plan.tabla == "empleados"
    assert brain.responder("¿Cómo ha evolucionado la rotación trimestral?").plan.tabla == "informe_clima_laboral_p1"


def test_preguntas_sobre_el_texto_del_pdf():
    brain = sistema("informe_clima_laboral.pdf")
    r = brain.responder("¿Qué dice el informe sobre los turnos nocturnos?")
    assert r.plan.intencion == "consultar_documentos" and not r.evidencias
    assert r.contexto and all(c.tipo == "documento" for c in r.contexto)
    assert "[C:informe_clima_laboral.pdf#" in r.texto
