import pandas as pd
import pytest

from dinamo.data_engine import DataEngine
from dinamo.skills import (
    Anomalias,
    DescribirDataset,
    ParametroInvalido,
    Ranking,
    Tendencia,
    crear_registro,
)


def valores(res):
    return {e.descripcion: e.valor for e in res.evidencias}


def test_describir_funciona_con_cualquier_base(datos_panel, datos_simple):
    v = valores(DescribirDataset()(datos_panel, {}))
    assert v["Número de tiendas en 'tiendas'"] == 3
    assert v["Número de periodos en 'tiendas'"] == 3
    assert v["Proporción de filas de 'tiendas' con dato reportado (no imputado)"] == pytest.approx(8 / 9)

    v = valores(DescribirDataset()(datos_simple, {}))
    assert v["Número de empleados en 'empleados'"] == 6
    assert "Número de periodos en 'empleados'" not in v


def test_tendencia_calcula_la_mediana_por_periodo(datos_panel):
    res = Tendencia()(datos_panel, {"metrica": "ventas"})
    v = valores(res)

    # enero: mediana(100, 200, 50) = 100
    # marzo: mediana(120, 160, 70) = 120
    assert v["Ventas en 2024-01"] == 100
    assert v["Ventas en 2024-03"] == 120

    assert v["Cambio relativo de ventas"] == pytest.approx(0.20)

    # febrero excluye el 999 de la tienda 3 (no válido):
    # mediana(110, 180) = 145
    assert [d["valor"] for d in res.datos] == [100, 145, 120]


def test_tendencia_con_un_solo_periodo(datos_panel):
    res = Tendencia()(
        datos_panel,
        {
            "metrica": "ventas",
            "filtros": {"mes": "2024-01"},
        },
    )

    assert len(res.evidencias) == 1
    assert "un periodo" in res.advertencias[0]


def test_tendencia_no_aplica_sin_tiempo(datos_simple):
    assert not Tendencia().aplica(datos_simple.perfil)

    with pytest.raises(ParametroInvalido):
        Tendencia()(
            datos_simple,
            {"metrica": "salario_mensual"},
        )


def test_ranking_ordena_y_respeta_el_minimo_de_periodos(datos_panel):
    res = Ranking()(
        datos_panel,
        {
            "metrica": "ventas",
            "min_periodos": 3,
        },
    )

    assert [d["entidad"] for d in res.datos] == [2, 1]
    assert "quedaron fuera" in res.advertencias[0]

    res = Ranking()(
        datos_panel,
        {
            "metrica": "ventas",
            "orden": "asc",
            "min_periodos": 1,
        },
    )

    assert [d["entidad"] for d in res.datos] == [3, 1, 2]


def test_ranking_funciona_sin_tiempo(datos_simple):
    res = Ranking()(
        datos_simple,
        {
            "metrica": "salario_mensual",
            "n": 2,
        },
    )

    assert [d["entidad"] for d in res.datos] == [4, 3]


def test_parametros_invalidos(datos_panel):
    with pytest.raises(ParametroInvalido):
        Tendencia()(datos_panel, {})

    with pytest.raises(ParametroInvalido):
        Tendencia()(
            datos_panel,
            {"metrica": "region"},
        )


def test_las_skills_son_deterministicas(datos_panel):
    assert Ranking()(
        datos_panel,
        {"metrica": "ventas"},
    ) == Ranking()(
        datos_panel,
        {"metrica": "ventas"},
    )


def test_el_registro_sabe_que_se_puede_responder_con_cada_base(
    datos_panel,
    datos_simple,
):
    registro = crear_registro()

    assert {
        "describir_datos",
        "tendencia",
        "ranking",
    } <= registro.intenciones_disponibles(
        datos_panel.perfil
    )

    assert "tendencia" not in registro.intenciones_disponibles(
        datos_simple.perfil
    )


def test_ranking_cuenta_periodos_unicos_y_no_filas_duplicadas(
    tabla_panel,
    datos_panel,
):
    """Una entidad repetida en el mismo periodo no debe sumar periodos."""
    filas_base = tabla_panel[
        ~(
            (tabla_panel["tienda_id"] == 3)
            & (tabla_panel["mes"] != "2024-01")
        )
    ].copy()

    fila = filas_base[
        (filas_base["tienda_id"] == 3)
        & (filas_base["mes"] == "2024-01")
    ].iloc[0]

    duplicados = pd.DataFrame(
        [
            fila.to_dict(),
            fila.to_dict(),
        ]
    )

    tabla = pd.concat(
        [filas_base, duplicados],
        ignore_index=True,
    )

    datos = DataEngine(
        tabla,
        datos_panel.perfil,
    )

    res = Ranking()(
        datos,
        {
            "metrica": "ventas",
            "min_periodos": 2,
        },
    )

    assert 3 not in [d["entidad"] for d in res.datos]
    assert any(
        "quedaron fuera" in advertencia
        for advertencia in res.advertencias
    )


