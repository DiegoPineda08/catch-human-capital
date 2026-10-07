"""Skill para detectar anomalías respecto a la historia de cada entidad."""
from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, columna_con_rol, filtros_de


class Anomalias(Skill):
    nombre = "anomalias"
    descripcion = (
        "Detecta entidades cuyo valor del último periodo se aleja "
        "más de un umbral de desviaciones robustas de su propia historia."
    )
    intenciones = ()
    requiere = ("entidad", "metrica", "tiempo")
    parametros = {
        "metrica": "Nombre de la columna (rol metrica o binaria)",
        "umbral": "Número de desviaciones robustas para considerar anomalía (3)",
        "min_periodos": "Mínimo de periodos históricos requeridos (3)",
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica",)

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: dict[str, Any],
    ) -> ResultadoSkill:
        perfil = datos.perfil

        met = columna_con_rol(
            perfil,
            parametros["metrica"],
            ("metrica", "binaria"),
        )
        ent = perfil.una("entidad")
        tiempo = perfil.una("tiempo")

        umbral = float(parametros.get("umbral", 3))
        min_periodos = int(parametros.get("min_periodos", 3))
        filtros = filtros_de(parametros)

        if umbral <= 0:
            raise ValueError("umbral debe ser mayor que 0.")

        if min_periodos < 1:
            raise ValueError("min_periodos debe ser al menos 1.")

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).dropna(
            subset=[ent.nombre, tiempo.nombre, met.nombre],
        )

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos válidos para esos filtros.",),
            )

        # Primero reducimos a una observación por entidad y periodo.
        # Esto evita que filas duplicadas alteren la historia.
        agregado = (
            df.groupby(
                [ent.nombre, tiempo.nombre],
                dropna=False,
            )[met.nombre]
            .median()
            .reset_index(name="valor")
        )

        if agregado.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay observaciones válidas para analizar.",),
            )

        # El periodo evaluado es el último periodo disponible globalmente.
        ultimo_periodo = agregado[tiempo.nombre].max()

        actual = agregado[
            agregado[tiempo.nombre] == ultimo_periodo
        ].copy()

        if actual.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay entidades con dato en el último periodo.",),
            )

        advertencias: list[str] = []
        resultados: list[dict[str, Any]] = []
        evidencias = []

        entidades_insuficientes = 0
        entidades_mad_cero = 0

        for entidad, fila_actual in actual.groupby(
            ent.nombre,
            sort=True,
        ):
            valor_actual = float(fila_actual["valor"].iloc[0])

            historia = agregado[
                (agregado[ent.nombre] == entidad)
                & (agregado[tiempo.nombre] != ultimo_periodo)
            ].copy()

            periodos_historia = int(len(historia))

            if periodos_historia < min_periodos:
                entidades_insuficientes += 1
                continue

            valores_historia = historia["valor"].astype(float)

            mediana = float(valores_historia.median())

            desviaciones = (valores_historia - mediana).abs()
            mad = float(desviaciones.median())

            if mad == 0:
                entidades_mad_cero += 1
                continue

            desviacion_robusta = abs(valor_actual - mediana) / mad

            if desviacion_robusta <= umbral:
                continue

            diferencia = valor_actual - mediana

            resultado = {
                "entidad": _simple(entidad),
                "periodo": _simple(ultimo_periodo),
                "valor": round(valor_actual, 6),
                "mediana_historica": round(mediana, 6),
                "mad": round(mad, 6),
                "desviacion_robusta": round(
                    desviacion_robusta,
                    6,
                ),
                "diferencia": round(diferencia, 6),
                "periodos_historia": periodos_historia,
            }

            resultados.append(resultado)

        if entidades_insuficientes:
            advertencias.append(
                f"{entidades_insuficientes} {perfil.entidad_plural} "
                f"quedaron fuera por tener menos de {min_periodos} "
                "periodos de historia."
            )

        if entidades_mad_cero:
            advertencias.append(
                f"{entidades_mad_cero} {perfil.entidad_plural} "
                "no pudieron evaluarse porque su MAD histórico es 0."
            )

        # Orden determinista: mayor desviación robusta primero y,
        # en empate, identificador de entidad.
        resultados.sort(
            key=lambda x: (
                -x["desviacion_robusta"],
                _ordenable(x["entidad"]),
            )
        )

        for resultado in resultados:
            entidad_txt = str(resultado["entidad"])

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"Anomalía de {met.nombre_visible} en "
                        f"{perfil.entidad_singular} {entidad_txt}"
                    ),
                    resultado["desviacion_robusta"],
                    "desviaciones robustas",
                    resultado["periodos_historia"],
                    (
                        "distancia absoluta entre el último valor y la "
                        "mediana histórica, dividida por el MAD histórico"
                    ),
                    {
                        "metrica": met.nombre,
                        "periodo": resultado["periodo"],
                        "entidad": resultado["entidad"],
                        "umbral": umbral,
                        **filtros,
                    },
                )
            )

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"Mediana histórica de {met.nombre_visible} "
                        f"para {perfil.entidad_singular} {entidad_txt}"
                    ),
                    resultado["mediana_historica"],
                    met.unidad,
                    resultado["periodos_historia"],
                    "mediana de los valores históricos por entidad",
                    {
                        "metrica": met.nombre,
                        "periodo": resultado["periodo"],
                        "entidad": resultado["entidad"],
                        **filtros,
                    },
                )
            )

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"MAD histórico de {met.nombre_visible} "
                        f"para {perfil.entidad_singular} {entidad_txt}"
                    ),
                    resultado["mad"],
                    met.unidad,
                    resultado["periodos_historia"],
                    (
                        "mediana de las desviaciones absolutas "
                        "respecto a la mediana histórica"
                    ),
                    {
                        "metrica": met.nombre,
                        "periodo": resultado["periodo"],
                        "entidad": resultado["entidad"],
                        **filtros,
                    },
                )
            )

        return ResultadoSkill(
            self.nombre,
            tuple(evidencias),
            tuple(resultados),
            tuple(advertencias),
        )


def _simple(valor: Any) -> Any:
    """Convierte escalares de pandas/numpy a tipos Python."""
    return valor.item() if hasattr(valor, "item") else valor


def _ordenable(valor: Any) -> tuple[str, str]:
    """Clave estable para ordenar identificadores heterogéneos."""
    return (type(valor).__name__, str(valor))
