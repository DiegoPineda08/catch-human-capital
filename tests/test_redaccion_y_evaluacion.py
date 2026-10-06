"""Story Engine (redacción por sección) y script de evaluación del LLM."""
import sys
from dataclasses import dataclass
from pathlib import Path

from dinamo.core.contracts import crear_evidencia
from dinamo.llm import formatear_valor
from dinamo.story_engine.redaccion import redactar_historia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluar_llm import evaluar_modelo, tabla_markdown   # noqa: E402

E1 = crear_evidencia("kpi_por_periodo", "Mediana de rotación, Julio - Agosto 2024", 0.104, "proporcion", 32, "mediana")
E2 = crear_evidencia("kpi_por_periodo", "Mediana de rotación, Julio - Agosto 2025", 0.057, "proporcion", 35, "mediana")


@dataclass(frozen=True)
class Seccion:
    rol: str
    ids_evidencia: tuple
    texto: str


class LLMGuion:
    def __init__(self, *r):
        self.r, self.prompts = list(r), []

    def generar(self, sistema, usuario):
        self.prompts.append(usuario)
        return self.r.pop(0)


def test_cada_seccion_ve_solo_sus_evidencias():
    llm = LLMGuion(f"Pasó de {formatear_valor(E1)} [E:{E1.id}].")
    out = redactar_historia(llm, [Seccion("Hallazgo", (E1.id,), "plantilla")], [E1, E2])
    assert E1.id in llm.prompts[0] and E2.id not in llm.prompts[0]
    assert not out[0].uso_plantilla


def test_si_el_llm_inventa_dos_veces_se_usa_la_plantilla_de_gabriela():
    llm = LLMGuion("Bajó 50%.", "Bajó 60%.")
    out = redactar_historia(llm, [Seccion("Hallazgo", (E1.id,), "Texto de plantilla de Gabriela")], [E1])
    assert out[0].texto == "Texto de plantilla de Gabriela" and out[0].uso_plantilla


def test_una_seccion_fallida_no_afecta_a_las_demas():
    llm = LLMGuion("Bajó 50%.", "Bajó 60%.", f"Hubo {formatear_valor(E2)} [E:{E2.id}].")
    out = redactar_historia(llm, [Seccion("Hallazgo", (E1.id,), "P1"), Seccion("Tensión", (E2.id,), "P2")], [E1, E2])
    assert [s.uso_plantilla for s in out] == [True, False]


def test_evaluar_modelo_cuenta_problemas_y_tabla():
    llm = LLMGuion("Bajó 50%.", f"Fue {formatear_valor(E1)} [E:{E1.id}].")
    res = evaluar_modelo(llm, ["p1", "p2"], lambda p: ([E1], []))
    assert (res["cifras"], res["errores"]) == (1, 0)
    assert "| llama · x |" in tabla_markdown({"llama · x": res})
