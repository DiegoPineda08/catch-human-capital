from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / "data" / "raw" / "BASE_HISTORICA_LIMPIA.xlsx"
HOJA = "PANEL_COMPLETO"


def cargar_panel():
    df = pd.read_excel(ARCHIVO, sheet_name=HOJA)

    requeridas = [
        "empresa",
        "id_empresa",
        "periodo",
        "orden_periodo",
        "periodo_etiqueta",
        "tasa_rotacion_bimestral",
        "nivel_proveeduria_auto__tier_1",
        "nivel_proveeduria_auto__tier_2",
    ]
    faltantes = [c for c in requeridas if c not in df.columns]

    if faltantes:
        raise ValueError(f"Faltan columnas necesarias: {faltantes}")

    df["tasa_rotacion_bimestral"] = pd.to_numeric(
        df["tasa_rotacion_bimestral"], errors="coerce"
    )
    return df


def caso_tendencia(df):
    datos = df.dropna(
        subset=["orden_periodo", "tasa_rotacion_bimestral"]
    )
    resumen = (
        datos.groupby(
            ["orden_periodo", "periodo", "periodo_etiqueta"],
            as_index=False,
        )
        .agg(
            rotacion_media=("tasa_rotacion_bimestral", "mean"),
            registros=("tasa_rotacion_bimestral", "count"),
        )
        .sort_values("orden_periodo")
    )

    if resumen.empty:
        raise ValueError("No hay datos para calcular la tendencia.")

    primero = resumen.iloc[0]
    ultimo = resumen.iloc[-1]
    cambio_pp = (ultimo["rotacion_media"] - primero["rotacion_media"]) * 100

    lineas = [
        "CASO 1 — TENDENCIA DE ROTACIÓN",
        f"Fuente: {ARCHIVO.name}, hoja {HOJA}.",
        f"Primer periodo: {primero['periodo_etiqueta']}: "
        f"{primero['rotacion_media']:.2%}.",
        f"Último periodo: {ultimo['periodo_etiqueta']}: "
        f"{ultimo['rotacion_media']:.2%}.",
        f"Cambio entre ambos periodos: {cambio_pp:+.2f} puntos porcentuales.",
        "Resultados por periodo:",
    ]

    for _, fila in resumen.iterrows():
        evidencia = (
            f"E:TENDENCIA-{int(fila['orden_periodo'])}"
        )
        lineas.append(
            f"- {fila['periodo_etiqueta']}: "
            f"{fila['rotacion_media']:.2%}; "
            f"n={int(fila['registros'])}; [{evidencia}]"
        )

    lineas.append(
        "Interpretación descriptiva: el cambio compara los extremos "
        "del periodo observado; no demuestra sus causas."
    )
    return "\n".join(lineas)


def caso_comparacion_tier(df):
    grupos = [
        ("Tier 1", "nivel_proveeduria_auto__tier_1"),
        ("Tier 2", "nivel_proveeduria_auto__tier_2"),
    ]
    resultados = []

    for nombre, columna in grupos:
        seleccion = df[
            (pd.to_numeric(df[columna], errors="coerce") == 1)
            & df["tasa_rotacion_bimestral"].notna()
        ]
        if seleccion.empty:
            raise ValueError(f"No hay registros válidos para {nombre}.")

        media = seleccion["tasa_rotacion_bimestral"].mean()
        resultados.append((nombre, media, len(seleccion), columna))

    lineas = [
        "CASO 2 — COMPARACIÓN DE ROTACIÓN POR TIER",
        f"Fuente: {ARCHIVO.name}, hoja {HOJA}.",
    ]

    for nombre, media, n, columna in resultados:
        ref = nombre.upper().replace(" ", "-")
        lineas.append(
            f"- {nombre}: rotación media {media:.2%}; "
            f"n={n}; [E:COMPARACION-{ref}]"
        )

    diferencia = (resultados[0][1] - resultados[1][1]) * 100
    lineas.append(
        f"Diferencia Tier 1 menos Tier 2: {diferencia:+.2f} "
        "puntos porcentuales."
    )
    lineas.append(
        "Nota: los indicadores Tier 1 y Tier 2 son independientes; "
        "una empresa puede pertenecer a ambos. Los grupos no son "
        "necesariamente excluyentes."
    )
    return "\n".join(lineas)


def mostrar_casos():
    df = cargar_panel()
    print("=" * 65)
    print("DINAMO — DEMOSTRACIÓN CON DATOS REALES")
    print("=" * 65)
    print(f"Registros cargados: {len(df)}")
    print(f"Periodos: {df['periodo'].nunique()}")

    print("\n" + caso_tendencia(df))
    print("\n" + caso_comparacion_tier(df))

    print(
        "\nCASO 3 — DOCUMENTO PDF/WORD\n"
        "Pendiente: no se encontró un documento fuente en data/ o docs/. "
        "No se genera una respuesta documental ficticia."
    )


if __name__ == "__main__":
    mostrar_casos()