def test_tendencia_cuenta_entidades_y_no_filas_duplicadas(
    tabla_panel,
    datos_panel,
):
    """El n de tendencia debe contar entidades, no filas duplicadas."""
    fila = tabla_panel[
        (tabla_panel["tienda_id"] == 1)
        & (tabla_panel["mes"] == "2024-01")
    ].iloc[0]

    duplicados = pd.DataFrame(
        [
            fila.to_dict(),
            fila.to_dict(),
            fila.to_dict(),
            fila.to_dict(),
        ]
    )

    tabla = pd.concat(
        [tabla_panel, duplicados],
        ignore_index=True,
    )

    datos = DataEngine(
        tabla,
        datos_panel.perfil,
    )

    res = Tendencia()(
        datos,
        {
            "metrica": "ventas",
        },
    )

    enero = next(
        dato
        for dato in res.datos
        if dato["periodo"] == "2024-01"
    )

    # Siguen siendo 3 tiendas distintas en enero,
    # aunque una tenga filas duplicadas.
    assert enero["n"] == 3
    assert enero["valor"] == 100


def test_anomalias_detecta_un_valor_extremo_en_el_ultimo_periodo(
    tabla_panel,
    datos_panel,
):
    """Detecta una entidad cuyo último valor se aleja fuertemente de su historia."""
    tabla = tabla_panel.copy()

    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-03"),
        "ventas",
    ] = 1000

    datos = DataEngine(tabla, datos_panel.perfil)

    res = Anomalias()(
        datos,
        {
            "metrica": "ventas",
            "min_periodos": 2,
        },
    )

    entidad_1 = next(
        d for d in res.datos
        if d["entidad"] == 1
    )

    assert entidad_1["periodo"] == "2024-03"
    assert entidad_1["mediana_historica"] == pytest.approx(105)
    assert entidad_1["mad"] == pytest.approx(5)
    assert entidad_1["desviacion_robusta"] == pytest.approx(179)
    assert entidad_1["desviacion_robusta"] > 3

def test_anomalias_no_usa_el_ultimo_periodo_para_la_historia(
    tabla_panel,
    datos_panel,
):
    """La referencia histórica se calcula antes del periodo evaluado."""
    tabla = tabla_panel.copy()

    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-03"),
        "ventas",
    ] = 1000

    datos = DataEngine(tabla, datos_panel.perfil)

    res = Anomalias()(
        datos,
        {
            "metrica": "ventas",
            "min_periodos": 2,
        },
    )

    entidad_1 = next(
        d for d in res.datos
        if d["entidad"] == 1
    )

    assert entidad_1["periodo"] == "2024-03"
    assert entidad_1["mediana_historica"] == pytest.approx(105)


def test_anomalias_no_confunde_filas_duplicadas_con_periodos(
    tabla_panel,
    datos_panel,
):
    """Duplicar filas del mismo periodo no aumenta la historia de la entidad."""
    tabla = tabla_panel.copy()

    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-03"),
        "ventas",
    ] = 1000

    fila = tabla[
        (tabla["tienda_id"] == 1)
        & (tabla["mes"] == "2024-01")
    ].iloc[0]

    duplicados = pd.DataFrame(
        [fila.to_dict(), fila.to_dict(), fila.to_dict()]
    )

    tabla = pd.concat(
        [tabla, duplicados],
        ignore_index=True,
    )

    datos = DataEngine(tabla, datos_panel.perfil)

    res = Anomalias()(
        datos,
        {
            "metrica": "ventas",
            "min_periodos": 2,
        },
    )

    entidad_1 = next(
        d for d in res.datos
        if d["entidad"] == 1
    )

    assert entidad_1["periodos_historia"] == 2

def test_anomalias_excluye_entidades_con_historia_insuficiente(
    datos_panel,
):
    res = Anomalias()(
        datos_panel,
        {
            "metrica": "ventas",
            "min_periodos": 3,
        },
    )

    assert res.datos == ()
    assert any(
        "historia" in advertencia
        for advertencia in res.advertencias
    )


