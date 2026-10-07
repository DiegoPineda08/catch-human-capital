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

    def ejecutar(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        p = datos.perfil
        met = columna_con_rol(p, parametros["metrica"], ("metrica", "binaria"))
        tiempo = p.una("tiempo")
        filtros = filtros_de(parametros)
        df = datos.filas(solo_validas=True, **filtros)
        df = df.dropna(subset=[met.nombre, tiempo.nombre])
        if df.empty:
            return ResultadoSkill(self.nombre, (), (), ("No hay datos para esos filtros.",))

        etiquetas = dict(datos.periodos())
        tabla = (df.groupby(tiempo.nombre)[met.nombre]
                 .agg(valor=lambda s: agregar(s, met.agregacion), n="count")
                 .reset_index().sort_values(tiempo.nombre))
        tabla["periodo"] = [etiquetas.get(v, str(v)) for v in tabla[tiempo.nombre]]

        ini, fin = tabla.iloc[0], tabla.iloc[-1]
        nombre, unidad = met.nombre_visible, met.unidad
        metodo = f"{met.agregacion} entre {p.entidad_plural} por periodo"
        ctx = {"metrica": met.nombre, **filtros}
        if len(tabla) == 1:                       # un solo periodo: no hay evolución que medir
            unico = crear_evidencia(self.nombre, f"{nombre.capitalize()} en {ini.periodo}", float(ini.valor),
                                    unidad, int(ini.n), metodo, {**ctx, "periodo": ini.periodo})
            return ResultadoSkill(self.nombre, (unico,), ({"periodo": ini.periodo, "orden": 0,
                                                           "valor": round(float(ini.valor), 6), "n": int(ini.n)},),
                                  ("Sólo hay un periodo con datos para estos filtros: no se puede medir un cambio.",))
        n_comun = int(min(ini.n, fin.n))
        unidad_cambio = "diferencia_proporcion" if unidad == "proporcion" else unidad

        evid = [
            crear_evidencia(self.nombre, f"{nombre.capitalize()} en {ini.periodo}", float(ini.valor), unidad,
                            int(ini.n), metodo, {**ctx, "periodo": ini.periodo}),
            crear_evidencia(self.nombre, f"{nombre.capitalize()} en {fin.periodo}", float(fin.valor), unidad,
                            int(fin.n), metodo, {**ctx, "periodo": fin.periodo}),
            crear_evidencia(self.nombre, f"Cambio absoluto de {nombre} ({ini.periodo} a {fin.periodo})",
                            float(fin.valor - ini.valor), unidad_cambio, n_comun, "valor final - valor inicial", ctx),
        ]
        if ini.valor:
            evid.append(crear_evidencia(self.nombre, f"Cambio relativo de {nombre}",
                                        float((fin.valor - ini.valor) / abs(ini.valor)), "cambio_relativo",
                                        n_comun, "(final - inicial) / |inicial|", ctx))
        alto, bajo = tabla.loc[tabla["valor"].idxmax()], tabla.loc[tabla["valor"].idxmin()]
        evid += [
            crear_evidencia(self.nombre, f"Periodo con el valor más alto de {nombre}", str(alto.periodo), "texto",
                            int(alto.n), "periodo con el valor máximo", ctx),
            crear_evidencia(self.nombre, f"Periodo con el valor más bajo de {nombre}", str(bajo.periodo), "texto",
                            int(bajo.n), "periodo con el valor mínimo", ctx),
        ]

        advertencias = []
        if p.tiene("entidad") and tabla["n"].min() < MIN_ENTIDADES:
            advertencias.append(f"Algún periodo tiene menos de {MIN_ENTIDADES} {p.entidad_plural}: "
                                "interpretar con cautela.")
        datos_grafico = tuple({"periodo": r.periodo, "orden": i, "valor": round(float(r.valor), 6), "n": int(r.n)}
                              for i, r in enumerate(tabla.itertuples()))
        return ResultadoSkill(self.nombre, tuple(evid), datos_grafico, tuple(advertencias))
