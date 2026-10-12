"""
Perfiles guardados: JSON en perfiles/ que corrigen o completan lo que el Perfilador deduce.

Un perfil se aplica a una tabla cuando su campo "archivo" coincide con el nombre del archivo
y, si el archivo tiene varias tablas, su "hoja" (Excel) o su "tabla" (PDF) coincide también.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dinamo.ingesta import leer_documento


def leer_config_perfil(ruta: str | Path) -> dict:
    """Lee un perfil guardado en JSON (puede estar incompleto: lo que falte se deduce)."""
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def configs_de_archivo(carpeta: str | Path | None, nombre_archivo: str) -> list[dict]:
    """Todos los perfiles JSON de perfiles/ escritos para este archivo."""
    if carpeta is None or not Path(carpeta).exists():
        return []
    salida = []
    for candidato in sorted(Path(carpeta).glob("*.json")):
        try:
            config = leer_config_perfil(candidato)
        except (json.JSONDecodeError, OSError):
            continue
        if config.get("archivo") == nombre_archivo:
            salida.append(config)
    return salida


def buscar_config_perfil(carpeta: str | Path, ruta_datos: str | Path) -> Path | None:
    """Ruta del primer perfil JSON cuyo "archivo" coincide con el archivo de datos (o None)."""
    carpeta, nombre = Path(carpeta), Path(ruta_datos).name
    for candidato in sorted(carpeta.glob("*.json")) if carpeta.exists() else []:
        try:
            if leer_config_perfil(candidato).get("archivo") == nombre:
                return candidato
        except (json.JSONDecodeError, OSError):
            continue
    return None


def cargar_tabla(ruta: str | Path, hoja: str | None = None) -> tuple[pd.DataFrame, str | None]:
    """Atajo: la tabla de un archivo. Con `hoja`, esa hoja; si no, la tabla con más datos."""
    doc = leer_documento(ruta)
    if not doc.tablas:
        raise ValueError(f"'{Path(ruta).name}' no contiene tablas")
    if hoja is not None:
        elegidas = [t for t in doc.tablas if t.hoja == hoja]
        if not elegidas:
            raise KeyError(f"No existe la hoja '{hoja}' en {Path(ruta).name}")
        return elegidas[0].tabla, hoja
    mejor = max(doc.tablas, key=lambda t: int(t.tabla.notna().sum().sum()))
    return mejor.tabla, mejor.hoja
