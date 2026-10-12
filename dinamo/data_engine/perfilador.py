"""
PERFILADOR: mira una tabla que nunca ha visto y deduce qué significa cada columna.

Ejemplo: en una tabla de ventas deduce que "tienda_id" identifica la entidad, "mes" es
el tiempo, "region" es una dimensión y "ventas" es una métrica en dinero.

Reglas (en orden; la primera que se cumple decide):
  1. Lo que diga la configuración (un JSON en perfiles/) manda sobre todo.
  2. Columna sin variación (un solo valor)                 -> ignorar
  3. Fecha, o nombre de tiempo (mes, año, periodo...)      -> tiempo
  4. Nombre de identificador (id, codigo...)               -> entidad
  5. Texto que corresponde 1 a 1 con la entidad            -> nombre_entidad
  6. Sólo valores 0/1, sí/no, true/false                   -> binaria
  7. Número                                                -> metrica
  8. Texto con pocas categorías                            -> dimension
  9. Texto con muchas categorías distintas                 -> texto

Es una deducción: puede equivocarse. Por eso el resultado se puede revisar con
`python -m app.perfilar <archivo>` y corregir guardando un JSON en perfiles/.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from dinamo.core.contracts import Columna, PerfilDataset
from dinamo.core.texto import PALABRAS_GENERICAS, humanizar, palabras, sin_acentos

PALABRAS_TIEMPO = {"fecha", "date", "mes", "month", "anio", "ano", "year", "periodo", "period",
                   "bimestre", "trimestre", "semestre", "semana", "week", "dia", "day", "corte"}
PALABRAS_ID = {"id", "codigo", "code", "clave", "folio", "nit", "rut"}
PALABRAS_MONEDA = {"salario", "sueldo", "precio", "monto", "costo", "venta", "ventas", "ingreso",
                   "ingresos", "ticket", "mxn", "usd", "cop", "pesos", "presupuesto", "pago", "gasto"}
PALABRAS_CONTEO = {"cantidad", "clientes", "empleados", "unidades", "bajas", "contrataciones",
                   "personas", "visitas", "pedidos", "hc", "headcount", "transacciones"}
PALABRAS_PROPORCION = {"tasa", "pct", "porcentaje", "proporcion", "ratio", "share", "rate"}
MAX_CATEGORIAS = 30


def _tokens(nombre: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", sin_acentos(str(nombre).lower())))


def _es_binaria(serie: pd.Series) -> bool:
    vals = {sin_acentos(str(v)).strip().lower() for v in serie.dropna().unique()}
    return 1 <= len(vals) <= 2 and (vals <= {"0", "1", "0.0", "1.0"} or vals <= {"si", "no"}
                                    or vals <= {"true", "false"})


def _es_tiempo(nombre: str, serie: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(serie):
        return True
    if not (_tokens(nombre) & PALABRAS_TIEMPO):
        return False
    muestra = serie.dropna().astype(str).head(20)
    parece_fecha = muestra.str.match(r"^\d{4}[-/]\d{1,2}").mean() > 0.8 if len(muestra) else False
    return pd.api.types.is_numeric_dtype(serie) or bool(parece_fecha) or serie.nunique() <= 60


def _unidad(nombre: str, serie: pd.Series) -> str:
    t = _tokens(nombre)
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s) and s.between(0, 1).all() and (t & PALABRAS_PROPORCION or s.max() <= 1):
        return "proporcion"
    if t & PALABRAS_MONEDA:
        return "moneda"
    if t & {"dias", "dia"}:
        return "dias"
    enteros = len(s) and (s % 1 == 0).all()
    if enteros and s.min() >= 0 and s.max() <= 10 and s.nunique() <= 11:
        return "escala"
    if enteros and s.min() >= 0 and t & PALABRAS_CONTEO:
        return "conteo"
    return "numero"


def _es_texto(serie: pd.Series) -> bool:
    return not pd.api.types.is_numeric_dtype(serie) and not pd.api.types.is_datetime64_any_dtype(serie)


def _sinonimos(nombre: str, etiqueta: str, rol: str) -> tuple[str, ...]:
    """Palabras con las que el usuario puede nombrar la columna.

    En las métricas se quitan palabras genéricas ("promedio", "tasa") para que "promedio de
    ventas" no apunte también a "ticket_promedio"."""
    todas = palabras(nombre) + palabras(etiqueta)
    if rol == "metrica":
        todas = [p for p in todas if p not in PALABRAS_GENERICAS]
    return tuple(dict.fromkeys(todas))            # sin repetidos, en orden


def _entidad_en_palabras(nombre_columna: str) -> tuple[str, str]:
    base = [p for p in re.findall(r"[a-z]+", sin_acentos(nombre_columna.lower())) if p not in PALABRAS_ID]
    singular = base[0] if base else "registro"
    plural = singular + ("es" if singular[-1] not in "aeiou" else "s")
    return singular, plural


