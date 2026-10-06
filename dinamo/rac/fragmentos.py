"""Convierte fuentes de conocimiento en fragmentos (fuente, texto) que el RAC puede buscar.

Un fragmento es una tupla (fuente, texto). `fuente` es lo que se cita ("glosario.md#Aguinaldo",
"diccionario:salario_diario_inicial", "leeme:Faltantes"). Nada aquí es específico de un tema:
cualquier carpeta de .md/.txt/.csv y cualquier Excel con un diccionario de datos funciona.

Principio de diseño: el RAC aporta DEFINICIONES Y METODOLOGÍA, nunca cifras del análisis. Por eso
no se indexan hojas de resultados (correlaciones, resúmenes por periodo): esos números sólo pueden
llegar al usuario a través de una Evidencia.
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from .texto import quitar_acentos

Fragmento = tuple[str, str]

MAX_CHARS = 900          # tamaño máximo de un fragmento (cabe 3 veces en el prompt de un modelo de 3B)
MAX_OPCIONES = 25        # opciones de una pregunta de encuesta que se listan en su fragmento
MAX_FILAS_CSV = 2000

_RE_TITULO = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto)).strip()


def _recortar(texto: str, n: int = MAX_CHARS) -> str:
    texto = _limpiar(texto)
    return texto if len(texto) <= n else texto[: n - 1].rsplit(" ", 1)[0] + "…"


def _trocear(texto: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Parte un texto largo por párrafos (y por frases si un párrafo sigue siendo largo)."""
    partes: list[str] = []
    actual = ""
    for parrafo in re.split(r"\n\s*\n", texto.strip()):
        parrafo = _limpiar(parrafo)
        if not parrafo:
            continue
        piezas = [parrafo] if len(parrafo) <= max_chars else re.split(r"(?<=[.!?])\s+", parrafo)
        for pieza in piezas:
            if actual and len(actual) + len(pieza) + 1 > max_chars:
                partes.append(actual)
                actual = pieza
            else:
                actual = f"{actual} {pieza}".strip()
    if actual:
        partes.append(actual)
    return partes


# ------------------------------------------------------------------ carpeta
def dividir_markdown(texto: str, archivo: str) -> list[Fragmento]:
    """Un fragmento por título (#, ## o ###). El título viaja dentro del texto y de la fuente."""
    marcas = list(_RE_TITULO.finditer(texto))
    if not marcas:
        return [(archivo, p) for p in _trocear(texto)]
    salida: list[Fragmento] = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        titulo, cuerpo = m.group(2).strip(), texto[m.end():fin].strip()
        if not cuerpo or len(m.group(1)) == 1:   # el título (#) del archivo + su introducción no es un concepto
            continue
        for j, parte in enumerate(_trocear(cuerpo)):
            sufijo = f" (parte {j + 1})" if j else ""
            salida.append((f"{archivo}#{titulo}{sufijo}", f"{titulo}. {parte}"))
    return salida


def cargar_csv(ruta: Path) -> list[Fragmento]:
    """Cada fila de un CSV pequeño se vuelve 'col: valor; col: valor' (útil para glosarios en tabla)."""
    salida: list[Fragmento] = []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        for i, fila in enumerate(csv.DictReader(f)):
            if i >= MAX_FILAS_CSV:
                break
            texto = "; ".join(f"{k}: {_limpiar(v)}" for k, v in fila.items() if v and str(v).strip())
            if texto:
                salida.append((f"{ruta.name}#fila{i + 1}", _recortar(texto)))
    return salida


def cargar_carpeta(carpeta: str | Path) -> list[Fragmento]:
    """Lee recursivamente .md, .txt y .csv. Archivos nuevos entran solos: no hay que registrarlos."""
    carpeta = Path(carpeta)
    if not carpeta.exists():
        return []
    salida: list[Fragmento] = []
    for ruta in sorted(carpeta.rglob("*")):
        if not ruta.is_file():
            continue
        sufijo = ruta.suffix.lower()
        rel = ruta.relative_to(carpeta).as_posix()
        try:
            if sufijo == ".md":
                salida += dividir_markdown(ruta.read_text(encoding="utf-8"), rel)
            elif sufijo == ".txt":
                salida += [(rel, p) for p in _trocear(ruta.read_text(encoding="utf-8"))]
            elif sufijo == ".csv":
                salida += cargar_csv(ruta)
        except (UnicodeDecodeError, csv.Error):
            continue  # un archivo corrupto no debe tumbar el arranque
    return salida


# ------------------------------------------------------------------ Excel
_NOMBRES_LEEME = ("leeme", "readme", "metodologia", "notas", "acerca")
_COLS_VARIABLE = ("variable", "campo", "columna", "nombre")
_COLS_PREGUNTA = ("pregunta", "descripcion", "definicion", "significado")
_COLS_OPCION = ("opcion", "valor", "categoria")
_COLS_JUSTIFICACION = ("justificacion", "comentario", "nota", "detalle")
_COLS_ROL = ("rol_en_proyecto", "rol")
_COLS_TEMA = ("tema", "area")


def _col(df, candidatas: tuple[str, ...]):
    """Primera columna cuyo nombre (sin acentos, minúsculas) coincide con alguna candidata."""
    mapa = {quitar_acentos(str(c)).lower().strip(): c for c in df.columns}
    for cand in candidatas:
        if cand in mapa:
            return mapa[cand]
    return None


