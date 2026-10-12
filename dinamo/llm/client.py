"""
Clientes LLM. Todos cumplen el mismo contrato:  generar(sistema, usuario) -> str

- LLMFalso: determinístico, sin red. Para tests y para trabajar sin Ollama instalado.
- LLMOllama: modelo local vía la API HTTP de Ollama (http://localhost:11434).

El texto que devuelve el LLM NUNCA se ejecuta como código (regla 10).
"""
from __future__ import annotations

from typing import Protocol

import requests


class LLMNoDisponible(RuntimeError):
    pass


class ClienteLLM(Protocol):
    def generar(self, sistema: str, usuario: str) -> str: ...


class LLMFalso:
    """Copia las líneas de evidencia (o, si no hay, los fragmentos de documentos).

    Permite probar el sistema completo sin un modelo real: es determinístico y no inventa nada."""

    def generar(self, sistema: str, usuario: str) -> str:
        lineas = [l[2:] for l in usuario.splitlines() if l.startswith("- [E:")]
        if lineas:
            return "Esto es lo que muestran los datos:\n" + "\n".join(f"• {l}" for l in lineas)
        citas = [l[2:] for l in usuario.splitlines() if l.startswith("- [C:") and "#" in l.split("]")[0]
                 and not l.startswith("- [C:perfil#")]
        if citas:
            return "Esto dicen los documentos:\n" + "\n".join(f"• {c[:400]}" for c in citas[:4])
        return "No encontré evidencia suficiente para responder esa pregunta."


class LLMOllama:
    def __init__(self, modelo: str = "llama3.2:3b", url: str = "http://localhost:11434",
                 temperatura: float = 0.2, timeout: int = 120):
        self.modelo, self.url, self.temperatura, self.timeout = modelo, url.rstrip("/"), temperatura, timeout

    def generar(self, sistema: str, usuario: str) -> str:
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            "stream": False,
            "options": {"temperature": self.temperatura},
        }
        try:
            r = requests.post(f"{self.url}/api/chat", json=cuerpo, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise LLMNoDisponible(
                f"No pude hablar con Ollama en {self.url} ({exc}). "
                f"¿Está abierto Ollama y descargaste el modelo con 'ollama pull {self.modelo}'?") from exc
        return r.json()["message"]["content"].strip()


def crear_cliente(proveedor: str, **kwargs) -> ClienteLLM:
    if proveedor == "falso":
        return LLMFalso()
    if proveedor == "ollama":
        return LLMOllama(**kwargs)
    raise ValueError(f"Proveedor LLM desconocido: {proveedor}")
