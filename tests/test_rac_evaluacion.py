"""RAC contra la base real: 15 preguntas y el fragmento que debe salir (meta: 13 de 15 en el top 3).
Se salta solo si el Excel no está (igual que el test con datos reales)."""
import os
from pathlib import Path

import pytest

from dinamo.rac import Retriever

RAIZ = Path(__file__).resolve().parents[1]


def _excel() -> Path | None:
    candidatos = [os.environ.get("DINAMO_EXCEL"), RAIZ / "data" / "BASE_HISTORICA_LIMPIA.xlsx"]
    try:
        from dinamo.core.config import Config
        candidatos.append(Config().ruta_datos)
    except Exception:
        pass
    return next((Path(c) for c in candidatos if c and Path(c).exists()), None)


# (pregunta, [subcadenas aceptables en la fuente del fragmento correcto])
PREGUNTAS = [
    ("¿Qué es el bono de puntualidad?", ["puntualidad"]),
    ("¿Cómo se define la rotación?", ["tasa_rotacion", "rotacion"]),
    ("¿Qué significa Tier 1 y OEM?", ["Tier 1", "OEM", "nivel_proveeduria"]),
    ("¿Cómo se calcula el ausentismo?", ["tasa_ausentismo"]),
    ("¿Qué hacen con los datos faltantes?", ["Faltantes"]),
    ("¿Cómo se tratan las empresas que no reportaron un bimestre?", ["Arrastre", "reportó", "bimestre_reportado"]),
    ("¿Los porcentajes van de 0 a 1 o de 0 a 100?", ["Porcentajes"]),
    ("¿Qué es el salario diario inicial?", ["salario_diario_inicial"]),
    ("¿Qué es la prima vacacional?", ["Prima vacacional", "prima_vacacional"]),
    ("¿Cuántos días de aguinaldo da la ley?", ["Aguinaldo", "aguinaldo"]),
    ("¿Qué es el SGMM?", ["SGMM", "sgmm"]),
    ("¿Para qué sirve el bono de permanencia?", ["permanencia"]),
    ("¿Qué son las incapacidades?", ["incapacidad"]),
    ("¿Por qué renuncia la gente?", ["motivo_baja", "renuncia"]),
    ("¿Cómo corrigieron los errores de captura de headcount?", ["CORRECCIONES"]),
]
ERRATAS = [("que es el bono de puntualdad", ["puntualidad"]), ("ke significa tier 2", ["Tier 2"])]


@pytest.fixture(scope="module")
def retriever():
    ruta = _excel()
    if ruta is None:
        pytest.skip("No está BASE_HISTORICA_LIMPIA.xlsx en data/")
    return Retriever.desde_carpeta(RAIZ / "docs" / "conocimiento", ruta)


def _acierta(retriever, pregunta, esperados, k=3) -> bool:
    return any(any(e.lower() in c.fuente.lower() for e in esperados) for c in retriever.buscar(pregunta, k))


def test_top3_acierta_al_menos_13_de_15(retriever):
    fallas = [p for p, esp in PREGUNTAS if not _acierta(retriever, p, esp)]
    assert len(PREGUNTAS) - len(fallas) >= 13, f"Fallaron: {fallas}"


def test_tolera_erratas_con_la_base_real(retriever):
    assert all(_acierta(retriever, p, esp) for p, esp in ERRATAS)


def test_pregunta_ajena_no_trae_contexto(retriever):
    assert retriever.buscar("¿Cuál es la capital de Francia?", 3) == []


def test_indexa_diccionario_agrupado(retriever):
    fuentes = [f for f, _ in retriever.fragmentos]
    assert any(f.startswith("diccionario:") for f in fuentes) and any(f.startswith("encuesta:") for f in fuentes)
    assert len(fuentes) < 400      # 927 filas del DICCIONARIO se agruparon por pregunta
