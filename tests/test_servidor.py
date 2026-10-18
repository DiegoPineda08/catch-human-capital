"""Servidor HTTP real en un puerto libre (local). LLM ausente; red externa no usada."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from dinamo.servidor import crear_servidor

CSV = b"empleado_id,area,salario,renuncio\n" + b"\n".join(
    f"{i},{'Ventas' if i % 2 else 'TI'},{10000 + i * 137},{int(i % 3 == 0)}".encode() for i in range(1, 41))


@pytest.fixture
def base(tmp_path, monkeypatch):
    for v in ("GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DINAMO_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("dinamo.llm.proveedores.Ollama.modelos", lambda self: [])
    front = tmp_path / "frontend"
    front.mkdir()
    (front / "index.html").write_text("<h1>DINAMO</h1>", encoding="utf-8")
    (front / ".secreto").write_text("no", encoding="utf-8")
    (tmp_path / ".env").write_text("CLAVE=1", encoding="utf-8")
    srv = crear_servidor("127.0.0.1", 0, tmp_path / "datos", front)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def pedir(url, metodo="GET", datos=None, cabeceras=None, crudo=None):
    cab = {"X-DINAMO": "1", **(cabeceras or {})}
    cuerpo = crudo if crudo is not None else (json.dumps(datos).encode() if datos is not None else None)
    if cuerpo is not None and crudo is None:
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_estaticos_seguros(base):
    s, cuerpo, cab = pedir(base + "/")
    assert s == 200 and b"DINAMO" in cuerpo and "Content-Security-Policy" in cab
    for malo in ("/.secreto", "/../.env", "/%2e%2e/.env", "/..%2f.env", "/dinamo/servidor/app.py", "/.env"):
        assert pedir(base + malo)[0] == 404, malo


def test_escritura_requiere_cabecera_y_mismo_origen(base):
    req = urllib.request.Request(base + "/api/conversaciones", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403
    assert pedir(base + "/api/conversaciones", "POST", {}, {"Origin": "https://malicioso.com"})[0] == 403


def test_flujo_completo_sin_llm(base):
    s, cuerpo, _ = pedir(base + "/api/estado")
    estado = json.loads(cuerpo)
    assert estado["llm"] is None and estado["llm_navegador"] is True
    assert "clave" not in json.dumps(estado).lower() or "CLAVE=1" not in json.dumps(estado)

    s, cuerpo, _ = pedir(base + "/api/conversaciones", "POST", {"titulo": "Prueba"})
    cid = json.loads(cuerpo)["id"]
    s, cuerpo, _ = pedir(base + f"/api/conversaciones/{cid}/archivos", "POST", crudo=CSV,
                         cabeceras={"X-Nombre-Archivo": "empleados.csv", "Content-Type": "application/octet-stream"})
    assert s == 201 and json.loads(cuerpo)["archivo"]["tablas"][0]["filas"] == 40
    conv = json.loads(pedir(base + f"/api/conversaciones/{cid}")[1])
    assert conv["mensajes"] == []                                     # subir NO genera mensajes ni análisis

    s, cuerpo, cab = pedir(base + f"/api/conversaciones/{cid}/mensajes", "POST",
                           {"texto": "¿Cuál es la proporción de renuncias por área?"})
    eventos = [json.loads(l) for l in cuerpo.decode().splitlines() if l.strip()]
    assert cab["Content-Type"].startswith("application/x-ndjson")
    assert eventos[0]["tipo"] == "plan" and eventos[-1]["tipo"] == "final"
    assert any(e["tipo"] == "evidencias" for e in eventos)

    s, cuerpo, _ = pedir(base + f"/api/conversaciones/{cid}/tablas/empleados/vista?filas=5")
    assert len(json.loads(cuerpo)["filas"]) == 5

    s, cuerpo, _ = pedir(base + f"/api/conversaciones/{cid}/limpieza/proponer", "POST", {"archivo": "empleados.csv"})
    assert s == 200 and "problemas" in json.loads(cuerpo)

    s, _, _ = pedir(base + f"/api/conversaciones/{cid}/memoria", "POST", {"hecho": "Somos 40 personas"})
    assert s == 201
    assert pedir(base + f"/api/conversaciones/{cid}/descargas/archivos/..%2F..%2Fconversacion.json")[0] == 404
    assert pedir(base + f"/api/conversaciones/{cid}/descargas/archivos/empleados.csv")[0] == 200
    assert pedir(base + f"/api/conversaciones/{cid}", "DELETE")[0] == 200
    assert pedir(base + f"/api/conversaciones/{cid}")[0] == 404


def test_validaciones(base):
    assert pedir(base + "/api/conversaciones/../../etc")[0] == 404
    cid = json.loads(pedir(base + "/api/conversaciones", "POST", {})[1])["id"]
    s, cuerpo, _ = pedir(base + f"/api/conversaciones/{cid}/archivos", "POST", crudo=b"MZ...",
                         cabeceras={"X-Nombre-Archivo": "virus.exe"})
    assert s == 400 and "no admitido" in json.loads(cuerpo)["error"]
    assert pedir(base + f"/api/conversaciones/{cid}/mensajes", "POST", {"texto": "  "})[0] == 400
    assert pedir(base + f"/api/conversaciones/{cid}/investigacion", "POST", {"modo": "hackear", "consulta": "x"})[0] == 400
    s, cuerpo, _ = pedir(base + "/api/integraciones")
    filas = json.loads(cuerpo)["integraciones"]
    assert {f["id"] for f in filas} >= {"tavily", "openalex", "banco_mundial", "llm_ollama", "avatar_labios"}
    assert all(f["estado"] != "disponible" for f in filas if f["id"] != "llm_ollama")   # sin comprobar, no se afirma


def test_token_si_se_configura(tmp_path, monkeypatch):
    monkeypatch.setenv("DINAMO_TOKEN", "secreto123")
    monkeypatch.setattr("dinamo.llm.proveedores.Ollama.modelos", lambda self: [])
    front = tmp_path / "f"
    front.mkdir()
    (front / "index.html").write_text("x")
    srv = crear_servidor("127.0.0.1", 0, tmp_path / "d", front)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert pedir(base + "/api/estado")[0] == 401
        assert pedir(base + "/api/estado", cabeceras={"X-DINAMO-TOKEN": "secreto123"})[0] == 200
        s, _, cab = pedir(base + "/?token=secreto123")
        assert s == 200 and "HttpOnly" in cab.get("Set-Cookie", "")
    finally:
        srv.shutdown()


def test_no_escucha_fuera_sin_token(tmp_path, monkeypatch):
    monkeypatch.delenv("DINAMO_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        crear_servidor("0.0.0.0", 0, tmp_path / "d", tmp_path)
