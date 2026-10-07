"""
INGESTA: convierte cualquier archivo en un `Documento` (tablas + fragmentos de texto).

Es la ÚNICA parte del sistema que sabe de formatos de archivo. El resto de DINAMO no sabe
si los datos vinieron de un Excel, un CSV o un PDF: sólo ve tablas y textos.

Para agregar un formato nuevo (por ejemplo Word .docx):
  1. escribe una función  leer_docx(ruta) -> Documento  (en un archivo nuevo, como pdf.py);
  2. regístrala en LECTORES con su extensión;
  3. agrega un test en tests/test_ingesta.py.
Nada más cambia: ni el Brain, ni las Skills, ni la interfaz.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from dinamo.core.contracts import Documento, Fragmento, TablaExtraida

from .pdf import leer_pdf, trocear
from .tablas import detectar_encabezado, normalizar_tabla, slug
from .word import leer_word, tabla_a_dataframe as _tabla_a_df

MIN_FILAS, MIN_COLUMNAS = 2, 2


def leer_csv(ruta: str | Path) -> Documento:
    """CSV con cualquier separador (, ; tab |) y codificación UTF-8 o Latin-1 (la de Excel en español)."""
    ruta = Path(ruta)
    for codificacion in ("utf-8-sig", "latin-1"):
        try:   # sep=None: pandas detecta solo si el separador es coma, punto y coma o tabulador
            df = pd.read_csv(ruta, sep=None, engine="python", encoding=codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"No pude leer {ruta.name}: codificación desconocida")
    tabla = TablaExtraida(slug(ruta.stem), ruta.name, normalizar_tabla(df))
    return Documento(ruta.name, "csv", (tabla,))


def leer_excel(ruta: str | Path, hojas: list[str] | None = None) -> Documento:
    """Cada hoja con datos es una tabla. Detecta filas de título encima de los encabezados."""
    ruta = Path(ruta)
    crudas = pd.read_excel(ruta, sheet_name=hojas or None, header=None)
    tablas, advertencias = [], []
    for hoja, crudo in crudas.items():
        df = normalizar_tabla(detectar_encabezado(crudo))
        if df.shape[0] < MIN_FILAS or df.shape[1] < MIN_COLUMNAS:
            advertencias.append(f"Hoja '{hoja}' omitida: no tiene una tabla ({df.shape[0]} filas).")
            continue
        nombre = slug(ruta.stem) if len(crudas) == 1 else f"{slug(ruta.stem)}_{slug(hoja, 30)}"
        tablas.append(TablaExtraida(nombre, f"{ruta.name}, hoja {hoja}", df, hoja=str(hoja)))
    return Documento(ruta.name, "excel", tuple(tablas), (), tuple(advertencias))


def fragmentar_markdown(texto: str, nombre: str) -> list[Fragmento]:
    """Divide un texto Markdown por sus títulos '## ' -> un fragmento por sección."""
    partes, titulo, buffer = [], Path(nombre).stem, []
    for linea in texto.splitlines():
        if linea.startswith("## "):
            if "".join(buffer).strip():
                partes.append(Fragmento(f"{nombre}#{titulo}", "\n".join(buffer).strip()))
            titulo, buffer = linea[3:].strip(), [linea]
        else:
            buffer.append(linea)
    if "".join(buffer).strip():
        partes.append(Fragmento(f"{nombre}#{titulo}", "\n".join(buffer).strip()))
    return partes


def leer_docx(ruta: str | Path) -> Documento:
    """.docx: secciones de texto -> Fragmentos; tablas -> TablaExtraida."""
    ruta = Path(ruta)
    contenido = leer_word(ruta)
    frags = []
    for sec in contenido.secciones:
        titulo = sec.titulo or ruta.stem
        if sec.texto.strip():
            frags.append(Fragmento(f"{ruta.name}#{titulo}", sec.texto))
    tablas = []
    for i, tabla in enumerate(contenido.tablas):
        df = _tabla_a_df(tabla)
        if df.shape[0] >= MIN_FILAS and df.shape[1] >= MIN_COLUMNAS:
            tablas.append(TablaExtraida(f"{slug(ruta.stem)}_tabla{i + 1}", ruta.name, df))
    return Documento(ruta.name, "docx", tuple(tablas), tuple(frags))


def leer_texto(ruta: str | Path) -> Documento:
    """.md se divide por títulos; .txt se corta en fragmentos de pocas frases."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    frags = fragmentar_markdown(texto, ruta.name) if ruta.suffix.lower() == ".md" else trocear(texto, f"{ruta.name}#texto")
    return Documento(ruta.name, "texto", (), tuple(frags))


# Extensión -> función que la lee. Agregar un formato = agregar una línea aquí.
LECTORES: dict[str, Callable[[str | Path], Documento]] = {
    ".csv": leer_csv, ".tsv": leer_csv,
    ".xlsx": leer_excel, ".xlsm": leer_excel, ".xls": leer_excel,
    ".pdf": leer_pdf,
    ".docx": leer_docx,
    ".txt": leer_texto, ".md": leer_texto,
}
EXTENSIONES = tuple(LECTORES)


def leer_documento(ruta: str | Path) -> Documento:
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo {ruta}")
    lector = LECTORES.get(ruta.suffix.lower())
    if lector is None:
        raise ValueError(f"Formato no soportado: '{ruta.suffix}'. DINAMO lee: {', '.join(EXTENSIONES)}")
    return lector(ruta)
