"""
Limpieza mínima y genérica de cualquier tabla recién leída (de un Excel, un CSV o un PDF).

No sabe nada de ninguna base concreta. Sólo arregla problemas de FORMA que aparecen en
cualquier archivo:
  - encabezados vacíos o repetidos         -> "columna_3", "ventas_2"
  - filas y columnas completamente vacías  -> se eliminan
  - números escritos como texto            -> "12%" = 0.12 ; "$1,200" = 1200 ; "3,5" = 3.5
Una columna de texto sólo se convierte a número si al menos el 90% de sus valores lo son
(así "Tienda 12" o "entre 10 y 20" no se tocan).
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

UMBRAL_NUMERICO = 0.9
NULOS_TEXTO = {"", "-", "--", "nan", "none", "null", "n/a", "na", "s/d", "sin dato"}


def slug(texto: str, max_len: int = 40) -> str:
    """'Informe Clima 2025.pdf' -> 'informe_clima_2025_pdf'. Sirve para nombres de tablas."""
    t = "".join(c for c in unicodedata.normalize("NFKD", str(texto).lower()) if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:max_len].strip("_") or "tabla"


def _numero(valor) -> float | None:
    """Convierte un texto con forma de número; devuelve None si no lo es."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    t = str(valor).strip().replace(" ", "").replace(" ", "")
    if t.lower() in NULOS_TEXTO:
        return None
    pct = t.endswith("%")
    t = t.rstrip("%").replace("$", "").replace("€", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):        # 1.234.567,5 (formato europeo/latino)
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t):      # 1,234,567.5 (formato inglés)
        t = t.replace(",", "")
    elif re.fullmatch(r"-?\d+,\d+", t):                       # 3,5 (coma decimal)
        t = t.replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    return float(t) / 100 if pct else float(t)


def _nombres_unicos(nombres) -> list[str]:
    salida, vistos = [], {}
    for i, n in enumerate(nombres):
        n = re.sub(r"\s+", " ", str(n)).strip() if n is not None and str(n).strip() not in ("", "nan") else ""
        if not n or n.lower().startswith("unnamed"):
            n = f"columna_{i + 1}"
        if n in vistos:
            vistos[n] += 1
            n = f"{n}_{vistos[n]}"
        else:
            vistos[n] = 1
        salida.append(n)
    return salida


def normalizar_tabla(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una copia limpia de la tabla (ver reglas arriba)."""
    df = df.copy()
    df.columns = _nombres_unicos(df.columns)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    for col in df.columns:
        serie = df[col]
        if pd.api.types.is_numeric_dtype(serie) or pd.api.types.is_datetime64_any_dtype(serie):
            continue
        texto = serie.dropna()
        texto = texto[~texto.astype(str).str.strip().str.lower().isin(NULOS_TEXTO)]
        if texto.empty:
            continue
        convertidos = texto.map(_numero)
        if convertidos.notna().mean() >= UMBRAL_NUMERICO:
            numeros = serie.map(_numero).astype(float)
            sin_nulos = numeros.dropna()
            enteros = len(sin_nulos) == len(numeros) and (sin_nulos % 1 == 0).all()
            df[col] = numeros.astype("int64") if enteros else numeros
        elif texto.map(lambda v: isinstance(v, (pd.Timestamp,)) or hasattr(v, "isoformat")).mean() >= UMBRAL_NUMERICO:
            df[col] = pd.to_datetime(serie, errors="coerce")
        else:
            df[col] = serie.map(lambda v: v.strip() if isinstance(v, str) else v)
    return df.reset_index(drop=True)


def detectar_encabezado(crudo: pd.DataFrame, max_filas: int = 10) -> pd.DataFrame:
    """En una tabla leída SIN encabezado, busca la primera fila que parece de títulos y la usa.

    Una fila 'parece de títulos' si al menos el 60% de sus celdas tiene texto (no números).
    Sirve para Excel con filas de título arriba ("Reporte 2025", fila vacía, y luego la tabla)."""
    crudo = crudo.dropna(how="all").dropna(axis=1, how="all")
    if crudo.empty:
        return crudo
    ncols = crudo.shape[1]
    for i in range(min(max_filas, len(crudo))):
        fila = crudo.iloc[i]
        textos = sum(isinstance(v, str) and _numero(v) is None and v.strip() != "" for v in fila)
        if textos >= max(2, 0.6 * ncols):
            tabla = crudo.iloc[i + 1:].copy()
            tabla.columns = list(fila)
            return tabla.infer_objects()          # números y fechas recuperan su tipo
    tabla = crudo.copy()
    tabla.columns = [f"columna_{j + 1}" for j in range(ncols)]
    return tabla.infer_objects()
