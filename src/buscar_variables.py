
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from consulta_datos import buscar_excel

archivo = buscar_excel()
libro = pd.ExcelFile(archivo)

# Palabras relacionadas con los análisis que queremos realizar.
palabras_clave = [
    "rotacion", "rotación", "turnover",
    "baja", "retiro", "salida",
    "periodo", "período", "fecha", "bimestre",
    "empresa", "company", "tier",
    "empleados", "personal", "headcount",
]

print(f"Archivo: {archivo.name}")

for hoja in libro.sheet_names:
    encabezados = pd.read_excel(
        archivo,
        sheet_name=hoja,
        nrows=0,
    ).columns

    encontrados = [
        str(columna)
        for columna in encabezados
        if any(
            palabra in str(columna).lower()
            for palabra in palabras_clave
        )
    ]

    print(f"\n--- Hoja: {hoja} ---")
    print(f"Total de columnas: {len(encabezados)}")
    print("Columnas relacionadas con los análisis:")

    if encontrados:
        for columna in encontrados:
            print(f"- {columna}")
    else:
        print("No se encontraron coincidencias por nombre.")
