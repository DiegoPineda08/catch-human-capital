import pytest

from dinamo.skills import DescribirDataset, ParametroInvalido, Ranking, Tendencia, crear_registro


def valores(res):
    return {e.descripcion: e.valor for e in res.evidencias}


def test_describir_funciona_con_cualquier_base(datos_panel, datos_simple):
    v = valores(DescribirDataset()(datos_panel, {}))
    assert v["Número de tiendas en 'tiendas'"] == 3 and v["Número de periodos en 'tiendas'"] == 3
    assert v["Proporción de filas de 'tiendas' con dato reportado (no imputado)"] == pytest.approx(8 / 9)
    v = valores(DescribirDataset()(datos_simple, {}))
    assert v["Número de empleados en 'empleados'"] == 6 and "Número de periodos en 'empleados'" not in v


def test_tendencia_calcula_la_mediana_por_periodo(datos_panel):
    res = Tendencia()(datos_panel, {"metrica": "ventas"})
    v = valores(res)
    # enero: mediana(100, 200, 50) = 100 ; marzo: mediana(120, 160, 70) = 120
    assert v["Ventas en 2024-01"] == 100 and v["Ventas en 2024-03"] == 120
    assert v["Cambio relativo de ventas"] == pytest.approx(0.20)
    # febrero excluye el 999 de la tienda 3 (no válido): mediana(110, 180) = 145
    assert [d["valor"] for d in res.datos] == [100, 145, 120]


def test_tendencia_con_un_solo_periodo(datos_panel):
    res = Tendencia()(datos_panel, {"metrica": "ventas", "filtros": {"mes": "2024-01"}})
    assert len(res.evidencias) == 1 and "un periodo" in res.advertencias[0]


def test_tendencia_no_aplica_sin_tiempo(datos_simple):
    assert not Tendencia().aplica(datos_simple.perfil)
    with pytest.raises(ParametroInvalido):
        Tendencia()(datos_simple, {"metrica": "salario_mensual"})


def test_ranking_ordena_y_respeta_el_minimo_de_periodos(datos_panel):
    res = Ranking()(datos_panel, {"metrica": "ventas", "min_periodos": 3})
    assert [d["entidad"] for d in res.datos] == [2, 1]          # la tienda 3 sólo tiene 2 meses válidos
    assert "quedaron fuera" in res.advertencias[0]
    res = Ranking()(datos_panel, {"metrica": "ventas", "orden": "asc", "min_periodos": 1})
    assert [d["entidad"] for d in res.datos] == [3, 1, 2]


def test_ranking_funciona_sin_tiempo(datos_simple):
    res = Ranking()(datos_simple, {"metrica": "salario_mensual", "n": 2})
    assert [d["entidad"] for d in res.datos] == [4, 3]


def test_parametros_invalidos(datos_panel):
    with pytest.raises(ParametroInvalido):
        Tendencia()(datos_panel, {})
    with pytest.raises(ParametroInvalido):
        Tendencia()(datos_panel, {"metrica": "region"})       # region es dimensión, no métrica


def test_las_skills_son_deterministicas(datos_panel):
    assert Ranking()(datos_panel, {"metrica": "ventas"}) == Ranking()(datos_panel, {"metrica": "ventas"})


def test_el_registro_sabe_que_se_puede_responder_con_cada_base(datos_panel, datos_simple):
    registro = crear_registro()
    assert {"describir_datos", "tendencia", "ranking"} <= registro.intenciones_disponibles(datos_panel.perfil)
    assert "tendencia" not in registro.intenciones_disponibles(datos_simple.perfil)
