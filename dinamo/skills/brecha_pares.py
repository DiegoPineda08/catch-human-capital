"""
Skill para comparar una entidad con la mediana de sus pares.

La Skill es genérica:
- no conoce nombres específicos de Catch;
- recibe explícitamente las dimensiones que definen el grupo de pares;
- trabaja en un único periodo;
- agrega primero al nivel entidad-periodo;
- calcula después la mediana entre entidades pares;
- devuelve únicamente datos estructurados, Evidence y advertencias.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, columna_con_rol, filtros_de


class BrechaPares(Skill):
    nombre = "brecha_pares"
    descripcion = (
        "Compara una entidad con la mediana de las entidades que comparten "
        "las dimensiones definidas como grupo de pares."
    )
    intenciones = ()
    requiere = ("entidad", "metrica", "tiempo")
    parametros = {
        "metrica": "Nombre de la columna (rol metrica o binaria)",
        "entidad_objetivo": "Identificador de la entidad que se quiere comparar",
        "dimensiones_pares": (
            "Lista de nombres de columnas con rol dimension que definen "
            "el grupo de pares"
        ),
        "periodo": "Periodo específico; por defecto se usa el último periodo válido",
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica", "entidad_objetivo", "dimensiones_pares")

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
        entidad = perfil.una("entidad")
        tiempo = perfil.una("tiempo")

        dimensiones = parametros["dimensiones_pares"]

        if not isinstance(dimensiones, (list, tuple)) or not dimensiones:
            raise ValueError(
                "dimensiones_pares debe ser una lista o tupla no vacía."
            )

        dimensiones = tuple(dimensiones)

        for nombre in dimensiones:
            columna_con_rol(
                perfil,
                nombre,
                ("dimension",),
            )

        periodo_solicitado = parametros.get("periodo")
        filtros = filtros_de(parametros)

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).copy()

        columnas_necesarias = [
            entidad.nombre,
            tiempo.nombre,
            met.nombre,
            *dimensiones,
        ]

        df = df.dropna(subset=columnas_necesarias)

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos válidos para esos filtros y dimensiones.",),
            )

        if periodo_solicitado is None:
            periodo = df[tiempo.nombre].max()
        else:
            periodo = periodo_solicitado

        df = df[df[tiempo.nombre] == periodo].copy()

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos para el periodo seleccionado.",),
            )

        entidad_periodo = (
            df.groupby(
                [entidad.nombre, *dimensiones],
                sort=False,
                dropna=False,
            )[met.nombre]
            .agg(
                valor=lambda serie: agregar(
                    serie,
                    met.agregacion,
                )
            )
            .reset_index()
        )

        if entidad_periodo.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No fue posible construir valores por entidad.",),
            )

        objetivo = entidad_periodo[
            entidad_periodo[entidad.nombre]
            == parametros["entidad_objetivo"]
        ].copy()

        if objetivo.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "La entidad objetivo no tiene un valor válido "
                    "en el periodo seleccionado.",
                ),
            )

        combinaciones = objetivo[list(dimensiones)].drop_duplicates()

        if len(combinaciones) != 1:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "La entidad objetivo tiene más de una combinación "
                    "de dimensiones de pares en el periodo seleccionado.",
                ),
            )

        valores_objetivo = combinaciones.iloc[0].to_dict()

        mascara_pares = pd.Series(
            True,
            index=entidad_periodo.index,
        )

        for dimension in dimensiones:
            mascara_pares &= (
                entidad_periodo[dimension]
                == valores_objetivo[dimension]
            )

        pares = entidad_periodo[
            mascara_pares
            & (
                entidad_periodo[entidad.nombre]
                != parametros["entidad_objetivo"]
            )
        ].copy()

        valor_entidad = float(objetivo["valor"].iloc[0])
        n_pares = int(len(pares))

        if n_pares == 0:
            return ResultadoSkill(
                self.nombre,
                (),
                (
                    {
                        "entidad": _simple(
                            parametros["entidad_objetivo"]
                        ),
                        "periodo": _simple(periodo),
                        "valor_entidad": valor_entidad,
                        "mediana_pares": None,
                        "brecha": None,
                        "n_pares": 0,
                        "dimensiones_pares": {
                            k: _simple(v)
                            for k, v in valores_objetivo.items()
                        },
                    },
                ),
                (
                    "No existen otras entidades con la misma combinación "
                    "de dimensiones de pares en el periodo seleccionado.",
                ),
            )

        advertencias = []

        if n_pares == 1:
            advertencias.append(
                "El grupo de pares contiene solo 1 entidad."
            )

        mediana_pares = float(pares["valor"].median())

        brecha = valor_entidad - mediana_pares

        contexto = {
            "metrica": met.nombre,
            "periodo": _simple(periodo),
            **{
                nombre: _simple(valor)
                for nombre, valor in valores_objetivo.items()
            },
            **filtros,
        }

        evidencias = (
            crear_evidencia(
                self.nombre,
                f"Valor de la entidad objetivo para {met.nombre}",
                valor_entidad,
                met.unidad,
                1,
                "Agregación de la métrica al nivel de entidad en el periodo seleccionado",
                {
                    **contexto,
                    entidad.nombre: _simple(
                        parametros["entidad_objetivo"]
                    ),
                },
            ),
            crear_evidencia(
                self.nombre,
                f"Mediana de {met.nombre} de las entidades pares",
                mediana_pares,
                met.unidad,
                n_pares,
                "Mediana de los valores agregados por entidad entre los pares",
                contexto,
            ),
            crear_evidencia(
                self.nombre,
                f"Brecha de la entidad respecto a la mediana de pares para {met.nombre}",
                brecha,
                met.unidad,
                n_pares,
                "Valor de la entidad menos mediana de sus entidades pares",
                {
                    **contexto,
                    entidad.nombre: _simple(
                        parametros["entidad_objetivo"]
                    ),
                },
            ),
        )

        registro = {
            "entidad": _simple(
                parametros["entidad_objetivo"]
            ),
            "periodo": _simple(periodo),
            "valor_entidad": valor_entidad,
            "mediana_pares": mediana_pares,
            "brecha": brecha,
            "n_pares": n_pares,
            "dimensiones_pares": {
                k: _simple(v)
                for k, v in valores_objetivo.items()
            },
        }

        return ResultadoSkill(
            self.nombre,
            evidencias,
            (registro,),
            tuple(advertencias),
        )


def _simple(valor: Any) -> Any:
    """Convierte escalares de pandas/numpy a tipos simples."""
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except (ValueError, TypeError):
            pass
    return valor
