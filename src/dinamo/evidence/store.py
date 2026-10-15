"""Almacenamiento interno de evidencia analítica de DINAMO_ANALYTICS.

Este módulo mantiene evidencia estructurada generada por las Skills.

Responsabilidad:
- almacenar resultados analíticos estructurados;
- conservar trazabilidad de la Skill y el método utilizado;
- conservar el tamaño de muestra cuando exista;
- conservar advertencias asociadas al resultado;
- permitir recuperar y filtrar evidencia.

Este almacenamiento es interno al bloque de Evidence.
No define ni sustituye los contratos compartidos de dinamo.core.contracts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RegistroEvidencia:
    """Representa una evidencia analítica estructurada."""

    skill: str
    metodo: str
    n: int | None
    resultado: Mapping[str, Any]
    metadatos: Mapping[str, Any]
    advertencias: tuple[str, ...]

    def __post_init__(self) -> None:
        """Valida los campos mínimos de una evidencia."""
        if not isinstance(self.skill, str) or not self.skill.strip():
            raise ValueError(
                "skill debe ser una cadena no vacía."
            )

        if not isinstance(self.metodo, str) or not self.metodo.strip():
            raise ValueError(
                "metodo debe ser una cadena no vacía."
            )

        if self.n is not None:
            if not isinstance(self.n, int):
                raise TypeError(
                    "n debe ser un entero o None."
                )

            if self.n < 0:
                raise ValueError(
                    "n no puede ser negativo."
                )

        if not isinstance(self.resultado, Mapping):
            raise TypeError(
                "resultado debe ser un Mapping."
            )

        if not isinstance(self.metadatos, Mapping):
            raise TypeError(
                "metadatos debe ser un Mapping."
            )

        if not isinstance(self.advertencias, tuple):
            raise TypeError(
                "advertencias debe ser una tupla."
            )

        if any(
            not isinstance(advertencia, str)
            for advertencia in self.advertencias
        ):
            raise TypeError(
                "Todas las advertencias deben ser cadenas."
            )


class EvidenceStore:
    """Almacena evidencia analítica de forma determinística."""

    def __init__(self) -> None:
        """Inicializa un almacenamiento vacío."""
        self._evidencias: list[RegistroEvidencia] = []

    def agregar(
        self,
        *,
        skill: str,
        metodo: str,
        n: int | None,
        resultado: Mapping[str, Any],
        metadatos: Mapping[str, Any] | None = None,
        advertencias: tuple[str, ...] | list[str] = (),
    ) -> RegistroEvidencia:
        """Agrega una evidencia y devuelve el registro almacenado."""
        if not isinstance(resultado, Mapping):
            raise TypeError(
                "resultado debe ser un Mapping."
            )

        if metadatos is None:
            metadatos = {}

        if not isinstance(metadatos, Mapping):
            raise TypeError(
                "metadatos debe ser un Mapping."
            )

        advertencias_tuple = tuple(advertencias)

        registro = RegistroEvidencia(
            skill=skill,
            metodo=metodo,
            n=n,
            resultado=deepcopy(dict(resultado)),
            metadatos=deepcopy(dict(metadatos)),
            advertencias=advertencias_tuple,
        )

        self._evidencias.append(registro)

        return self._copiar_registro(registro)

    def agregar_registro(
        self,
        registro: RegistroEvidencia,
    ) -> RegistroEvidencia:
        """Agrega un RegistroEvidencia ya construido."""
        if not isinstance(
            registro,
            RegistroEvidencia,
        ):
            raise TypeError(
                "registro debe ser un RegistroEvidencia."
            )

        copia = self._copiar_registro(registro)

        self._evidencias.append(copia)

        return self._copiar_registro(copia)

    def todos(self) -> tuple[RegistroEvidencia, ...]:
        """Devuelve todas las evidencias en orden de inserción."""
        return tuple(
            self._copiar_registro(registro)
            for registro in self._evidencias
        )

    def filtrar(
        self,
        *,
        skill: str | None = None,
        metodo: str | None = None,
    ) -> tuple[RegistroEvidencia, ...]:
        """Filtra evidencia por Skill y/o método."""
        resultados = self._evidencias

        if skill is not None:
            resultados = [
                registro
                for registro in resultados
                if registro.skill == skill
            ]

        if metodo is not None:
            resultados = [
                registro
                for registro in resultados
                if registro.metodo == metodo
            ]

        return tuple(
            self._copiar_registro(registro)
            for registro in resultados
        )

    def limpiar(self) -> None:
        """Elimina toda la evidencia almacenada."""
        self._evidencias.clear()

    def cantidad(self) -> int:
        """Devuelve la cantidad de evidencias almacenadas."""
        return len(self._evidencias)

    def esta_vacio(self) -> bool:
        """Indica si no existen evidencias almacenadas."""
        return not self._evidencias

    @staticmethod
    def _copiar_registro(
        registro: RegistroEvidencia,
    ) -> RegistroEvidencia:
        """Genera una copia independiente de un registro."""
        return RegistroEvidencia(
            skill=registro.skill,
            metodo=registro.metodo,
            n=registro.n,
            resultado=deepcopy(dict(registro.resultado)),
            metadatos=deepcopy(dict(registro.metadatos)),
            advertencias=tuple(registro.advertencias),
        )