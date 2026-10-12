"""
DATA ENGINE: único punto de acceso a los datos.

- Guarda la tabla y su PerfilDataset.
- Entrega COPIAS de la tabla sólo a las Skills (el Brain nunca toca DataFrames).
- Entrega listas simples (periodos, entidades) a quien las necesite, sin exponer la tabla.
- No conoce ninguna base concreta: todo lo que sabe de las columnas sale del perfil.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from dinamo.core.contracts import PerfilDataset

from .cargador import buscar_config_perfil, cargar_tabla, leer_config_perfil
from .perfilador import inferir_perfil


class DatosInvalidos(ValueError):
    """La tabla no coincide con su perfil."""


class DataEngine:
    def __init__(self, tabla: pd.DataFrame, perfil: PerfilDataset):
        faltan = [c.nombre for c in perfil.columnas if c.nombre not in tabla.columns]
        if faltan:
            raise DatosInvalidos(f"El perfil '{perfil.nombre}' describe columnas que no están en la tabla: {faltan}")
        self._tabla = tabla
        self.perfil = perfil
        self.origen = perfil.nombre          # de dónde salió (archivo y hoja/página); lo completa la Biblioteca
        self.documento: str | None = None    # nombre del archivo de origen
        self._version: str | None = None

    # ------------------------------------------------------------------ construcción
    @classmethod
    def desde_tabla(cls, tabla: pd.DataFrame, nombre: str = "dataset", config: dict | None = None,
                    hoja: str | None = None) -> "DataEngine":
        if config and config.get("columnas_usar"):
            tabla = tabla[config["columnas_usar"]]
        return cls(tabla, inferir_perfil(tabla, nombre=nombre, config=config, hoja=hoja))

    @classmethod
    def desde_archivo(cls, ruta: str | Path, ruta_perfil: str | Path | None = None,
                      carpeta_perfiles: str | Path | None = None) -> "DataEngine":
        """Carga UNA tabla de cualquier archivo (la de más datos, o la hoja que diga el perfil JSON).
        Para varios archivos o varias tablas a la vez, usa la Biblioteca."""
        ruta = Path(ruta)
        if ruta_perfil is None and carpeta_perfiles is not None:
            ruta_perfil = buscar_config_perfil(carpeta_perfiles, ruta)
        config = leer_config_perfil(ruta_perfil) if ruta_perfil else {}
        tabla, hoja = cargar_tabla(ruta, hoja=config.get("hoja"))
        motor = cls.desde_tabla(tabla, nombre=config.get("nombre", ruta.stem), config=config, hoja=hoja)
        motor.origen, motor.documento = ruta.name + (f", hoja {hoja}" if hoja else ""), ruta.name
        return motor

    @property
    def version(self) -> str:
        """Huella del contenido de la tabla: si los datos cambian, cambia (y cambian los ids de evidencia)."""
        if self._version is None:
            huella = pd.util.hash_pandas_object(self._tabla, index=False).values.tobytes()
            self._version = hashlib.sha1(huella).hexdigest()[:8]
        return self._version

    # ------------------------------------------------------------------ consultas para Skills
    def filas(self, solo_validas: bool = True, **filtros: Any) -> pd.DataFrame:
        """Copia de la tabla filtrada. filtros: columna=valor (o lista de valores)."""
        df = self._tabla
        validez = self.perfil.una("validez")
        if solo_validas and validez is not None:
            df = df[df[validez.nombre] == 1]
        for col, val in filtros.items():
            if val is None:
                continue
            self.perfil.columna(col)                       # KeyError claro si no existe
            valores = val if isinstance(val, (list, tuple, set)) else [val]
            df = df[df[col].astype(str).isin([str(v) for v in valores])]
        return df.copy()

    # ------------------------------------------------------------------ listas para el Brain
    def periodos(self) -> list[tuple[Any, str]]:
        """[(valor_del_tiempo, etiqueta legible)] en orden cronológico."""
        tiempo = self.perfil.una("tiempo")
        if tiempo is None:
            return []
        etiqueta = self.perfil.una("etiqueta_tiempo")
        cols = [tiempo.nombre] + ([etiqueta.nombre] if etiqueta else [])
        df = self._tabla[cols].dropna(subset=[tiempo.nombre]).drop_duplicates(tiempo.nombre)
        df = df.sort_values(tiempo.nombre)
        return [(_python(r[0]), str(r[-1]) if etiqueta else _texto_tiempo(r[0]))
                for r in df.itertuples(index=False)]

    def entidades(self) -> list[tuple[Any, str]]:
        """[(id, nombre legible)] ordenadas por id."""
        ent = self.perfil.una("entidad")
        if ent is None:
            return []
        nom = self.perfil.una("nombre_entidad")
        cols = [ent.nombre] + ([nom.nombre] if nom else [])
        df = self._tabla[cols].dropna(subset=[ent.nombre]).drop_duplicates(ent.nombre).sort_values(ent.nombre)
        return [(_python(r[0]), str(r[-1])) for r in df.itertuples(index=False)]

    def num_filas(self) -> int:
        return len(self._tabla)


def _python(valor: Any) -> Any:
    """Convierte tipos de numpy/pandas a tipos simples de Python (para JSON y comparaciones)."""
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _texto_tiempo(valor: Any) -> str:
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%d")
    return str(valor)
