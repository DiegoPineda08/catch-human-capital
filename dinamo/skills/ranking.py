"""Skill: entidades con el valor más alto (o más bajo) de una métrica. Funciona con cualquier base."""
from __future__ import annotations

from typing import Any

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, columna_con_rol, filtros_de


class Ranking(Skill):
    nombre = "ranking"
    descripcion = (
        "Ordena las entidades según la agregación declarada para la métrica "
        "sobre sus periodos con dato real."
    )
    intenciones = ("ranking",)
    requiere = ("entidad", "metrica")
    parametros = {
        "metrica": "Nombre de la columna (rol metrica)",
        "orden": "'desc' = mayores primero (por defecto) | 'asc' = menores primero",
        "n": "Cuántas entidades mostrar (5)",
        "min_periodos": "Mínimo de periodos con dato para entrar al ranking (por defecto 3 si hay tiempo)",
        "filtros": "Opcional: {columna: valor}",
    }
    requeridos = ("metrica",)

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: dict[str, Any],
    ) -> ResultadoSkill:
        p = datos.perfil

        met = columna_con_rol(
            p,
            parametros["metrica"],
            ("metrica", "binaria"),
        )
        ent = p.una("entidad")
        nom = p.una("nombre_entidad")
        tiempo = p.una("tiempo")

        asc = parametros.get("orden", "desc") == "asc"
        n = int(parametros.get("n", 5))
        filtros = filtros_de(parametros)

        df = datos.filas(
            solo_validas=True,
            **filtros,
        ).dropna(subset=[met.nombre, ent.nombre])

        if tiempo is not None:
            df = df.dropna(subset=[tiempo.nombre])

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos para esos filtros.",),
            )

        if tiempo is not None:
            n_periodos = int(
                df[tiempo.nombre].nunique()
            )
        else:
            n_periodos = 0

        min_periodos = int(
            parametros.get(
                "min_periodos",
                min(3, n_periodos) if n_periodos else 1,
            )
        )

        if tiempo is not None:
            # Primero se elimina la posible inflación causada por varias
            # filas de una misma entidad en el mismo periodo.
            por_entidad_periodo = (
                df.groupby(
                    [ent.nombre, tiempo.nombre],
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

            # Después se comparan las entidades a partir de la agregación
            # declarada en el perfil sobre sus periodos disponibles.
            por_ent = (
                por_entidad_periodo.groupby(
                    ent.nombre,
                    sort=False,
                )["valor"]
                .agg(
                    valor=lambda serie: agregar(
                        serie,
                        met.agregacion,
                    )
                )
                .reset_index()
            )

            periodos_por_entidad = (
                por_entidad_periodo.groupby(
                    ent.nombre,
                    sort=False,
                )[tiempo.nombre]
                .nunique()
                .rename("periodos")
                .reset_index()
            )

            por_ent = por_ent.merge(
                periodos_por_entidad,
                on=ent.nombre,
                how="left",
            )
        else:
            por_ent = (
                df.groupby(
                    ent.nombre,
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

            periodos_por_entidad = (
                df.groupby(
                    ent.nombre,
                    sort=False,
                )[met.nombre]
                .count()
                .rename("periodos")
                .reset_index()
            )

            por_ent = por_ent.merge(
                periodos_por_entidad,
                on=ent.nombre,
                how="left",
            )

        excluidas = int(
            (por_ent["periodos"] < min_periodos).sum()
        )

        elegibles = por_ent[
            por_ent["periodos"] >= min_periodos
        ]

        if elegibles.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                (
                    f"Ninguna {p.entidad_singular} tiene {min_periodos} "
                    "periodos con dato.",
                ),
            )

        elegibles = elegibles.sort_values(
            ["valor", ent.nombre],
            ascending=[asc, True],
        )

        top = elegibles.head(n)

        nombre = met.nombre_visible
        orden_txt = "menor" if asc else "mayor"

        ctx = {
            "metrica": met.nombre,
            "orden": "asc" if asc else "desc",
            **filtros,
        }

        if tiempo is not None:
            if n_periodos > 1:
                metodo = (
                    f"{met.agregacion} de los valores por periodo, "
                    "después de agregarlos al nivel entidad-periodo"
                )
            else:
                metodo = (
                    f"{met.agregacion} del valor al nivel entidad-periodo"
                )
        else:
            metodo = (
                f"{met.agregacion} de los valores por "
                f"{p.entidad_singular}"
            )

        if nom is not None:
            nombres_entidad = (
                df.dropna(subset=[nom.nombre])
                .groupby(
                    ent.nombre,
                    sort=False,
                )[nom.nombre]
                .first()
                .to_dict()
            )
        else:
            nombres_entidad = {}

        evid = []

        for pos, r in enumerate(
            top.itertuples(),
            start=1,
        ):
            entidad_id = getattr(r, ent.nombre)

            etiqueta = (
                nombres_entidad.get(
                    entidad_id,
                    f"{p.entidad_singular} {entidad_id}",
                )
                if nom is not None
                else f"{p.entidad_singular} {entidad_id}"
            )

            evid.append(
                crear_evidencia(
                    self.nombre,
                    f"Puesto {pos} ({orden_txt} {nombre}): {etiqueta}",
                    float(r.valor),
                    met.unidad,
                    int(r.periodos),
                    metodo,
                    {
                        **ctx,
                        ent.nombre: _simple(entidad_id),
                    },
                )
            )

        evid.append(
            crear_evidencia(
                self.nombre,
                f"Mediana de {nombre} en el conjunto de {p.entidad_plural}",
                float(elegibles["valor"].median()),
                met.unidad,
                len(elegibles),
                f"mediana de los valores agregados por {p.entidad_singular}",
                ctx,
            )
        )

        advertencias = []

        if excluidas:
            advertencias.append(
                f"{excluidas} {p.entidad_plural} quedaron fuera por tener menos de "
                f"{min_periodos} periodos con dato."
            )

        datos_grafico = tuple(
            {
                "entidad": _simple(
                    getattr(r, ent.nombre)
                ),
                "nombre": str(
                    nombres_entidad.get(
                        getattr(r, ent.nombre),
                        getattr(r, ent.nombre),
                    )
                ),
                "valor": round(
                    float(r.valor),
                    6,
                ),
                "periodos": int(r.periodos),
            }
            for r in top.itertuples()
        )

        return ResultadoSkill(
            self.nombre,
            tuple(evid),
            datos_grafico,
            tuple(advertencias),
        )


def _simple(v):
    return v.item() if hasattr(v, "item") else v
