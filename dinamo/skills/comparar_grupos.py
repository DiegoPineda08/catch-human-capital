"""Skill genérica para comparar una métrica entre grupos de una dimensión."""

from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, columna_con_rol, filtros_de


MIN_GRUPO = 10


class CompararGrupos(Skill):
    """Compara una métrica entre grupos definidos por una dimensión."""

    nombre = "comparar_grupos"
    descripcion = (
        "Compara una métrica entre grupos mediante agregación "
        "a nivel de entidad y resumen por grupo."
    )
    intenciones = ("comparar_grupos",)
    requiere = ("entidad", "metrica", "dimension")
    parametros = {
        "metrica": "Nombre de la columna con rol metrica",
        "dimension": (
            "Nombre de la columna con rol dimension o binaria"
        ),
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica", "dimension")

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

        grupo = columna_con_rol(
            perfil,
            parametros["dimension"],
            ("dimension", "binaria"),
        )

        entidad = perfil.una("entidad")

        filtros = filtros_de(parametros)

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).copy()

        columnas_necesarias = [
            entidad.nombre,
            grupo.nombre,
            met.nombre,
        ]

        df = df.dropna(
            subset=columnas_necesarias,
        )

        df[met.nombre] = pd.to_numeric(
            df[met.nombre],
            errors="coerce",
        )

        df = df.dropna(
            subset=[met.nombre],
        )

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "No hay datos válidos para comparar "
                    "los grupos.",
                ),
            )

        # --------------------------------------------------------------
        # 1. Resumir primero a nivel de entidad.
        #
        # Así una entidad con varios periodos no tiene más peso
        # simplemente por aparecer más veces.
        # --------------------------------------------------------------
        por_entidad = (
            df.groupby(
                [entidad.nombre, grupo.nombre],
                sort=False,
                dropna=False,
            )[met.nombre]
            .agg(
                valor=lambda serie: agregar(
                    serie,
                    met.agregacion,
                ),
            )
            .reset_index()
        )

        if por_entidad.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "No hay entidades válidas para "
                    "comparar los grupos.",
                ),
            )

        # --------------------------------------------------------------
        # 2. Resumir las entidades dentro de cada grupo.
        #
        # La guía de comparación utiliza la mediana de los valores
        # agregados a nivel de entidad.
        # --------------------------------------------------------------
        por_grupo = (
            por_entidad.groupby(
                grupo.nombre,
                sort=False,
                dropna=False,
            )["valor"]
            .agg(
                valor="median",
                n="count",
            )
            .reset_index()
        )

        if por_grupo.shape[0] < 2:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    "Se necesitan al menos dos grupos "
                    "con datos válidos para realizar "
                    "la comparación.",
                ),
            )

        por_grupo["_clave"] = por_grupo[
            grupo.nombre
        ].map(_clave_determinista)

        por_grupo = por_grupo.sort_values(
            "_clave",
            kind="mergesort",
        ).reset_index(drop=True)

        nombre_metrica = met.nombre_visible
        nombre_grupo = grupo.nombre_visible

        contexto = {
            "metrica": met.nombre,
            "dimension": grupo.nombre,
            **filtros,
        }

        evidencias = []

        # --------------------------------------------------------------
        # 3. Evidence individual de cada grupo.
        # --------------------------------------------------------------
        for fila in por_grupo.itertuples():
            categoria = getattr(
                fila,
                grupo.nombre,
            )

            valor = float(fila.valor)
            n = int(fila.n)

            evidencias.append(
                crear_evidencia(
                    self.nombre,
                    (
                        f"Mediana de {nombre_metrica} "
                        f"en {nombre_grupo}={categoria}"
                    ),
                    valor,
                    met.unidad,
                    n,
                    (
                        "mediana de los valores "
                        "agregados por entidad"
                    ),
                    {
                        **contexto,
                        "grupo": _simple(categoria),
                    },
                )
            )

        # --------------------------------------------------------------
        # 4. Identificar los grupos extremos.
        #
        # Para dos grupos equivale directamente a su diferencia.
        # Con más grupos, compara la mediana mayor contra la menor.
        # --------------------------------------------------------------
        grupo_menor = por_grupo.loc[
            por_grupo["valor"].idxmin()
        ]

        grupo_mayor = por_grupo.loc[
            por_grupo["valor"].idxmax()
        ]

        valor_menor = float(
            grupo_menor["valor"]
        )
        valor_mayor = float(
            grupo_mayor["valor"]
        )

        categoria_menor = grupo_menor[
            grupo.nombre
        ]
        categoria_mayor = grupo_mayor[
            grupo.nombre
        ]

        diferencia = valor_mayor - valor_menor

        unidad_diferencia = (
            "diferencia_proporcion"
            if met.unidad == "proporcion"
            else met.unidad
        )

        n_comparacion = int(
            grupo_menor["n"] + grupo_mayor["n"]
        )

        evidencias.append(
            crear_evidencia(
                self.nombre,
                (
                    f"Diferencia entre la mediana de "
                    f"{nombre_metrica} de "
                    f"{categoria_mayor} y {categoria_menor}"
                ),
                diferencia,
                unidad_diferencia,
                n_comparacion,
                "mediana del grupo mayor - mediana del grupo menor",
                {
                    **contexto,
                    "grupo_mayor": _simple(categoria_mayor),
                    "grupo_menor": _simple(categoria_menor),
                },
            )
        )

        # --------------------------------------------------------------
        # 5. Datos estructurados para visualización.
        # --------------------------------------------------------------
        datos_grafico = tuple(
            {
                "grupo": _simple(
                    getattr(fila, grupo.nombre)
                ),
                "valor": round(
                    float(fila.valor),
                    6,
                ),
                "n": int(fila.n),
            }
            for fila in por_grupo.itertuples()
        )

        # --------------------------------------------------------------
        # 6. Advertencias por tamaño de grupo.
        # --------------------------------------------------------------
        advertencias = []

        grupos_pequenos = por_grupo[
            por_grupo["n"] < MIN_GRUPO
        ]

        if not grupos_pequenos.empty:
            nombres = ", ".join(
                str(valor)
                for valor in grupos_pequenos[
                    grupo.nombre
                ].tolist()
            )

            advertencias.append(
                (
                    f"Los grupos {nombres} tienen menos de "
                    f"{MIN_GRUPO} {perfil.entidad_plural}; "
                    "interpretar la comparación con cautela."
                )
            )

        return ResultadoSkill(
            self.nombre,
            tuple(evidencias),
            datos_grafico,
            tuple(advertencias),
        )


def _simple(valor: Any) -> Any:
    """Convierte escalares NumPy/Pandas a valores Python simples."""
    return (
        valor.item()
        if hasattr(valor, "item")
        else valor
    )


def _clave_determinista(valor: Any) -> tuple[str, str]:
    """Genera una clave estable para ordenar categorías."""
    return (
        type(valor).__name__,
        str(valor),
    )