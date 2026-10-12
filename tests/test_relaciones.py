"""Pruebas v2 para la Skill relaciones."""

from __future__ import annotations

from dinamo.skills.relaciones import Relaciones


def test_relaciones_panel(datos_panel):
    """Calcula relaciones a nivel de tienda."""
    skill = Relaciones()

    resultado = skill(
        datos_panel,
        {
            "metrica": "tasa_quejas",
        },
    )

    assert resultado.skill == "relaciones"
    assert len(resultado.datos) >= 1
    assert len(resultado.evidencias) == len(resultado.datos)

    for registro in resultado.datos:
        assert "variable" in registro
        assert "rho" in registro
        assert -1.0 <= registro["rho"] <= 1.0
        assert registro["n"] >= 2

    for evidencia in resultado.evidencias:
        assert evidencia.unidad == "rho"
        assert evidencia.metodo == (
            "correlación de Spearman a nivel de entidad"
        )


def test_relaciones_simple(datos_simple):
    """Funciona también con una base sin tiempo."""
    skill = Relaciones()

    resultado = skill(
        datos_simple,
        {
            "metrica": "renuncio",
        },
    )

    assert resultado.skill == "relaciones"
    assert any(
        registro["variable"] == "salario_mensual"
        for registro in resultado.datos
    )


def test_orden_por_abs_rho(datos_panel):
    """Las relaciones se ordenan por fuerza absoluta."""
    skill = Relaciones()

    resultado = skill(
        datos_panel,
        {
            "metrica": "tasa_quejas",
        },
    )

    abs_rhos = [
        registro["abs_rho"]
        for registro in resultado.datos
    ]

    assert abs_rhos == sorted(
        abs_rhos,
        reverse=True,
    )


def test_es_determinista(datos_panel):
    """La misma entrada produce el mismo resultado."""
    skill = Relaciones()

    parametros = {
        "metrica": "tasa_quejas",
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


def test_filtros(datos_panel):
    """Los filtros se aplican antes del cálculo."""
    skill = Relaciones()

    resultado = skill(
        datos_panel,
        {
            "metrica": "tasa_quejas",
            "filtros": {"region": "Norte"},
        },
    )

    # Con las dos tiendas Norte existe variación suficiente para
    # calcular la correlación.
    assert resultado.skill == "relaciones"
    assert len(resultado.datos) >= 1


def test_exige_metrica(datos_panel):
    """La métrica objetivo es obligatoria."""
    skill = Relaciones()

    try:
        skill(datos_panel, {})
    except ValueError:
        return

    raise AssertionError(
        "La Skill debía exigir el parámetro 'metrica'."
    )
