"""Limpieza con aprobación: datos sintéticos con problemas conocidos."""
import pandas as pd

from dinamo.limpieza import aplicar, comparar, diagnosticar, leer_crudo, script_python

CSV = """id,area,salario,fecha_ingreso,vacia
1,Ventas,"$12,500",2023-01-10,
2, ventas ,"$13,000",2023-02-11,
3,VENTAS,"$11,800",2023-03-12,
4,Logística,"$9,900",2023-04-13,
5,Logistica,"$10,100",2023-05-14,
6,TI,"$25,000",2023-06-15,
6,TI,"$25,000",2023-06-15,
7,TI,,2023-07-16,
8,Ventas,"$12,000",2023-08-17,
9,Ventas,"$900,000",2023-09-18,
10,Ventas,"$12,200",2023-10-19,
"""


def preparar(tmp_path):
    ruta = tmp_path / "personal.csv"
    ruta.write_text(CSV, encoding="utf-8")
    return ruta, leer_crudo(ruta)


def test_diagnostico_detecta_lo_esperado(tmp_path):
    _, df = preparar(tmp_path)
    tipos = {(p.tipo, p.columna) for p in diagnosticar(df)}
    assert ("filas duplicadas", None) in tipos
    assert ("espacios sobrantes", "area") in tipos
    assert ("categorías inconsistentes", "area") in tipos
    assert ("números como texto", "salario") in tipos
    assert ("fechas como texto", "fecha_ingreso") in tipos
    assert ("columna vacía", "vacia") in tipos
    assert ("valores faltantes", "salario") in tipos
    assert ("valores atípicos", "salario") in tipos


def test_solo_se_aplica_lo_aprobado_y_original_intacto(tmp_path):
    ruta, df = preparar(tmp_path)
    original = ruta.read_bytes()
    problemas = diagnosticar(df)
    pid = {p.tipo: p.id for p in problemas if p.columna in (None, "area", "salario")}
    aprobadas = {pid["filas duplicadas"]: "quitar_duplicados", pid["categorías inconsistentes"]: "unificar_categorias",
                 pid["números como texto"]: "convertir_numero"}
    limpio, registro = aplicar(df, problemas, aprobadas)
    assert len(limpio) == 10
    assert sorted(limpio["area"].unique()) == ["Logistica", "TI", "Ventas"] or \
        sorted(limpio["area"].unique()) == ["Logística", "TI", "Ventas"]
    assert limpio["salario"].iloc[0] == 12500.0
    assert limpio["salario"].isna().sum() == 1                    # no se imputó sin permiso
    assert 900000.0 in limpio["salario"].values                    # atípico señalado, no borrado
    assert "vacia" in limpio.columns                               # no aprobado: no se quitó
    assert ruta.read_bytes() == original
    assert [r["problema"] for r in registro] == list(aprobadas)
    c = comparar(df, limpio)
    assert c["antes"]["filas"] == 11 and c["despues"]["filas"] == 10


def test_script_reproduce_el_resultado(tmp_path, monkeypatch):
    ruta, df = preparar(tmp_path)
    problemas = diagnosticar(df)
    aprobadas = {p.id: p.accion for p in problemas if p.accion}
    limpio, registro = aplicar(df, problemas, aprobadas)
    monkeypatch.chdir(tmp_path)
    exec(compile(script_python("personal.csv", registro), "script", "exec"), {})
    rehecho = pd.read_csv(tmp_path / "personal_limpio.csv")
    assert len(rehecho) == len(limpio) and list(rehecho.columns) == list(limpio.columns)
    assert rehecho["salario"].sum() == limpio["salario"].sum()


def test_accion_no_propuesta_se_rechaza(tmp_path):
    _, df = preparar(tmp_path)
    problemas = diagnosticar(df)
    import pytest
    with pytest.raises(ValueError):
        aplicar(df, problemas, {problemas[0].id: "imputar_mediana"})


def test_limpieza_en_conversacion_crea_archivo_nuevo(tmp_path):
    from dinamo.conversacion import Gestor
    e = Gestor(tmp_path).crear()
    e.agregar_archivo("personal.csv", CSV.encode())
    prop = e.proponer_limpieza("personal.csv")
    dup = next(p for p in prop["problemas"] if p["tipo"] == "filas duplicadas")
    res = e.aplicar_limpieza("personal.csv", {dup["id"]: "quitar_duplicados"})
    assert res["resultado"] == "personal_limpio_v1.csv"
    assert (e.carpeta_archivos / "personal.csv").read_text(encoding="utf-8") == CSV
    assert {a["nombre"] for a in e.archivos} == {"personal.csv", "personal_limpio_v1.csv"}
    assert e.limpieza[0]["registro"][0]["filas_cambiadas"] == 1
