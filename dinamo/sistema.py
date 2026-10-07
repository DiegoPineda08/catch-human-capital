"""
Ensamblado del sistema: aquí se conectan todas las piezas (y sólo aquí).

Cada módulo se puede reemplazar por otro que cumpla el mismo contrato; por ejemplo, en los
tests se usa un LLM falso y tablas pequeñas inventadas.

    from dinamo.sistema import construir_sistema
    brain = construir_sistema(archivos=["ejemplos/ventas_tiendas.csv", "ejemplos/informe_clima_laboral.pdf"])
    print(brain.responder("¿Cómo han evolucionado las ventas?").texto)
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dinamo.brain import Brain
from dinamo.core.config import Config
from dinamo.core.contracts import PerfilUsuario
from dinamo.data_engine import Biblioteca
from dinamo.evidence import EvidenceStore
from dinamo.llm import crear_cliente
from dinamo.rac import Retriever
from dinamo.skills import crear_registro
from dinamo.state import EstadoSesion


def construir_sistema(config: Config | None = None, archivos=None, llm=None,
                      usuario: PerfilUsuario | None = None, biblioteca: Biblioteca | None = None) -> Brain:
    config = config or Config()
    if archivos is not None:
        config = replace(config, archivos=tuple(Path(a) for a in archivos))
    biblioteca = biblioteca or Biblioteca.desde_archivos(config.archivos, config.carpeta_perfiles)
    if llm is None:
        kwargs = {"modelo": config.ollama_modelo, "url": config.ollama_url} if config.llm_proveedor == "ollama" else {}
        llm = crear_cliente(config.llm_proveedor, **kwargs)
    return Brain(biblioteca=biblioteca, registro=crear_registro(),
                 rac=Retriever(carpeta_conocimiento=config.carpeta_conocimiento),
                 llm=llm, evidencias=EvidenceStore(), estado=EstadoSesion(usuario=usuario or PerfilUsuario()),
                 top_k=config.rac_top_k)
