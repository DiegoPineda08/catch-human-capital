"""Skill genérica para describir la distribución de una métrica."""

from __future__ import annotations

from math import isfinite
from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, columna_con_rol, filtros_de


class Distribucion(Skill):
    """Describe estadísticamente la distribución de una métrica."""

    nombre = "distribucion"
    descripcion = (
        "Describe la distribución de una métrica mediante estadísticos "
        "descriptivos y datos para visualización."
    )
    intenciones = ("describir_datos",)
    requiere = ("metrica",)
    parametros = {
        "metrica": "Nombre de la columna con rol metrica",
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica",)

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: dict[str, Any],
    ) -> ResultadoSkill:
        perfil = datos.perfil

        metrica = columna_con_rol(
            perfil,
            parametros["metrica"],
            ("metrica", "binaria"),
        )

        filtros = filtros_de(parametros)

        dataframe = datos.filas(
            solo_validas=True,
            **filtros,
        )

        if metrica.nombre not in dataframe.columns:
            raise ValueError(
                f"La métrica '{metrica.nombre}' no existe en el dataset."
            )

        serie = pd.to_numeric(
            dataframe[metrica.nombre],
            errors="coerce",
        )

        valores = [
            float(valor)
            for valor in serie.dropna().tolist()
            if isfinite(float(valor))
        ]

        invalidos = int(serie.isna().sum())

        advertencias: list[str] = []

        if invalidos > 0:
            advertencias.append(
                f"Se excluyeron {invalidos} observaciones faltantes "
                "o no numéricas."
            )

        if not valores:
            advertencias.append(
                f"No hay observaciones numéricas válidas para "
                f"la métrica '{metrica.nombre}'."
            )

            return ResultadoSkill(
                skill=self.nombre,
                evidencias=(),
                datos=(),
                advertencias=tuple(advertencias),
            )

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

        desviacion_estandar = (
            float(serie_valida.std(ddof=1))
            if n > 1
            else None
        )

        unidad = metrica.unidad

        metodo_base = (
            "estadísticos descriptivos calculados sobre "
            "observaciones numéricas válidas"
        )

        evidencias = [
            crear_evidencia(
                self.nombre,
                f"Número de observaciones válidas de {metrica.nombre_visible}",
                n,
                "conteo",
                n,
                "conteo de observaciones numéricas válidas",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Mínimo de {metrica.nombre_visible}",
                minimo,
                unidad,
                n,
                "mínimo de las observaciones válidas",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Q1 de {metrica.nombre_visible}",
                q1,
                unidad,
                n,
                "cuartil 1; percentil 25",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Mediana de {metrica.nombre_visible}",
                mediana,
                unidad,
                n,
                "mediana; percentil 50",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Q3 de {metrica.nombre_visible}",
                q3,
                unidad,
                n,
                "cuartil 3; percentil 75",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Máximo de {metrica.nombre_visible}",
                maximo,
                unidad,
                n,
                "máximo de las observaciones válidas",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"Rango de {metrica.nombre_visible}",
                rango,
                unidad,
                n,
                "máximo menos mínimo",
                filtros,
            ),
            crear_evidencia(
                self.nombre,
                f"IQR de {metrica.nombre_visible}",
                iqr,
                unidad,
                n,
                "cuartil 3 menos cuartil 1",
                filtros,
            ),
        ]

        if desviacion_estandar is not None:
            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    f"Desviación estándar de {metrica.nombre_visible}",
                    desviacion_estandar,
                    unidad,
                    n,
                    "desviación estándar muestral",
                    filtros,
                )
            )

        datos_visualizacion = (
            {
                "metrica": metrica.nombre,
                "min": round(minimo, 6),
                "q1": round(q1, 6),
                "mediana": round(mediana, 6),
                "q3": round(q3, 6),
                "max": round(maximo, 6),
            },
        )

        return ResultadoSkill(
            skill=self.nombre,
            evidencias=tuple(evidencias),
            datos=datos_visualizacion,
            advertencias=tuple(advertencias),
        )