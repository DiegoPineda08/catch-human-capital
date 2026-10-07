"""
Configuración central. Cada valor se puede cambiar con una variable de entorno,
sin tocar el código (por ejemplo: DINAMO_LLM=ollama).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # carpeta dinamo_analitics/


def _archivos_por_defecto() -> tuple[Path, ...]:
    """Lo que se carga si no se indica nada: todo lo que haya en data/; si está vacía, los ejemplos."""
    from dinamo.ingesta import EXTENSIONES          # import tardío: evita importar pandas al leer la config
    if os.getenv("DINAMO_ARCHIVOS"):
        return tuple(Path(p) for p in os.getenv("DINAMO_ARCHIVOS").split(os.pathsep) if p)
    for carpeta in (RAIZ / "data", RAIZ / "ejemplos"):
        archivos = tuple(sorted(p for p in carpeta.glob("*") if p.suffix.lower() in EXTENSIONES
                                and p.name.lower() != "readme.md"))
        if archivos:
            return archivos
    return ()


@dataclass(frozen=True)
class Config:
    archivos: tuple[Path, ...] = field(default_factory=_archivos_por_defecto)
    carpeta_perfiles: Path = RAIZ / "perfiles"
    carpeta_conocimiento: Path = Path(os.getenv("DINAMO_CONOCIMIENTO", RAIZ / "conocimiento"))
    llm_proveedor: str = os.getenv("DINAMO_LLM", "falso")            # "falso" | "ollama"
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_modelo: str = os.getenv("OLLAMA_MODELO", "llama3.2:3b")
    rac_top_k: int = int(os.getenv("DINAMO_RAC_TOP_K", "3"))
