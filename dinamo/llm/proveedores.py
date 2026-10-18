"""
PROVEEDORES DE LLM con streaming, intercambiables.

Todos cumplen dos interfaces:
  - `generar(sistema, usuario) -> str`   (el contrato ClienteLLM que ya usa el Brain)
  - `chat(mensajes, ...) -> Iterator[str]` (streaming, para la conversación)

Proveedores:
  ollama     modelo local (http://localhost:11434). Los datos NO salen del equipo.
  gemini     Google Gemini (GEMINI_API_KEY). Plan gratuito con límites.        ⚠ nube
  groq       Groq, API compatible con OpenAI (GROQ_API_KEY).                    ⚠ nube
  anthropic  Claude (ANTHROPIC_API_KEY).                                         ⚠ nube
  openai     OpenAI o cualquier API compatible (OPENAI_API_KEY, OPENAI_BASE_URL). ⚠ nube

`elegir_proveedor("auto")` usa Ollama si responde; si no, el primero con clave configurada.
El navegador puede además usar su propia IA (WebLLM) cuando el servidor no tiene ninguno.

Las claves sólo se leen del entorno del servidor (archivo .env). Nunca se envían al navegador.
El texto que devuelve un LLM nunca se ejecuta como código.
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import requests

from .client import LLMNoDisponible

TIEMPO_CONEXION = 8
TIEMPO_LECTURA = 180


def separar_sistema(mensajes: list[dict]) -> tuple[str, list[dict]]:
    """Separa el mensaje de sistema y une mensajes seguidos del mismo rol (Gemini y Claude lo exigen)."""
    sistema = "\n\n".join(m["content"] for m in mensajes if m.get("role") == "system")
    resto: list[dict] = []
    for m in mensajes:
        if m.get("role") == "system":
            continue
        rol = "assistant" if m.get("role") == "assistant" else "user"
        if resto and resto[-1]["role"] == rol:
            resto[-1] = {"role": rol, "content": resto[-1]["content"] + "\n\n" + m["content"]}
        else:
            resto.append({"role": rol, "content": m["content"]})
    while resto and resto[0]["role"] != "user":
        resto.pop(0)
    return sistema, resto


def _lineas_sse(r: requests.Response) -> Iterator[dict]:
    for linea in r.iter_lines(decode_unicode=True):
        if not linea or not linea.startswith("data:"):
            continue
        dato = linea[5:].strip()
        if not dato or dato == "[DONE]":
            continue
        try:
            yield json.loads(dato)
        except json.JSONDecodeError:
            continue


class ProveedorLLM:
    nombre = "base"
    nube = False
    etiqueta = ""

    def __init__(self, modelo: str):
        self.modelo = modelo

    # -- interfaz común
    def chat(self, mensajes: list[dict], temperatura: float = 0.3, max_tokens: int = 1500) -> Iterator[str]:
        raise NotImplementedError

    def generar(self, sistema: str, usuario: str) -> str:
        return "".join(self.chat([{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                                 temperatura=0.2)).strip()

    def describir(self) -> dict:
        return {"proveedor": self.nombre, "etiqueta": self.etiqueta, "modelo": self.modelo, "nube": self.nube}

    # -- utilidades
    def _post(self, url: str, cuerpo: dict, cabeceras: dict | None = None) -> requests.Response:
        try:
            r = requests.post(url, json=cuerpo, headers=cabeceras or {}, stream=True,
                              timeout=(TIEMPO_CONEXION, TIEMPO_LECTURA))
        except requests.RequestException as exc:
            raise LLMNoDisponible(f"No pude conectarme con {self.etiqueta}: {exc}") from exc
        if r.status_code != 200:
            detalle = r.text[:300]
            r.close()
            raise LLMNoDisponible(f"{self.etiqueta} respondió {r.status_code}: {detalle}")
        return r


class Ollama(ProveedorLLM):
    nombre, etiqueta = "ollama", "Ollama (local)"

    def __init__(self, modelo: str = "", url: str = "http://localhost:11434"):
        super().__init__(modelo)
        self.url = url.rstrip("/")

    def modelos(self) -> list[str]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=2)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except (requests.RequestException, ValueError):
            return []

    def chat(self, mensajes, temperatura=0.3, max_tokens=1500):
        cuerpo = {"model": self.modelo, "messages": mensajes, "stream": True,
                  "options": {"temperature": temperatura, "num_predict": max_tokens}}
        r = self._post(f"{self.url}/api/chat", cuerpo)
        try:
            for linea in r.iter_lines(decode_unicode=True):
                if not linea:
                    continue
                d = json.loads(linea)
                if d.get("error"):
                    raise LLMNoDisponible(f"Ollama: {d['error']}")
                trozo = (d.get("message") or {}).get("content")
                if trozo:
                    yield trozo
        finally:
            r.close()


class Gemini(ProveedorLLM):
    nombre, etiqueta, nube = "gemini", "Gemini (Google)", True

    def __init__(self, clave: str, modelo: str = "gemini-2.5-flash"):
        super().__init__(modelo)
        self.clave = clave

    def chat(self, mensajes, temperatura=0.3, max_tokens=1500):
        sistema, resto = separar_sistema(mensajes)
        cuerpo = {"contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                               for m in resto],
                  "generationConfig": {"temperature": temperatura, "maxOutputTokens": max_tokens}}
        if sistema:
            cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:streamGenerateContent?alt=sse"
        r = self._post(url, cuerpo, {"x-goog-api-key": self.clave})
        try:
            for d in _lineas_sse(r):
                partes = ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                trozo = "".join(p.get("text", "") for p in partes)
                if trozo:
                    yield trozo
        finally:
            r.close()


class Anthropic(ProveedorLLM):
    nombre, etiqueta, nube = "anthropic", "Claude (Anthropic)", True

    def __init__(self, clave: str, modelo: str = "claude-haiku-4-5-20251001"):
        super().__init__(modelo)
        self.clave = clave

    def chat(self, mensajes, temperatura=0.3, max_tokens=1500):
        sistema, resto = separar_sistema(mensajes)
        cuerpo = {"model": self.modelo, "max_tokens": max_tokens, "temperature": temperatura, "stream": True,
                  "system": sistema, "messages": resto}
        r = self._post("https://api.anthropic.com/v1/messages", cuerpo,
                       {"x-api-key": self.clave, "anthropic-version": "2023-06-01"})
        try:
            for d in _lineas_sse(r):
                if d.get("type") == "content_block_delta":
                    trozo = (d.get("delta") or {}).get("text")
                    if trozo:
                        yield trozo
                elif d.get("type") == "error":
                    raise LLMNoDisponible(f"Claude: {d.get('error')}")
        finally:
            r.close()


class OpenAICompatible(ProveedorLLM):
    nube = True

    def __init__(self, clave: str, modelo: str, base: str, nombre: str = "openai", etiqueta: str = "OpenAI / compatible"):
        super().__init__(modelo)
        self.clave, self.base, self.nombre, self.etiqueta = clave, base.rstrip("/"), nombre, etiqueta

    def chat(self, mensajes, temperatura=0.3, max_tokens=1500):
        cuerpo = {"model": self.modelo, "messages": mensajes, "stream": True, "temperature": temperatura,
                  "max_tokens": max_tokens}
        r = self._post(f"{self.base}/chat/completions", cuerpo, {"Authorization": f"Bearer {self.clave}"})
        try:
            for d in _lineas_sse(r):
                trozo = ((d.get("choices") or [{}])[0].get("delta") or {}).get("content")
                if trozo:
                    yield trozo
        finally:
            r.close()


# ---------------------------------------------------------------------------------------------
NUBE = {
    "gemini": ("GEMINI_API_KEY", lambda c: Gemini(c, os.getenv("GEMINI_MODELO", "gemini-2.5-flash"))),
    "groq": ("GROQ_API_KEY", lambda c: OpenAICompatible(c, os.getenv("GROQ_MODELO", "llama-3.3-70b-versatile"),
                                                        "https://api.groq.com/openai/v1", "groq", "Groq")),
    "anthropic": ("ANTHROPIC_API_KEY", lambda c: Anthropic(c, os.getenv("ANTHROPIC_MODELO", "claude-haiku-4-5-20251001"))),
    "openai": ("OPENAI_API_KEY", lambda c: OpenAICompatible(c, os.getenv("OPENAI_MODELO", "gpt-4o-mini"),
                                                            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))),
}


def _ollama_disponible() -> Ollama | None:
    o = Ollama(url=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    modelos = o.modelos()
    if not modelos:
        return None
    preferido = os.getenv("OLLAMA_MODELO", "")
    utiles = [m for m in modelos if not any(x in m for x in ("embed", "bge", "minilm"))] or modelos
    o.modelo = preferido if preferido in modelos else utiles[0]
    return o


def elegir_proveedor(preferencia: str | None = None) -> ProveedorLLM | None:
    """Devuelve el proveedor a usar, o None si no hay ninguno (el navegador usará su propia IA)."""
    pref = (preferencia or os.getenv("DINAMO_LLM", "auto")).lower()
    if pref in ("auto", "ollama"):
        o = _ollama_disponible()
        if o:
            return o
    candidatos = [pref] if pref in NUBE else (list(NUBE) if pref == "auto" else [])
    for nombre in candidatos:
        variable, fabrica = NUBE[nombre]
        clave = os.getenv(variable, "").strip()
        if clave:
            return fabrica(clave)
    return None


def proveedores_configurados() -> list[dict]:
    """Estado de cada proveedor, para el catálogo de integraciones (sin exponer claves)."""
    filas = []
    o = _ollama_disponible()
    filas.append({"proveedor": "ollama", "etiqueta": "Ollama (local)", "nube": False,
                  "estado": "disponible" if o else "sin conexión", "modelo": o.modelo if o else None,
                  "requisito": "Instalar Ollama y descargar un modelo (ollama pull llama3.2)"})
    for nombre, (variable, fabrica) in NUBE.items():
        tiene = bool(os.getenv(variable, "").strip())
        modelo = fabrica("x").modelo
        filas.append({"proveedor": nombre, "etiqueta": fabrica("x").etiqueta, "nube": True,
                      "estado": "configurado" if tiene else "sin configurar", "modelo": modelo,
                      "requisito": f"Variable {variable} en .env"})
    return filas
