import pytest

from dinamo.core.contracts import Pregunta


@pytest.mark.parametrize("texto, intencion, metrica", [
    ("¿Qué datos tienes?", "describir_datos", None),
    ("¿Cómo han evolucionado las ventas?", "tendencia", "ventas"),
    ("¿Qué tiendas tienen la mayor tasa de quejas?", "ranking", "tasa_quejas"),
    ("Compara las ventas por región", "comparar_grupos", "ventas"),
    ("¿Qué factores se relacionan con los reclamos?", "relaciones", "tasa_quejas"),
    ("Cuéntame de la Tienda Plaza", "perfil_entidad", "ventas"),
    ("Hola", "desconocida", None),
])
def test_interpreta_intencion_y_metrica(brain_panel, texto, intencion, metrica):
    plan = brain_panel.interpretar(Pregunta(texto))
    assert plan.intencion == intencion
    assert plan.metrica == metrica


def test_el_vocabulario_sale_del_perfil_no_del_codigo(brain_simple):
    plan = brain_simple.interpretar(Pregunta("¿Quiénes tienen el mayor salario?"))
    assert plan.intencion == "ranking" and plan.metrica == "salario_mensual"


def test_valor_de_dimension_se_vuelve_filtro(brain_panel):
    plan = brain_panel.interpretar(Pregunta("¿Cómo han evolucionado las ventas en el Norte?"))
    assert plan.filtros == {"region": "Norte"}


def test_dos_valores_de_una_dimension_son_una_comparacion(brain_panel):
    plan = brain_panel.interpretar(Pregunta("ventas del Norte vs Sur"))
    assert plan.intencion == "comparar_grupos" and plan.dimension == "region"


def test_detecta_entidad_por_nombre_o_por_numero(brain_panel):
    assert brain_panel.interpretar(Pregunta("ventas de la Tienda Centro")).filtros == {"tienda_id": 1}
    assert brain_panel.interpretar(Pregunta("ventas de la tienda 2")).filtros == {"tienda_id": 2}


def test_detecta_el_ultimo_periodo(brain_panel):
    plan = brain_panel.interpretar(Pregunta("¿Qué tiendas tuvieron más ventas en el último mes?"))
    assert plan.filtros == {"mes": "2024-03"}


def test_menor_ordena_de_menor_a_mayor(brain_panel):
    assert brain_panel.interpretar(Pregunta("tiendas con menor ventas")).orden == "asc"


def test_mejores_depende_de_si_mas_alto_es_mejor(brain_panel):
    # en tasa_quejas, más alto es PEOR: las "mejores" tiendas son las de menos quejas
    assert brain_panel.interpretar(Pregunta("las mejores tiendas en quejas")).orden == "asc"


def test_no_confunde_trabajo_con_bajo(brain_panel):
    plan = brain_panel.interpretar(Pregunta("quejas en el trabajo"))
    assert plan.intencion == "tendencia" and plan.confianza == 0.4


def test_pregunta_de_seguimiento(brain_panel):
    brain_panel.responder("¿Cómo han evolucionado las quejas?")
    plan = brain_panel.interpretar(Pregunta("¿y en el Sur?"))
    assert plan.intencion == "tendencia" and plan.metrica == "tasa_quejas" and plan.filtros == {"region": "Sur"}


def test_nombre_de_entidad_no_se_confunde_con_una_categoria():
    """'Tienda Norte' es una tienda, no un filtro de la región 'Norte'."""
    import pandas as pd
    from dinamo.data_engine import DataEngine
    from dinamo.brain import Interprete
    tabla = pd.DataFrame({"tienda_id": [1, 1, 2, 2], "tienda": ["Tienda Norte", "Tienda Norte", "Plaza", "Plaza"],
                          "mes": ["2024-01", "2024-02"] * 2, "region": ["Sur", "Sur", "Norte", "Norte"],
                          "ventas": [1, 2, 3, 4]})
    d = DataEngine.desde_tabla(tabla, nombre="t")
    plan = Interprete(d.perfil, d.periodos(), d.entidades()).interpretar("Cuéntame de la Tienda Norte")
    assert plan.intencion == "perfil_entidad" and plan.filtros == {"tienda_id": 1}


