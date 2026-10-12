from dinamo.core.contracts import crear_evidencia
from dinamo.llm import LLMFalso, citas_invalidas, construir_mensajes, formatear_valor


def ev(valor, unidad):
    return crear_evidencia("s", "d", valor, unidad, 1, "m")


def test_formatea_valores_para_que_el_llm_no_calcule():
    assert formatear_valor(ev(0.0931, "proporcion")) == "9.3%"
    assert formatear_valor(ev(-0.035, "diferencia_proporcion")) == "-3.5 puntos porcentuales"
    assert formatear_valor(ev(-1234.4, "moneda")) == "-$1,234"
    assert formatear_valor(ev(0.2, "cambio_relativo")) == "+20.0%"
    assert formatear_valor(ev("2024-03", "texto")) == "2024-03"


def test_prompt_incluye_ids_reglas_y_descripcion_de_la_base():
    e = crear_evidencia("s", "Mediana", 0.1, "proporcion", 5, "mediana")
    sistema, usuario = construir_mensajes("¿Quejas?", [], [e], sobre_la_base="Tiendas de ropa")
    assert f"[E:{e.id}]" in usuario and "Tiendas de ropa" in usuario and "causalidad" in sistema.lower()


def test_citas_invalidas():
    assert citas_invalidas("x [E:a:1] y [E:b:2]", {"a:1"}) == ["b:2"]


def test_llm_falso_es_deterministico():
    _, u = construir_mensajes("q", [], [ev(0.1, "proporcion")])
    assert LLMFalso().generar("", u) == LLMFalso().generar("", u)