def _deducir_rol(nombre: str, serie: pd.Series, n: int) -> str:
    if serie.nunique(dropna=True) <= 1:
        return "ignorar"
    if _es_tiempo(nombre, serie):
        return "tiempo"
    if _tokens(nombre) & PALABRAS_ID:
        return "entidad"
    if _es_binaria(serie):
        return "binaria"
    if pd.api.types.is_numeric_dtype(serie):
        return "metrica"
    if serie.nunique() <= min(MAX_CATEGORIAS, max(2, n // 2)):
        return "dimension"
    return "texto"


def inferir_perfil(df: pd.DataFrame, nombre: str = "dataset", config: dict[str, Any] | None = None,
                   hoja: str | None = None) -> PerfilDataset:
    """Construye el PerfilDataset de una tabla. `config` (opcional) corrige o completa lo deducido."""
    config = config or {}
    manual = {c["nombre"]: c for c in config.get("columnas", [])}
    faltan = [c for c in manual if c not in df.columns]
    if faltan:
        raise KeyError(f"El perfil menciona columnas que no están en la tabla: {faltan}")
    n = len(df)

    roles = {col: manual[col]["rol"] if col in manual and "rol" in manual[col] else _deducir_rol(col, df[col], n)
             for col in df.columns}

    # Un solo "tiempo": los demás candidatos pasan a etiqueta (texto) o se ignoran.
    tiempos = [c for c, r in roles.items() if r == "tiempo"]
    if len(tiempos) > 1:
        manuales = [c for c in tiempos if c in manual]
        principal = manuales[0] if manuales else sorted(
            tiempos, key=lambda c: (not pd.api.types.is_datetime64_any_dtype(df[c]),
                                    not pd.api.types.is_numeric_dtype(df[c]), list(df.columns).index(c)))[0]
        for c in tiempos:
            if c != principal and c not in manual:
                uno_a_uno = df.groupby(principal)[c].nunique().max() == 1
                roles[c] = "etiqueta_tiempo" if uno_a_uno and _es_texto(df[c]) else "ignorar"

    # Entidad: si no hay columna "id", buscar una categoría que se repite una vez por periodo.
    entidades = [c for c, r in roles.items() if r == "entidad"]
    tiempo = next((c for c, r in roles.items() if r == "tiempo"), None)
    if not entidades and tiempo:
        n_periodos = df[tiempo].nunique()
        for c, r in roles.items():
            if r == "dimension" and df[c].nunique() * n_periodos == n:
                roles[c], entidades = "entidad", [c]
                break
    if len(entidades) > 1:
        for c in entidades[1:]:
            if c not in manual:
                roles[c] = "dimension"
        entidades = entidades[:1]

    # Nombre de la entidad: texto que corresponde 1 a 1 con el identificador.
    if entidades and not any(r == "nombre_entidad" for r in roles.values()):
        ent = entidades[0]
        for c, r in roles.items():
            if c != ent and r in ("dimension", "texto") and c not in manual and _es_texto(df[c]) \
                    and df[c].nunique() == df[ent].nunique() and df.groupby(ent)[c].nunique().max() == 1:
                roles[c] = "nombre_entidad"
                break

    columnas = []
    for col in df.columns:
        m = manual.get(col, {})
        rol = roles[col]
        etiqueta = m.get("etiqueta") or humanizar(col)
        unidad = m.get("unidad") or (_unidad(col, df[col]) if rol == "metrica" else
                                     "proporcion" if rol == "binaria" else
                                     "texto" if _es_texto(df[col]) else "numero")
        valores = ()
        if rol in ("dimension", "binaria") and df[col].nunique() <= 50:
            valores = tuple(sorted(df[col].dropna().astype(str).unique()))
        columnas.append(Columna(
            nombre=col, rol=rol, etiqueta=etiqueta, descripcion=m.get("descripcion", ""),
            unidad=unidad, agregacion=m.get("agregacion", "promedio" if rol == "binaria" else "mediana"),
            sinonimos=tuple(m.get("sinonimos", ())) or _sinonimos(col, etiqueta, rol),
            valores=tuple(m.get("valores", ())) or valores,
            mayor_es_mejor=m.get("mayor_es_mejor"),
            describe_a=tuple(m.get("describe_a", ())),
        ))

    singular, plural = _entidad_en_palabras(entidades[0]) if entidades else ("registro", "registros")
    return PerfilDataset(
        nombre=config.get("nombre", nombre),
        descripcion=config.get("descripcion", f"Tabla '{nombre}' de {n} filas y {len(df.columns)} columnas."),
        columnas=tuple(columnas),
        entidad_singular=config.get("entidad_singular", singular),
        entidad_plural=config.get("entidad_plural", plural),
        filas=n,
        hoja=hoja or config.get("hoja"),
    )
