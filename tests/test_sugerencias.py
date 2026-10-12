import pytest

from dinamo.brain import Interprete, sugerir
from dinamo.core.contracts import Plan


@pytest.mark.parametrize("base", ["datos_panel", "datos_simple"])
def test_cada_sugerencia_se_entiende_y_se_puede_responder(base, request):
    """Si DINAMO sugiere una pregunta, debe entenderla y tener con qué responderla."""
    from dinamo.skills import crear_registro
    datos = request.getfixturevalue(base)
    disponibles = crear_registro().intenciones_disponibles(datos.perfil)
    interprete = Interprete(datos.perfil, datos.periodos(), datos.entidades())
    for intencion in ("describir_datos", "tendencia", "ranking", "desconocida"):
        for texto in sugerir(datos.perfil, Plan(intencion), disponibles):
            assert interprete.interpretar(texto).intencion in disponibles, texto


def test_no_sugiere_lo_que_la_base_no_permite(datos_simple):
    sugerencias = sugerir(datos_simple.perfil, Plan("describir_datos"), {"describir_datos", "ranking"})
    assert sugerencias and not any("evolucionado" in s for s in sugerencias)


def test_maximo_tres_sugerencias(datos_panel):
    todas = {"describir_datos", "tendencia", "ranking", "comparar_grupos", "relaciones", "perfil_entidad"}
    assert len(sugerir(datos_panel.perfil, Plan("describir_datos"), todas)) == 3


def test_cuando_exista_una_skill_nueva_se_empezara_a_sugerir(datos_panel):
    sin = sugerir(datos_panel.perfil, Plan("tendencia", ("ventas",)), {"tendencia", "ranking"})
    con = sugerir(datos_panel.perfil, Plan("tendencia", ("ventas",)), {"tendencia", "ranking", "comparar_grupos"})
    assert not any(s.startswith("Compara") for s in sin)
    assert any(s.startswith("Compara") for s in con)
