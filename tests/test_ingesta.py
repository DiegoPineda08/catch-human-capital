import csv

import pytest


def test_leer_csv(tmp_path):
    """Comprueba que se puedan leer los encabezados y datos de un CSV."""
    archivo = tmp_path / "empleados.csv"
    archivo.write_text(
        "empresa,empleados\nEmpresa A,120\nEmpresa B,95\n",
        encoding="utf-8",
    )

    with archivo.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))

    assert len(filas) == 2
    assert filas[0]["empresa"] == "Empresa A"
    assert filas[0]["empleados"] == "120"


def test_csv_vacio_no_tiene_registros(tmp_path):
    """Comprueba que un CSV con encabezados no tenga filas de datos."""
    archivo = tmp_path / "empleados.csv"
    archivo.write_text("empresa,empleados\n", encoding="utf-8")

    with archivo.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))

    assert filas == []


def test_leer_pdf(tmp_path):
    """Comprueba la extracción básica de texto de un PDF."""
    pdfplumber = pytest.importorskip("pdfplumber")
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")

    archivo = tmp_path / "informe.pdf"
    documento = reportlab.Canvas(str(archivo))
    documento.drawString(72, 720, "Informe de clima laboral")
    documento.save()

    with pdfplumber.open(archivo) as pdf:
        texto = "\n".join(
            pagina.extract_text() or "" for pagina in pdf.pages
        )

    assert "Informe de clima laboral" in texto
