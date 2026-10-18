"""
BUSCADORES: cada función consulta un servicio real y devuelve resultados crudos normalizados.

Servicios (todos con plan gratuito; ver docs/INTEGRACIONES.md):
  tavily          búsqueda web y noticias. Sin clave funciona en modo "keyless" con límite de uso;
                  con TAVILY_API_KEY (1.000 créditos/mes gratis) sin ese límite.
  brave           búsqueda web con BRAVE_API_KEY (opcional).
  wikipedia       respaldo de búsqueda general, sin clave.
  gdelt           respaldo de noticias, sin clave.
  openalex        artículos científicos, sin clave (OPENALEX_API_KEY opcional amplía el límite diario).
  crossref        metadatos de publicaciones (DOI), sin clave.
  semantic_scholar artículos científicos, sin clave (límite de frecuencia).
  pubmed          literatura biomédica y de salud ocupacional, sin clave.
  banco_mundial   indicadores oficiales por país, sin clave.

Si un servicio falla se lanza ErrorBuscador con un mensaje claro: nunca se inventan resultados.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

TIEMPO = (6, 20)
AGENTE = {"User-Agent": "DINAMO-Analytics/1.0 (investigacion)"}


class ErrorBuscador(RuntimeError):
    pass


@dataclass
class Resultado:
    titulo: str
    url: str
    fragmento: str
    proveedor: str
    fecha: str = ""
    contenido: str = ""                   # texto completo si el proveedor ya lo extrajo
    extra: dict = field(default_factory=dict)


def _json(metodo: str, url: str, servicio: str, **kw):
    try:
        r = requests.request(metodo, url, timeout=TIEMPO, **kw)
    except requests.RequestException as exc:
        raise ErrorBuscador(f"{servicio}: sin conexión ({type(exc).__name__})") from exc
    if r.status_code == 429:
        raise ErrorBuscador(f"{servicio}: se alcanzó el límite de uso gratuito; intenta más tarde o configura una clave.")
    if r.status_code in (401, 403):
        raise ErrorBuscador(f"{servicio}: la clave no es válida o no tiene permiso ({r.status_code}).")
    if r.status_code >= 400:
        raise ErrorBuscador(f"{servicio}: respondió {r.status_code}.")
    try:
        return r.json()
    except ValueError as exc:
        raise ErrorBuscador(f"{servicio}: respuesta no válida.") from exc


def _sin_html(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


# ------------------------------------------------------------------------------------------ web
def tavily(consulta: str, n: int = 6, tema: str = "general", dias: int | None = None) -> list[Resultado]:
    clave = os.getenv("TAVILY_API_KEY", "").strip()
    cab = {**AGENTE, "Content-Type": "application/json"}
    if clave:
        cab["Authorization"] = f"Bearer {clave}"
    else:
        cab["X-Tavily-Access-Mode"] = "keyless"
    cuerpo = {"query": consulta[:400], "topic": tema, "search_depth": "basic", "max_results": max(1, min(n, 20)),
              "include_raw_content": "text", "include_answer": False}
    if dias:
        cuerpo["time_range"] = "week" if dias <= 7 else "month" if dias <= 31 else "year"
    d = _json("POST", "https://api.tavily.com/search", "Tavily", json=cuerpo, headers=cab)
    prov = "tavily_noticias" if tema == "news" else "tavily"
    return [Resultado(r.get("title") or r.get("url", ""), r.get("url", ""), (r.get("content") or "")[:800], prov,
                      r.get("published_date") or "", (r.get("raw_content") or "")[:60000])
            for r in d.get("results", []) if r.get("url")]


def brave(consulta: str, n: int = 6, noticias: bool = False) -> list[Resultado]:
    clave = os.getenv("BRAVE_API_KEY", "").strip()
    if not clave:
        raise ErrorBuscador("Brave: falta BRAVE_API_KEY.")
    tipo = "news" if noticias else "web"
    d = _json("GET", f"https://api.search.brave.com/res/v1/{tipo}/search", "Brave",
              params={"q": consulta[:400], "count": min(n, 20)},
              headers={**AGENTE, "Accept": "application/json", "X-Subscription-Token": clave})
    filas = d.get("results", []) if noticias else (d.get("web") or {}).get("results", [])
    return [Resultado(_sin_html(r.get("title", "")), r.get("url", ""), _sin_html(r.get("description", "")),
                      "brave", r.get("page_age") or r.get("age") or "") for r in filas if r.get("url")]


def wikipedia(consulta: str, n: int = 4, idioma: str = "es") -> list[Resultado]:
    d = _json("GET", f"https://{idioma}.wikipedia.org/w/api.php", "Wikipedia", headers=AGENTE,
              params={"action": "query", "list": "search", "srsearch": consulta[:300], "srlimit": n,
                      "format": "json", "utf8": 1})
    return [Resultado(r["title"], f"https://{idioma}.wikipedia.org/wiki/{r['title'].replace(' ', '_')}",
                      _sin_html(r.get("snippet", "")), "wikipedia", r.get("timestamp", "")[:10])
            for r in (d.get("query") or {}).get("search", [])]


def gdelt(consulta: str, n: int = 8) -> list[Resultado]:
    d = _json("GET", "https://api.gdeltproject.org/api/v2/doc/doc", "GDELT", headers=AGENTE,
              params={"query": consulta[:250], "mode": "artlist", "format": "json", "maxrecords": n,
                      "sort": "datedesc"})
    salida = []
    for a in d.get("articles", []):
        f = a.get("seendate", "")
        fecha = f"{f[:4]}-{f[4:6]}-{f[6:8]}" if len(f) >= 8 else ""
        salida.append(Resultado(a.get("title", ""), a.get("url", ""), "", "gdelt", fecha,
                                extra={"medio": a.get("domain", ""), "pais": a.get("sourcecountry", "")}))
    return salida


# ------------------------------------------------------------------------------------ académicos
def _abstract_openalex(indice: dict | None) -> str:
    if not indice:
        return ""
    pos = sorted((p, w) for w, ps in indice.items() for p in ps)
    return " ".join(w for _, w in pos)


def openalex(consulta: str, n: int = 6, desde: int | None = None) -> list[Resultado]:
    params = {"search": consulta[:300], "per-page": min(n, 25)}
    if desde:
        params["filter"] = f"from_publication_date:{desde}-01-01"
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.getenv("OPENALEX_API_KEY")
    if os.getenv("DINAMO_CORREO_CONTACTO"):
        params["mailto"] = os.getenv("DINAMO_CORREO_CONTACTO")
    d = _json("GET", "https://api.openalex.org/works", "OpenAlex", params=params, headers=AGENTE)
    salida = []
    for w in d.get("results", []):
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        loc = w.get("primary_location") or {}
        oa = w.get("open_access") or {}
        url = w.get("doi") or (loc.get("landing_page_url")) or w.get("id", "")
        salida.append(Resultado(
            w.get("display_name") or w.get("title") or "", url, _abstract_openalex(w.get("abstract_inverted_index"))[:3000],
            "openalex", w.get("publication_date") or str(w.get("publication_year") or ""),
            extra={"doi": doi, "autores": [a["author"]["display_name"] for a in w.get("authorships", [])[:8]
                                           if a.get("author")],
                   "medio": ((loc.get("source") or {}).get("display_name") or ""), "citas": w.get("cited_by_count"),
                   "acceso_abierto": oa.get("is_oa"), "url_abierta": oa.get("oa_url") or ""}))
    return salida


def crossref(consulta: str, n: int = 6) -> list[Resultado]:
    params = {"query": consulta[:300], "rows": min(n, 20),
              "select": "DOI,title,author,issued,container-title,abstract,URL,is-referenced-by-count"}
    if os.getenv("DINAMO_CORREO_CONTACTO"):
        params["mailto"] = os.getenv("DINAMO_CORREO_CONTACTO")
    d = _json("GET", "https://api.crossref.org/works", "Crossref", params=params, headers=AGENTE)
    salida = []
    for it in (d.get("message") or {}).get("items", []):
        partes = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        fecha = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(partes) if p)
        salida.append(Resultado(
            (it.get("title") or [""])[0], f"https://doi.org/{it['DOI']}" if it.get("DOI") else it.get("URL", ""),
            _sin_html(it.get("abstract", ""))[:3000], "crossref", fecha,
            extra={"doi": it.get("DOI", ""), "medio": (it.get("container-title") or [""])[0],
                   "autores": [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in it.get("author", [])[:8]],
                   "citas": it.get("is-referenced-by-count")}))
    return salida


def semantic_scholar(consulta: str, n: int = 6) -> list[Resultado]:
    cab = dict(AGENTE)
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        cab["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    d = _json("GET", "https://api.semanticscholar.org/graph/v1/paper/search", "Semantic Scholar", headers=cab,
              params={"query": consulta[:300], "limit": min(n, 20),
                      "fields": "title,abstract,year,authors,url,venue,externalIds,openAccessPdf,citationCount,publicationDate"})
    salida = []
    for p in d.get("data", []):
        doi = (p.get("externalIds") or {}).get("DOI", "")
        salida.append(Resultado(
            p.get("title", ""), f"https://doi.org/{doi}" if doi else p.get("url", ""), (p.get("abstract") or "")[:3000],
            "semantic_scholar", p.get("publicationDate") or str(p.get("year") or ""),
            extra={"doi": doi, "medio": p.get("venue", ""), "autores": [a.get("name", "") for a in p.get("authors", [])[:8]],
                   "citas": p.get("citationCount"), "url_abierta": (p.get("openAccessPdf") or {}).get("url", ""),
                   "acceso_abierto": bool(p.get("openAccessPdf"))}))
    return salida


def pubmed(consulta: str, n: int = 5) -> list[Resultado]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ids = (_json("GET", f"{base}/esearch.fcgi", "PubMed", headers=AGENTE,
                 params={"db": "pubmed", "term": consulta[:300], "retmax": n, "retmode": "json"})
           .get("esearchresult") or {}).get("idlist", [])
    if not ids:
        return []
    d = _json("GET", f"{base}/esummary.fcgi", "PubMed", headers=AGENTE,
              params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}).get("result", {})
    salida = []
    for i in ids:
        r = d.get(i) or {}
        doi = next((a["value"] for a in r.get("articleids", []) if a.get("idtype") == "doi"), "")
        salida.append(Resultado(r.get("title", ""), f"https://pubmed.ncbi.nlm.nih.gov/{i}/", "", "pubmed",
                                r.get("sortpubdate", "")[:10].replace("/", "-"),
                                extra={"doi": doi, "medio": r.get("fulljournalname", ""),
                                       "autores": [a.get("name", "") for a in r.get("authors", [])[:8]]}))
    return salida
