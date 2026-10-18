"""Orquestador: planes, herramientas, síntesis y verificación. LLM y red SIMULADOS; datos sintéticos."""
import json
from pathlib import Path

import pytest

from dinamo.conversacion import Gestor
from dinamo.investigacion import buscadores as bus
from dinamo.orquestador import completar_desde_navegador, corregir, planificar, procesar, verificar
from dinamo.orquestador.herramientas import Material
from dinamo.orquestador.planificador import extraer_json, validar

EJEMPLOS = Path(__file__).resolve().parents[1] / "ejemplos"


class LLMGuion:
    """LLM simulado: responde al planificador con un JSON y a la síntesis con un texto fijo."""

    def __init__(self, plan: dict | None, respuesta: str):
        self.plan, self.respuesta, self.llamadas = plan, respuesta, []

    def generar(self, sistema, usuario):
        self.llamadas.append(("generar", sistema[:30]))
        return json.dumps(self.plan) if self.plan is not None else "no es json"

    def chat(self, mensajes, **kw):
        self.llamadas.append(("chat", mensajes[-1]["content"]))
        yield from [self.respuesta[:10], self.respuesta[10:]]

    def describir(self):
        return {"proveedor": "simulado", "modelo": "guion", "nube": False}


@pytest.fixture
def espacio(tmp_path):
    e = Gestor(tmp_path).crear()
    e.agregar_archivo("empleados.csv", (EJEMPLOS / "empleados.csv").read_bytes())
    return e


def eventos(gen):
    return list(gen)


def test_correccion_ortografica():
    assert corregir("investgia la rotasion de enpleados").split() == ["investiga", "la", "rotacion", "de", "empleados"]


def test_extraer_y_validar_json_del_llm():
    d = extraer_json('Claro:\n```json\n{"pregunta_normalizada": "x", "pasos": [{"herramienta": "analizar_datos", '
                     '"argumentos": {}}], "aclaracion": null}\n```')
    assert validar(d, "x").pasos[0]["herramienta"] == "analizar_datos"
    assert validar({"pasos": [{"herramienta": "borrar_disco"}]}, "x") is None     # fuera de la lista blanca


def test_sin_llm_responde_con_material_verificado(espacio):
    ev = eventos(procesar(espacio, "¿Cuál es la proporción de renuncias por área?"))
    tipos = [e["tipo"] for e in ev]
    assert tipos[0] == "plan" and "evidencias" in tipos and tipos[-1] == "final"
    final = ev[-1]["mensaje"]
    assert "[E:comparar_grupos:" in final["texto"] and final["modelo"]["proveedor"] == "ninguno"
    assert final["evidencias"] and final["datos"]


def test_con_llm_plan_y_citas_validas(espacio):
    llm = LLMGuion({"pregunta_normalizada": "proporción de renuncias por área",
                    "pasos": [{"herramienta": "analizar_datos", "argumentos": {"pregunta": "renuncias por área"}}]}, "")
    # primero se ejecuta para conocer un id real de evidencia
    ev = eventos(procesar(espacio, "renuncias x area", llm=None))
    eid = ev[-1]["mensaje"]["evidencias"][0]["id"]
    llm.respuesta = f"En Ventas la proporción es mayor [E:{eid}]. Además 87% de algo [E:inventada:1234]."
    ev = eventos(procesar(espacio, "renuncias x area", llm=llm))
    final = ev[-1]["mensaje"]
    assert ev[0]["plan"]["origen"] == "llm"
    assert "".join(e["delta"] for e in ev if e["tipo"] == "texto") == llm.respuesta
    assert any("E:inventada:1234" in p for p in final["verificacion"])
    assert any("87%" in p for p in final["verificacion"])                 # cifra fuera del material
    assert "EVIDENCIA (calculada por Python)" in llm.llamadas[-1][1]


def test_plan_invalido_del_llm_cae_a_reglas(espacio):
    llm = LLMGuion(None, "Hola")
    plan = planificar("¿cuál es el salario promedio por área?", espacio, llm)
    assert plan.origen == "reglas" and plan.pasos[0]["herramienta"] == "analizar_datos"


