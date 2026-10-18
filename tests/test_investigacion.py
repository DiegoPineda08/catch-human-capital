"""Investigación web: SIMULADA (respuestas HTTP falsas). No se contacta ningún servicio real en estos tests."""
import json
import socket

import pytest
import requests

from dinamo.investigacion import URLBloqueada, clasificar, investigar, validar_url
from dinamo.investigacion import buscadores as bus
from dinamo.investigacion import estadisticas as est
from dinamo.investigacion import red
from dinamo.investigacion.fuentes import BLOQUEADA, DATOS, LEIDA, SOLO_FRAGMENTO, SOLO_RESUMEN
from dinamo.investigacion.lector import leer_html, pasajes


def resolver_publico(host, puerto, *a, **k):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", puerto))]


def resolver_privado(host, puerto, *a, **k):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", puerto))]


class Resp:
    def __init__(self, status=200, cuerpo=b"", cab=None, js=None):
        self.status_code, self._c, self.headers, self._js = status, cuerpo, cab or {"Content-Type": "text/html"}, js
        self.text = cuerpo.decode() if isinstance(cuerpo, bytes) else str(cuerpo)

    def iter_content(self, n):
        for i in range(0, len(self._c), n):
            yield self._c[i:i + n]

    def json(self):
        if self._js is None:
            raise ValueError
        return self._js

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


# ------------------------------------------------------------------------------- seguridad (SSRF)
@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.com/a", "http://localhost:8000/", "http://user:pw@x.com",
                                 "http://intranet.local/", "javascript:alert(1)"])
def test_urls_peligrosas_se_bloquean(url):
    with pytest.raises(URLBloqueada):
        validar_url(url, resolver_publico)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0", "100.64.0.1"])
def test_ips_privadas_se_bloquean(ip):
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    with pytest.raises(URLBloqueada):
        validar_url("http://ejemplo.com/", lambda *a, **k: [(fam, 1, 6, "", (ip, 80))])


def test_redireccion_a_red_privada_se_bloquea(monkeypatch):
    llamadas = []

    class Sesion:
        def get(self, url, **kw):
            llamadas.append(url)
            return Resp(302, cab={"Location": "http://interno.empresa/"})

    resolver = lambda h, p, *a, **k: resolver_privado(h, p) if h == "interno.empresa" else resolver_publico(h, p)
    with pytest.raises(URLBloqueada, match="privada"):
        red.descargar("https://ejemplo.com/", resolver=resolver, sesion=Sesion())
    assert llamadas == ["https://ejemplo.com/"]


def test_tamano_y_tipo_limitados():
    class Grande:
        def get(self, url, **kw):
            return Resp(200, b"x" * 5000)

    with pytest.raises(URLBloqueada, match="grande"):
        red.descargar("https://ejemplo.com/", tamano_maximo=1000, resolver=resolver_publico, sesion=Grande())

    class Binario:
        def get(self, url, **kw):
            return Resp(200, b"MZ", {"Content-Type": "application/octet-stream"})

    with pytest.raises(URLBloqueada, match="Tipo"):
        red.descargar("https://ejemplo.com/", resolver=resolver_publico, sesion=Binario())


# ------------------------------------------------------------------------------------- lectura
HTML = """<html><head><title>Rotación de personal en 2025</title>
<meta name="author" content="Ana Pérez"><meta property="article:published_time" content="2025-03-02">
<meta name="description" content="Análisis de la rotación."></head>
<body><nav>Menú Inicio Contacto</nav><script>var x = 1;</script>
<article><p>La rotación voluntaria de personal aumentó en el sector manufacturero durante 2024, según la encuesta anual.</p>
<p>Las empresas con programas de capacitación mostraron menor rotación de personal en el primer año de contrato.</p>
<p>Este párrafo habla del clima en la ciudad y no tiene nada que ver con el tema principal.</p></article>
<footer>Copyright</footer></body></html>"""


def test_lector_extrae_texto_y_metadatos():
    p = leer_html(HTML, "https://www.revista.com/a")
    assert p.titulo == "Rotación de personal en 2025"
    assert p.autores == ["Ana Pérez"] and p.fecha_publicacion == "2025-03-02"
    assert "var x" not in p.texto and "Menú" not in p.texto and "Copyright" not in p.texto
    assert p.dominio == "revista.com"
    elegidos = pasajes(p.texto, "¿qué pasa con la rotación de personal y la capacitación?", k=1)
    assert "capacitación" in elegidos[0]


def test_clasificacion_con_justificacion():
    assert clasificar("https://www.inegi.org.mx/temas/empleo/")[0] == "fuente oficial"
    assert clasificar("https://www.oecd.org/employment/")[0] == "organismo internacional"
    assert clasificar("https://doi.org/10.1/abc")[0] == "fuente académica"
    assert clasificar("https://es.wikipedia.org/wiki/X")[0] == "enciclopedia"
    assert clasificar("https://www.elfinanciero.com.mx/a")[0] == "medio de noticias"
    tipo, just = clasificar("https://blog-cualquiera.net/post")
    assert tipo == "sitio web" and "no se verificó" in just


