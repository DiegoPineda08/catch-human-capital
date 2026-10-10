"""RAC: recuperación aumentada de contexto."""
from dinamo.ingesta import fragmentar_markdown

from .fragmentos import cargar_archivo, construir_fragmentos, fragmentos_paginas
from .retriever import (Retriever, RetrieverTfidf, desde_carpeta, documento_mencionado, fragmentos_de_carpeta,
                        fragmentos_del_perfil)
from .texto import Sinonimos, normalizar

__all__ = [
    "Retriever", "RetrieverTfidf", "Sinonimos", "normalizar",
    "construir_fragmentos", "cargar_archivo", "fragmentos_paginas",
    "documento_mencionado", "desde_carpeta",
    "fragmentar_markdown", "fragmentos_de_carpeta", "fragmentos_del_perfil",
]
