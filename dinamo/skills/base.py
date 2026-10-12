"""
SKILLS: unidades de análisis modulares y reutilizables con CUALQUIER base.

Una Skill:
  - declara su nombre, las intenciones que atiende y los ROLES de columna que necesita
    (por ejemplo, "tendencia" necesita una columna de "tiempo" y una "metrica");
  - recibe el DataEngine y un dict de parámetros con NOMBRES DE COLUMNAS (nunca nombres fijos);
  - calcula con código determinístico (pandas);
  - devuelve un ResultadoSkill con Evidencias (nunca texto interpretativo).

Una Skill NO llama al LLM, NO llama a otras Skills y NO guarda estado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from dataclasses import replace

from dinamo.core.contracts import Columna, PerfilDataset, ResultadoSkill, crear_evidencia
from dinamo.data_engine import DataEngine


class ParametroInvalido(ValueError):
    pass


class Skill(ABC):
    nombre: str = ""
    descripcion: str = ""
    intenciones: tuple[str, ...] = ()
    requiere: tuple[str, ...] = ()           # roles que la base debe tener para usar esta Skill
    parametros: dict[str, str] = {}          # documentación de parámetros
    requeridos: tuple[str, ...] = ()

    def aplica(self, perfil: PerfilDataset) -> bool:
        """¿Tiene esta base lo necesario para esta Skill? (p.ej. una base sin tiempo no tiene tendencia)."""
        return all(perfil.tiene(rol) for rol in self.requiere)

    def __call__(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        if not self.aplica(datos.perfil):
            faltan = [r for r in self.requiere if not datos.perfil.tiene(r)]
            raise ParametroInvalido(f"{self.nombre}: esta base no tiene columnas con rol {faltan}")
        faltan = [p for p in self.requeridos if parametros.get(p) is None]
        if faltan:
            raise ParametroInvalido(f"{self.nombre}: faltan parámetros {faltan}")
        return _con_fuente(self.ejecutar(datos, parametros), datos)

    @abstractmethod
    def ejecutar(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        ...


def _con_fuente(res: ResultadoSkill, datos: DataEngine) -> ResultadoSkill:
    """Agrega a cada evidencia de qué tabla salió y qué versión de los datos se usó.

    Así dos tablas distintas (o el mismo archivo con datos actualizados) nunca producen el mismo id,
    y cualquier número de una respuesta se puede rastrear hasta su fuente."""
    fuente = {"tabla": datos.perfil.nombre, "version": datos.version}
    evid = tuple(crear_evidencia(e.skill, e.descripcion, e.valor, e.unidad, e.n, e.metodo, {**fuente, **e.filtros})
                 for e in res.evidencias)
    return replace(res, evidencias=evid)


# ------------------------------------------------------------------ ayudas comunes a las Skills
def columna_con_rol(perfil: PerfilDataset, nombre: str, roles: tuple[str, ...]) -> Columna:
    """Devuelve la columna si existe y tiene uno de los roles esperados; si no, error claro."""
    try:
        col = perfil.columna(nombre)
    except KeyError as exc:
        raise ParametroInvalido(str(exc)) from exc
    if col.rol not in roles:
        raise ParametroInvalido(f"La columna '{nombre}' tiene rol '{col.rol}', se esperaba {roles}")
    return col


def agregar(serie: pd.Series, como: str) -> float:
    """Resume varios valores en uno, según la agregación declarada en el perfil."""
    if como == "suma":
        return float(serie.sum())
    if como == "promedio":
        return float(serie.mean())
    return float(serie.median())


def filtros_de(parametros: dict[str, Any]) -> dict[str, Any]:
    return dict(parametros.get("filtros") or {})


class Registro:
    """Catálogo de Skills disponibles. El Brain sólo conoce Skills a través de aquí."""

    def __init__(self, skills: list[Skill] | None = None):
        self._skills: dict[str, Skill] = {}
        for s in skills or []:
            self.registrar(s)

    def registrar(self, skill: Skill) -> None:
        if not skill.nombre:
            raise ValueError("La Skill debe tener nombre")
        if skill.nombre in self._skills:
            raise ValueError(f"Skill duplicada: {skill.nombre}")
        self._skills[skill.nombre] = skill

    def obtener(self, nombre: str) -> Skill | None:
        return self._skills.get(nombre)

    def para_intencion(self, intencion: str, perfil: PerfilDataset | None = None) -> list[Skill]:
        return [s for s in self._skills.values()
                if intencion in s.intenciones and (perfil is None or s.aplica(perfil))]

    def intenciones_disponibles(self, perfil: PerfilDataset) -> set[str]:
        """Intenciones que se pueden responder con ESTA base (sirve para sugerir preguntas)."""
        return {i for s in self._skills.values() if s.aplica(perfil) for i in s.intenciones}

    def nombres(self) -> list[str]:
        return list(self._skills)
