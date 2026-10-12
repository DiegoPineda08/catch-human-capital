"""
Datos INVENTADOS para los tests. No dependen del Excel real: así los tests corren en
cualquier computadora, en segundos, y con valores fáciles de verificar a mano.

Hay DOS bases muy distintas a propósito: si una pieza sólo funcionara con una de ellas,
los tests lo detectarían. Eso protege la promesa de que DINAMO sirve para cualquier base.
"""
import pandas as pd
import pytest

from dinamo.brain import Brain
from dinamo.data_engine import Biblioteca, DataEngine
from dinamo.evidence import EvidenceStore
from dinamo.llm import LLMFalso
from dinamo.rac import Retriever
from dinamo.skills import crear_registro
from dinamo.state import EstadoSesion


@pytest.fixture
def tabla_panel():
    """3 tiendas x 3 meses. La tienda 3 no reportó febrero (valido = 0)."""
    ventas = {1: [100, 110, 120], 2: [200, 180, 160], 3: [50, 999, 70]}
    quejas = {1: [0.10, 0.08, 0.06], 2: [0.20, 0.18, 0.10], 3: [0.05, 0.50, 0.02]}
    filas = []
    for tienda, nombre, region in [(1, "Tienda Centro", "Norte"), (2, "Tienda Plaza", "Norte"),
                                   (3, "Tienda Puerto", "Sur")]:
        for i, mes in enumerate(["2024-01", "2024-02", "2024-03"]):
            filas.append({"tienda_id": tienda, "tienda": nombre, "mes": mes, "region": region,
                          "ventas": ventas[tienda][i], "tasa_quejas": quejas[tienda][i],
                          "valido": 0 if (tienda == 3 and i == 1) else 1})
    return pd.DataFrame(filas)


@pytest.fixture
def tabla_simple():
    """6 empleados, sin columna de tiempo."""
    return pd.DataFrame({
        "empleado_id": [1, 2, 3, 4, 5, 6],
        "area": ["Ventas", "Ventas", "Finanzas", "Finanzas", "Logística", "Logística"],
        "salario_mensual": [10000, 12000, 20000, 22000, 9000, 9500],
        "renuncio": [1, 0, 0, 0, 1, 1],
    })


@pytest.fixture
def datos_panel(tabla_panel):
    config = {"columnas": [{"nombre": "valido", "rol": "validez"},
                           {"nombre": "tasa_quejas", "rol": "metrica", "etiqueta": "tasa de quejas",
                            "sinonimos": ["quejas", "reclamos"], "mayor_es_mejor": False}]}
    return DataEngine.desde_tabla(tabla_panel, nombre="tiendas", config=config)


@pytest.fixture
def datos_simple(tabla_simple):
    return DataEngine.desde_tabla(tabla_simple, nombre="empleados")


def _brain(*motores):
    rac = Retriever([("reglas.md#Causalidad", "Correlación no es causalidad.")])
    return Brain(biblioteca=Biblioteca.desde_motores(*motores), registro=crear_registro(), rac=rac, llm=LLMFalso(),
                 evidencias=EvidenceStore(), estado=EstadoSesion())


@pytest.fixture
def brain_panel(datos_panel):
    return _brain(datos_panel)


@pytest.fixture
def brain_simple(datos_simple):
    return _brain(datos_simple)


@pytest.fixture
def brain_doble(datos_panel, datos_simple):
    """Un Brain con DOS fuentes cargadas a la vez (tiendas y empleados)."""
    return _brain(datos_panel, datos_simple)
