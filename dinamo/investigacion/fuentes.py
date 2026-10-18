"""
FUENTES: el registro estructurado de cada fuente externa consultada y su clasificación.

La clasificación es por reglas explícitas sobre el dominio y el proveedor, y siempre devuelve su
JUSTIFICACIÓN. No se inventan puntuaciones de "confiabilidad": se dice qué tipo de fuente es y por qué.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

# Estados de lectura — se informan tal cual al usuario. Nunca se dice "leída" si sólo hay un fragmento.
LEIDA = "leída"                        # se descargó y extrajo el texto de la página
LEIDA_PARCIAL = "leída parcialmente"   # se extrajo texto pero muy corto o truncado
SOLO_RESUMEN = "solo resumen"          # artículo científico: título + resumen (abstract), no el texto completo
SOLO_FRAGMENTO = "solo fragmento"      # sólo el extracto que devolvió el buscador
SOLO_METADATOS = "solo metadatos"      # título / autores / fecha, sin contenido
BLOQUEADA = "no se pudo leer"          # bloqueo, error o tipo no permitido
DATOS = "datos oficiales"              # serie numérica obtenida de una API estadística

OFICIALES = ("inegi.org.mx", "imss.gob.mx", "stps.gob.mx", "banxico.org.mx", "ine.es", "sepe.es", "dane.gov.co",
             "bls.gov", "census.gov", "ons.gov.uk", "ibge.gov.br", "indec.gob.ar", "ine.cl", "inei.gob.pe",
             "europa.eu", "boe.es", "dof.gob.mx")
ORGANISMOS = ("worldbank.org", "oecd.org", "ilo.org", "imf.org", "un.org", "cepal.org", "who.int", "iadb.org",
              "undp.org", "unesco.org", "weforum.org", "ilostat.ilo.org")
ACADEMICOS = ("doi.org", "scielo", "sciencedirect.com", "springer.com", "link.springer.com", "wiley.com",
              "tandfonline.com", "jstor.org", "nature.com", "ncbi.nlm.nih.gov", "pubmed", "arxiv.org", "mdpi.com",
              "frontiersin.org", "sagepub.com", "researchgate.net", "redalyc.org", "dialnet.unirioja.es",
              "semanticscholar.org", "openalex.org", "emerald.com", "apa.org", "aom.org", "ssrn.com",
              "scholar.google", "plos.org", "oup.com", "cambridge.org", "elsevier.com", "hbr.org")
NOTICIAS = ("elpais.com", "eleconomista", "elfinanciero.com.mx", "expansion.mx", "reuters.com", "bloomberg",
            "bbc.", "nytimes.com", "forbes", "eluniversal.com.mx", "milenio.com", "infobae.com", "cnn.com",
            "eltiempo.com", "elmundo.es", "lanacion.com", "clarin.com", "ft.com", "wsj.com", "theguardian.com",
            "excelsior.com.mx", "jornada.com.mx", "portafolio.co", "larepublica.co", "cincodias", "apnews.com",
            "semana.com", "wired.com", "techcrunch.com", "theverge.com")
TECNICOS = ("readthedocs", "github.com", "developer.", "docs.", "learn.microsoft.com", "stackoverflow.com",
            "pandas.pydata.org", "python.org", "mozilla.org", "w3.org")
ENCICLOPEDIAS = ("wikipedia.org", "britannica.com")


@dataclass
class Fuente:
    id: str                                   # "W:1", "W:2"... único dentro de la investigación
    titulo: str
    url: str
    proveedor: str                            # quién la encontró: tavily, openalex, crossref, banco_mundial...
    tipo: str = "sitio web"
    justificacion: str = ""
    estado: str = SOLO_FRAGMENTO
    fragmento: str = ""                       # lo que devolvió el buscador
    pasajes: list[str] = field(default_factory=list)   # trozos relevantes extraídos del texto leído
    autores: list[str] = field(default_factory=list)
    fecha_publicacion: str = ""
    fecha_actualizacion: str = ""
    fecha_consulta: str = ""
    medio: str = ""                           # revista, periódico o sitio
    doi: str = ""
    citas: int | None = None                  # número de citas según el proveedor académico
    acceso_abierto: bool | None = None
    caracteres_leidos: int = 0
    motivo: str = ""                          # por qué no se pudo leer
    datos: list[dict] = field(default_factory=list)    # series numéricas (estadísticas oficiales)

    @property
    def dominio(self) -> str:
        return (urlsplit(self.url).hostname or "").removeprefix("www.")

    def a_dict(self) -> dict:
        d = asdict(self)
        d["dominio"] = self.dominio
        return d


def _coincide(dominio: str, lista) -> str:
    for patron in lista:
        if patron.endswith(".") or patron.startswith(("docs.", "developer.")):
            if patron in dominio:
                return patron
        elif dominio == patron or dominio.endswith("." + patron) or (("." not in patron) and patron in dominio):
            return patron
    return ""


def clasificar(url: str, proveedor: str = "") -> tuple[str, str]:
    """Devuelve (tipo de fuente, justificación)."""
    dominio = (urlsplit(url).hostname or "").removeprefix("www.").lower()
    if proveedor in ("openalex", "crossref", "semantic_scholar", "pubmed"):
        return "artículo científico", f"Registro del índice académico {proveedor.replace('_', ' ').title()}."
    if proveedor == "banco_mundial":
        return "estadística oficial", "Dato de la API pública del Banco Mundial (World Development Indicators)."
    if (p := _coincide(dominio, OFICIALES)) or ".gob." in f".{dominio}." or ".gov." in f".{dominio}." \
            or dominio.endswith((".gov", ".gob.mx", ".gob.es", ".gov.co", ".gob.ar", ".gob.cl", ".gob.pe")):
        return "fuente oficial", f"Dominio gubernamental o de instituto de estadística ({p or dominio})."
    if p := _coincide(dominio, ORGANISMOS):
        return "organismo internacional", f"Sitio de un organismo internacional ({p})."
    if (p := _coincide(dominio, ACADEMICOS)) or dominio.endswith(".edu") or ".edu." in dominio or ".ac." in dominio:
        return "fuente académica", f"Editorial, repositorio o institución académica ({p or dominio})."
    if p := _coincide(dominio, ENCICLOPEDIAS):
        return "enciclopedia", "Obra de consulta general; conviene verificar en las fuentes primarias que cita."
    if proveedor in ("tavily_noticias", "gdelt") or _coincide(dominio, NOTICIAS):
        return "medio de noticias", f"Medio periodístico ({dominio}); refleja información a la fecha de publicación."
    if p := _coincide(dominio, TECNICOS):
        return "documentación técnica", f"Documentación o repositorio técnico ({p})."
    return "sitio web", f"Sitio web general ({dominio}); no se verificó su autoría ni su metodología."
