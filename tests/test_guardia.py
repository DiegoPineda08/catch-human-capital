"""Pruebas de la guardia: el usuario siempre recibe un texto válido."""
from dinamo.core.contracts import crear_evidencia
from dinamo.llm import formatear_valor
from dinamo.llm.guardia import responder_con_guardia
from dinamo.llm.prompts import cifras_sin_respaldo, citas_invalidas

E1 = crear_evidencia("kpi_por_periodo", "Mediana de rotación, Julio - Agosto 2024", 0.104, "proporcion", 32, "mediana")
EVID = [E1]
BUENO = f"La mediana de rotación fue {formatear_valor(E1)} [E:{E1.id}]."


class LLMGuion:
    """LLM falso que responde lo que se le programe, en orden."""
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas, self.prompts = list(respuestas), 0, []

    def generar(self, sistema, usuario):
        self.llamadas += 1
        self.prompts.append(usuario)
        return self.respuestas.pop(0)


class LLMRoto:
    def generar(self, sistema, usuario):
        raise ConnectionError("Ollama apagado")


def test_respuesta_buena_pasa_al_primer_intento():
    llm = LLMGuion(BUENO)
    r = responder_con_guardia(llm, "¿Cómo va la rotación?", EVID)
    assert (r.texto, r.intentos, r.uso_plantilla) == (BUENO, 1, False)


def test_reintenta_con_correcciones_cuando_inventa():
    llm = LLMGuion("Bajó 50%.", BUENO)
    r = responder_con_guardia(llm, "q", EVID)
    assert r.texto == BUENO and r.intentos == 2
    assert "50" in llm.prompts[1] and "problemas" in llm.prompts[1]   # el 2º prompt incluye la corrección


def test_dos_fallos_usan_la_plantilla_y_avisan():
    r = responder_con_guardia(LLMGuion("Bajó 50%.", "Bajó 60%."), "q", EVID)
    assert r.uso_plantilla and r.intentos == 2 and r.advertencias
    assert cifras_sin_respaldo(r.texto, EVID) == [] and citas_invalidas(r.texto, EVID) == []


def test_llm_apagado_responde_igual_con_advertencia():
    r = responder_con_guardia(LLMRoto(), "q", EVID)
    assert r.uso_plantilla and "no está disponible" in r.advertencias[0]
    assert f"[E:{E1.id}]" in r.texto


def test_sin_evidencias_ni_contexto_no_llama_al_llm():
    llm = LLMGuion()
    r = responder_con_guardia(llm, "¿Capital de Francia?", [])
    assert llm.llamadas == 0 and "No tengo datos" in r.texto


def test_pregunta_conceptual_solo_con_contexto():
    from dinamo.core.contracts import Contexto
    ctx = [Contexto("glosario.md#Aguinaldo", "Aguinaldo: mínimo 15 días de salario.", 0.6)]
    llm = LLMGuion("El aguinaldo mínimo es de 15 días de salario.")
    r = responder_con_guardia(llm, "¿Qué es el aguinaldo?", [], ctx)
    assert not r.uso_plantilla and r.intentos == 1


def test_quita_bloque_think_de_modelos_con_razonamiento():
    r = responder_con_guardia(LLMGuion(f"<think>pienso…</think>{BUENO}"), "q", EVID)
    assert r.texto == BUENO


def test_las_advertencias_viajan_aparte_sin_duplicarse_en_el_texto():
    r = responder_con_guardia(LLMRoto(), "q", EVID, advertencias=["Datos de 3 empresas."])
    assert "Datos de 3 empresas." in r.advertencias and "Datos de 3 empresas." not in r.texto
