"""Investigación externa real: búsqueda, lectura segura de páginas, artículos y estadísticas oficiales."""
from .catalogo import integraciones
from .estadisticas import INDICADORES, PAISES, PAIS_REFERENCIA_SUGERIDO
from .fuentes import Fuente, clasificar
from .investigador import MODOS, Investigacion, investigar
from .red import URLBloqueada, descargar, validar_url

__all__ = ["investigar", "Investigacion", "MODOS", "Fuente", "clasificar", "integraciones", "descargar",
           "validar_url", "URLBloqueada", "INDICADORES", "PAISES", "PAIS_REFERENCIA_SUGERIDO"]
