"""
EVIDENCE: registro de todos los resultados numéricos producidos por las Skills.

- Trazabilidad: cada número que aparezca en una respuesta debe existir aquí con su id.
- Determinismo: el mismo cálculo produce el mismo id (ver core.contracts.crear_evidencia),
  así que agregar dos veces la misma evidencia no la duplica.
"""
from __future__ import annotations

import json
from pathlib import Path

from dinamo.core.contracts import Evidencia


class EvidenceStore:
    def __init__(self) -> None:
        self._por_id: dict[str, Evidencia] = {}

    def agregar(self, evidencias) -> list[str]:
        ids = []
        for e in evidencias:
            if not isinstance(e, Evidencia):
                raise TypeError(f"Se esperaba Evidencia, llegó {type(e).__name__}")
            previa = self._por_id.get(e.id)
            if previa is not None and previa != e:
                raise ValueError(f"Conflicto: el id {e.id} ya existe con otro contenido")
            self._por_id[e.id] = e
            ids.append(e.id)
        return ids

    def obtener(self, eid: str) -> Evidencia:
        return self._por_id[eid]

    def existe(self, eid: str) -> bool:
        return eid in self._por_id

    def todas(self) -> list[Evidencia]:
        return list(self._por_id.values())

    def __len__(self) -> int:
        return len(self._por_id)

    def guardar_json(self, ruta: str | Path) -> None:
        Path(ruta).write_text(json.dumps([e.a_dict() for e in self.todas()], ensure_ascii=False,
                                         indent=2, default=str), encoding="utf-8")

    @classmethod
    def cargar_json(cls, ruta: str | Path) -> "EvidenceStore":
        store = cls()
        store.agregar(Evidencia(**d) for d in json.loads(Path(ruta).read_text(encoding="utf-8")))
        return store
