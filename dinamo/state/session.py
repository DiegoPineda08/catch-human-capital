"""
STATE: memoria de la conversación.

Guarda lo que DINAMO necesita recordar entre una pregunta y la siguiente:
  - los turnos (pregunta + plan + ids de evidencia) -> preguntas de seguimiento:
    "¿y sólo en la región Norte?" reutiliza la métrica y los filtros del turno anterior;
  - la tabla activa -> si la pregunta no deja claro de qué fuente habla, se sigue con la última;
  - el perfil del usuario -> quién pregunta (cambia el tono de la respuesta, no los números);
  - la aclaración pendiente -> si DINAMO preguntó "¿cuál indicador?", el usuario puede responder "2".
No guarda DataFrames ni el texto del LLM como fuente de verdad: sólo planes e ids de evidencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dinamo.core.contracts import Aclaracion, PerfilUsuario, Plan


@dataclass
class Turno:
    pregunta: str
    plan: Plan
    evidencias: tuple[str, ...]


@dataclass
class EstadoSesion:
    turnos: list[Turno] = field(default_factory=list)
    usuario: PerfilUsuario = field(default_factory=PerfilUsuario)
    tabla_activa: str | None = None
    aclaracion_pendiente: Aclaracion | None = None

    def registrar(self, pregunta: str, plan: Plan, ids_evidencia: list[str]) -> None:
        self.turnos.append(Turno(pregunta, plan, tuple(ids_evidencia)))
        if plan.tabla:
            self.tabla_activa = plan.tabla

    @property
    def ultimo_plan(self) -> Plan | None:
        return self.turnos[-1].plan if self.turnos else None

    def ultimo_plan_de(self, tabla: str | None) -> Plan | None:
        """El último plan, sólo si fue sobre la misma tabla (no se mezclan filtros de fuentes distintas)."""
        plan = self.ultimo_plan
        return plan if plan is not None and plan.tabla == tabla else None

    def resolver_opcion(self, texto: str) -> str:
        """Si el usuario responde '2' a una aclaración pendiente, devuelve la opción 2 completa."""
        t = texto.strip()
        if self.aclaracion_pendiente and t.isdigit() and 1 <= int(t) <= len(self.aclaracion_pendiente.opciones):
            return self.aclaracion_pendiente.opciones[int(t) - 1]
        return texto

    def reiniciar(self) -> None:
        self.turnos.clear()
        self.aclaracion_pendiente = None