# --------------------------------------------------------------------------------- pipeline web
def test_pipeline_web_estados_de_lectura_honestos(monkeypatch):
    largo = "La rotación de personal es un indicador clave. " * 60
    monkeypatch.setattr(bus, "tavily", lambda q, n, **k: [
        bus.Resultado("Con texto", "https://a.com/1", "fragmento a", "tavily", "2025-01-01", largo),
        bus.Resultado("Sin texto", "https://b.com/2", "fragmento b", "tavily"),
        bus.Resultado("Bloqueada", "https://c.com/3", "", "tavily"),
    ])

    def descargar_falso(url, **kw):
        raise URLBloqueada("El sitio respondió con error 403.")
    monkeypatch.setattr("dinamo.investigacion.investigador.descargar", descargar_falso)
    inv = investigar("rotación de personal", "web")
    estados = {f.titulo: f.estado for f in inv.fuentes}
    assert estados == {"Con texto": LEIDA, "Sin texto": SOLO_FRAGMENTO, "Bloqueada": BLOQUEADA}
    assert [f.id for f in inv.fuentes] == ["W:1", "W:2", "W:3"]
    assert inv.fuentes[0].pasajes and inv.fuentes[0].fecha_consulta
    assert inv.a_dict()["resumen_lectura"][LEIDA] == 1


def test_pipeline_cae_al_respaldo_si_tavily_falla(monkeypatch):
    def falla(*a, **k):
        raise bus.ErrorBuscador("Tavily: se alcanzó el límite de uso gratuito")
    monkeypatch.setattr(bus, "tavily", falla)
    monkeypatch.setattr(bus, "wikipedia", lambda q, n: [bus.Resultado("Rotación", "https://es.wikipedia.org/wiki/R", "x", "wikipedia")])
    monkeypatch.setattr("dinamo.investigacion.investigador.descargar",
                        lambda url, **kw: (_ for _ in ()).throw(URLBloqueada("sin red")))
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    inv = investigar("rotación", "web")
    assert inv.proveedores == ["wikipedia"] and "límite" in inv.avisos[0]
    assert inv.fuentes[0].tipo == "enciclopedia"


def test_sin_resultados_no_inventa(monkeypatch):
    monkeypatch.setattr(bus, "tavily", lambda *a, **k: [])
    monkeypatch.setattr(bus, "wikipedia", lambda *a, **k: [])
    inv = investigar("xyzzy", "web")
    assert inv.fuentes == [] and inv.avisos


def test_openalex_reconstruye_resumen(monkeypatch):
    js = {"results": [{"display_name": "Employee turnover meta-analysis", "doi": "https://doi.org/10.1/x",
                       "publication_date": "2020-05-01", "abstract_inverted_index": {"Turnover": [0], "matters": [1]},
                       "authorships": [{"author": {"display_name": "J. Doe"}}], "cited_by_count": 12,
                       "primary_location": {"source": {"display_name": "J. Applied Psych"}},
                       "open_access": {"is_oa": False}}]}
    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp(200, js=js))
    r = bus.openalex("turnover", 1)[0]
    assert r.fragmento == "Turnover matters" and r.extra["doi"] == "10.1/x" and r.extra["citas"] == 12


def test_academico_deduplica_y_no_dice_leido(monkeypatch):
    a = bus.Resultado("Paper A", "https://doi.org/10.1/a", "Resumen largo " * 30, "openalex", "2021",
                      extra={"doi": "10.1/a"})
    b = bus.Resultado("Paper A", "https://doi.org/10.1/a", "", "crossref", "2021", extra={"doi": "10.1/A"})
    monkeypatch.setattr(bus, "openalex", lambda q, n: [a])
    monkeypatch.setattr(bus, "crossref", lambda q, n: [b])
    monkeypatch.setattr(bus, "semantic_scholar", lambda q, n: (_ for _ in ()).throw(bus.ErrorBuscador("S2: límite")))
    inv = investigar("turnover", "academico")
    assert len(inv.fuentes) == 1 and inv.fuentes[0].estado == SOLO_RESUMEN
    assert inv.fuentes[0].tipo == "artículo científico"


# ----------------------------------------------------------------------------- estadísticas
def test_banco_mundial_evidencias_sin_inventar(monkeypatch):
    js = [{"page": 1}, [
        {"countryiso3code": "MEX", "date": "2023", "value": 2.8},
        {"countryiso3code": "MEX", "date": "2022", "value": 3.3},
        {"countryiso3code": "COL", "date": "2023", "value": 10.2},
        {"countryiso3code": "COL", "date": "2022", "value": None},
    ]]
    capturado = {}

    def get(url, params=None, **k):
        capturado["url"] = url
        return Resp(200, js=js)
    monkeypatch.setattr(requests, "get", get)
    inv = investigar("Compara el desempleo de México y Colombia", "estadisticas")
    assert "MEX;COL" in capturado["url"] and "SL.UEM.TOTL.ZS" in capturado["url"]
    assert [f.estado for f in inv.fuentes] == [DATOS, DATOS]
    valores = {(e.filtros["pais"], e.filtros["anio"]): e.valor for e in inv.evidencias}
    assert valores == {("MEX", 2022): 3.3, ("MEX", 2023): 2.8, ("COL", 2023): 10.2}
    assert all(e.skill == "banco_mundial" for e in inv.evidencias)


def test_pais_referencia_se_sugiere_no_se_impone(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(200, js=[{}, [{"countryiso3code": "ESP", "date": "2023", "value": 12.0}]]))
    inv = investigar("desempleo", "estadisticas", paises=["ESP"])
    assert inv.fuentes[0].titulo.endswith("España") and not inv.avisos
    assert est.paises_en("México vs Colombia y la OCDE") == ["MEX", "COL", "OED"]
