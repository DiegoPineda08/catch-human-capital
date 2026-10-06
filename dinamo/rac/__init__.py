"""RAC: recuperación aumentada de contexto."""
from .fragmentos import construir_fragmentos
from .retriever import Retriever, RetrieverHibrido, RetrieverTfidf
from .texto import Sinonimos, normalizar

__all__ = ["Retriever", "RetrieverTfidf", "RetrieverHibrido", "Sinonimos", "normalizar", "construir_fragmentos"]
