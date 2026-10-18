"""
Escenarios obligatorios de la especificación (A–O) que se pueden probar sin servicios externos.
Todo es SIMULADO: LLM con guion y respuestas HTTP falsas. Datos sintéticos.
H (selección de personal) y M (autenticación multidispositivo) son de la Fase 2.
K (sincronización labial) no se implementa: el avatar no simula sincronía (ver docs).
L y O se prueban en la interfaz con tests/interfaz/prueba_interfaz.py (Playwright).
"""
import json
from pathlib import Path

import pytest
import requests

from dinamo.conversacion import Gestor
from dinamo.investigacion import buscadores as bus
from dinamo.orquestador import planificar, procesar

EJEMPLOS = Path(__file__).resolve().parents[1] / "ejemplos"


class LLMGuion:
    def __init__(self, plan, respuesta="Respuesta."):
        self.plan, self.respuesta, self.vistos = plan, respuesta, []

    def generar(self, sistema, usuario):
        return json.dumps(self.plan)

    def chat(self, mensajes, **kw):
        self.vistos.append(mensajes)
        yield self.respuesta

    def describir(self):
        return {"proveedor": "simulado"}


class Resp:
    def __init__(self, js, status=200):
        self._js, self.status_code = js, status

    def json(self):
        return self._js

    def raise_for_status(self):
        pass


@pytest.fixture
def gestor(tmp_path):
    return Gestor(tmp_path)


def test_A_subir_pdf_no_dispara_nada(gestor, monkeypatch):
    llamadas = []
    monkeypatch.setattr("dinamo.llm.client.LLMFalso.generar", lambda *a, **k: llamadas.append(1) or "")
    monkeypatch.setattr(bus, "tavily", lambda *a, **k: llamadas.append("web") or [])
    e = gestor.crear()
    ficha = e.agregar_archivo("informe_clima_laboral.pdf", (EJEMPLOS / "informe_clima_laboral.pdf").read_bytes())
    assert ficha["fragmentos_texto"] > 0
    assert e.mensajes == [] and e.investigaciones == [] and llamadas == []


def test_B_pregunta_fuera_del_documento_no_se_fuerza(gestor):
    e = gestor.crear()
    e.agregar_archivo("informe_clima_laboral.pdf", (EJEMPLOS / "informe_clima_laboral.pdf").read_bytes())
    plan = planificar("¿Quién fundó la empresa Toyota y cuál es su historia?", e, None)
    assert all(p["herramienta"] not in ("consultar_documentos", "analizar_datos") for p in plan.pasos)
    plan = planificar("¿Cuál es la temperatura actualmente en Ciudad de México?", e, None)
    assert [p["herramienta"] for p in plan.pasos] == ["investigar_web"]
    llm = LLMGuion({"pasos": []}, "Toyota fue fundada en 1937 (conocimiento general).")
    ev = list(procesar(e, "¿Quién fundó Toyota?", llm=llm))
    assert ev[-1]["mensaje"]["plan"]["pasos"] == []
    assert "no fuerces el archivo" in llm.vistos[-1][0]["content"]


def test_C_indicador_actual_con_periodo_y_fuente(gestor, monkeypatch):
    e = gestor.crear()
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp([{}, [{"countryiso3code": "MEX", "date": "2024", "value": 2.7}]]))
    ev = list(procesar(e, "¿Cuál es el desempleo actual de México según el Banco Mundial?"))
    final = ev[-1]["mensaje"]
    f = final["fuentes"][0]
    assert f["estado"] == "datos oficiales" and f["fecha_publicacion"] == "2024" and f["url"].startswith("https://data.worldbank.org")
    assert any(x["valor"] == 2.7 and x["filtros"]["anio"] == 2024 for x in final["evidencias"])


def test_C_si_falla_la_busqueda_lo_dice(gestor, monkeypatch):
    e = gestor.crear()
    def falla(*a, **k):
        raise requests.ConnectionError("sin red")
    monkeypatch.setattr(requests, "get", falla)
    monkeypatch.setattr(requests, "request", falla)
    ev = list(procesar(e, "investiga en internet la tasa de rotación promedio en México"))
    final = ev[-1]["mensaje"]
    assert final["fuentes"] == [] and any("sin conexión" in a for a in final["advertencias"])


def test_D_memoria_de_la_conversacion(gestor):
    e = gestor.crear()
    e.agregar_archivo("empleados.csv", (EJEMPLOS / "empleados.csv").read_bytes())
    list(procesar(e, "¿Cuál es la proporción de renuncias por área?"))
    llm = LLMGuion({"pasos": []}, "Resumen.")
    list(procesar(e, "Resume en una frase tu respuesta anterior", llm=llm))
    historial = " ".join(m["content"] for m in llm.vistos[-1])
    assert "proporción de renuncias" in historial and "[E:comparar_grupos:" in historial


