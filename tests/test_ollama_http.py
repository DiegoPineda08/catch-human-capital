"""Cliente de Ollama probado contra un servidor HTTP falso (no necesita Ollama instalado)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dinamo.llm.ollama_http import (LLMOllamaRobusto, OllamaEmbedder, OllamaError, OllamaHTTP,
                                    limpiar_respuesta)


class Falso(BaseHTTPRequestHandler):
    peticiones: list = []
    modelos_ausentes = {"qwen2.5:7b"}

    def log_message(self, *a):  # silencio
        pass

    def _json(self, codigo, obj):
        cuerpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._json(200, {"models": [{"name": "llama3.2:3b"}]})

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Falso.peticiones.append((self.path, cuerpo))
        if cuerpo["model"] in self.modelos_ausentes:
            return self._json(404, {"error": f"model '{cuerpo['model']}' not found"})
        if self.path == "/api/chat":
            return self._json(200, {"message": {"content": f"<think>x</think>Respuesta de {cuerpo['model']}"}})
        if self.path == "/api/embed":
            return self._json(200, {"embeddings": [[3.0, 4.0] for _ in cuerpo["input"]]})
        self._json(404, {"error": "?"})


@pytest.fixture(scope="module")
def cliente():
    srv = HTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield OllamaHTTP(f"http://127.0.0.1:{srv.server_port}", timeout=5)
    srv.shutdown()


def test_disponible_y_modelos(cliente):
    assert cliente.disponible() and cliente.modelos() == ["llama3.2:3b"]


def test_apagado_no_revienta():
    muerto = OllamaHTTP("http://127.0.0.1:1", timeout=1)
    assert not muerto.disponible() and muerto.modelos() == []
    with pytest.raises(OllamaError):
        muerto.chat("m", "s", "u")


def test_chat_usa_temperatura_cero_y_semilla(cliente):
    Falso.peticiones.clear()
    cliente.chat("llama3.2:3b", "sistema", "usuario")
    opciones = Falso.peticiones[0][1]["options"]
    assert opciones["temperature"] == 0.0 and opciones["seed"] == 7


def test_robusto_limpia_think_y_usa_modelo_de_respaldo(cliente):
    llm = LLMOllamaRobusto("qwen2.5:7b", respaldo=("llama3.2:3b",), cliente=cliente)
    assert llm.generar("s", "u") == "Respuesta de llama3.2:3b"      # el 7B no está descargado -> cae al 3B


def test_robusto_sin_ningun_modelo_lanza_error_claro(cliente):
    llm = LLMOllamaRobusto("qwen2.5:7b", respaldo=(), cliente=cliente)
    with pytest.raises(OllamaError):
        llm.generar("s", "u")


def test_embedder_normaliza_vectores(cliente):
    emb = OllamaEmbedder("nomic-embed-text", cliente=cliente)
    m = emb.documentos(["a", "b"])
    assert m.shape == (2, 2) and abs(float((m[0] ** 2).sum()) - 1.0) < 1e-6
    assert "search_query: " in emb._pre_preg


def test_limpiar_respuesta():
    assert limpiar_respuesta("<think>\nrazono\n</think>\nHola") == "Hola"
