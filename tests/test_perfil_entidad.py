"""Pruebas v2 para la Skill perfil_entidad."""

from __future__ import annotations


from dinamo.skills.perfil_entidad import PerfilEntidad


def test_perfil_entidad_panel(datos_panel):
    """Construye el perfil de una tienda en el último periodo."""
    skill = PerfilEntidad()

    resultado = skill(
        datos_panel,
        {
            "filtros": {"tienda_id": 1},
            "metrica": "ventas",
        },
    )

    assert resultado.skill == "perfil_entidad"
    assert len(resultado.datos) == 1

    perfil = resultado.datos[0]

    assert perfil["entidad"] == 1
    assert perfil["nombre"] == "Tienda Centro"
    assert perfil["periodo"] == "2024-03"

    assert perfil["metricas"]["ventas"] == 120.0
    assert perfil["metricas"]["tasa_quejas"] == 0.06

    assert perfil["atributos"]["region"] == "Norte"


def test_perfil_entidad_simple(datos_simple):
    """Funciona con una base que no tiene variable temporal."""
    skill = PerfilEntidad()

    resultado = skill(
        datos_simple,
        {
            "filtros": {"empleado_id": 1},
        },
    )

    assert resultado.skill == "perfil_entidad"
    assert len(resultado.datos) == 1

    perfil = resultado.datos[0]

    assert perfil["entidad"] == 1
    assert perfil["metricas"]["salario_mensual"] == 10000.0
    assert perfil["atributos"]["area"] == "Ventas"


def test_genera_comparacion_poblacional(datos_panel):
    """Genera mediana y percentil para las métricas."""
    skill = PerfilEntidad()

    resultado = skill(
        datos_panel,
        {
            "filtros": {"tienda_id": 1},
        },
    )

    medianas = [
        evidencia
        for evidencia in resultado.evidencias
        if "Mediana poblacional" in evidencia.descripcion
    ]

    percentiles = [
        evidencia
        for evidencia in resultado.evidencias
        if "Percentil" in evidencia.descripcion
    ]

    assert len(medianas) >= 1
    assert len(percentiles) >= 1


def test_usa_ultimo_periodo_valido(datos_panel):
    """El perfil utiliza marzo como último periodo válido."""
    skill = PerfilEntidad()

    resultado = skill(
        datos_panel,
        {
            "filtros": {"tienda_id": 1},
        },
    )

    assert resultado.datos[0]["periodo"] == "2024-03"


def test_entidad_inexistente(datos_panel):
    """Una entidad inexistente produce una advertencia."""
    skill = PerfilEntidad()

    resultado = skill(
        datos_panel,
        {
            "filtros": {"tienda_id": 999},
        },
    )

    assert resultado.datos == ()
    assert resultado.evidencias == ()
    assert len(resultado.advertencias) >= 1


def test_es_determinista(datos_panel):
    """La misma entrada produce el mismo resultado."""
    skill = PerfilEntidad()

    parametros = {
        "filtros": {"tienda_id": 1},
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
