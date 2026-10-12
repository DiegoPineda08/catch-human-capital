"""
Lector de PDF: saca del archivo dos cosas distintas.

  1. TABLAS  -> cada tabla de cada página se convierte en un DataFrame. Así una tabla que viene
               dentro de un informe se puede analizar igual que un Excel (tendencias, rankings...).
  2. TEXTO   -> el resto de la página (lo que NO es tabla) se corta en fragmentos de unas
               pocas frases. El RAC los usa para responder "¿qué dice el informe sobre...?".

Usa la librería pdfplumber, que lee PDFs "digitales" (creados desde Word, Excel, etc.).
Un PDF ESCANEADO es sólo una imagen: no tiene texto que leer. En ese caso se devuelve una
advertencia; leerlo exigiría OCR (reconocimiento de caracteres), que es una tarea pendiente.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from dinamo.core.contracts import Documento, Fragmento, TablaExtraida

from .tablas import detectar_encabezado, normalizar_tabla, slug

MAX_CARACTERES_FRAGMENTO = 600
MIN_CARACTERES_TEXTO = 30          # menos que esto en todo el PDF = probablemente escaneado


def trocear(texto: str, fuente: str, max_caracteres: int = MAX_CARACTERES_FRAGMENTO) -> list[Fragmento]:
    """Corta un texto largo en fragmentos de frases completas de hasta `max_caracteres`."""
    texto = re.sub(r"-\n(?=[a-záéíóúñ])", "", texto)           # une palabras cortadas con guion
    texto = re.sub(r"\s*\n\s*", " ", texto).strip()
    frases = [f for f in re.split(r"(?<=[.!?:])\s+", texto) if f.strip()]
    trozos, actual = [], ""
    for frase in frases:
        if actual and len(actual) + len(frase) + 1 > max_caracteres:
            trozos.append(actual)
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        trozos.append(actual)
    if len(trozos) == 1:
        return [Fragmento(fuente, trozos[0])]
    return [Fragmento(f"{fuente}.{i}", t) for i, t in enumerate(trozos, start=1)]


def _tabla_a_dataframe(filas: list[list]) -> pd.DataFrame:
    filas = [[c if c is None else str(c).replace("\n", " ").strip() for c in fila] for fila in filas]
    crudo = pd.DataFrame(filas).replace({"": None})
    return normalizar_tabla(detectar_encabezado(crudo))


def leer_pdf(ruta: str | Path) -> Documento:
    import pdfplumber                       # se importa aquí: sólo se necesita si llega un PDF

    ruta = Path(ruta)
    base = slug(ruta.stem)
    tablas, fragmentos, advertencias = [], [], []
    with pdfplumber.open(ruta) as pdf:
        for n_pagina, pagina in enumerate(pdf.pages, start=1):
            encontradas = pagina.find_tables()
            for i, t in enumerate(encontradas, start=1):
                df = _tabla_a_dataframe(t.extract())
                if df.shape[0] >= 2 and df.shape[1] >= 2:
                    sufijo = f"_t{i}" if len(encontradas) > 1 else ""
                    tablas.append(TablaExtraida(nombre=f"{base}_p{n_pagina}{sufijo}",
                                                origen=f"{ruta.name}, página {n_pagina}", tabla=df))
            resto = pagina
            for t in encontradas:                       # el texto de la tabla no se repite como párrafo
                resto = resto.outside_bbox(t.bbox)
            texto = resto.extract_text() or ""
            if texto.strip():
                fragmentos += trocear(texto, f"{ruta.name}#p{n_pagina}")
    if sum(len(f.texto) for f in fragmentos) < MIN_CARACTERES_TEXTO and not tablas:
        advertencias.append(f"'{ruta.name}' no tiene texto legible: parece un PDF escaneado. "
                            "Hace falta OCR para leerlo.")
    return Documento(ruta.name, "pdf", tuple(tablas), tuple(fragmentos), tuple(advertencias))
