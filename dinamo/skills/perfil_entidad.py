"""Skill genérica para construir el perfil de una entidad."""

from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, filtros_de


class PerfilEntidad(Skill):
    """Describe una entidad concreta usando su último periodo válido."""

    nombre = "perfil_entidad"
    descripcion = (
        "Construye el perfil de una entidad con sus métricas, "
        "comparaciones poblacionales, percentiles y atributos."
    )
    intenciones = ("perfil_entidad",)
    requiere = ("entidad",)
    parametros = {
        "metrica": "Métrica opcional a destacar",
        "filtros": (
            "Filtros que identifican la entidad, por ejemplo "
            "{tienda_id: 1}"
        ),
    }
    requeridos = ()

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: dict[str, Any],
    ) -> ResultadoSkill:
        perfil = datos.perfil
        entidad = perfil.una("entidad")
        tiempo = perfil.una("tiempo")
        nombre_entidad = perfil.una("nombre_entidad")

        filtros = filtros_de(parametros)

        if entidad.nombre not in filtros:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    f"No se recibió un filtro para identificar "
                    f"la {perfil.entidad_singular}.",
                ),
            )

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).copy()

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    f"No se encontraron datos para la "
                    f"{perfil.entidad_singular} solicitada.",
                ),
            )

        # --------------------------------------------------------------
        # Identificación de la entidad.
        # --------------------------------------------------------------
        valores_entidad = df[entidad.nombre].dropna().unique()

        if len(valores_entidad) != 1:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    f"Los filtros no identifican una única "
                    f"{perfil.entidad_singular}.",
                ),
            )

        identificador = _simple(valores_entidad[0])

        etiqueta = identificador

        if nombre_entidad is not None:
            nombres = df[nombre_entidad.nombre].dropna().unique()

            if len(nombres) > 0:
                etiqueta = _simple(nombres[0])

        # --------------------------------------------------------------
        # Último periodo válido.
        # --------------------------------------------------------------
        if tiempo is not None:
            df = df.dropna(subset=[tiempo.nombre])

            if df.empty:
                return ResultadoSkill(
                    self.nombre,
                    (),
                    (),
                    (
                        "La entidad no tiene periodos válidos "
                        "para construir su perfil.",
                    ),
                )

            ultimo_periodo = _ultimo_valor(
                df[tiempo.nombre]
            )

            df_entidad = df[
                df[tiempo.nombre] == ultimo_periodo
            ].copy()
        else:
            ultimo_periodo = None
            df_entidad = df.copy()

        if df_entidad.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "No hay observaciones válidas para el "
                    "último periodo de la entidad.",
                ),
            )

        # --------------------------------------------------------------
        # Una fila representativa de la entidad en el último periodo.
        # Si existen varias observaciones, cada métrica se agrega según
        # su configuración del Perfil.
        # --------------------------------------------------------------
        metricas = perfil.por_rol("metrica")
        binarias = perfil.por_rol("binaria")

        columnas_metricas = []

        for columna in metricas + binarias:
            if columna.nombre not in columnas_metricas:
                columnas_metricas.append(columna)

        metricas_resultado: dict[str, float] = {}
        evidencias: list[Any] = []

        # --------------------------------------------------------------
        # Comparación poblacional: último periodo disponible.
        # Primero construimos los valores a nivel de entidad.
        # --------------------------------------------------------------
        base_poblacion = datos.filas(
            solo_validas=True,
        ).copy()

        if tiempo is not None:
            base_poblacion = base_poblacion.dropna(
                subset=[tiempo.nombre]
            )

            if not base_poblacion.empty:
                base_poblacion = base_poblacion[
                    base_poblacion[tiempo.nombre] == ultimo_periodo
                ]

        base_poblacion = base_poblacion.dropna(
            subset=[entidad.nombre]
        )

        contexto_base = {
            entidad.nombre: identificador,
        }

        if ultimo_periodo is not None:
            contexto_base["periodo"] = _simple(
                ultimo_periodo
            )

        for columna in columnas_metricas:
            if columna.nombre not in df_entidad.columns:
                continue

            valores_entidad = pd.to_numeric(
                df_entidad[columna.nombre],
                errors="coerce",
            ).dropna()

            if valores_entidad.empty:
                continue

            valor = float(
                agregar(
                    valores_entidad,
                    columna.agregacion,
                )
            )

            metricas_resultado[columna.nombre] = valor

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"{columna.nombre_visible} de "
                        f"{etiqueta}"
                    ),
                    valor,
                    columna.unidad,
                    1,
                    (
                        f"{columna.agregacion} en el "
                        "último periodo válido"
                    ),
                    {
                        **contexto_base,
                        "metrica": columna.nombre,
                    },
                )
            )

            # ----------------------------------------------------------
            # Construcción de población a nivel de entidad.
            # ----------------------------------------------------------
            if base_poblacion.empty:
                continue

            valores_poblacion = (
                base_poblacion[
                    [entidad.nombre, columna.nombre]
                ]
                .copy()
            )

            valores_poblacion[columna.nombre] = pd.to_numeric(
                valores_poblacion[columna.nombre],
                errors="coerce",
            )

            valores_poblacion = valores_poblacion.dropna(
                subset=[columna.nombre]
            )

            if valores_poblacion.empty:
                continue

            poblacion_entidad = (
                valores_poblacion
                .groupby(
                    entidad.nombre,
                    sort=False,
                )[columna.nombre]
                .agg(
                    lambda serie: agregar(
                        serie,
                        columna.agregacion,
                    )
                )
                .dropna()
            )

            n_poblacion = int(
                poblacion_entidad.size
            )

            if n_poblacion == 0:
                continue

            mediana = float(
                poblacion_entidad.median()
            )

            percentil = float(
                (
                    poblacion_entidad <= valor
                ).mean()
                * 100
            )

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"Mediana poblacional de "
                        f"{columna.nombre_visible}"
                    ),
                    mediana,
                    columna.unidad,
                    n_poblacion,
                    (
                        "mediana de los valores agregados "
                        "por entidad en el último periodo válido"
                    ),
                    {
                        "metrica": columna.nombre,
                        "periodo": (
                            _simple(ultimo_periodo)
                            if ultimo_periodo is not None
                            else None
                        ),
                    },
                )
            )

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"Percentil de {etiqueta} en "
                        f"{columna.nombre_visible}"
                    ),
                    percentil,
                    "numero",
                    n_poblacion,
                    (
                        "proporción de entidades con valor "
                        "menor o igual, expresada en porcentaje"
                    ),
                    {
                        **contexto_base,
                        "metrica": columna.nombre,
                    },
                )
            )

        # --------------------------------------------------------------
        # Atributos relevantes: dimensiones y binarias.
        # --------------------------------------------------------------
        atributos: dict[str, Any] = {}

        for columna in (
            perfil.por_rol("dimension")
            + perfil.por_rol("binaria")
        ):
            if columna.nombre not in df_entidad.columns:
                continue

            valores = (
                df_entidad[columna.nombre]
                .dropna()
                .tolist()
            )

            if not valores:
                continue

            valor = _simple(valores[-1])

            atributos[columna.nombre] = valor

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"{columna.nombre_visible} de "
                        f"{etiqueta}"
                    ),
                    str(valor),
                    "texto",
                    1,
                    "valor reportado en el último periodo válido",
                    {
                        **contexto_base,
                        "atributo": columna.nombre,
                    },
                )
            )

        if not metricas_resultado and not atributos:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    f"No se encontraron métricas ni atributos "
                    f"válidos para la {perfil.entidad_singular}.",
                ),
            )

        datos_resultado = (
            {
                "entidad": identificador,
                "nombre": str(etiqueta),
                "periodo": (
                    _simple(ultimo_periodo)
                    if ultimo_periodo is not None
                    else None
                ),
                "metricas": {
                    nombre: round(float(valor), 6)
                    for nombre, valor in metricas_resultado.items()
                },
                "atributos": atributos,
            },
        )

        return ResultadoSkill(
            self.nombre,
            tuple(evidencias),
            datos_resultado,
            (),
        )


def _simple(valor: Any) -> Any:
    """Convierte escalares NumPy/Pandas a valores Python simples."""
    return (
        valor.item()
        if hasattr(valor, "item")
        else valor
    )


def _ultimo_valor(serie: pd.Series) -> Any:
    """Obtiene el último periodo de forma robusta."""
    valores = serie.dropna().unique()

    try:
        return max(valores)
    except TypeError:
        return max(
            valores,
            key=lambda valor: str(valor),
        )
