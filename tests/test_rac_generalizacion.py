"""El RAC no está atado a Capital Humano: funciona con cualquier tema y tolera cómo escribe la gente."""
import numpy as np
import pytest

from dinamo.rac import Retriever, RetrieverHibrido, Sinonimos, construir_fragmentos
from dinamo.rac.fragmentos import dividir_markdown

COCINA = [
    ("recetas.md#Masa madre", "Masa madre. Es un cultivo de harina y agua fermentado que sirve para leudar el pan."),
    ("recetas.md#Mantequilla clarificada", "Mantequilla clarificada. Se obtiene calentando mantequilla y retirando la espuma."),
    ("finanzas.md#Liquidez", "Liquidez. Capacidad de una empresa para pagar sus deudas de corto plazo."),
]


@pytest.fixture
def r():
    return Retriever(COCINA, sinonimos=Sinonimos([]))


def test_funciona_con_otro_dominio(r):
    assert r.buscar("¿qué es la masa madre?", 1)[0].fuente == "recetas.md#Masa madre"
    assert r.buscar("¿qué es la liquidez?", 1)[0].fuente == "finanzas.md#Liquidez"


def test_tolera_acentos_mayusculas_y_plurales(r):
    assert r.buscar("MASAS MADRES", 1)[0].fuente == "recetas.md#Masa madre"
    assert r.buscar("mantequilla clarificáda", 1)[0].fuente == "recetas.md#Mantequilla clarificada"


def test_tolera_erratas(r):
    assert r.buscar("que es la mantekilla clarificada", 1)[0].fuente == "recetas.md#Mantequilla clarificada"
    assert r.buscar("liquides de la empresa", 1)[0].fuente == "finanzas.md#Liquidez"


def test_pregunta_ajena_no_devuelve_contexto(r):
    assert r.buscar("¿quién ganó el mundial de 2014?", 3) == []


def test_pregunta_vacia_y_retriever_vacio():
    assert Retriever(COCINA).buscar("   ") == []
    assert Retriever([]).buscar("hola") == []


def test_resultados_deterministas(r):
    assert r.buscar("harina y agua", 3) == r.buscar("harina y agua", 3)


def test_digitos_se_conservan_tier_1_vs_tier_2():
    r = Retriever([("g#Tier 1", "Tier 1. Proveedor directo de la armadora."),
                   ("g#Tier 2", "Tier 2. Proveedor de un Tier 1.")], sinonimos=Sinonimos([]))
    assert r.buscar("tier 2", 1)[0].fuente == "g#Tier 2"
    assert r.buscar("tier 1", 1)[0].fuente == "g#Tier 1"


def test_sinonimos_configurables_por_dominio():
    frag = [("a#Churn", "Churn. Porcentaje de clientes que cancelan su suscripción."),
            ("b#Ventas", "Ventas. Ingresos por producto vendido.")]
    sin = Sinonimos([["churn", "cancelaciones", "bajas de clientes"]])
    assert Retriever(frag, sinonimos=sin).buscar("¿cómo van las cancelaciones?", 1)[0].fuente == "a#Churn"
    # sin el grupo de sinónimos, "cancelaciones" no comparte palabras con "Churn": no inventa una coincidencia
    assert Retriever(frag, sinonimos=Sinonimos([])).buscar("¿cómo van las cancelaciones?", 1) == []


def test_agregar_conocimiento_en_caliente(r):
    assert r.buscar("¿qué es el EBITDA?", 1) == []
    r.agregar([("nuevo.md#EBITDA", "EBITDA. Utilidad antes de intereses, impuestos, depreciación y amortización.")])
    assert r.buscar("¿qué es el EBITDA?", 1)[0].fuente == "nuevo.md#EBITDA"


def test_carpeta_nueva_se_indexa_sin_registrar_nada(tmp_path):
    (tmp_path / "logistica.md").write_text("# Guía\n\n## Cross-docking\nMover mercancía del muelle de entrada al de salida sin almacenarla.\n",
                                           encoding="utf-8")
    (tmp_path / "notas.txt").write_text("El lead time es el tiempo entre pedir y recibir.", encoding="utf-8")
    r = Retriever.desde_carpeta(tmp_path, ruta_excel=None)
    assert r.buscar("¿qué es cross docking?", 1)[0].fuente.startswith("logistica.md#Cross-docking")
    assert r.buscar("lead time", 1)[0].fuente == "notas.txt"


def test_titulo_del_archivo_no_es_un_fragmento():
    frags = dividir_markdown("# Glosario\nIntro general.\n\n## Término\nDefinición.", "g.md")
    assert [f for f, _ in frags] == ["g.md#Término"]


def test_fragmentos_duplicados_se_eliminan():
    assert len(construir_fragmentos(extra=COCINA + COCINA)) == 3


# ---------------------------------------------------------------- híbrido
class EmbedderFalso:
    """Espacio semántico de juguete: 'va', 'baja' y 'renuncia' comparten dimensión."""
    modelo = "falso"
    GRUPOS = [{"va", "baja", "renuncia", "salida"}, {"sueldo", "salario"}, {"pan", "harina"}]

    def _v(self, t):
        v = np.zeros(len(self.GRUPOS), dtype="float32")
        for p in t.lower().replace("?", " ").replace("¿", " ").split():
            for i, g in enumerate(self.GRUPOS):
                if p in g:
                    v[i] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def documentos(self, textos):
        return np.stack([self._v(t) for t in textos])

    def pregunta(self, t):
        return self._v(t)


class EmbedderRoto(EmbedderFalso):
    def documentos(self, textos):
        raise ConnectionError("Ollama apagado")


FR = [("m#Motivos de baja", "Motivos de baja. Razones de renuncia del personal."),
      ("m#Salario", "Salario. Pago diario de entrada.")]


def test_hibrido_encuentra_lo_que_tfidf_no_ve(tmp_path):
    base = Retriever(FR, sinonimos=Sinonimos([]))
    assert base.buscar("¿por qué la gente se va?", 1) == []                    # sin palabras en común
    h = RetrieverHibrido(base, EmbedderFalso(), cache_dir=tmp_path)
    assert h.buscar("¿por qué la gente se va?", 1)[0].fuente == "m#Motivos de baja"
    assert list(tmp_path.glob("emb_*.npy"))                                     # dejó caché en disco


def test_hibrido_cae_a_tfidf_si_el_embedder_falla():
    h = RetrieverHibrido(Retriever(FR, sinonimos=Sinonimos([])), EmbedderRoto())
    assert h.degradado
    assert h.buscar("salario diario", 1)[0].fuente == "m#Salario"
