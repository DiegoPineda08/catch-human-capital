"""
LECTOR de páginas: convierte HTML (o PDF) en texto limpio + metadatos, y elige los pasajes
más relevantes para la pregunta. Sólo usa la biblioteca estándar (y pdfplumber, ya en el proyecto).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

from dinamo.core.texto import palabras, raiz

IGNORAR = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe",
           "button", "select", "template", "canvas"}
BLOQUES = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br",
           "blockquote", "pre", "td", "th", "dd", "dt", "figcaption", "main"}
META_AUTOR = ("author", "citation_author", "dc.creator", "article:author", "parsely-author")
META_FECHA = ("article:published_time", "citation_publication_date", "citation_date", "dc.date",
              "date", "pubdate", "publish-date", "og:published_time", "datepublished")
META_MODIF = ("article:modified_time", "og:updated_time", "last-modified", "datemodified")


@dataclass
class PaginaLeida:
    url: str
    titulo: str = ""
    autores: list[str] = field(default_factory=list)
    fecha_publicacion: str = ""
    fecha_actualizacion: str = ""
    descripcion: str = ""
    sitio: str = ""
    texto: str = ""
    tipo: str = "html"

    @property
    def dominio(self) -> str:
        return (urlsplit(self.url).hostname or "").removeprefix("www.")


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.saltar = 0
        self.en_titulo = False
        self.titulo = ""
        self.meta: dict[str, list[str]] = {}
        self.partes: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in IGNORAR:
            self.saltar += 1
        elif tag == "title":
            self.en_titulo = True
        elif tag == "meta":
            clave = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
            if clave and a.get("content"):
                self.meta.setdefault(clave, []).append(a["content"].strip())
        elif tag == "time" and a.get("datetime"):
            self.meta.setdefault("time", []).append(a["datetime"])
        if tag in BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in IGNORAR and self.saltar:
            self.saltar -= 1
        elif tag == "title":
            self.en_titulo = False
        if tag in BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data):
        if self.en_titulo:
            self.titulo += data
        elif not self.saltar:
            self.partes.append(data)


def _primero(meta: dict, claves) -> str:
    for c in claves:
        if meta.get(c):
            return meta[c][0]
    return ""


def limpiar(texto: str) -> str:
    lineas = [re.sub(r"[ \t\r\f\v\xa0]+", " ", l).strip() for l in texto.split("\n")]
    salida, vacias = [], 0
    for l in lineas:
        if l:
            salida.append(l)
            vacias = 0
        elif vacias == 0:
            salida.append("")
            vacias = 1
    return "\n".join(salida).strip()


def leer_html(html: str, url: str) -> PaginaLeida:
    ex = _Extractor()
    try:
        ex.feed(html)
        ex.close()
    except Exception:            # HTML muy roto: nos quedamos con lo que se haya podido leer
        pass
    m = ex.meta
    autores = []
    for c in META_AUTOR:
        for v in m.get(c, []):
            if v and v not in autores and not v.startswith("http"):
                autores.append(v)
    return PaginaLeida(
        url=url,
        titulo=limpiar(_primero(m, ("citation_title", "og:title", "twitter:title")) or ex.titulo)[:300],
        autores=autores[:8],
        fecha_publicacion=_primero(m, META_FECHA) or (m.get("time") or [""])[0],
        fecha_actualizacion=_primero(m, META_MODIF),
        descripcion=_primero(m, ("description", "og:description", "citation_abstract"))[:600],
        sitio=_primero(m, ("og:site_name", "citation_journal_title")),
        texto=limpiar("".join(ex.partes)),
    )


def leer_pdf(contenido: bytes, url: str, max_paginas: int = 30) -> PaginaLeida:
    try:
        import pdfplumber
    except ImportError:
        return PaginaLeida(url=url, tipo="pdf")
    textos, titulo, autor = [], "", ""
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        info = pdf.metadata or {}
        titulo, autor = str(info.get("Title") or ""), str(info.get("Author") or "")
        for pagina in pdf.pages[:max_paginas]:
            textos.append(pagina.extract_text() or "")
    return PaginaLeida(url=url, titulo=titulo, autores=[autor] if autor else [], texto=limpiar("\n\n".join(textos)),
                       tipo="pdf")


def leer(contenido: bytes, tipo: str, url: str) -> PaginaLeida:
    if tipo == "application/pdf" or contenido[:5] == b"%PDF-":
        return leer_pdf(contenido, url)
    texto = contenido.decode("utf-8", errors="replace")
    if tipo.startswith("text/plain"):
        return PaginaLeida(url=url, texto=limpiar(texto), tipo="texto")
    return leer_html(texto, url)


def pasajes(texto: str, pregunta: str, k: int = 4, largo: int = 700) -> list[str]:
    """Los k párrafos (o trozos) que más términos de la pregunta contienen. Determinístico."""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n|\n", texto) if len(p.strip()) >= 60]
    trozos: list[str] = []
    for p in parrafos:
        while len(p) > largo:
            corte = p.rfind(". ", 0, largo)
            corte = corte + 1 if corte > largo // 3 else largo
            trozos.append(p[:corte].strip())
            p = p[corte:].strip()
        if len(p) >= 60:
            trozos.append(p)
    claves = {raiz(w) for w in palabras(pregunta)}
    if not claves:
        return trozos[:k]
    puntuados = []
    for i, t in enumerate(trozos):
        presentes = {raiz(w) for w in palabras(t)} & claves
        if presentes:
            puntuados.append((-len(presentes), i, t))
    puntuados.sort()
    elegidos = sorted(puntuados[:k], key=lambda x: x[1])      # en el orden del documento
    return [t for _, _, t in elegidos] or trozos[:min(k, 2)]