def test_un_saludo_no_hereda_la_pregunta_anterior(brain_panel):
    brain_panel.responder("¿Cómo han evolucionado las ventas?")
    assert brain_panel.interpretar(Pregunta("Hola")).intencion == "desconocida"


def test_que_entidades_tienen_menos_es_un_ranking_ascendente(brain_panel):
    plan = brain_panel.interpretar(Pregunta("¿Qué tiendas tienen menos quejas?"))
    assert (plan.intencion, plan.metrica, plan.orden) == ("ranking", "tasa_quejas", "asc")


def test_reconoce_variantes_de_una_palabra(brain_simple):
    # la columna se llama 'renuncio'; el usuario escribe 'renuncia'
    assert brain_simple.interpretar(Pregunta("¿Qué se relaciona con la renuncia?")).metrica == "renuncio"


def test_que_categoria_tiene_mas_es_comparar_grupos(brain_simple):
    plan = brain_simple.interpretar(Pregunta("¿Qué áreas tienen mayor salario?"))
    assert plan.intencion == "comparar_grupos" and plan.dimension == "area"


# ---------------------------------------------------------------------- conversación interactiva (v2)
def test_si_no_dice_el_indicador_pregunta_cual(brain_panel):
    r = brain_panel.responder("¿Qué tiendas son las mejores?")
    assert r.aclaracion is not None and not r.evidencias
    assert any("ventas" in o for o in r.aclaracion.opciones)
    r2 = brain_panel.responder("1")                       # el usuario responde con el número
    assert r2.aclaracion is None and r2.plan.intencion == "ranking" and r2.evidencias


def test_cada_pregunta_va_a_la_fuente_que_la_responde(brain_doble):
    assert brain_doble.responder("¿Cómo han evolucionado las ventas?").plan.tabla == "tiendas"
    assert brain_doble.responder("¿Qué empleados tienen mayor salario?").plan.tabla == "empleados"
    # una pregunta de seguimiento sin fuente clara sigue con la última usada
    assert brain_doble.responder("¿y el menor?").plan.tabla == "empleados"


def test_si_dos_fuentes_empatan_pregunta_cual(datos_panel, datos_simple):
    import pandas as pd

    from dinamo.brain import Brain
    from dinamo.data_engine import Biblioteca, DataEngine
    from dinamo.llm import LLMFalso
    from dinamo.rac import Retriever
    from dinamo.skills import crear_registro

    norte = DataEngine.desde_tabla(pd.DataFrame({"sucursal": ["A", "B"], "ventas": [1, 2]}), nombre="norte")
    sur = DataEngine.desde_tabla(pd.DataFrame({"sucursal": ["C", "D"], "ventas": [3, 4]}), nombre="sur")
    brain = Brain(Biblioteca.desde_motores(datos_simple, norte, sur), crear_registro(), Retriever(), LLMFalso())
    r = brain.responder("¿Qué sucursales tienen mayores ventas?")      # norte y sur empatan; activa = empleados
    assert r.aclaracion is not None and len(r.aclaracion.opciones) == 2
    elegida = brain.responder("2")
    assert elegida.plan.tabla == "sur" and elegida.evidencias


def test_el_perfil_del_usuario_llega_al_llm_pero_no_cambia_los_numeros(brain_panel):
    class LLMEspia:
        def generar(self, sistema, usuario):
            self.visto = usuario
            return "ok"
    espia = LLMEspia()
    antes = brain_panel.responder("¿Cómo han evolucionado las ventas?").evidencias
    brain_panel.llm = espia
    brain_panel.cambiar_usuario(nombre="Ana", rol="Gerente de RR. HH.", nivel="directivo")
    despues = brain_panel.responder("¿Cómo han evolucionado las ventas?").evidencias
    assert "Ana, Gerente de RR. HH." in espia.visto and "directivo" in espia.visto
    assert antes == despues


def test_bienvenida_lista_las_fuentes_y_propone_preguntas(brain_doble):
    r = brain_doble.bienvenida()
    assert "tiendas" in r.texto and "empleados" in r.texto and len(r.sugerencias) >= 2
