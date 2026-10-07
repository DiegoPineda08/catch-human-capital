"""Cliente HTTP para Ollama. Usa sólo urllib (sin requests).

LLMOllamaRobusto: misma interfaz que LLMOllama (generar(sistema, usuario) -> str)
pero con reintentos y modelo de respaldo.

OllamaEmbedder: genera vectores densos para el RetrieverHibrido.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

_TIMEOUT = 120


class OllamaHTTP:
    """Thin wrapper sobre la API REST de Ollama."""

    def __init__(self, url: str = "http://localhost:11434", timeout: int = _TIMEOUT):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _post(self, endpoint: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.url}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def disponible(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.url}/api/tags", timeout=5)
            return True
        except Exception:
            return False

    def modelos(self) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=10) as resp:
                data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def chat(self, modelo: str, sistema: str, usuario: str,
             temperatura: float = 0.0, seed: int = 42) -> str:
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "options": {"temperature": temperatura, "seed": seed},
            "stream": False,
        }
        resp = self._post("/api/chat", payload)
        return resp["message"]["content"]

    def embed(self, modelo: str, texto: str) -> list[float]:
        resp = self._post("/api/embeddings", {"model": modelo, "prompt": texto})
        return resp.get("embedding", [])


def limpiar_respuesta(texto: str) -> str:
    """Quita bloques <think>...</think> que generan algunos modelos (qwen, deepseek)."""
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL).strip()


class LLMOllamaRobusto:
    """Reintentos + modelo de respaldo. Misma interfaz: generar(sistema, usuario) -> str."""

    def __init__(self, modelo: str = "llama3.2:3b", respaldo: str | None = None,
                 reintentos: int = 2, cliente: OllamaHTTP | None = None):
        self.modelo = modelo
        self.respaldo = respaldo
        self.reintentos = reintentos
        self._cliente = cliente or OllamaHTTP()

    def generar(self, sistema: str, usuario: str) -> str:
        modelos = [self.modelo] + ([self.respaldo] if self.respaldo else [])
        ultimo_error: Exception | None = None
        for modelo in modelos:
            for intento in range(self.reintentos):
                try:
                    texto = self._cliente.chat(modelo, sistema, usuario)
                    return limpiar_respuesta(texto)
                except Exception as exc:
                    ultimo_error = exc
        from dinamo.llm.client import LLMNoDisponible
        raise LLMNoDisponible(f"Ollama no responde ({self.modelo}): {ultimo_error}") from ultimo_error


class OllamaEmbedder:
    """Genera embeddings para el RetrieverHibrido."""

    def __init__(self, modelo: str = "nomic-embed-text", cliente: OllamaHTTP | None = None,
                 lote: int = 32):
        self.modelo = modelo
        self._cliente = cliente or OllamaHTTP()
        self.lote = lote

    def embed(self, textos: list[str]) -> list[list[float]]:
        return [self._cliente.embed(self.modelo, t) for t in textos]

    def disponible(self) -> bool:
        return self._cliente.disponible() and self.modelo in self._cliente.modelos()
