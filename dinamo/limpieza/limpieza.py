"""Detección de problemas de calidad y aplicación de correcciones aprobadas (determinístico)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from dinamo.ingesta.tablas import _numero

# acción -> descripción para el usuario
ACCIONES = {
    "quitar_duplicados": "Eliminar filas idénticas repetidas (se conserva la primera).",
    "recortar_espacios": "Quitar espacios al inicio y al final del texto.",
    "unificar_categorias": "Unificar variantes de la misma categoría (mayúsculas, acentos, espacios).",
    "convertir_numero": "Convertir texto con forma de número ($, %, separadores de miles) a número.",
    "convertir_fecha": "Convertir texto con forma de fecha a fecha.",
    "quitar_columna_vacia": "Eliminar una columna completamente vacía.",
    "quitar_filas_vacias": "Eliminar filas completamente vacías.",
    "imputar_mediana": "Rellenar vacíos numéricos con la mediana de la columna (cambia los datos: úsalo con cuidado).",
    "marcar_atipicos": "Agregar una columna que marca valores atípicos (no cambia los valores).",
}


@dataclass
class Problema:
    id: str
    tipo: str
    columna: str | None
    descripcion: str
    filas_afectadas: int
    ejemplos: list = field(default_factory=list)
    accion: str = ""                    # acción propuesta (vacía = sólo informativo)
    alternativas: list[str] = field(default_factory=list)
    parametros: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return asdict(self)


def leer_crudo(ruta: str | Path) -> pd.DataFrame:
    """Lee el archivo SIN normalizar (para ver los problemas tal como están)."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext == ".csv":
        for cod in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(ruta, sep=None, engine="python", encoding=cod, dtype=object, keep_default_na=False,
                                   na_values=[""])
            except UnicodeDecodeError:
                continue
        raise ValueError("Codificación desconocida")
    if ext in (".xlsx", ".xlsm", ".xls"):
        hojas = pd.read_excel(ruta, sheet_name=None, dtype=object)
        return max(hojas.values(), key=lambda d: d.size)
    raise ValueError("La limpieza funciona con archivos CSV o Excel.")


def _clave_categoria(v) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(v)) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _parece_fecha(s: pd.Series) -> float:
    muestra = s.dropna().astype(str).head(200)
    if muestra.empty:
        return 0.0
    patron = r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"
    return muestra.str.match(patron).mean()


