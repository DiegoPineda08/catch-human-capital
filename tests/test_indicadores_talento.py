"""Skill indicadores_talento con datos sintéticos."""
import pandas as pd
import pytest

from dinamo.data_engine import DataEngine
from dinamo.skills import ParametroInvalido, crear_registro

SKILL = crear_registro().obtener("indicadores_talento")


def panel():
    return DataEngine.desde_tabla(pd.DataFrame({
        "sucursal": ["A", "B", "C", "D"] * 3, "mes": [1] * 4 + [2] * 4 + [3] * 4,
        "headcount": [100, 50, 80, 120] * 3, "bajas": [5, 2, 4, 6, 3, 1, 8, 2, 4, 4, 4, 4],
        "faltas": [40, 20, 30, 50] * 3, "dias_habiles": [20] * 12, "contrataciones": [6, 1, 3, 7] * 3,
        "tasa_rotacion": [0.5] * 12}), "suc")


def valores(res):
    return {e.descripcion: e.valor for e in res.evidencias}


def test_formulas_agregan_antes_de_dividir():
    v = valores(SKILL(panel(), {}))
    assert v["Rotación — periodo 1"] == pytest.approx(17 / 350, abs=1e-6)          # no el promedio de tasas
    assert v["Retención — periodo 1"] == pytest.approx(1 - 17 / 350, abs=1e-6)
    assert v["Ausentismo — periodo 2"] == pytest.approx(140 / (350 * 20), abs=1e-6)
    assert v["Contratación — periodo 3"] == pytest.approx(17 / 350, abs=1e-6)
    assert all("tasa_rotacion" not in e.metodo for e in SKILL(panel(), {}).evidencias)


def test_reproducible_y_trazable():
    a, b = SKILL(panel(), {}), SKILL(panel(), {})
    assert [e.id for e in a.evidencias] == [e.id for e in b.evidencias]
    assert all(e.filtros["tabla"] == "suc" and e.unidad == "proporcion" for e in a.evidencias)


def test_foto_de_empleados_advierte_que_no_es_tasa():
    df = pd.DataFrame({"empleado_id": range(30), "area": ["X"] * 25 + ["Y"] * 5,
                       "salario": [10000 + 37 * i for i in range(30)], "renuncio": [1, 0, 0] * 10})
    res = SKILL(DataEngine.desde_tabla(df, "emp"), {"dimension": "area"})
    v = valores(res)
    assert v["Proporción de personas que dejaron la empresa (foto, no tasa por periodo) — area Y"] == pytest.approx(0.2)
    assert any("foto" in a for a in res.advertencias) and any("sólo 5" in a for a in res.advertencias)


def test_sin_columnas_reconocibles_falla_claro():
    m = DataEngine.desde_tabla(pd.DataFrame({"tienda": list("abcdef"), "ventas": [1, 2, 3, 4, 5, 6.5]}), "v")
    assert not SKILL.aplica(m.perfil)
    with pytest.raises(ParametroInvalido, match="no encontré"):
        SKILL(m, {})
    with pytest.raises(ParametroInvalido, match="no existe"):
        SKILL(m, {"bajas": "inventada", "plantilla": "ventas"})