def test_anomalias_mad_cero_genera_advertencia(
    tabla_panel,
    datos_panel,
):
    tabla = tabla_panel.copy()

    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-01"),
        "ventas",
    ] = 100
    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-02"),
        "ventas",
    ] = 100
    tabla.loc[
        (tabla["tienda_id"] == 1) & (tabla["mes"] == "2024-03"),
        "ventas",
    ] = 120

    datos = DataEngine(tabla, datos_panel.perfil)

    res = Anomalias()(
        datos,
        {
            "metrica": "ventas",
            "min_periodos": 2,
        },
    )

    assert 1 not in [d["entidad"] for d in res.datos]
    assert any(
        "MAD" in advertencia
        for advertencia in res.advertencias
    )


def test_anomalias_es_deterministica(datos_panel):
    parametros = {
        "metrica": "ventas",
        "min_periodos": 2,
    }

    assert Anomalias()(datos_panel, parametros) == Anomalias()(
        datos_panel,
        parametros,
    )

from dinamo.skills import BrechaPares


def _datos_brecha():
    """Base sintética genérica para probar la comparación contra pares."""
    tabla = pd.DataFrame(
        [
            # Entidad objetivo: empresa 1.
            {
                "empresa_id": 1,
                "periodo": "2024-01",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 90.0,
                "valido": 1,
            },
            {
                "empresa_id": 1,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 10.0,
                "valido": 1,
            },
            # Par 1: dos filas en el mismo periodo.
            # Promedio = 20.
            {
                "empresa_id": 2,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 18.0,
                "valido": 1,
            },
            {
                "empresa_id": 2,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 22.0,
                "valido": 1,
            },
            # Par 2.
            {
                "empresa_id": 3,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 30.0,
                "valido": 1,
            },
            # Par 3.
            {
                "empresa_id": 4,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 40.0,
                "valido": 1,
            },
            # Misma categoría, distinto Tier: no es par.
            {
                "empresa_id": 5,
                "periodo": "2024-02",
                "nivel": "Tier 2",
                "categoria": "A",
                "region": "Norte",
                "kpi": 200.0,
                "valido": 1,
            },
            # Mismo Tier, distinta categoría: no es par.
            {
                "empresa_id": 6,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "B",
                "region": "Norte",
                "kpi": 300.0,
                "valido": 1,
            },
            # Mismo grupo, pero otro periodo: no debe entrar.
            {
                "empresa_id": 7,
                "periodo": "2024-01",
                "nivel": "Tier 1",
                "categoria": "A",
                "region": "Norte",
                "kpi": 1000.0,
                "valido": 1,
            },
        ]
    )

    config = {
        "columnas": [
            {"nombre": "empresa_id", "rol": "entidad"},
            {"nombre": "periodo", "rol": "tiempo"},
            {
                "nombre": "kpi",
                "rol": "metrica",
                "agregacion": "promedio",
            },
            {"nombre": "nivel", "rol": "dimension"},
            {"nombre": "categoria", "rol": "dimension"},
            {"nombre": "region", "rol": "dimension"},
            {"nombre": "valido", "rol": "validez"},
        ]
    }

    return DataEngine.desde_tabla(
        tabla,
        nombre="empresas_genericas",
        config=config,
    )


def test_brecha_pares_calcula_mediana_y_brecha():
    """La brecha usa la mediana de los pares del mismo grupo."""
    datos = _datos_brecha()

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    assert len(res.datos) == 1

    resultado = res.datos[0]

    assert resultado["entidad"] == 1
    assert resultado["periodo"] == "2024-02"
    assert resultado["valor_entidad"] == pytest.approx(10.0)
    assert resultado["mediana_pares"] == pytest.approx(30.0)
    assert resultado["brecha"] == pytest.approx(-20.0)
    assert resultado["n_pares"] == 3


def test_brecha_pares_excluye_la_entidad_objetivo_de_los_pares():
    """La propia entidad nunca debe participar en su mediana de pares."""
    datos = _datos_brecha()

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 3,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    resultado = res.datos[0]

    assert resultado["n_pares"] == 3
    assert resultado["mediana_pares"] == pytest.approx(20.0)
    assert resultado["brecha"] == pytest.approx(10.0)


def test_brecha_pares_respeta_la_agregacion_del_perfil():
    """Varias filas de una entidad en un periodo se agregan según el Perfil."""
    datos = _datos_brecha()

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    resultado = res.datos[0]

    # Empresa 2: promedio de 18 y 22 = 20.
    # Pares: 20, 30 y 40 -> mediana = 30.
    assert resultado["mediana_pares"] == pytest.approx(30.0)
    assert resultado["n_pares"] == 3


