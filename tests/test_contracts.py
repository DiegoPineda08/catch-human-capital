import dataclasses

import pytest

from dinamo.core.contracts import Columna, Evidencia, PerfilDataset, Plan, crear_evidencia


def test_id_de_evidencia_es_deterministico():
    a = crear_evidencia("s", "desc", 0.1234567891, "proporcion", 10, "mediana", {"metrica": "x"})
    b = crear_evidencia("s", "desc", 0.1234567891, "proporcion", 10, "mediana", {"metrica": "x"})
    assert a.id == b.id and a.id.startswith("s:")


def test_id_cambia_si_cambian_los_filtros():
    a = crear_evidencia("s", "desc", 1, "proporcion", 10, "mediana", {"metrica": "x"})
    b = crear_evidencia("s", "desc", 1, "proporcion", 10, "mediana", {"metrica": "y"})
    assert a.id != b.id


def test_contratos_son_inmutables():
    e = crear_evidencia("s", "desc", 1, "proporcion", 1, "m")
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.valor = 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        Plan("tendencia").intencion = "ranking"


def test_evidencia_se_serializa():
    e = crear_evidencia("s", "desc", 1.5, "moneda", 3, "m", {"a": 1})
    assert Evidencia(**e.a_dict()) == e


def test_columna_rechaza_roles_y_unidades_invalidas():
    with pytest.raises(ValueError):
        Columna("x", "kpi")
    with pytest.raises(ValueError):
        Columna("x", "metrica", unidad="pesos")


def test_perfil_ida_y_vuelta_a_diccionario(datos_panel):
    perfil = datos_panel.perfil
    assert PerfilDataset.desde_dict(perfil.a_dict()) == perfil


def test_con_columna_no_modifica_el_original(datos_panel):
    perfil = datos_panel.perfil
    nueva = dataclasses.replace(perfil.columna("ventas"), etiqueta="ingresos")
    cambiado = perfil.con_columna(nueva)
    assert cambiado.columna("ventas").etiqueta == "ingresos"
    assert perfil.columna("ventas").etiqueta != "ingresos"
