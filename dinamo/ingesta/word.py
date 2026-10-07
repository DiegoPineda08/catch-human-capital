"""Lector de Word (.docx) sólo con la biblioteca estándar (cero dependencias nuevas).

Un .docx es un zip con `word/document.xml`. Aquí se lee ese XML y se entrega:
  * secciones: título + párrafos (el texto que el RAC consulta), y
  * tablas: filas de celdas como texto (los datos que Ingesta puede analizar con el Perfilador).

    contenido = leer_word("informe.docx")
    contenido.secciones   -> (Seccion(titulo="Recomendaciones", nivel=1, texto="..."), ...)
    contenido.tablas      -> ((("Área", "Trimestre", "Rotación"), ("Ventas", "T1", "6.1%"), ...), ...)
    tabla_a_dataframe(contenido.tablas[0])   # primera fila como encabezado (necesita pandas)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_RE_ESTILO_TITULO = re.compile(r"^(heading|titulo|ttulo|title)\s*(\d*)$", re.IGNORECASE)


class WordError(ValueError):
    """El archivo no es un .docx válido."""


@dataclass(frozen=True)
class Seccion:
    titulo: str      # "" si el texto aparece antes del primer título
    nivel: int       # 1 = título principal, 2 = subtítulo... (0 si no tiene título)
    texto: str       # párrafos separados por una línea en blanco


@dataclass(frozen=True)
class ContenidoWord:
    secciones: tuple[Seccion, ...]
    tablas: tuple[tuple[tuple[str, ...], ...], ...]


def _texto(nodo: ET.Element) -> str:
    partes: list[str] = []
    for el in nodo.iter():
        if el.tag == f"{_W}t" and el.text:
            partes.append(el.text)
        elif el.tag in (f"{_W}tab", f"{_W}br"):
            partes.append(" ")
    return re.sub(r"\s+", " ", "".join(partes)).strip()


def _nivel_titulo(parrafo: ET.Element) -> int:
    ppr = parrafo.find(f"{_W}pPr")
    if ppr is None:
        return 0
    estilo = ppr.find(f"{_W}pStyle")
    if estilo is not None:
        m = _RE_ESTILO_TITULO.match(estilo.get(f"{_W}val", ""))
        if m:
            return int(m.group(2)) if m.group(2) else 1
    nivel = ppr.find(f"{_W}outlineLvl")
    if nivel is not None:
        try:
            return int(nivel.get(f"{_W}val", "")) + 1
        except ValueError:
            return 0
    return 0


def leer_word(ruta: str | Path) -> ContenidoWord:
    ruta = Path(ruta)
    try:
        with zipfile.ZipFile(ruta) as z:
            raiz = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise WordError(f"No se pudo leer {ruta.name} como .docx: {e}") from e

    cuerpo = raiz.find(f"{_W}body")
    if cuerpo is None:
        return ContenidoWord((), ())

    secciones: list[Seccion] = []
    tablas: list[tuple[tuple[str, ...], ...]] = []
    titulo, nivel, parrafos = "", 0, []

    def cerrar() -> None:
        if parrafos:
            secciones.append(Seccion(titulo, nivel, "\n\n".join(parrafos)))

    for hijo in cuerpo:
        if hijo.tag == f"{_W}p":
            texto = _texto(hijo)
            if not texto:
                continue
            n = _nivel_titulo(hijo)
            if n:
                cerrar()
                titulo, nivel, parrafos = texto, n, []
            else:
                parrafos.append(texto)
        elif hijo.tag == f"{_W}tbl":
            filas = tuple(tuple(_texto(c) for c in fila.findall(f"{_W}tc"))
                          for fila in hijo.findall(f"{_W}tr"))
            filas = tuple(f for f in filas if any(f))
            if filas:
                tablas.append(filas)
    cerrar()
    return ContenidoWord(tuple(secciones), tuple(tablas))


def tabla_a_dataframe(tabla: tuple[tuple[str, ...], ...]):
    """Primera fila = encabezado. Nombres repetidos o vacíos se corrigen."""
    import pandas as pd

    if not tabla:
        return pd.DataFrame()
    nombres: list[str] = []
    for i, nombre in enumerate(tabla[0], start=1):
        base = nombre.strip() or f"columna_{i}"
        final, k = base, 2
        while final in nombres:
            final, k = f"{base}_{k}", k + 1
        nombres.append(final)
    ancho = len(nombres)
    filas = [list(f[:ancho]) + [""] * (ancho - len(f)) for f in tabla[1:]]
    return pd.DataFrame(filas, columns=nombres)
