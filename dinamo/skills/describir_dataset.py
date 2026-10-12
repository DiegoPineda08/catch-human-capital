"""Skill: describe la base cargada (qué hay, cuánto, de cuándo). Funciona con cualquier tabla."""
from __future__ import annotations

from typing import Any

from dinamo.core.contracts import ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine

from .base import Skill


class DescribirDataset(Skill):
    nombre = "describir_dataset"
    descripcion = "Resume la base: filas, entidades, periodos y qué métricas y dimensiones contiene."
    intenciones = ("describir_datos",)
    requiere = ()

    def ejecutar(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        p = datos.perfil
        n = datos.num_filas()
        metodo = "conteo sobre el perfil y la tabla"
        b = f"'{p.nombre}'"
        evid = [crear_evidencia(self.nombre, f"Filas de la base {b}", n, "conteo", n, metodo)]

        entidades = datos.entidades()
        if entidades:
            evid.append(crear_evidencia(self.nombre, f"Número de {p.entidad_plural} en {b}", len(entidades),
                                        "conteo", n, metodo))
        periodos = datos.periodos()
        if periodos:
            evid += [
                crear_evidencia(self.nombre, f"Número de periodos en {b}", len(periodos), "conteo", n, metodo),
                crear_evidencia(self.nombre, f"Primer periodo en {b}", periodos[0][1], "texto", n, metodo),
                crear_evidencia(self.nombre, f"Último periodo en {b}", periodos[-1][1], "texto", n, metodo),
            ]
        metricas = [c.nombre_visible for c in p.por_rol("metrica")]
        grupos = [c.nombre_visible for c in p.por_rol("dimension") + p.por_rol("binaria")]
        evid.append(crear_evidencia(self.nombre, f"Indicadores numéricos en {b}", len(metricas), "conteo", n, metodo))
        if metricas:
            evid.append(crear_evidencia(self.nombre, f"Algunos indicadores de {b}", ", ".join(metricas[:8]), "texto", n, metodo))
        if grupos:
            evid.append(crear_evidencia(self.nombre, f"Formas de agrupar {b}", ", ".join(grupos[:8]), "texto", n, metodo))
        validez = p.una("validez")
        if validez is not None:
            validas = len(datos.filas(solo_validas=True))
            evid.append(crear_evidencia(self.nombre, f"Proporción de filas de {b} con dato reportado (no imputado)",
                                        validas / n if n else 0.0, "proporcion", n, f"filas con {validez.nombre} = 1"))

        tabla = tuple({"columna": c.nombre, "rol": c.rol, "nombre": c.nombre_visible, "unidad": c.unidad}
                      for c in p.columnas if c.rol != "ignorar")
        return ResultadoSkill(self.nombre, tuple(evid), tabla)