def diagnosticar(df: pd.DataFrame) -> list[Problema]:
    problemas: list[Problema] = []
    n = 0

    def nuevo(**kw):
        nonlocal n
        n += 1
        problemas.append(Problema(id=f"P{n}", **kw))

    vacias = df.index[df.isna().all(axis=1)]
    if len(vacias):
        nuevo(tipo="filas vacías", columna=None, descripcion=f"{len(vacias)} filas no tienen ningún dato.",
              filas_afectadas=len(vacias), accion="quitar_filas_vacias")
    dup = df[df.duplicated(keep="first") & ~df.isna().all(axis=1)]
    if len(dup):
        nuevo(tipo="filas duplicadas", columna=None, descripcion=f"{len(dup)} filas son copia exacta de otra.",
              filas_afectadas=len(dup), ejemplos=[int(i) + 2 for i in dup.index[:5]], accion="quitar_duplicados")

    for col in df.columns:
        s = df[col]
        if s.isna().all():
            nuevo(tipo="columna vacía", columna=str(col), descripcion=f"La columna '{col}' está vacía.",
                  filas_afectadas=len(s), accion="quitar_columna_vacia")
            continue
        texto = s.dropna()
        es_texto = texto.map(lambda v: isinstance(v, str))
        textos = texto[es_texto]
        if len(textos):
            con_espacios = textos[textos != textos.str.strip()]
            if len(con_espacios):
                nuevo(tipo="espacios sobrantes", columna=str(col),
                      descripcion=f"{len(con_espacios)} valores de '{col}' tienen espacios al inicio o al final.",
                      filas_afectadas=len(con_espacios), ejemplos=[repr(v) for v in con_espacios.unique()[:4]],
                      accion="recortar_espacios")
            numeros = textos.map(_numero)
            if numeros.notna().mean() >= 0.9 and textos.str.contains(r"[$%€,]|\d\.\d{3}", regex=True).any():
                nuevo(tipo="números como texto", columna=str(col),
                      descripcion=f"'{col}' tiene números escritos como texto (con $, %, o separadores).",
                      filas_afectadas=int(numeros.notna().sum()), ejemplos=list(textos.unique()[:4]),
                      accion="convertir_numero")
            elif _parece_fecha(textos) >= 0.9:
                nuevo(tipo="fechas como texto", columna=str(col), descripcion=f"'{col}' parece contener fechas en texto.",
                      filas_afectadas=len(textos), ejemplos=list(textos.unique()[:3]), accion="convertir_fecha",
                      parametros={"dia_primero": bool(textos.astype(str).str.match(r"^\d{1,2}/").any())})
            elif textos.nunique() <= max(30, len(textos) // 20):
                grupos: dict[str, set] = {}
                for v in textos.unique():
                    grupos.setdefault(_clave_categoria(v), set()).add(v)
                variantes = {k: sorted(v) for k, v in grupos.items() if len(v) > 1}
                if variantes:
                    afectadas = int(textos.map(lambda v: _clave_categoria(v) in variantes).sum())
                    mapa = {}
                    for k, vs in variantes.items():
                        conteo = textos[textos.isin(vs)].map(str.strip).value_counts()
                        canonica = sorted(conteo.index, key=lambda x: (-conteo[x], x))[0]
                        mapa.update({v: canonica for v in vs})
                    nuevo(tipo="categorías inconsistentes", columna=str(col),
                          descripcion=f"'{col}' tiene variantes de la misma categoría: "
                                      + "; ".join(" / ".join(repr(x) for x in v) for v in list(variantes.values())[:3]),
                          filas_afectadas=afectadas, ejemplos=list(variantes.values())[:3], accion="unificar_categorias",
                          parametros={"mapa": mapa})
        faltan = int(s.isna().sum())
        num = pd.to_numeric(s.map(_numero) if s.dtype == object else s, errors="coerce")
        if faltan and faltan < len(s):
            es_num = num.notna().sum() >= 0.9 * s.notna().sum()
            nuevo(tipo="valores faltantes", columna=str(col),
                  descripcion=f"'{col}' tiene {faltan} valores vacíos ({faltan / len(s):.0%}). Se recomienda dejarlos "
                              "vacíos: los análisis los excluyen y se informa el tamaño de muestra.",
                  filas_afectadas=faltan, accion="", alternativas=["imputar_mediana"] if es_num else [])
        if num.notna().sum() >= 8:
            q1, q3 = num.quantile(0.25), num.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                fuera = num[(num < q1 - 3 * iqr) | (num > q3 + 3 * iqr)]
                if len(fuera):
                    nuevo(tipo="valores atípicos", columna=str(col),
                          descripcion=f"'{col}' tiene {len(fuera)} valores muy alejados del resto (más de 3 rangos "
                                      "intercuartílicos). Revisa si son errores de captura; no se modifican.",
                          filas_afectadas=len(fuera), ejemplos=[float(x) for x in fuera.head(5)], accion="",
                          alternativas=["marcar_atipicos"], parametros={"q1": float(q1), "q3": float(q3)})
    return problemas


def aplicar(df: pd.DataFrame, problemas: list[Problema], aprobadas: dict[str, str]) -> tuple[pd.DataFrame, list[dict]]:
    """aprobadas: {id_problema: acción}. Sólo se aplican esas. Devuelve (copia limpia, registro)."""
    nuevo = df.copy()
    registro = []
    por_id = {p.id: p for p in problemas}
    for pid, accion in aprobadas.items():
        p = por_id.get(pid)
        if p is None or accion not in ACCIONES or (accion != p.accion and accion not in p.alternativas):
            raise ValueError(f"Acción no válida para {pid}: {accion}")
        col = p.columna
        antes_filas = len(nuevo)
        cambiadas = 0
        accion_det = ACCIONES[accion]
        if accion == "quitar_filas_vacias":
            nuevo = nuevo.dropna(how="all")
            cambiadas = antes_filas - len(nuevo)
        elif accion == "quitar_duplicados":
            nuevo = nuevo.drop_duplicates(keep="first")
            cambiadas = antes_filas - len(nuevo)
        elif accion == "quitar_columna_vacia":
            nuevo = nuevo.drop(columns=[col])
            cambiadas = antes_filas
        elif accion == "recortar_espacios":
            previo = nuevo[col].copy()
            nuevo[col] = nuevo[col].map(lambda v: v.strip() if isinstance(v, str) else v)
            cambiadas = int((previo.astype(str) != nuevo[col].astype(str)).sum())
        elif accion == "unificar_categorias":
            mapa = p.parametros["mapa"]
            previo = nuevo[col].copy()
            nuevo[col] = nuevo[col].map(lambda v: mapa.get(v, v.strip() if isinstance(v, str) else v))
            cambiadas = int((previo.astype(str) != nuevo[col].astype(str)).sum())
        elif accion == "convertir_numero":
            previo = nuevo[col].copy()
            nuevo[col] = nuevo[col].map(_numero).astype(float)
            cambiadas = int(previo.notna().sum())
        elif accion == "convertir_fecha":
            nuevo[col] = pd.to_datetime(nuevo[col], errors="coerce", dayfirst=p.parametros.get("dia_primero", False))
            cambiadas = int(nuevo[col].notna().sum())
        elif accion == "imputar_mediana":
            num = pd.to_numeric(nuevo[col].map(_numero) if nuevo[col].dtype == object else nuevo[col], errors="coerce")
            mediana = float(num.median())
            cambiadas = int(num.isna().sum())
            nuevo[col] = num.fillna(mediana)
            accion_det = f"{ACCIONES[accion]} Mediana usada: {mediana:g}."
        elif accion == "marcar_atipicos":
            q1, q3 = p.parametros["q1"], p.parametros["q3"]
            iqr = q3 - q1
            num = pd.to_numeric(nuevo[col].map(_numero) if nuevo[col].dtype == object else nuevo[col], errors="coerce")
            nuevo[f"{col}_atipico"] = ((num < q1 - 3 * iqr) | (num > q3 + 3 * iqr)).astype(int)
            cambiadas = int(nuevo[f"{col}_atipico"].sum())
        registro.append({"problema": pid, "tipo": p.tipo, "columna": col, "accion": accion,
                         "detalle": accion_det, "filas_cambiadas": cambiadas,
                         "parametros": p.parametros})
    return nuevo.reset_index(drop=True), registro


def comparar(antes: pd.DataFrame, despues: pd.DataFrame) -> dict:
    def ficha(d):
        return {"filas": int(len(d)), "columnas": int(d.shape[1]), "duplicados": int(d.duplicated().sum()),
                "vacios": {str(c): int(d[c].isna().sum()) for c in d.columns},
                "tipos": {str(c): str(d[c].dtype) for c in d.columns}}
    return {"antes": ficha(antes), "despues": ficha(despues)}


def script_python(nombre_archivo: str, registro: list[dict]) -> str:
    """Script de pandas que reproduce exactamente los cambios aprobados."""
    l = ["# Script generado por DINAMO: reproduce la limpieza aprobada.",
         "# El archivo original no se modifica; el resultado se guarda como archivo nuevo.",
         "import pandas as pd", "import re", "",
         "def numero(v):",
         "    if v is None or (isinstance(v, float) and pd.isna(v)): return None",
         "    t = str(v).strip().replace(' ', '')",
         "    pct = t.endswith('%'); t = t.rstrip('%').replace('$', '').replace('€', '')",
         "    if re.fullmatch(r'-?\\d{1,3}(\\.\\d{3})+(,\\d+)?', t): t = t.replace('.', '').replace(',', '.')",
         "    elif re.fullmatch(r'-?\\d{1,3}(,\\d{3})+(\\.\\d+)?', t): t = t.replace(',', '')",
         "    elif re.fullmatch(r'-?\\d+,\\d+', t): t = t.replace(',', '.')",
         "    try: x = float(t)",
         "    except ValueError: return None",
         "    return x / 100 if pct else x", "",
         f"df = pd.read_csv({nombre_archivo!r}, sep=None, engine='python', dtype=object, keep_default_na=False, na_values=[''])"
         if nombre_archivo.lower().endswith(".csv") else f"df = pd.read_excel({nombre_archivo!r}, dtype=object)"]
    for r in registro:
        c, a = r["columna"], r["accion"]
        l.append(f"# {r['problema']}: {r['detalle']}")
        if a == "quitar_filas_vacias":
            l.append("df = df.dropna(how='all')")
        elif a == "quitar_duplicados":
            l.append("df = df.drop_duplicates(keep='first')")
        elif a == "quitar_columna_vacia":
            l.append(f"df = df.drop(columns=[{c!r}])")
        elif a == "recortar_espacios":
            l.append(f"df[{c!r}] = df[{c!r}].map(lambda v: v.strip() if isinstance(v, str) else v)")
        elif a == "unificar_categorias":
            l.append(f"mapa = {json.dumps(r['parametros']['mapa'], ensure_ascii=False)}")
            l.append(f"df[{c!r}] = df[{c!r}].map(lambda v: mapa.get(v, v.strip() if isinstance(v, str) else v))")
        elif a == "convertir_numero":
            l.append(f"df[{c!r}] = df[{c!r}].map(numero).astype(float)")
        elif a == "convertir_fecha":
            l.append(f"df[{c!r}] = pd.to_datetime(df[{c!r}], errors='coerce', dayfirst={r['parametros'].get('dia_primero', False)})")
        elif a == "imputar_mediana":
            l.append(f"num = pd.to_numeric(df[{c!r}].map(numero), errors='coerce'); df[{c!r}] = num.fillna(num.median())")
        elif a == "marcar_atipicos":
            q1, q3 = r["parametros"]["q1"], r["parametros"]["q3"]
            l.append(f"num = pd.to_numeric(df[{c!r}].map(numero), errors='coerce')")
            l.append(f"df[{c + '_atipico'!r}] = ((num < {q1} - 3 * {q3 - q1}) | (num > {q3} + 3 * {q3 - q1})).astype(int)")
    salida = Path(nombre_archivo).stem + "_limpio.csv"
    l += ["df = df.reset_index(drop=True)", f"df.to_csv({salida!r}, index=False)", f"print('Guardado:', {salida!r})"]
    return "\n".join(l) + "\n"
