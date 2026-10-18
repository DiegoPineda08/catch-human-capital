"""
LIMPIEZA DE DATOS con aprobación del usuario.

Flujo:  perfilar → detectar problemas → proponer → el usuario aprueba → aplicar →
        comparar antes/después → registro de cambios → script reproducible → exportar.

Reglas:
  - El archivo original NUNCA se modifica: la versión limpia es un archivo nuevo.
  - Nada se cambia sin aprobación explícita de cada propuesta.
  - No se imputan valores faltantes por defecto (sólo si el usuario lo elige).
  - Los valores atípicos se SEÑALAN; no se borran ni se recortan automáticamente.
"""
from .limpieza import (ACCIONES, Problema, aplicar, comparar, diagnosticar, leer_crudo, script_python)

__all__ = ["ACCIONES", "Problema", "diagnosticar", "aplicar", "comparar", "script_python", "leer_crudo"]
