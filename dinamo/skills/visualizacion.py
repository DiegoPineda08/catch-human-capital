"""
Skills de VISUALIZACIÓN: preparan los datos exactos que necesita un gráfico pedido explícitamente.

  histograma  reparte una métrica en intervalos de igual ancho (regla de Sturges) y cuenta observaciones.
  dispersion  pares (x, y) a nivel de entidad + correlación de Spearman como Evidencia (asociación, no causa).

Agregan primero a nivel de entidad cuando la base tiene entidad y varios periodos (una entidad = un punto).
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import ParametroInvalido, Skill, agregar, columna_con_rol, filtros_de


def _por_entidad(datos: DataEngine, df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    ent = datos.perfil.una("entidad")
    if ent is None or not df[ent.nombre].duplicated().any():
        return df
    aggs = {c: (lambda s, c=c: agregar(s, datos.perfil.columna(c).agregacion)) for c in columnas}
    return df.groupby(ent.nombre, sort=True).agg(aggs).reset_index()


def _corto(x: float) -> str:
    """Etiqueta legible de un límite de intervalo: 13470 -> '13,470'; 0.0345 -> '0.0345'."""
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"


class Histograma(Skill):
    nombre = "histograma"
    descripcion = "Cuenta cuántas observaciones caen en cada intervalo de una métrica."
    intenciones = ()
    requiere = ("metrica",)
    parametros = {"metrica": "Columna numérica", "intervalos": "Número de intervalos (opcional)", "filtros": "Opcional"}
    requeridos = ("metrica",)

    def ejecutar(self, datos: DataEngine, p: dict[str, Any]) -> ResultadoSkill:
        met = columna_con_rol(datos.perfil, p["metrica"], ("metrica",))
        filtros = filtros_de(p)
        df = datos.filas(solo_validas=True, **filtros)
        df = _por_entidad(datos, df.dropna(subset=[met.nombre]), [met.nombre])
        v = pd.to_numeric(df[met.nombre], errors="coerce").dropna().astype(float)
        if len(v) < 5:
            return ResultadoSkill(self.nombre, (), (), ("Hay menos de 5 observaciones: no tiene sentido un histograma.",))
        k = int(p.get("intervalos") or min(20, max(5, math.ceil(math.log2(len(v)) + 1))))
        lo, hi = float(v.min()), float(v.max())
        ancho = (hi - lo) / k if hi > lo else 1.0
        cubos = []
        for i in range(k):
            desde, hasta = lo + i * ancho, lo + (i + 1) * ancho
            dentro = (v >= desde) & ((v < hasta) if i < k - 1 else (v <= hasta))
            cubos.append({"rango": f"{_corto(desde)}–{_corto(hasta)}", "desde": round(desde, 6), "hasta": round(hasta, 6),
                          "conteo": int(dentro.sum())})
        fuente = {"metrica": met.nombre, **filtros}
        evid = (crear_evidencia(self.nombre, f"Observaciones de {met.nombre_visible} en el histograma", len(v), "conteo",
                                len(v), f"{k} intervalos de igual ancho (regla de Sturges)", fuente),
                crear_evidencia(self.nombre, f"Mínimo de {met.nombre_visible}", lo, met.unidad, len(v), "mínimo", fuente),
                crear_evidencia(self.nombre, f"Máximo de {met.nombre_visible}", hi, met.unidad, len(v), "máximo", fuente))
        return ResultadoSkill(self.nombre, evid, tuple(cubos), ())


class Dispersion(Skill):
    nombre = "dispersion"
    descripcion = "Pares (x, y) por entidad para un gráfico de dispersión, con la correlación de Spearman."
    intenciones = ()
    requiere = ("metrica",)
    parametros = {"metrica_x": "Columna del eje X", "metrica_y": "Columna del eje Y", "filtros": "Opcional"}
    requeridos = ("metrica_x", "metrica_y")

    def ejecutar(self, datos: DataEngine, p: dict[str, Any]) -> ResultadoSkill:
        from scipy.stats import spearmanr
        cx = columna_con_rol(datos.perfil, p["metrica_x"], ("metrica", "binaria"))
        cy = columna_con_rol(datos.perfil, p["metrica_y"], ("metrica", "binaria"))
        if cx.nombre == cy.nombre:
            raise ParametroInvalido("dispersion: los ejes X e Y deben ser columnas distintas.")
        filtros = filtros_de(p)
        df = datos.filas(solo_validas=True, **filtros).dropna(subset=[cx.nombre, cy.nombre])
        df = _por_entidad(datos, df, [cx.nombre, cy.nombre])
        ent = datos.perfil.una("entidad")
        pares = [{"entidad": (r[ent.nombre].item() if hasattr(r[ent.nombre], "item") else r[ent.nombre]) if ent else i,
                  "x": float(r[cx.nombre]), "y": float(r[cy.nombre]),
                  "eje_x": cx.nombre_visible, "eje_y": cy.nombre_visible} for i, r in df.iterrows()]
        adv = []
        evid = ()
        if len(pares) >= 5:
            rho, pval = spearmanr(df[cx.nombre], df[cy.nombre])
            if not math.isnan(rho):
                evid = (crear_evidencia(self.nombre, f"Correlación de Spearman entre {cx.nombre_visible} y {cy.nombre_visible}",
                                        round(float(rho), 6), "rho", len(pares),
                                        f"Spearman a nivel de {datos.perfil.entidad_singular}; p={pval:.3g}; asociación, no causalidad",
                                        {"x": cx.nombre, "y": cy.nombre, **filtros}),)
        else:
            adv.append("Menos de 5 puntos: no se calcula la correlación.")
        return ResultadoSkill(self.nombre, evid, tuple(pares[:2000]), tuple(adv))
