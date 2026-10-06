"""Pruebas del validador de cifras y citas (tarea C2)."""
from dinamo.core.contracts import crear_evidencia
from dinamo.llm import formatear_valor
from dinamo.llm.prompts import (cifras_sin_cita, cifras_sin_respaldo, citas_invalidas, plantilla_respaldo)

E1 = crear_evidencia("kpi_por_periodo", "Mediana de rotación, Julio - Agosto 2024", 0.104, "proporcion", 32, "mediana")
E2 = crear_evidencia("kpi_por_periodo", "Mediana de rotación, Julio - Agosto 2025", 0.057, "proporcion", 35, "mediana")
EVID = [E1, E2]


def bueno() -> str:
    return (f"La mediana pasó de {formatear_valor(E1)} [E:{E1.id}] a {formatear_valor(E2)} [E:{E2.id}], "
            f"con 32 y 35 empresas.")


def test_texto_correcto_no_marca_nada():
    assert cifras_sin_respaldo(bueno(), EVID) == []
    assert citas_invalidas(bueno(), EVID) == []


def test_detecta_cifra_inventada():
    """Un LLM falso que inventa «50%» debe ser detectado."""
    assert "50" in cifras_sin_respaldo(f"Bajó 50% [E:{E1.id}].", EVID)


def test_detecta_cifra_calculada_por_el_llm():
    """El LLM no calcula: '4.7 puntos' (10.4 - 5.7) no está en ninguna evidencia."""
    assert "4.7" in cifras_sin_respaldo(f"Bajó 4.7 puntos [E:{E2.id}].", EVID)


def test_acepta_coma_decimal_y_formato_espanol():
    assert cifras_sin_respaldo(f"La rotación fue de 10,4% [E:{E1.id}].", EVID) == []


def test_acepta_miles_con_coma():
    e = crear_evidencia("kpi", "Headcount total del periodo", 35200, "empresas", 40, "suma")
    assert cifras_sin_respaldo(f"Hay 35,200 personas [E:{e.id}].", [e]) == []


def test_ignora_ids_y_numeracion_de_listas():
    texto = f"1. La rotación bajó [E:{E1.id}].\n2. Sigue baja [E:{E2.id}]."
    assert cifras_sin_respaldo(texto, EVID) == []


def test_numeros_de_la_pregunta_son_validos():
    """Si el usuario dijo 'compañía 7', el LLM puede repetir el 7."""
    assert cifras_sin_respaldo("La compañía 7 va bien.", EVID, pregunta="¿Cómo va la compañía 7?") == []
    assert cifras_sin_respaldo("La compañía 7 va bien.", EVID) == ["7"]


def test_numeros_del_contexto_son_validos():
    from dinamo.core.contracts import Contexto
    ctx = [Contexto("glosario.md#Aguinaldo", "El aguinaldo mínimo es de 15 días de salario.", 0.5)]
    assert cifras_sin_respaldo("La ley pide 15 días.", [], ctx) == []


def test_citas_inventadas():
    assert citas_invalidas(f"Dato [E:{E1.id}] y otro [E:kpi:zzzz].", EVID) == ["kpi:zzzz"]


def test_frase_con_cifra_sin_cita():
    texto = f"Bajó [E:{E1.id}]. La mediana es 5.7%."
    assert cifras_sin_cita(texto) == ["La mediana es 5.7%."]


def test_plantilla_respaldo_cita_todo_y_pasa_sus_propios_validadores():
    texto = plantilla_respaldo(EVID)
    assert cifras_sin_respaldo(texto, EVID) == [] and citas_invalidas(texto, EVID) == []
    assert cifras_sin_cita(texto) == []
