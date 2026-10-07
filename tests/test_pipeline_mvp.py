"""Test de punta a punta: Pregunta -> Brain -> RAC -> Skill -> Evidence -> LLM -> Respuesta, con DOS bases."""
import pytest

from dinamo.llm import LLMNoDisponible


@pytest.mark.parametrize("base, pregunta", [
    ("brain_panel", "¿Cómo han evolucionado las ventas?"),
    ("brain_simple", "¿Qué empleados tienen el mayor salario?"),
])
def test_pipeline_completo_con_bases_distintas(base, pregunta, request):
    brain = request.getfixturevalue(base)
    r = brain.responder(pregunta)
    assert len(r.evidencias) >= 3
    assert all(brain.evidencias.existe(e.id) for e in r.evidencias)   # todo número queda registrado
    assert f"[E:{r.evidencias[0].id}]" in r.texto                       # el texto cita evidencia
    assert r.contexto and r.sugerencias


def test_pregunta_imposible_en_esta_base_se_explica(brain_simple):
    r = brain_simple.responder("¿Cómo ha evolucionado el salario?")
    assert any("no tiene columnas de tipo ['tiempo']" in a for a in r.advertencias)
    assert r.evidencias                                                 # igual responde algo útil


def test_pregunta_no_entendida_muestra_la_base(brain_panel):
    r = brain_panel.responder("Hola")
    assert "describir_dataset" in r.datos and r.sugerencias


def test_detecta_citas_inventadas(brain_panel):
    class LLMMentiroso:
        def generar(self, sistema, usuario):
            return "Las ventas subieron 50% [E:inventada:123]."
    brain_panel.llm = LLMMentiroso()
    r = brain_panel.responder("¿Cómo han evolucionado las ventas?")
    assert any("no existen" in a for a in r.advertencias)


def test_si_el_llm_no_esta_disponible_responde_igual(brain_panel):
    class LLMCaido:
        def generar(self, sistema, usuario):
            raise LLMNoDisponible("Ollama apagado")
    brain_panel.llm = LLMCaido()
    r = brain_panel.responder("¿Cómo han evolucionado las ventas?")
    assert r.evidencias and "Ollama apagado" in " ".join(r.advertencias)
