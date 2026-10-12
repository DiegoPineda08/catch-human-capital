"""Skill genérica para medir asociaciones entre una métrica y otras variables."""

from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, columna_con_rol, filtros_de


class Relaciones(Skill):
    """Calcula correlaciones de Spearman a nivel de entidad."""

    nombre = "relaciones"
    descripcion = (
        "Mide la asociación de una métrica con otras variables "
        "numéricas mediante correlación de Spearman a nivel de entidad."
    )
    intenciones = ("relaciones",)
    requiere = ("entidad", "metrica")
    parametros = {
        "metrica": "Nombre de la métrica objetivo",
        "dimension": "Opcional; se conserva para compatibilidad con Brain",
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica",)

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: dict[str, Any],
    ) -> ResultadoSkill:
        perfil = datos.perfil

        objetivo = columna_con_rol(
            perfil,
            parametros["metrica"],
            ("metrica", "binaria"),
        )

        entidad = perfil.una("entidad")
        filtros = filtros_de(parametros)

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).copy()

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos para calcular relaciones.",),
            )

        columnas = [
            objetivo.nombre,
            entidad.nombre,
        ]

        df = df.dropna(subset=columnas)

        # --------------------------------------------------------------
        # Variables candidatas provenientes del Perfil.
        # No se codifican nombres específicos de ninguna base.
        # --------------------------------------------------------------
        candidatas = []

        for columna in (
            perfil.por_rol("metrica")
            + perfil.por_rol("binaria")
        ):
            if columna.nombre == objetivo.nombre:
                continue

            # Una variable que describe directamente el objetivo no se
            # trata como driver independiente.
            if columna.describe_a in {
                objetivo.nombre,
                objetivo.etiqueta,
            }:
                continue

            if columna.nombre not in df.columns:
                continue

            if columna not in candidatas:
                candidatas.append(columna)

        if not candidatas:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "No hay otras variables numéricas "
                    "adecuadas para calcular relaciones.",
                ),
            )

        # --------------------------------------------------------------
        # Agregación al nivel de entidad.
        # Esto evita que una entidad con muchos periodos tenga mayor
        # peso que otra simplemente por reportar más observaciones.
        # --------------------------------------------------------------
        por_entidad = (
            df.groupby(
                entidad.nombre,
                sort=False,
                dropna=False,
            )
        )

        objetivo_entidad = por_entidad[objetivo.nombre].agg(
            lambda serie: agregar(
                serie,
                objetivo.agregacion,
            )
        ).rename("objetivo")

        resultados = []
        evidencias = []
        advertencias: list[str] = []

        for candidata in candidatas:
            candidato_entidad = por_entidad[
                candidata.nombre
            ].agg(
                lambda serie: agregar(
                    serie,
                    candidata.agregacion,
                )
            ).rename("candidato")

            pares = pd.concat(
                [
                    objetivo_entidad,
                    candidato_entidad,
                ],
                axis=1,
            ).dropna()

            # Spearman necesita al menos dos pares y variación en ambas
            # variables para producir una asociación definida.
            n = int(len(pares))

            if n < 2:
                continue

            if (
                pares["objetivo"].nunique() < 2
                or pares["candidato"].nunique() < 2
            ):
                continue

            rho = float(
                pares["objetivo"].corr(
                    pares["candidato"],
                    method="spearman",
                )
            )

            if pd.isna(rho):
                continue

            resultados.append(
                {
                    "variable": candidata.nombre,
                    "nombre": candidata.nombre_visible,
                    "rho": round(rho, 6),
                    "abs_rho": round(abs(rho), 6),
                    "n": n,
                }
            )

        if not resultados:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "No fue posible calcular una correlación "
                    "de Spearman válida con las variables disponibles.",
                ),
            )

        # Primero fuerza absoluta de asociación y después nombre de
        # variable para que los empates sean deterministas.
        resultados.sort(
            key=lambda registro: (
                -registro["abs_rho"],
                registro["variable"],
            )
        )

        contexto = {
            "metrica": objetivo.nombre,
            **filtros,
        }

        for registro in resultados:
            descripcion = (
                f"Relación entre {objetivo.nombre_visible} y "
                f"{registro['nombre']}"
            )

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    descripcion,
                    registro["rho"],
                    "rho",
                    registro["n"],
                    "correlación de Spearman a nivel de entidad",
                    {
                        **contexto,
                        "variable": registro["variable"],
                    },
                )
            )

        datos = tuple(
            {
                "variable": registro["variable"],
                "nombre": registro["nombre"],
                "rho": registro["rho"],
                "abs_rho": registro["abs_rho"],
                "n": registro["n"],
            }
            for registro in resultados
        )

        return ResultadoSkill(
            self.nombre,
            tuple(evidencias),
            datos,
            tuple(advertencias),
        )
