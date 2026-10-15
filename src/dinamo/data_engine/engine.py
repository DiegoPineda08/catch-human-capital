"""Motor de acceso a datos de DINAMO_ANALYTICS.

Responsabilidad:
- cargar datos desde Excel o CSV;
- conservar una copia interna de la base;
- entregar copias del DataFrame a las Skills;
- exponer información estructural básica de la fuente.

El Data Engine no conoce columnas específicas de Catch ni realiza
cálculos estadísticos. El significado de las columnas será responsabilidad
del PerfilDataset/Perfilador.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class DataEngine:
    """Acceso determinista a una fuente tabular de datos."""

    def __init__(
        self,
        dataframe: pd.DataFrame,
        fuente: str | Path | None = None,
    ) -> None:
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError("dataframe debe ser un pandas.DataFrame.")

        self._dataframe = dataframe.copy(deep=True).reset_index(drop=True)
        self._fuente = Path(fuente) if fuente is not None else None

    @classmethod
    def desde_excel(
        cls,
        ruta: str | Path,
        *,
        hoja: str | int = 0,
    ) -> DataEngine:
        """Carga una hoja de un archivo Excel."""
        path = cls._validar_archivo(
            ruta,
            extensiones={".xlsx", ".xlsm", ".xls"},
        )

        dataframe = pd.read_excel(path, sheet_name=hoja)

        return cls(dataframe=dataframe, fuente=path)

    @classmethod
    def desde_csv(
        cls,
        ruta: str | Path,
        **kwargs,
    ) -> DataEngine:
        """Carga un archivo CSV."""
        path = cls._validar_archivo(
            ruta,
            extensiones={".csv"},
        )

        dataframe = pd.read_csv(path, **kwargs)

        return cls(dataframe=dataframe, fuente=path)

    @classmethod
    def desde_archivo(
        cls,
        ruta: str | Path,
        **kwargs,
    ) -> DataEngine:
        """Carga automáticamente Excel o CSV según la extensión."""
        path = Path(ruta)

        if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            return cls.desde_excel(path, **kwargs)

        if path.suffix.lower() == ".csv":
            return cls.desde_csv(path, **kwargs)

        raise ValueError(
            f"Formato no soportado: '{path.suffix}'. "
            "DINAMO acepta actualmente Excel (.xlsx, .xlsm, .xls) "
            "y CSV (.csv)."
        )

    def dataframe(self) -> pd.DataFrame:
        """Devuelve una copia independiente de los datos."""
        return self._dataframe.copy(deep=True)

    def columnas(self) -> list[str]:
        """Devuelve los nombres de las columnas."""
        return self._dataframe.columns.tolist()

    def numero_filas(self) -> int:
        """Devuelve el número de filas."""
        return len(self._dataframe)

    def numero_columnas(self) -> int:
        """Devuelve el número de columnas."""
        return len(self._dataframe.columns)

    def forma(self) -> tuple[int, int]:
        """Devuelve (filas, columnas)."""
        return self._dataframe.shape

    def fuente(self) -> Path | None:
        """Devuelve la ruta de origen, si existe."""
        return self._fuente

    @staticmethod
    def _validar_archivo(
        ruta: str | Path,
        *,
        extensiones: set[str],
    ) -> Path:
        """Valida existencia y extensión de un archivo."""
        path = Path(ruta)

        if not path.exists():
            raise FileNotFoundError(
                f"No existe el archivo: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"La ruta no corresponde a un archivo: {path}"
            )

        if path.suffix.lower() not in extensiones:
            extensiones_texto = ", ".join(sorted(extensiones))
            raise ValueError(
                f"Extensión no soportada: '{path.suffix}'. "
                f"Extensiones permitidas: {extensiones_texto}."
            )

        return path