"""Skill genérica para describir la distribución de una métrica.

La Skill:
- recibe un DataEngine;
- recibe el nombre de una métrica;
- valida que la métrica exista;
- convierte sus valores a numéricos;
- excluye valores faltantes o no numéricos;
- calcula estadísticos descriptivos;
- genera evidencia estructurada;
- devuelve datos estructurados para visualización.

No contiene nombres de columnas específicos de Catch.
No define ni modifica los contratos compartidos de dinamo.core.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

import pandas as pd

from dinamo.data_engine.engine import DataEngine
from dinamo.evidence.store import EvidenceStore


class DistribucionSkill:
    """Describe estadísticamente la distribución de una métrica."""

    nombre = "distribucion"

    def __init__(
        self,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        """Inicializa la Skill.

        Parameters
        ----------
        evidence_store:
            Almacenamiento opcional para registrar la evidencia generada.
        """
        self._evidence_store = evidence_store

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Ejecuta el análisis de distribución.

        Parameters
        ----------
        datos:
            DataEngine que contiene el dataset.

        parametros:
            Debe contener:
                - ``metrica``: nombre de la columna numérica a analizar.

        Returns
        -------
        dict
            Resultado estructurado con:
            - skill;
            - metrica;
            - n;
            - resultado;
            - datos_visualizacion;
            - advertencias;
            - evidencia;
            - tipo_grafico.
        """
        self._validar_entrada(datos, parametros)

        metrica = parametros["metrica"]
        dataframe = datos.dataframe()

        if metrica not in dataframe.columns:
            raise ValueError(
                f"La métrica '{metrica}' no existe en el dataset."
            )

        serie = pd.to_numeric(
            dataframe[metrica],
            errors="coerce",
        )

        faltantes_o_invalidos = int(serie.isna().sum())

        valores = [
            float(valor)
            for valor in serie.dropna().tolist()
            if isfinite(float(valor))
        ]

        advertencias: list[str] = []

        if faltantes_o_invalidos > 0:
            advertencias.append(
                f"Se excluyeron {faltantes_o_invalidos} "
                "observaciones faltantes o no numéricas."
            )

        if not valores:
            advertencias.append(
                f"No hay observaciones numéricas válidas "
                f"para la métrica '{metrica}'."
            )

            return {
                "skill": self.nombre,
                "metrica": metrica,
                "n": 0,
                "resultado": {
                    "n": 0,
                    "min": None,
                    "q1": None,
                    "mediana": None,
                    "q3": None,
                    "max": None,
                    "rango": None,
                    "iqr": None,
                    "desviacion_estandar": None,
                },
                "datos_visualizacion": [],
                "advertencias": advertencias,
                "evidencia": [],
                "tipo_grafico": "boxplot",
            }

        serie_valida = pd.Series(
            valores,
            dtype="float64",
        )

        n = int(serie_valida.size)

        minimo = float(serie_valida.min())
        q1 = float(serie_valida.quantile(0.25))
        mediana = float(serie_valida.quantile(0.50))
        q3 = float(serie_valida.quantile(0.75))
        maximo = float(serie_valida.max())

        rango = float(maximo - minimo)
        iqr = float(q3 - q1)

        if n > 1:
            desviacion_estandar = float(
                serie_valida.std(ddof=1)
            )
        else:
            desviacion_estandar = None

        resultado = {
            "n": n,
            "min": minimo,
            "q1": q1,
            "mediana": mediana,
            "q3": q3,
            "max": maximo,
            "rango": rango,
            "iqr": iqr,
            "desviacion_estandar": desviacion_estandar,
        }

        datos_visualizacion = [
            {
                "metrica": metrica,
                "min": minimo,
                "q1": q1,
                "mediana": mediana,
                "q3": q3,
                "max": maximo,
            }
        ]

        evidencia = self._generar_evidencia(
            metrica=metrica,
            resultado=resultado,
            n=n,
        )

        return {
            "skill": self.nombre,
            "metrica": metrica,
            "n": n,
            "resultado": resultado,
            "datos_visualizacion": datos_visualizacion,
            "advertencias": advertencias,
            "evidencia": evidencia,
            "tipo_grafico": "boxplot",
        }

    @staticmethod
    def _validar_entrada(
        datos: DataEngine,
        parametros: Mapping[str, Any],
    ) -> None:
        """Valida los argumentos de ejecución."""
        if not isinstance(datos, DataEngine):
            raise TypeError(
                "datos debe ser una instancia de DataEngine."
            )

        if not isinstance(parametros, Mapping):
            raise TypeError(
                "parametros debe ser un Mapping."
            )

        if "metrica" not in parametros:
            raise ValueError(
                "Falta el parámetro requerido: 'metrica'."
            )

        metrica = parametros["metrica"]

        if not isinstance(metrica, str):
            raise TypeError(
                "metrica debe ser una cadena."
            )

        if not metrica.strip():
            raise ValueError(
                "metrica no puede ser una cadena vacía."
            )

    def _generar_evidencia(
        self,
        *,
        metrica: str,
        resultado: Mapping[str, Any],
        n: int,
    ) -> list[dict[str, Any]]:
        """Genera evidencia estructurada para los resultados numéricos."""
        elementos = [
            (
                "n",
                resultado["n"],
                "observaciones",
                "conteo de observaciones numéricas válidas",
            ),
            (
                "min",
                resultado["min"],
                "unidad de la métrica",
                "mínimo de las observaciones válidas",
            ),
            (
                "q1",
                resultado["q1"],
                "unidad de la métrica",
                "cuartil 1; percentil 25",
            ),
            (
                "mediana",
                resultado["mediana"],
                "unidad de la métrica",
                "mediana; percentil 50",
            ),
            (
                "q3",
                resultado["q3"],
                "unidad de la métrica",
                "cuartil 3; percentil 75",
            ),
            (
                "max",
                resultado["max"],
                "unidad de la métrica",
                "máximo de las observaciones válidas",
            ),
            (
                "rango",
                resultado["rango"],
                "unidad de la métrica",
                "máximo menos mínimo",
            ),
            (
                "iqr",
                resultado["iqr"],
                "unidad de la métrica",
                "cuartil 3 menos cuartil 1",
            ),
            (
                "desviacion_estandar",
                resultado["desviacion_estandar"],
                "unidad de la métrica",
                "desviación estándar muestral",
            ),
        ]

        evidencia: list[dict[str, Any]] = []

        for nombre, valor, unidad, metodo in elementos:
            registro = {
                "skill": self.nombre,
                "descripcion": f"{nombre} de {metrica}",
                "valor": valor,
                "unidad": unidad,
                "n": n,
                "metodo": metodo,
            }

            evidencia.append(registro)

            if self._evidence_store is not None:
                self._evidence_store.agregar(
                    skill=self.nombre,
                    metodo=metodo,
                    n=n,
                    resultado={
                        "descripcion": registro["descripcion"],
                        "valor": valor,
                        "unidad": unidad,
                    },
                )

        return evidencia