"""
INVESTIGADOR: buscar → seleccionar → leer → extraer evidencia → registrar fuentes.

Modos (una sola sección "Investigación" en la interfaz):
  web          búsqueda general (Tavily → Brave → Wikipedia como respaldo)
  academico    artículos científicos (OpenAlex + Crossref + Semantic Scholar [+ PubMed si es salud])
  noticias     noticias recientes (Tavily noticias → Brave noticias → GDELT)
  estadisticas indicadores oficiales por país (Banco Mundial)
  tecnica      documentación técnica (búsqueda web orientada a documentación)

Cada fuente queda con su estado de lectura real: nunca se dice "leída" si sólo se obtuvo el fragmento.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from dinamo.core.contracts import Evidencia
from dinamo.core.texto import texto_plano

from . import buscadores as bus
from . import estadisticas as est
from .fuentes import (BLOQUEADA, DATOS, LEIDA, LEIDA_PARCIAL, SOLO_FRAGMENTO, SOLO_METADATOS, SOLO_RESUMEN, Fuente,
                      clasificar)
from .lector import leer, pasajes
from .red import URLBloqueada, descargar

MODOS = ("web", "academico", "noticias", "estadisticas", "tecnica")
MIN_LEIDA = 1500        # caracteres para considerar que una página se leyó (y no sólo su portada)
SALUD = ("salud", "burnout", "estres", "ergonom", "enfermedad", "ausentismo medico", "incapacidad", "mental")


@dataclass
class Investigacion:
    pregunta: str
    modo: str
    consulta: str
    fecha: str
    fuentes: list[Fuente] = field(default_factory=list)
    evidencias: list[Evidencia] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    proveedores: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {"pregunta": self.pregunta, "modo": self.modo, "consulta": self.consulta, "fecha": self.fecha,
                "fuentes": [f.a_dict() for f in self.fuentes], "avisos": self.avisos, "proveedores": self.proveedores,
                "evidencias": [e.__dict__ for e in self.evidencias],
                "resumen_lectura": resumen_lectura(self.fuentes)}


def resumen_lectura(fuentes: list[Fuente]) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for f in fuentes:
        conteo[f.estado] = conteo.get(f.estado, 0) + 1
    return conteo


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _intentar(proveedores, consulta, n, avisos, usados):
    """Prueba cada buscador en orden; devuelve los resultados del primero que funcione."""
    for nombre, fn in proveedores:
        try:
            res = fn(consulta, n)
        except bus.ErrorBuscador as exc:
            avisos.append(str(exc))
            continue
        usados.append(nombre)
        if res:
            return res
    return []


def _buscar_web(consulta, n, avisos, usados, noticias=False):
    cadena = []
    if noticias:
        cadena.append(("tavily", lambda q, k: bus.tavily(q, k, tema="news", dias=30)))
        if os.getenv("BRAVE_API_KEY"):
            cadena.append(("brave", lambda q, k: bus.brave(q, k, noticias=True)))
        cadena.append(("gdelt", bus.gdelt))
    else:
        if os.getenv("BRAVE_API_KEY") and os.getenv("DINAMO_BUSCADOR", "").lower() == "brave":
            cadena.append(("brave", bus.brave))
        cadena.append(("tavily", bus.tavily))
        if os.getenv("BRAVE_API_KEY") and ("brave", bus.brave) not in cadena:
            cadena.append(("brave", bus.brave))
        cadena.append(("wikipedia", bus.wikipedia))
    return _intentar(cadena, consulta, n, avisos, usados)


def _clave_titulo(t: str) -> str:
    return texto_plano(t).strip()[:120]


def _buscar_academico(consulta, n, avisos, usados):
    resultados, vistos = [], set()
    servicios = [("openalex", bus.openalex), ("crossref", bus.crossref), ("semantic_scholar", bus.semantic_scholar)]
    if any(s in texto_plano(consulta) for s in SALUD):
        servicios.append(("pubmed", bus.pubmed))
    with ThreadPoolExecutor(max_workers=len(servicios)) as ex:
        futuros = [(nombre, ex.submit(fn, consulta, n)) for nombre, fn in servicios]
    for nombre, fut in futuros:
        try:
            filas = fut.result()
        except bus.ErrorBuscador as exc:
            avisos.append(str(exc))
            continue
        usados.append(nombre)
        for r in filas:
            clave = (r.extra.get("doi") or "").lower() or _clave_titulo(r.titulo)
            if not r.titulo or clave in vistos:
                continue
            vistos.add(clave)
            resultados.append(r)
    # intercalar proveedores para no quedarnos sólo con los primeros de uno
    return resultados[: n * 2]


def _a_fuente(i: int, r: bus.Resultado, consultado: str) -> Fuente:
    tipo, just = clasificar(r.url, r.proveedor)
    e = r.extra
    f = Fuente(id=f"W:{i}", titulo=r.titulo.strip() or r.url, url=r.url, proveedor=r.proveedor, tipo=tipo,
               justificacion=just, fragmento=r.fragmento.strip(), fecha_publicacion=r.fecha, fecha_consulta=consultado,
               autores=e.get("autores", []), medio=e.get("medio", ""), doi=e.get("doi", ""), citas=e.get("citas"),
               acceso_abierto=e.get("acceso_abierto"))
    if r.proveedor in ("openalex", "crossref", "semantic_scholar", "pubmed"):
        f.estado = SOLO_RESUMEN if len(f.fragmento) > 200 else SOLO_METADATOS
    elif not f.fragmento:
        f.estado = SOLO_METADATOS
    return f


def leer_fuente(f: Fuente, pregunta: str, contenido_previo: str = "", url_lectura: str = "", **kw) -> Fuente:
    """Intenta leer la página. Si el buscador ya trajo el texto (Tavily), se usa ese texto."""
    texto, via = "", ""
    if contenido_previo and len(contenido_previo) >= 300:
        texto, via = contenido_previo, "texto extraído por el buscador"
    else:
        try:
            d = descargar(url_lectura or f.url, **kw)
            pagina = leer(d.contenido, d.tipo, d.url)
            texto, via = pagina.texto, "lectura directa"
            f.autores = f.autores or pagina.autores
            f.fecha_publicacion = f.fecha_publicacion or pagina.fecha_publicacion
            f.fecha_actualizacion = pagina.fecha_actualizacion
            f.medio = f.medio or pagina.sitio
            if pagina.titulo and (not f.titulo or f.titulo == f.url):
                f.titulo = pagina.titulo
            if not f.fragmento:
                f.fragmento = pagina.descripcion
        except URLBloqueada as exc:
            if f.estado not in (SOLO_RESUMEN,):
                f.estado = BLOQUEADA if not f.fragmento else SOLO_FRAGMENTO
            f.motivo = str(exc)
            return f
        except Exception as exc:          # HTML/PDF imposible de procesar
            f.motivo = f"No se pudo procesar el contenido ({type(exc).__name__})."
            if f.estado != SOLO_RESUMEN:
                f.estado = SOLO_FRAGMENTO if f.fragmento else BLOQUEADA
            return f
    f.caracteres_leidos = len(texto)
    f.pasajes = pasajes(texto, pregunta)
    if len(texto) >= MIN_LEIDA:
        f.estado = LEIDA
    elif texto:
        f.estado = LEIDA_PARCIAL if f.estado != SOLO_RESUMEN else SOLO_RESUMEN
    f.motivo = via
    return f


def investigar(pregunta: str, modo: str = "web", consulta: str | None = None, n: int = 6, leer_k: int = 4,
               paises: list[str] | None = None, indicador: str | None = None, desde: int = 2014) -> Investigacion:
    if modo not in MODOS:
        raise ValueError(f"Modo de investigación desconocido: {modo}")
    consulta = (consulta or pregunta).strip()
    inv = Investigacion(pregunta, modo, consulta, _ahora())
    if modo == "estadisticas":
        return _estadisticas(inv, paises, indicador, desde)

    if modo == "academico":
        crudos = _buscar_academico(consulta, n, inv.avisos, inv.proveedores)
    elif modo == "noticias":
        crudos = _buscar_web(consulta, n, inv.avisos, inv.proveedores, noticias=True)
    elif modo == "tecnica":
        crudos = _buscar_web(f"{consulta} documentación", n, inv.avisos, inv.proveedores)
    else:
        crudos = _buscar_web(consulta, n, inv.avisos, inv.proveedores)

    vistos, unicos = set(), []
    for r in crudos:
        if r.url and r.url not in vistos:
            vistos.add(r.url)
            unicos.append(r)
    inv.fuentes = [_a_fuente(i + 1, r, inv.fecha) for i, r in enumerate(unicos[: max(n, 1) * (2 if modo == "academico" else 1)])]

    # Leer las primeras `leer_k` (artículos: sólo los de acceso abierto con URL de texto)
    tareas = []
    for f, r in zip(inv.fuentes, unicos):
        if len(tareas) >= leer_k:
            break
        if modo == "academico":
            url_abierta = r.extra.get("url_abierta")
            if url_abierta:
                tareas.append((f, "", url_abierta))
        else:
            tareas.append((f, r.contenido, ""))
    if tareas:
        with ThreadPoolExecutor(max_workers=min(4, len(tareas))) as ex:
            list(ex.map(lambda t: leer_fuente(t[0], pregunta, t[1], t[2]), tareas))
    if not inv.fuentes:
        inv.avisos.append("No se encontraron fuentes. Prueba con otras palabras o con otro modo de investigación.")
    return inv


def _estadisticas(inv: Investigacion, paises, indicador, desde) -> Investigacion:
    indicador = indicador or est.indicador_en(inv.pregunta)
    paises = paises or est.paises_en(inv.pregunta)
    if not indicador:
        inv.avisos.append("No identifiqué qué indicador consultar. Disponibles: "
                          + "; ".join(v[0] for v in est.INDICADORES.values()))
        return inv
    if not paises:
        inv.avisos.append(f"No indicaste países; uso {est.PAISES[est.PAIS_REFERENCIA_SUGERIDO]} como referencia "
                          "sugerida (puedes cambiarla).")
        paises = [est.PAIS_REFERENCIA_SUGERIDO]
    try:
        series = est.consultar(indicador, paises, desde)
    except bus.ErrorBuscador as exc:
        inv.avisos.append(str(exc))
        return inv
    inv.proveedores.append("banco_mundial")
    inv.evidencias = est.evidencias_de(series)
    for i, s in enumerate(series, 1):
        f = Fuente(id=f"W:{i}", titulo=f"{s.nombre} — {s.pais_nombre}", url=s.url, proveedor="banco_mundial",
                   fecha_consulta=inv.fecha, estado=DATOS if s.valores else SOLO_METADATOS, medio="Banco Mundial",
                   datos=[{"anio": a, "valor": v} for a, v in s.valores])
        f.tipo, f.justificacion = clasificar(s.url, "banco_mundial")
        if not s.valores:
            f.motivo = "El Banco Mundial no publica datos de este país para el periodo."
        else:
            f.fecha_publicacion = str(s.valores[-1][0])
        inv.fuentes.append(f)
    return inv