def _es_valor(v) -> bool:
    return v is not None and str(v).strip() not in ("", "nan", "NaN", "None")


def fragmentos_leeme(df, hoja: str) -> list[Fragmento]:
    """Hoja de 2 columnas (sección, descripción) -> un fragmento por fila."""
    if df.shape[1] < 2:
        return []
    salida = []
    for _, fila in df.iterrows():
        seccion, descripcion = fila.iloc[0], fila.iloc[1]
        if _es_valor(seccion) and _es_valor(descripcion):
            salida.append((f"{hoja.lower()}:{_limpiar(seccion)}",
                           f"{_limpiar(seccion)}. {_recortar(descripcion)}"))
    return salida


def fragmentos_diccionario(df) -> list[Fragmento]:
    """Diccionario de datos genérico (variable, pregunta, opción, justificación...).

    - Variables con justificación: un fragmento por variable (suelen ser las importantes).
    - El resto: se AGRUPAN por pregunta, porque una pregunta de encuesta con 30 opciones genera
      30 filas casi idénticas que, indexadas por separado, taparían a todo lo demás.
    """
    c_var, c_preg = _col(df, _COLS_VARIABLE), _col(df, _COLS_PREGUNTA)
    c_opc, c_just = _col(df, _COLS_OPCION), _col(df, _COLS_JUSTIFICACION)
    c_rol, c_tema = _col(df, _COLS_ROL), _col(df, _COLS_TEMA)
    if c_var is None or (c_preg is None and c_just is None):
        return []

    salida: list[Fragmento] = []
    grupos: dict[str, dict] = {}
    for _, fila in df.iterrows():
        var = _limpiar(fila[c_var]) if _es_valor(fila[c_var]) else ""
        if not var:
            continue
        pregunta = _limpiar(fila[c_preg]) if c_preg is not None and _es_valor(fila[c_preg]) else ""
        derivada = pregunta.upper().startswith("VARIABLE DERIVADA")
        if c_just is not None and _es_valor(fila[c_just]):
            meta = [str(fila[c]) for c in (c_tema, c_rol) if c is not None and _es_valor(fila[c])]
            cabecera = f"{var} ({'; '.join(meta)})" if meta else var
            extra = "" if derivada or not pregunta else f" Pregunta original: {_recortar(pregunta, 300)}"
            salida.append((f"diccionario:{var}", _recortar(f"{cabecera}. {_limpiar(fila[c_just]).rstrip('.')}.{extra}")))
        elif pregunta and not derivada:
            g = grupos.setdefault(pregunta, {"vars": [], "opciones": []})
            g["vars"].append(var)
            if c_opc is not None and _es_valor(fila[c_opc]) and _limpiar(fila[c_opc]).lower() != "response":
                g["opciones"].append(_limpiar(fila[c_opc]))

    for pregunta, g in grupos.items():
        prefijo = g["vars"][0].split("__")[0]
        opciones = list(dict.fromkeys(g["opciones"]))[:MAX_OPCIONES]
        texto = f"Pregunta de la encuesta: {pregunta}"
        if opciones:
            texto += f" Opciones: {'; '.join(opciones)}."
        texto += f" Variables: {prefijo}."
        salida.append((f"encuesta:{prefijo}", _recortar(texto, MAX_CHARS + 300)))
    return salida


def cargar_excel_conocimiento(ruta: str | Path) -> list[Fragmento]:
    """Detecta solo qué hojas son documentación (LEEME/metodología o diccionario de datos).

    No necesita saber nombres de hojas ni de columnas exactos: funciona con otro Excel
    que siga la misma idea. Las hojas de datos y de resultados se ignoran a propósito."""
    import pandas as pd  # import tardío: el RAC sin Excel no lo necesita

    ruta = Path(ruta)
    if not ruta.exists():
        return []
    salida: list[Fragmento] = []
    vistos: set[str] = set()
    with pd.ExcelFile(ruta) as libro:
        for hoja in libro.sheet_names:
            nombre = quitar_acentos(hoja).lower()
            if any(n in nombre for n in _NOMBRES_LEEME):
                df = libro.parse(hoja)
                nuevos = fragmentos_leeme(df, hoja)
            else:
                df = libro.parse(hoja, nrows=3000)
                if _col(df, _COLS_VARIABLE) is None or df.shape[1] < 3:
                    continue
                nuevos = fragmentos_diccionario(df)
            for frag in nuevos:  # evita duplicados entre hojas (p. ej. VARIABLES_SELECCIONADAS vs DICCIONARIO)
                if frag[0] not in vistos:
                    vistos.add(frag[0])
                    salida.append(frag)
    return salida


def construir_fragmentos(carpeta: str | Path | None = None, ruta_excel: str | Path | None = None,
                         extra: list[Fragmento] | None = None) -> list[Fragmento]:
    """Une todas las fuentes y quita fragmentos repetidos. Orden estable -> resultados reproducibles."""
    todos: list[Fragmento] = []
    if carpeta:
        todos += cargar_carpeta(carpeta)
    if ruta_excel:
        todos += cargar_excel_conocimiento(ruta_excel)
    todos += extra or []
    vistos, unicos = set(), []
    for fuente, texto in todos:
        h = hashlib.md5(f"{fuente}|{texto}".encode()).hexdigest()
        if h not in vistos:
            vistos.add(h)
            unicos.append((fuente, texto))
    return unicos
