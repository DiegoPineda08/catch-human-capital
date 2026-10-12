from dinamo.core.contracts import Fragmento
from dinamo.data_engine import Biblioteca
from dinamo.ingesta import fragmentar_markdown
from dinamo.rac import Retriever, documento_mencionado, fragmentos_del_perfil


def test_fragmenta_markdown_por_titulos():
    texto = "# Título\nintro\n## Uno\ntexto uno\n## Dos\ntexto dos\n"
    assert [f.fuente for f in fragmentar_markdown(texto, "doc.md")] == ["doc.md#doc", "doc.md#Uno", "doc.md#Dos"]


def test_el_perfil_genera_contexto_automatico(datos_panel):
    fuentes = [f for f, _, tipo in fragmentos_del_perfil(datos_panel.perfil)]
    assert "perfil#tiendas.ventas" in fuentes and "perfil#tiendas.region" in fuentes


def test_recupera_el_fragmento_mas_relevante(datos_panel):
    rac = Retriever(fragmentos_del_perfil(datos_panel.perfil))
    assert rac.buscar("¿Cómo van los reclamos?", k=1)[0].fuente == "perfil#tiendas.tasa_quejas"


def test_sin_coincidencias_devuelve_vacio(datos_panel):
    assert Retriever(fragmentos_del_perfil(datos_panel.perfil)).buscar("xyz qwerty") == []


def test_carga_conocimiento_general_y_el_de_cada_tabla(tmp_path, datos_panel):
    (tmp_path / "general").mkdir()
    (tmp_path / "general" / "reglas.md").write_text("## Regla\nCorrelación no es causalidad.", encoding="utf-8")
    (tmp_path / "tiendas").mkdir()
    (tmp_path / "tiendas" / "negocio.md").write_text("## Temporada\nDiciembre vende más.", encoding="utf-8")
    (tmp_path / "otra_base").mkdir()
    (tmp_path / "otra_base" / "x.md").write_text("## No\nNo debe cargarse.", encoding="utf-8")
    rac = Retriever(carpeta_conocimiento=tmp_path)
    rac.sincronizar(Biblioteca.desde_motores(datos_panel))
    fuentes = {c.fuente for c in rac.buscar("causalidad diciembre cargarse", k=10)}
    assert "reglas.md#Regla" in fuentes and "negocio.md#Temporada" in fuentes
    assert "x.md#No" not in fuentes


def test_indexa_los_textos_de_los_documentos(datos_panel):
    bib = Biblioteca.desde_motores(datos_panel)
    bib.fragmentos = [Fragmento("informe.pdf#p2", "Se recomienda revisar los turnos nocturnos."),
                      Fragmento("otro.pdf#p1", "Texto sin relación.")]
    rac = Retriever()
    rac.sincronizar(bib)
    res = rac.buscar("¿qué pasa con los turnos nocturnos?", k=1, tipos=("documento",))
    assert res[0].fuente == "informe.pdf#p2" and res[0].tipo == "documento"
    assert rac.documentos() == ["informe.pdf", "otro.pdf"]
    assert [c.fuente for c in rac.fragmentos_de("otro.pdf")] == ["otro.pdf#p1"]


def test_reconoce_el_documento_que_se_nombra():
    docs = ["informe_clima_laboral.pdf", "ventas_2025.xlsx"]
    assert documento_mencionado("¿Qué recomienda el informe de clima?", docs) == "informe_clima_laboral.pdf"
    assert documento_mencionado("¿Cómo van las tiendas?", docs) is None
