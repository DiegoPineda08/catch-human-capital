"""Cliente de Ollama sólo con la biblioteca estándar (cero dependencias nuevas).

Aporta tres cosas que el cliente básico no tiene:
  * temperatura 0 y semilla fija -> la misma pregunta con la misma evidencia da el mismo texto
    (reproducibilidad, igual que el resto del sistema);
  * reintentos y lista de modelos de respaldo (si el 7B no está descargado, usa el 3B);
  * embeddings (/api/embed), que usa el RAC híbrido para entender preguntas con otras palabras.

`LLMOllamaRobusto` tiene el mismo método `generar(sistema, usuario)` que LLMOllama, así que se puede
cambiar en dinamo/sistema.py sin tocar al Brain.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Sequence

URL_POR_DEFECTO = "http://localhost:11434"


class OllamaError(RuntimeError):
    """Ollama apagado, modelo no descargado, respuesta inválida o tiempo agotado."""


def _post(url: str, cuerpo: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")[:200]
        raise OllamaError(f"HTTP {e.code}: {detalle}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
        raise OllamaError(f"No se pudo hablar con Ollama: {e}") from e


class OllamaHTTP:
    def __init__(self, url: str | None = None, timeout: float = 120.0):
        self.url = (url or os.environ.get("OLLAMA_URL") or URL_POR_DEFECTO).rstrip("/")
        self.timeout = timeout

    def disponible(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def modelos(self) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=5) as r:
                return [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
        except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
            return []

    def chat(self, modelo: str, sistema: str, usuario: str, *, temperatura: float = 0.0,
             semilla: int = 7, num_ctx: int = 4096, max_tokens: int = 400) -> str:
        cuerpo = {"model": modelo, "stream": False,
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                  "options": {"temperature": temperatura, "seed": semilla, "num_ctx": num_ctx,
                              "num_predict": max_tokens}}
        data = _post(f"{self.url}/api/chat", cuerpo, self.timeout)
        try:
            return str(data["message"]["content"])
        except (KeyError, TypeError) as e:
            raise OllamaError(f"Respuesta inesperada de Ollama: {str(data)[:200]}") from e

    def embed(self, modelo: str, textos: Sequence[str]) -> list[list[float]]:
        data = _post(f"{self.url}/api/embed", {"model": modelo, "input": list(textos)}, self.timeout)
        try:
            return data["embeddings"]
        except KeyError as e:
            raise OllamaError(f"Respuesta de embeddings inesperada: {str(data)[:200]}") from e


_RE_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def limpiar_respuesta(texto: str) -> str:
    """Quita el bloque <think>…</think> que algunos modelos (qwen, deepseek) escriben antes de responder."""
    return _RE_PENSAMIENTO.sub("", texto).strip()


class LLMOllamaRobusto:
    """Mismo contrato que LLMOllama: generar(sistema, usuario) -> texto."""

    def __init__(self, modelo: str | None = None, respaldo: Sequence[str] = ("llama3.2:3b",),
                 reintentos: int = 1, cliente: OllamaHTTP | None = None, **opciones):
        self.modelo = modelo or os.environ.get("OLLAMA_MODELO", "llama3.2:3b")
        self.respaldo = [m for m in respaldo if m != self.modelo]
        self.reintentos = reintentos
        self.cliente = cliente or OllamaHTTP()
        self.opciones = opciones

    def generar(self, sistema: str, usuario: str) -> str:
        ultimo: Exception | None = None
        for modelo in [self.modelo, *self.respaldo]:
            for intento in range(self.reintentos + 1):
                try:
                    return limpiar_respuesta(self.cliente.chat(modelo, sistema, usuario, **self.opciones))
                except OllamaError as e:
                    ultimo = e
                    if "not found" in str(e).lower():   # modelo no descargado: no tiene caso reintentar
                        break
                    time.sleep(0.5 * (intento + 1))
        raise OllamaError(f"Ningún modelo respondió ({ultimo})")


class OllamaEmbedder:
    """Convierte textos en vectores. Modelo sugerido: `ollama pull nomic-embed-text` (~270 MB)."""

    def __init__(self, modelo: str | None = None, cliente: OllamaHTTP | None = None, lote: int = 32):
        self.modelo = modelo or os.environ.get("OLLAMA_EMBED_MODELO", "nomic-embed-text")
        self.cliente = cliente or OllamaHTTP()
        self.lote = lote
        nomic = "nomic" in self.modelo        # nomic-embed-text espera estos prefijos
        self._pre_doc = "search_document: " if nomic else ""
        self._pre_preg = "search_query: " if nomic else ""

    def _vectores(self, textos: Sequence[str]):
        import numpy as np
        filas: list[list[float]] = []
        for i in range(0, len(textos), self.lote):
            filas += self.cliente.embed(self.modelo, textos[i:i + self.lote])
        m = np.asarray(filas, dtype="float32")
        norma = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.where(norma == 0, 1, norma)

    def documentos(self, textos: Sequence[str]):
        return self._vectores([self._pre_doc + t for t in textos])

    def pregunta(self, texto: str):
        return self._vectores([self._pre_preg + texto])[0]
