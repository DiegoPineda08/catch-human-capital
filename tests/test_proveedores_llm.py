"""Proveedores de LLM: se prueban con respuestas HTTP simuladas (no se llama a ningún servicio real)."""
import json

import pytest
import requests

from dinamo.llm import LLMFalso, crear_cliente
from dinamo.llm import proveedores as pv
from dinamo.llm.client import LLMNoDisponible


class RespuestaFalsa:
    def __init__(self, lineas, status=200, texto=""):
        self.lineas, self.status_code, self.text = lineas, status, texto

    def iter_lines(self, decode_unicode=True):
        yield from self.lineas

    def close(self):
        pass


@pytest.fixture
def sin_claves(monkeypatch):
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DINAMO_LLM"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(pv.Ollama, "modelos", lambda self: [])


def test_separar_sistema_une_roles_repetidos():
    sis, resto = pv.separar_sistema([
        {"role": "system", "content": "S"}, {"role": "assistant", "content": "hola"},
        {"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
    assert sis == "S"
    assert resto == [{"role": "user", "content": "a\n\nb"}]


def test_gemini_stream(monkeypatch):
    capturado = {}

    def post(url, json=None, headers=None, **kw):
        capturado.update(url=url, cuerpo=json, cab=headers)
        return RespuestaFalsa(['data: {"candidates":[{"content":{"parts":[{"text":"Ho"}]}}]}',
                               'data: {"candidates":[{"content":{"parts":[{"text":"la"}]}}]}'])
    monkeypatch.setattr(requests, "post", post)
    g = pv.Gemini("CLAVE")
    assert g.generar("sis", "u") == "Hola"
    assert capturado["cab"]["x-goog-api-key"] == "CLAVE"
    assert "CLAVE" not in capturado["url"]
    assert capturado["cuerpo"]["systemInstruction"]["parts"][0]["text"] == "sis"


def test_anthropic_y_openai_stream(monkeypatch):
    def post_a(url, json=None, headers=None, **kw):
        assert json["system"] == "sis"
        return RespuestaFalsa(['data: {"type":"content_block_delta","delta":{"text":"A"}}',
                               'data: {"type":"message_stop"}'])
    monkeypatch.setattr(requests, "post", post_a)
    assert pv.Anthropic("k").generar("sis", "u") == "A"

    def post_o(url, json=None, headers=None, **kw):
        assert headers["Authorization"] == "Bearer k"
        return RespuestaFalsa(['data: {"choices":[{"delta":{"content":"B"}}]}', "data: [DONE]"])
    monkeypatch.setattr(requests, "post", post_o)
    assert pv.OpenAICompatible("k", "m", "https://x/v1").generar("sis", "u") == "B"


def test_ollama_stream(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa(
        [json.dumps({"message": {"content": "x"}}), json.dumps({"message": {"content": "y"}, "done": True})]))
    assert "".join(pv.Ollama("m").chat([{"role": "user", "content": "h"}])) == "xy"


def test_error_http_se_traduce(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa([], 401, "clave inválida"))
    with pytest.raises(LLMNoDisponible, match="401"):
        pv.Gemini("mala").generar("s", "u")


def test_auto_sin_nada_devuelve_falso(sin_claves):
    assert pv.elegir_proveedor("auto") is None
    assert isinstance(crear_cliente("auto"), LLMFalso)


def test_auto_elige_primera_clave(sin_claves, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    p = pv.elegir_proveedor("auto")
    assert p.nombre == "groq"
    assert p.describir()["nube"] is True


def test_proveedor_nube_sin_clave_falla_claro(sin_claves):
    with pytest.raises(LLMNoDisponible, match="GEMINI_API_KEY"):
        crear_cliente("gemini")


def test_catalogo_no_expone_claves(sin_claves, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secreta")
    filas = pv.proveedores_configurados()
    assert "sk-secreta" not in json.dumps(filas)
    assert {f["proveedor"]: f["estado"] for f in filas}["openai"] == "configurado"
