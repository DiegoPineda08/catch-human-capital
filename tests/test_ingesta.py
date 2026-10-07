"""La Ingesta debe leer cualquier formato soportado y entregar siempre el mismo contrato: Documento."""
import pandas as pd
import pytest

from dinamo.core.config import RAIZ
from dinamo.ingesta import leer_documento, normalizar_tabla


def test_csv_con_punto_y_coma_latin1_y_numeros_como_texto(tmp_path):
    ruta = tmp_path / "nómina.csv"
    ruta.write_bytes("área;salario;tasa\nVentas;$1.200,50;12%\nFinanzas;$2.000;8%\n".encode("latin-1"))
    doc = leer_documento(ruta)
    df = doc.tablas[0].tabla
    assert doc.tipo == "csv" and list(df.columns) == ["área", "salario", "tasa"]
    assert df["salario"].tolist() == [1200.5, 2000.0] and [round(x, 4) for x in df["tasa"]] == [0.12, 0.08]


def test_excel_con_varias_hojas_y_filas_de_titulo(tmp_path):
    ruta = tmp_path / "reporte.xlsx"
    with pd.ExcelWriter(ruta) as xw:
        pd.DataFrame([["Reporte de ventas 2025", None], [None, None], ["mes", "ventas"],
                      ["2025-01", 100], ["2025-02", 120]]).to_excel(xw, sheet_name="Ventas", header=False, index=False)
        pd.DataFrame({"nota": ["sólo una fila"]}).to_excel(xw, sheet_name="Notas", index=False)
    doc = leer_documento(ruta)
    assert [t.nombre for t in doc.tablas] == ["reporte_ventas"]          # la hoja de notas no es una tabla
    assert doc.tablas[0].tabla["ventas"].tolist() == [100, 120]           # se saltó el título
    assert any("Notas" in a for a in doc.advertencias)


def test_pdf_entrega_tablas_y_texto():
    doc = leer_documento(RAIZ / "ejemplos" / "informe_clima_laboral.pdf")
    assert doc.tipo == "pdf" and len(doc.tablas) == 1
    tabla = doc.tablas[0].tabla
    assert tabla.shape == (16, 5) and tabla["Rotación trimestral"].iloc[0] == pytest.approx(0.061)
    assert any("turnos nocturnos" in f.texto for f in doc.fragmentos)
    assert all(f.fuente.startswith("informe_clima_laboral.pdf#p") for f in doc.fragmentos)
    assert not any("2025-T1 Producción" in f.texto for f in doc.fragmentos)  # la tabla no se repite como texto


def test_markdown_se_divide_por_titulos(tmp_path):
    ruta = tmp_path / "politicas.md"
    ruta.write_text("# Políticas\n## Vacaciones\n12 días.\n## Bonos\nTrimestrales.", encoding="utf-8")
    doc = leer_documento(ruta)
    assert doc.tipo == "texto" and [f.fuente for f in doc.fragmentos] == [
        "politicas.md#politicas", "politicas.md#Vacaciones", "politicas.md#Bonos"]


def test_formato_no_soportado_da_un_error_claro(tmp_path):
    ruta = tmp_path / "foto.png"
    ruta.write_bytes(b"x")
    with pytest.raises(ValueError, match="Formato no soportado"):
        leer_documento(ruta)


def test_normalizar_no_toca_texto_que_solo_contiene_numeros():
    df = normalizar_tabla(pd.DataFrame({"tienda": ["Tienda 1", "Tienda 2"], "Unnamed: 1": ["1,5", "2"]}))
    assert df["tienda"].tolist() == ["Tienda 1", "Tienda 2"]
    assert list(df.columns) == ["tienda", "columna_2"] and df["columna_2"].tolist() == [1.5, 2.0]
