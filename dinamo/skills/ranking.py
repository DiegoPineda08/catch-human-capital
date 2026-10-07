"""Skill: entidades con el valor más alto (o más bajo) de una métrica. Funciona con cualquier base."""
from __future__ import annotations

from typing import Any

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, columna_con_rol, filtros_de


class Ranking(Skill):
    nombre = "ranking"
    descripcion = "Ordena las entidades por el promedio de una métrica en sus periodos con dato real."
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

    def ejecutar(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
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
        ).dropna(subset=[met.nombre])

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
            n_periodos = int(df[tiempo.nombre].nunique())
        else:
            n_periodos = 0

        min_periodos = int(
            parametros.get(
                "min_periodos",
                min(3, n_periodos) if n_periodos else 1,
            )
        )

        claves = [ent.nombre] + ([nom.nombre] if nom else [])

        por_ent = (
            df.groupby(claves)[met.nombre]
            .agg(valor="mean")
            .reset_index()
        )

        if tiempo is not None:
            periodos_por_entidad = (
                df.groupby(claves)[tiempo.nombre]
                .nunique()
                .rename("periodos")
                .reset_index()
            )

            por_ent = por_ent.merge(
                periodos_por_entidad,
                on=claves,
                how="left",
            )
        else:
            por_ent["periodos"] = df.groupby(claves)[met.nombre].count().to_numpy()

        excluidas = int((por_ent["periodos"] < min_periodos).sum())
        elegibles = por_ent[por_ent["periodos"] >= min_periodos]

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

        metodo = (
            "promedio de los periodos con dato real"
            if n_periodos > 1
            else "valor del periodo"
            if n_periodos == 1
            else "valor de la fila"
        )

        evid = []

        for pos, r in enumerate(top.itertuples(), start=1):
            etiqueta = (
                getattr(r, nom.nombre)
                if nom
                else f"{p.entidad_singular} {getattr(r, ent.nombre)}"
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
                        ent.nombre: _simple(getattr(r, ent.nombre)),
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
                f"mediana de los promedios por {p.entidad_singular}",
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
                "entidad": _simple(getattr(r, ent.nombre)),
                "nombre": (
                    str(getattr(r, nom.nombre))
                    if nom
                    else str(getattr(r, ent.nombre))
                ),
                "valor": round(float(r.valor), 6),
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
