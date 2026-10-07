import pytest

from dinamo.core.contracts import Columna, PerfilDataset
from dinamo.data_engine import DataEngine, DatosInvalidos


def test_filtra_filas_validas_y_por_columna(datos_panel):
    assert len(datos_panel.filas(solo_validas=False)) == 9
    assert len(datos_panel.filas()) == 8                       # la tienda 3 no reportó febrero
    assert set(datos_panel.filas(region="Sur")["tienda_id"]) == {3}


def test_devuelve_copias(datos_panel):
    df = datos_panel.filas()
    df["ventas"] = -1
    assert datos_panel.filas()["ventas"].min() > 0


def test_periodos_y_entidades(datos_panel, datos_simple):
    assert datos_panel.periodos() == [("2024-01", "2024-01"), ("2024-02", "2024-02"), ("2024-03", "2024-03")]
    assert datos_panel.entidades()[0] == (1, "Tienda Centro")
    assert datos_simple.periodos() == []


def test_filtro_sobre_columna_inexistente(datos_panel):
    with pytest.raises(KeyError):
        datos_panel.filas(no_existe=1)


def test_perfil_que_no_coincide_con_la_tabla(tabla_simple):
    perfil = PerfilDataset("x", "x", (Columna("otra_columna", "metrica"),))
    with pytest.raises(DatosInvalidos):
        DataEngine(tabla_simple, perfil)
