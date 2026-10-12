
from pathlib import Path
import pandas as pd

from consulta_datos import buscar_excel

archivo = buscar_excel()
salida = Path("data/processed")
salida.mkdir(parents=True, exist_ok=True)

libro = pd.ExcelFile(archivo)

with open(
    salida / "estructura_base.txt",
    "w",
    encoding="utf-8",
) as informe:
    informe.write(f"Archivo: {archivo.name}\n")
    informe.write(f"Hojas: {libro.sheet_names}\n\n")

    for hoja in libro.sheet_names:
        df = pd.read_excel(archivo, sheet_name=hoja, nrows=0)

        informe.write(f"\nHOJA: {hoja}\n")
        informe.write(f"Número de columnas: {len(df.columns)}\n")

        for columna in df.columns:
            informe.write(f"- {columna}\n")

print("Informe creado: data/processed/estructura_base.txt")