def test_E_chats_independientes(gestor):
    a, b = gestor.crear(), gestor.crear()
    a.agregar_archivo("empleados.csv", (EJEMPLOS / "empleados.csv").read_bytes())
    b.agregar_archivo("ventas_tiendas.csv", (EJEMPLOS / "ventas_tiendas.csv").read_bytes())
    list(procesar(a, "¿Cuál es la proporción de renuncias por área?"))
    assert b.mensajes == [] and b.brain.evidencias.todas() == []
    assert {x["nombre"] for x in a.archivos} == {"empleados.csv"} and {x["nombre"] for x in b.archivos} == {"ventas_tiendas.csv"}


def test_F_limpieza_con_fechas_y_ausentes(gestor):
    csv = ("id,area,fecha_ingreso,salario\n1,Ventas,03/01/2023,1000\n2,ventas ,04/02/2023,\n2,ventas ,04/02/2023,\n"
           "3,TI,05/03/2023,1200\n4,TI,06/04/2023,1300\n5,Ventas,07/05/2023,1100\n")
    e = gestor.crear()
    e.agregar_archivo("base.csv", csv.encode())
    p = e.proponer_limpieza("base.csv")
    tipos = {x["tipo"] for x in p["problemas"]}
    assert {"filas duplicadas", "valores faltantes", "categorías inconsistentes", "fechas como texto"} <= tipos
    aprobadas = {x["id"]: x["accion"] for x in p["problemas"] if x["accion"]}
    r = e.aplicar_limpieza("base.csv", aprobadas)
    assert r["resultado"].endswith("_limpio_v1.csv") and r["registro"] and "df = pd.read_csv" in r["script_texto"]


def test_G_kpis_de_capital_humano_reproducibles(gestor):
    csv = "sucursal,mes,headcount,bajas,faltas,dias_habiles\n" + "\n".join(
        f"S{i % 3},{1 + i // 3},{100 + 10 * (i % 3)},{2 + i % 4},{30 + i},20" for i in range(12))
    e = gestor.crear()
    e.agregar_archivo("rrhh.csv", csv.encode())
    ev1 = list(procesar(e, "calcula la rotación, retención y ausentismo"))[-1]["mensaje"]["evidencias"]
    ev2 = list(procesar(e, "calcula la rotación, retención y ausentismo"))[-1]["mensaje"]["evidencias"]
    assert [x["id"] for x in ev1] == [x["id"] for x in ev2]
    nombres = {x["descripcion"].split(" — ")[0] for x in ev1}
    assert {"Rotación", "Retención", "Ausentismo"} <= nombres
    assert all(x["skill"] == "indicadores_talento" for x in ev1)


def test_I_comparacion_internacional_con_referencia(gestor, monkeypatch):
    e = gestor.crear()
    list(procesar(e, "El país de referencia es México"))
    pedido = {}
    def get(url, params=None, **k):
        pedido["url"] = url
        return Resp([{}, [{"countryiso3code": c, "date": "2023", "value": v} for c, v in (("COL", 10.2), ("ESP", 12.1), ("MEX", 2.8))]])
    monkeypatch.setattr(requests, "get", get)
    final = list(procesar(e, "Compara la tasa de participación laboral de Colombia y España con el país de referencia"))[-1]["mensaje"]
    assert "COL;ESP;MEX" in pedido["url"] and "SL.TLF.CACT.ZS" in pedido["url"]
    assert {x["filtros"]["pais"] for x in final["evidencias"]} == {"COL", "ESP", "MEX"}
    assert all(x["unidad"] == "porcentaje" and "World Development Indicators" in x["metodo"] for x in final["evidencias"])


@pytest.mark.parametrize("pregunta,tipo", [("haz un gráfico de dispersión del salario", "dispersion"),
                                            ("muéstrame un histograma de salarios", "histograma"),
                                            ("grafica la evolución de las ventas en una serie de líneas", "lineas")])
def test_J_tipo_de_grafico_pedido(gestor, pregunta, tipo):
    e = gestor.crear()
    e.agregar_archivo("empleados.csv", (EJEMPLOS / "empleados.csv").read_bytes())
    assert planificar(pregunta, e, None).grafico == tipo


def test_N_api_sin_configurar_no_inventa(monkeypatch):
    from dinamo.investigacion import integraciones
    for v in ("BRAVE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("dinamo.llm.proveedores.Ollama.modelos", lambda self: [])
    filas = {f["id"]: f for f in integraciones()}
    assert filas["brave"]["estado"] == "sin configurar" and "BRAVE_API_KEY" in filas["brave"]["detalle"]
    assert filas["llm_gemini"]["estado"] == "sin configurar"
    with pytest.raises(bus.ErrorBuscador, match="BRAVE_API_KEY"):
        bus.brave("x")


def test_J_histograma_y_dispersion_usan_todos_los_datos(gestor):
    e = gestor.crear()
    e.agregar_archivo("empleados.csv", (EJEMPLOS / "empleados.csv").read_bytes())
    final = list(procesar(e, "muéstrame un histograma del salario mensual"))[-1]["mensaje"]
    cubos = final["datos"]["histograma"]
    assert sum(c["conteo"] for c in cubos) == 120 and final["grafico"] == "histograma"
    final = list(procesar(e, "gráfico de dispersión entre satisfaccion y salario mensual"))[-1]["mensaje"]
    assert len(final["datos"]["dispersion"]) == 120
    assert final["evidencias"][0]["unidad"] == "rho"