def test_investigacion_integrada_con_citas_web(espacio, monkeypatch):
    largo = "Las estrategias de retención incluyen desarrollo profesional y reconocimiento. " * 40
    monkeypatch.setattr(bus, "tavily", lambda q, n, **k: [bus.Resultado("Guía de retención", "https://www.oecd.org/x",
                                                                        "frag", "tavily", "2025-02-01", largo)])
    llm = LLMGuion({"pasos": [{"herramienta": "investigar_web", "argumentos": {"consulta": "retención de talento"}}]},
                   "Según la OCDE conviene invertir en desarrollo [W:1]. También [W:7].")
    ev = eventos(procesar(espacio, "investiga cómo retener talento", llm=llm))
    fuentes = next(e for e in ev if e["tipo"] == "fuentes")["items"]
    assert fuentes[0]["id"] == "W:1" and fuentes[0]["estado"] == "leída" and fuentes[0]["tipo"] == "organismo internacional"
    final = ev[-1]["mensaje"]
    assert any("W:7" in p for p in final["verificacion"]) and not any("W:1," in p for p in final["verificacion"])
    assert espacio.investigaciones and espacio.investigaciones[-1]["modo"] == "web"


def test_memoria_y_pais_de_referencia(espacio):
    eventos(procesar(espacio, "Recuerda que la plantilla total es de 300 personas"))
    assert espacio.memoria[0]["hecho"] == "la plantilla total es de 300 personas"
    eventos(procesar(espacio, "El país de referencia es Colombia"))
    assert espacio.preferencias["pais_referencia"] == "COL"
    llm = LLMGuion({"pasos": []}, "ok")
    eventos(procesar(espacio, "¿qué sabes de mi empresa?", llm=llm))
    assert "300 personas" in llm.llamadas[-1][1]                         # la memoria llega al LLM


def test_aclaracion_cuando_hay_varias_metricas(tmp_path):
    e = Gestor(tmp_path).crear()
    e.agregar_archivo("ventas_tiendas.csv", (EJEMPLOS / "ventas_tiendas.csv").read_bytes())
    ev = eventos(procesar(e, "¿cómo ha evolucionado?"))
    tipos = [x["tipo"] for x in ev]
    assert "aclaracion" in tipos or "evidencias" in tipos            # pregunta sólo si la base es ambigua


def test_llm_del_navegador(espacio):
    ev = eventos(procesar(espacio, "proporción de renuncias por área", llm_en_navegador=True))
    pedido = ev[-1]
    assert pedido["tipo"] == "necesita_llm" and pedido["mensajes"][0]["role"] == "system"
    m = completar_desde_navegador(espacio, pedido["mensaje_id"], "Todo sube 99% [E:no:existe]")
    assert m["pendiente"] is False and m["verificacion"]


def test_charla_general_sin_herramientas(espacio):
    llm = LLMGuion({"pasos": []}, "¡Hola! Soy DINAMO.")
    ev = eventos(procesar(espacio, "hola", llm=llm))
    assert ev[0]["plan"]["pasos"] == [] and ev[-1]["mensaje"]["texto"] == "¡Hola! Soy DINAMO."


def test_verificar_acepta_cifras_del_material():
    from dinamo.core.contracts import crear_evidencia
    e = crear_evidencia("x", "Rotación", 0.072, "proporcion", 10, "m")
    m = Material(evidencias=[e])
    assert verificar(f"La rotación es 7.2% [E:{e.id}]", m) == []


def test_verificar_no_acepta_coincidencias_parciales():
    from dinamo.core.contracts import crear_evidencia
    e = crear_evidencia("x", "Rotación", 0.1999, "proporcion", 10, "m")      # se muestra como 20.0%
    m = Material(evidencias=[e])
    assert verificar("Es 20.0%", m) == []
    assert any("99%" in p for p in verificar("Es 99%", m))
    assert any("1.5" in p for p in verificar("Sube 1.5 veces", m))
