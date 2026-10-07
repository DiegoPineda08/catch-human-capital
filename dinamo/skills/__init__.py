"""
Registro de Skills. Para agregar una Skill nueva:
  1. crea dinamo/skills/mi_skill.py;
  2. impórtala aquí y agrégala a la lista de crear_registro();
  3. escribe tests para la Skill y pruébala con bases distintas.
"""

from .base import (
    ParametroInvalido,
    Registro,
    Skill,
    agregar,
    columna_con_rol,
)
from .comparar_grupos import CompararGrupos
from .describir_dataset import DescribirDataset
from .distribucion import Distribucion
from .ranking import Ranking
from .perfil_entidad import PerfilEntidad
from .relaciones import Relaciones
from .tendencia import Tendencia


def crear_registro() -> Registro:
    return Registro(
        [
            DescribirDataset(),
            Tendencia(),
            Ranking(),
            Distribucion(),
            CompararGrupos(),
            Relaciones(),
            PerfilEntidad(),
            # PerfilEntidad(),     # TODO Diego Pineda
        ]
    )


__all__ = [
    "Skill",
    "Registro",
    "ParametroInvalido",
    "agregar",
    "columna_con_rol",
    "DescribirDataset",
    "Tendencia",
    "Ranking",
    "Relaciones",
    "PerfilEntidad",
    "Distribucion",
    "CompararGrupos",
    "crear_registro",
]
