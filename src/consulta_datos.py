
from pathlib import Path

import pandas as pd


CARPETA_DATOS = Path("data/raw")


def buscar_excel():
    """Encuentra el archivo Excel disponible en data/raw."""
    archivos = sorted(CARPETA_DATOS.glob("*.xlsx"))

    if not archivos:
        raise FileNotFoundError(
            "No se encontró ningún archivo .xlsx en data/raw."
        )

    if len(archivos) > 1:
        nombres = ", ".join(a.name for a in archivos)
        raise ValueError(
            "Hay varios Excel. Deja uno seleccionado o configura "
            f"el archivo explícitamente. Archivos: {nombres}"
        )

    return archivos[0]


def cargar_datos(hoja=0):
    """Carga una hoja del Excel sin modificar el archivo original."""
    archivo = buscar_excel()
    datos = pd.read_excel(archivo, sheet_name=hoja)

    if datos.empty:
        raise ValueError(f"La hoja seleccionada está vacía: {hoja}")

    return datos


def inspeccionar_datos():
    """Muestra las hojas, columnas y tipos de datos disponibles."""
    archivo = buscar_excel()

    print(f"Archivo: {archivo.name}")
    print(f"Tamaño: {archivo.stat().st_size / (1024 * 1024):.2f} MB")

    libro = pd.ExcelFile(archivo)
    print(f"\nHojas: {libro.sheet_names}")

    for hoja in libro.sheet_names:
        datos = pd.read_excel(archivo, sheet_name=hoja, nrows=5)

        print(f"\n{'=' * 55}")
        print(f"HOJA: {hoja}")
        print(f"Columnas: {len(datos.columns)}")

        for columna, tipo in datos.dtypes.items():
            print(f"- {columna!r} | tipo: {tipo}")

        print("\nEjemplo de estructura:")
        print(datos.head(3).to_string(index=False))


def calcular_tendencia(datos, columna_metrica, columna_periodo):
    """Resume una métrica por periodo. No presupone una fórmula de KPI."""
    requeridas = [columna_metrica, columna_periodo]
    faltantes = [c for c in requeridas if c not in datos.columns]

    if faltantes:
        raise ValueError(f"No existen estas columnas: {faltantes}")

    copia = datos[requeridas].copy()
    copia[columna_metrica] = pd.to_numeric(
        copia[columna_metrica], errors="coerce"
    )
    copia = copia.dropna(subset=requeridas)

    if copia.empty:
        raise ValueError("No hay datos válidos para calcular la tendencia.")

    resultado = (
        copia.groupby(columna_periodo)[columna_metrica]
        .agg(["mean", "count"])
        .reset_index()
        .sort_values(columna_periodo)
    )

    return resultado


def comparar_grupos(
    datos,
    columna_metrica,
    columna_grupo,
    grupo_a="Tier 1",
    grupo_b="Tier 2",
):
    """Compara una métrica entre dos grupos explícitamente seleccionados."""
    requeridas = [columna_metrica, columna_grupo]
    faltantes = [c for c in requeridas if c not in datos.columns]

    if faltantes:
        raise ValueError(f"No existen estas columnas: {faltantes}")

    copia = datos[requeridas].copy()
    copia[columna_metrica] = pd.to_numeric(
        copia[columna_metrica], errors="coerce"
    )
    copia = copia.dropna(subset=requeridas)

    seleccion = copia[
        copia[columna_grupo].astype(str).str.strip().isin(
            [grupo_a, grupo_b]
        )
    ].copy()

    if seleccion.empty:
        raise ValueError(
            "No se encontraron registros de los grupos indicados. "
            "Revisa los valores reales de la columna de grupo."
        )

    resultado = (
        seleccion.groupby(columna_grupo)[columna_metrica]
        .agg(["mean", "count"])
        .reindex([grupo_a, grupo_b])
    )

    return resultado


if __name__ == "__main__":
    inspeccionar_datos()
