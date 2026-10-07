"""Se ejecuta sólo si data/BASE_HISTORICA_LIMPIA.xlsx existe (los datos reales no se suben a GitHub)."""
import pytest

from dinamo.core.config import RAIZ, Config

RUTA = RAIZ / "data" / "BASE_HISTORICA_LIMPIA.xlsx"
pytestmark = pytest.mark.skipif(not RUTA.exists(), reason="Falta data/BASE_HISTORICA_LIMPIA.xlsx")


def test_base_de_catch_con_su_perfil():
    from dinamo.sistema import construir_sistema
    brain = construir_sistema(Config(archivos=(RUTA,)))
    assert brain.perfil.nombre == "catch_capital_humano"           # el perfil de perfiles/ se aplicó
    r = brain.responder("¿Cómo ha evolucionado la rotación?")
    assert [d["orden"] for d in r.datos["tendencia"]] == list(range(7))
    assert r.evidencias[0].valor == pytest.approx(0.1035, abs=1e-3)       # Julio-Agosto 2024
