"""La Biblioteca reúne varias fuentes a la vez y aplica los perfiles guardados."""
import json

import pandas as pd

from dinamo.data_engine import Biblioteca


def _csv(ruta, df):
    df.to_csv(ruta, index=False)
    return ruta


def test_carga_varias_fuentes(tmp_path):
    a = _csv(tmp_path / "ventas.csv", pd.DataFrame({"mes": ["2025-01", "2025-02"] * 2, "tienda": ["A", "A", "B", "B"],
                                                     "ventas": [1, 2, 3, 4]}))
    b = _csv(tmp_path / "salarios.csv", pd.DataFrame({"area": ["X", "Y", "Z"], "salario": [10, 20, 30]}))
    bib = Biblioteca.desde_archivos([a, b])
    assert bib.tablas() == ["ventas", "salarios"]
    assert {r["tabla"]: r["tiene_tiempo"] for r in bib.resumen()} == {"ventas": True, "salarios": False}


def test_tabla_sin_numeros_se_omite_con_aviso(tmp_path):
    ruta = _csv(tmp_path / "directorio.csv", pd.DataFrame({"nombre": ["Ana", "Luis"], "correo": ["a@x", "l@x"]}))
    bib = Biblioteca.desde_archivos([ruta])
    assert bib.tablas() == [] and "sin indicadores numéricos" in bib.advertencias[0]


def test_el_perfil_guardado_elige_la_hoja_y_corrige_columnas(tmp_path):
    ruta = tmp_path / "base.xlsx"
    with pd.ExcelWriter(ruta) as xw:
        pd.DataFrame({"cod": [1, 2, 3], "ventas": [5, 6, 7]}).to_excel(xw, sheet_name="Datos", index=False)
        pd.DataFrame({"otra": [1, 2, 3], "cosa": [4, 5, 6]}).to_excel(xw, sheet_name="Auxiliar", index=False)
    perfiles = tmp_path / "perfiles"
    perfiles.mkdir()
    (perfiles / "base.json").write_text(json.dumps({
        "archivo": "base.xlsx", "hoja": "Datos", "nombre": "mi_base",
        "columnas": [{"nombre": "ventas", "rol": "metrica", "sinonimos": ["facturacion"]}]}), encoding="utf-8")
    bib = Biblioteca.desde_archivos([ruta], carpeta_perfiles=perfiles)
    assert bib.tablas() == ["mi_base"]                                  # la hoja Auxiliar no se cargó
    assert "facturacion" in bib.motor("mi_base").perfil.columna("ventas").sinonimos


def test_volver_a_cargar_un_archivo_reemplaza_la_version_anterior(tmp_path):
    ruta = _csv(tmp_path / "ventas.csv", pd.DataFrame({"tienda": ["A", "B"], "ventas": [1, 2]}))
    bib = Biblioteca.desde_archivos([ruta])
    version_1 = bib.motor("ventas").version
    _csv(ruta, pd.DataFrame({"tienda": ["A", "B"], "ventas": [10, 20]}))
    bib.agregar_archivo(ruta)
    assert bib.tablas() == ["ventas"] and bib.motor("ventas").version != version_1
