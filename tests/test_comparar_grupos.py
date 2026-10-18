"""Pruebas v2 para la Skill comparar_grupos."""

from __future__ import annotations

import pytest

from dinamo.skills.comparar_grupos import CompararGrupos


def test_compara_grupos_panel(datos_panel):
    """Compara ventas entre regiones a nivel de entidad."""
    skill = CompararGrupos()

    resultado = skill(
        datos_panel,
        {
            "metrica": "ventas",
            "dimension": "region",
        },
    )

    assert resultado.skill == "comparar_grupos"
    assert len(resultado.evidencias) == 3

    grupos = {
        registro["grupo"]: registro
        for registro in resultado.datos
    }

    assert grupos["Norte"]["valor"] == 145.0
    assert grupos["Sur"]["valor"] == 60.0

    diferencia = next(
        evidencia
        for evidencia in resultado.evidencias
        if "Diferencia" in evidencia.descripcion
    )

    assert diferencia.valor == 85.0
    assert diferencia.n == 3


def test_agrega_primero_por_entidad(datos_panel):
    """Los periodos no deben dar mayor peso a una entidad."""
    skill = CompararGrupos()

    resultado = skill(
        datos_panel,
        {
            "metrica": "ventas",
            "dimension": "region",
        },
    )

    grupos = {
        registro["grupo"]: registro
        for registro in resultado.datos
    }

    assert grupos["Norte"]["valor"] == 145.0
    assert grupos["Sur"]["valor"] == 60.0


def test_compara_grupos_sin_tiempo(datos_simple):
    """También funciona con una base sin columna temporal."""
    skill = CompararGrupos()

    resultado = skill(
        datos_simple,
        {
            "metrica": "salario_mensual",
            "dimension": "area",
        },
    )

    assert resultado.skill == "comparar_grupos"

    grupos = {
        registro["grupo"]: registro
        for registro in resultado.datos
    }

    assert grupos["Ventas"]["valor"] == 11000.0
    assert grupos["Finanzas"]["valor"] == 21000.0
    assert grupos["Logística"]["valor"] == 9250.0

    diferencia = next(
        evidencia
        for evidencia in resultado.evidencias
        if "Diferencia" in evidencia.descripcion
    )

    assert diferencia.valor == 11750.0


def test_advierte_grupos_pequenos(datos_panel):
    """Advierte cuando existen grupos con menos de 10 entidades."""
    skill = CompararGrupos()

    resultado = skill(
        datos_panel,
        {
            "metrica": "ventas",
            "dimension": "region",
        },
    )

    assert any(
        "menos de 10" in advertencia
        for advertencia in resultado.advertencias
    )


def test_aplica_filtros(datos_panel):
    """Los filtros del usuario se aplican antes del cálculo."""
    skill = CompararGrupos()

    resultado = skill(
        datos_panel,
        {
            "metrica": "ventas",
            "dimension": "region",
            "filtros": {"region": "Norte"},
        },
    )

    assert resultado.datos == ()
    assert resultado.evidencias == ()
    assert any(
        "al menos dos grupos" in advertencia
        for advertencia in resultado.advertencias
    )


def test_es_determinista(datos_panel):
    """La misma entrada produce el mismo ResultadoSkill."""
    skill = CompararGrupos()

    parametros = {
        "metrica": "ventas",
        "dimension": "region",
    }

    resultado_1 = skill(
        datos_panel,
        parametros,
    )

    resultado_2 = skill(
        datos_panel,
        parametros,
    )

    assert resultado_1 == resultado_2


def test_exige_metrica_y_dimension(datos_panel):
    """Los parámetros requeridos deben ser obligatorios."""
    skill = CompararGrupos()

    with pytest.raises(ValueError):
        skill(
            datos_panel,
            {
                "dimension": "region",
            },
        )

    with pytest.raises(ValueError):
        skill(
            datos_panel,
            {
                "metrica": "ventas",
            },
        )


def test_metrica_binaria_usa_proporcion_no_mediana():
    """Con una marca 0/1 (p.ej. renunció) la mediana por grupo sería 0 o 1: se usa la proporción."""
    import pandas as pd
    from dinamo.data_engine import DataEngine
    from dinamo.skills import CompararGrupos
    df = pd.DataFrame({"empleado_id": range(1001, 1041), "area": ["A"] * 20 + ["B"] * 20,
                       "salario": [1000 + 13 * i for i in range(40)],
                       "renuncio": [1] * 6 + [0] * 14 + [1] * 2 + [0] * 18})
    m = DataEngine.desde_tabla(df, "emp")
    res = CompararGrupos()(m, {"metrica": "renuncio", "dimension": "area"})
    valores = {e.filtros.get("grupo"): e.valor for e in res.evidencias if "grupo" in e.filtros}
    assert valores == {"A": 0.3, "B": 0.1}
    assert any(abs(e.valor - 0.2) < 1e-9 and e.unidad == "diferencia_proporcion" for e in res.evidencias)