def test_brecha_pares_usa_solo_el_periodo_seleccionado():
    """Los valores de otros periodos no contaminan la comparación."""
    datos = _datos_brecha()

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
            "periodo": "2024-01",
        },
    )

    resultado = res.datos[0]

    # En 2024-01 solo existe la entidad objetivo y la empresa 7.
    assert resultado["periodo"] == "2024-01"
    assert resultado["n_pares"] == 1
    assert resultado["mediana_pares"] == pytest.approx(1000.0)
    assert resultado["brecha"] == pytest.approx(-910.0)
    assert any(
        "solo 1 entidad" in advertencia
        for advertencia in res.advertencias
    )


def test_brecha_pares_advierte_si_no_existen_pares():
    """Un grupo sin otras entidades produce advertencia y no inventa una mediana."""
    tabla = pd.DataFrame(
        [
            {
                "empresa_id": 1,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "kpi": 10.0,
                "valido": 1,
            }
        ]
    )

    config = {
        "columnas": [
            {"nombre": "empresa_id", "rol": "entidad"},
            {"nombre": "periodo", "rol": "tiempo"},
            {
                "nombre": "kpi",
                "rol": "metrica",
                "agregacion": "promedio",
            },
            {"nombre": "nivel", "rol": "dimension"},
            {"nombre": "categoria", "rol": "dimension"},
            {"nombre": "valido", "rol": "validez"},
        ]
    }

    datos = DataEngine.desde_tabla(
        tabla,
        nombre="sin_pares",
        config=config,
    )

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    assert len(res.datos) == 1
    assert res.datos[0]["mediana_pares"] is None
    assert res.datos[0]["brecha"] is None
    assert res.datos[0]["n_pares"] == 0
    assert any("No existen otras entidades" in a for a in res.advertencias)
    assert res.evidencias == ()


def test_brecha_pares_advierte_con_un_solo_par():
    """Una sola entidad de referencia se calcula, pero se advierte su baja base."""
    tabla = pd.DataFrame(
        [
            {
                "empresa_id": 1,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "kpi": 10.0,
                "valido": 1,
            },
            {
                "empresa_id": 2,
                "periodo": "2024-02",
                "nivel": "Tier 1",
                "categoria": "A",
                "kpi": 20.0,
                "valido": 1,
            },
            {
                "empresa_id": 3,
                "periodo": "2024-02",
                "nivel": "Tier 2",
                "categoria": "A",
                "kpi": 100.0,
                "valido": 1,
            },
        ]
    )

    config = {
        "columnas": [
            {"nombre": "empresa_id", "rol": "entidad"},
            {"nombre": "periodo", "rol": "tiempo"},
            {
                "nombre": "kpi",
                "rol": "metrica",
                "agregacion": "promedio",
            },
            {"nombre": "nivel", "rol": "dimension"},
            {"nombre": "categoria", "rol": "dimension"},
            {"nombre": "valido", "rol": "validez"},
        ]
    }

    datos = DataEngine.desde_tabla(
        tabla,
        nombre="un_par",
        config=config,
    )

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    resultado = res.datos[0]

    assert resultado["n_pares"] == 1
    assert resultado["mediana_pares"] == pytest.approx(20.0)
    assert resultado["brecha"] == pytest.approx(-10.0)
    assert any(
        "solo 1 entidad" in advertencia
        for advertencia in res.advertencias
    )


def test_brecha_pares_genera_evidence_trazable():
    """La salida numérica principal queda respaldada por Evidence."""
    datos = _datos_brecha()

    res = BrechaPares()(
        datos,
        {
            "metrica": "kpi",
            "entidad_objetivo": 1,
            "dimensiones_pares": ["nivel", "categoria"],
        },
    )

    assert len(res.evidencias) == 3

    valores = [e.valor for e in res.evidencias]
    assert valores == pytest.approx([10.0, 30.0, -20.0])

    assert res.evidencias[0].n == 1
    assert res.evidencias[1].n == 3
    assert res.evidencias[2].n == 3

    assert all(e.skill == "brecha_pares" for e in res.evidencias)
    assert all(e.unidad == "numero" for e in res.evidencias)


def test_brecha_pares_es_deterministica():
    """La misma Skill con los mismos datos produce exactamente el mismo resultado."""
    datos = _datos_brecha()

    parametros = {
        "metrica": "kpi",
        "entidad_objetivo": 1,
        "dimensiones_pares": ["nivel", "categoria"],
    }

    assert BrechaPares()(datos, parametros) == BrechaPares()(
        datos,
        parametros,
    )
