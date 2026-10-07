"""
Skill: evolución de una métrica a lo largo del tiempo. Funciona con cualquier base que
tenga una columna de "tiempo" y al menos una "metrica".

Sirve de PLANTILLA para escribir las demás Skills: copia este archivo y cambia el cálculo.
"""
from __future__ import annotations

from typing import Any

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill, agregar, columna_con_rol, filtros_de

MIN_ENTIDADES = 5


class Tendencia(Skill):
    nombre = "tendencia"
    descripcion = "Valor de una métrica en cada periodo y su cambio entre el primero y el último."
    intenciones = ("tendencia",)
    requiere = ("tiempo", "metrica")
    parametros = {
        "metrica": "Nombre de la columna (rol metrica)",
        "filtros": "Opcional: {columna: valor}, p.ej. {'region': 'Norte'}",
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
        tiempo = p.una("tiempo")
        entidad = p.una("entidad")
        filtros = filtros_de(parametros)

        df = datos.filas(
            solo_validas=True,
            **filtros,
        )
        df = df.dropna(subset=[met.nombre, tiempo.nombre])

        if df.empty:
            return ResultadoSkill(
                self.nombre,
                (),
                (),
                ("No hay datos para esos filtros.",),
            )

        etiquetas = dict(datos.periodos())

        if entidad is not None:
            # ----------------------------------------------------------
            # 1. Primero agregamos cada entidad dentro de cada periodo.
            #
            # Esto evita que una entidad con varias filas para el mismo
            # periodo tenga más peso que las demás.
            # ----------------------------------------------------------
            por_entidad_periodo = (
                df.groupby(
                    [entidad.nombre, tiempo.nombre],
                    sort=False,
                    dropna=False,
                )[met.nombre]
                .agg(
                    lambda serie: agregar(
                        serie,
                        met.agregacion,
                    )
                )
                .rename("valor")
                .reset_index()
            )

            # ----------------------------------------------------------
            # 2. Después agregamos las entidades dentro de cada periodo.
            # ----------------------------------------------------------
            tabla = (
                por_entidad_periodo.groupby(
                    tiempo.nombre,
                    sort=False,
                    dropna=False,
                )["valor"]
                .agg(
                    lambda serie: agregar(
                        serie,
                        met.agregacion,
                    )
                )
                .rename("valor")
                .reset_index()
            )

            # n = número de entidades distintas con dato en cada periodo.
            conteo_entidades = (
                por_entidad_periodo.groupby(
                    tiempo.nombre,
                    sort=False,
                )[entidad.nombre]
                .nunique()
                .rename("n")
                .reset_index()
            )

            tabla = tabla.merge(
                conteo_entidades,
                on=tiempo.nombre,
                how="left",
            )
        else:
            # Sin entidad, n representa observaciones válidas del periodo.
            tabla = (
                df.groupby(
                    tiempo.nombre,
                    sort=False,
                    dropna=False,
                )[met.nombre]
                .agg(
                    valor=lambda serie: agregar(
                        serie,
                        met.agregacion,
                    ),
                    n="count",
                )
                .reset_index()
            )

        tabla = tabla.sort_values(
            tiempo.nombre,
            kind="mergesort",
        ).reset_index(drop=True)

        tabla["n"] = tabla["n"].astype(int)
        tabla["periodo"] = [
            etiquetas.get(v, str(v))
            for v in tabla[tiempo.nombre]
        ]

        ini = tabla.iloc[0]
        fin = tabla.iloc[-1]

        nombre = met.nombre_visible
        unidad = met.unidad

        metodo = (
            f"{met.agregacion} entre {p.entidad_plural} por periodo"
            if entidad is not None
            else f"{met.agregacion} de las observaciones por periodo"
        )

        ctx = {
            "metrica": met.nombre,
            **filtros,
        }

        if len(tabla) == 1:
            unico = crear_evidencia(
                self.nombre,
                f"{nombre.capitalize()} en {ini.periodo}",
                float(ini.valor),
                unidad,
                int(ini.n),
                metodo,
                {
                    **ctx,
                    "periodo": ini.periodo,
                },
            )

            return ResultadoSkill(
                self.nombre,
                (unico,),
                (
                    {
                        "periodo": ini.periodo,
                        "orden": 0,
                        "valor": round(float(ini.valor), 6),
                        "n": int(ini.n),
                    },
                ),
                (
                    "Sólo hay un periodo con datos para estos filtros: "
                    "no se puede medir un cambio.",
                ),
            )

        n_comun = int(min(ini.n, fin.n))

        unidad_cambio = (
            "diferencia_proporcion"
            if unidad == "proporcion"
            else unidad
        )

        evid = [
            crear_evidencia(
                self.nombre,
                f"{nombre.capitalize()} en {ini.periodo}",
                float(ini.valor),
                unidad,
                int(ini.n),
                metodo,
                {
                    **ctx,
                    "periodo": ini.periodo,
                },
            ),
            crear_evidencia(
                self.nombre,
                f"{nombre.capitalize()} en {fin.periodo}",
                float(fin.valor),
                unidad,
                int(fin.n),
                metodo,
                {
                    **ctx,
                    "periodo": fin.periodo,
                },
            ),
            crear_evidencia(
                self.nombre,
                f"Cambio absoluto de {nombre} ({ini.periodo} a {fin.periodo})",
                float(fin.valor - ini.valor),
                unidad_cambio,
                n_comun,
                "valor final - valor inicial",
                ctx,
            ),
        ]

        if ini.valor:
            evid.append(
                crear_evidencia(
                    self.nombre,
                    f"Cambio relativo de {nombre}",
                    float(
                        (fin.valor - ini.valor)
                        / abs(ini.valor)
                    ),
                    "cambio_relativo",
                    n_comun,
                    "(final - inicial) / |inicial|",
                    ctx,
                )
            )

        alto = tabla.loc[tabla["valor"].idxmax()]
        bajo = tabla.loc[tabla["valor"].idxmin()]

        evid += [
            crear_evidencia(
                self.nombre,
                f"Periodo con el valor más alto de {nombre}",
                str(alto.periodo),
                "texto",
                int(alto.n),
                "periodo con el valor máximo",
                ctx,
            ),
            crear_evidencia(
                self.nombre,
                f"Periodo con el valor más bajo de {nombre}",
                str(bajo.periodo),
                "texto",
                int(bajo.n),
                "periodo con el valor mínimo",
                ctx,
            ),
        ]

        advertencias = []

        if entidad is not None and tabla["n"].min() < MIN_ENTIDADES:
            advertencias.append(
                f"Algún periodo tiene menos de {MIN_ENTIDADES} "
                f"{p.entidad_plural}: interpretar con cautela."
            )

        datos_grafico = tuple(
            {
                "periodo": fila.periodo,
                "orden": i,
                "valor": round(float(fila.valor), 6),
                "n": int(fila.n),
            }
            for i, fila in enumerate(tabla.itertuples())
        )

        return ResultadoSkill(
            self.nombre,
            tuple(evid),
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


def _ultimo_valor(serie):
    """Obtiene el último periodo de forma robusta."""
    valores = serie.dropna().unique()

    try:
        return max(valores)
    except TypeError:
        return max(
            valores,
            key=lambda valor: str(valor),
        )
