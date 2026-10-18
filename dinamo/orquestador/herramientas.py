"""
HERRAMIENTAS AUTORIZADAS del orquestador. El LLM sólo puede pedir estas, con argumentos validados.

Cada herramienta devuelve un Material (evidencias, fragmentos de documentos, fuentes externas,
datos para gráficos, advertencias). Ninguna herramienta deja que el LLM calcule: los números
salen de las Skills (Python) o se copian tal cual de una API oficial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from dinamo.core.contracts import Aclaracion, Contexto, Evidencia, Pregunta
from dinamo.investigacion import estadisticas as est
from dinamo.investigacion import investigar
from dinamo.investigacion.fuentes import Fuente
from dinamo.skills import ParametroInvalido


@dataclass
class Material:
    evidencias: list[Evidencia] = field(default_factory=list)
    contexto: list[Contexto] = field(default_factory=list)
    fuentes: list[Fuente] = field(default_factory=list)
    datos: dict[str, list[dict]] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    sugerencias: list[str] = field(default_factory=list)
    aclaracion: Aclaracion | None = None
    investigaciones: list[dict] = field(default_factory=list)

    def sumar(self, otro: "Material") -> None:
        vistos = {e.id for e in self.evidencias}
        self.evidencias += [e for e in otro.evidencias if e.id not in vistos]
        fuentes_ctx = {c.fuente for c in self.contexto}
        self.contexto += [c for c in otro.contexto if c.fuente not in fuentes_ctx]
        base = len(self.fuentes)
        for i, f in enumerate(otro.fuentes, 1):        # numeración única W:1..n en toda la respuesta
            f.id = f"W:{base + i}"
            self.fuentes.append(f)
        self.datos.update(otro.datos)
        self.advertencias += [a for a in otro.advertencias if a not in self.advertencias]
        self.notas += otro.notas
        self.sugerencias += [s for s in otro.sugerencias if s not in self.sugerencias]
        self.investigaciones += otro.investigaciones
        self.aclaracion = self.aclaracion or otro.aclaracion

    def vacio(self) -> bool:
        return not (self.evidencias or self.contexto or self.fuentes or self.notas)


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    argumentos: dict[str, str]
    funcion: Callable[..., Material]


# ------------------------------------------------------------------------------------------------
def _brain(espacio):
    return espacio.brain


def analizar_datos(espacio, pregunta: str, **_) -> Material:
    brain = _brain(espacio)
    m = Material()
    if not brain.biblioteca.motores and not brain.rac_tiene_documentos():
        m.advertencias.append("No hay archivos cargados en esta conversación.")
        return m
    r = brain.responder(pregunta)
    if r.aclaracion is not None:
        m.aclaracion = r.aclaracion
        return m
    m.evidencias = list(r.evidencias)
    m.contexto = [c for c in r.contexto if c.tipo == "documento" or c.puntaje > 0]
    m.datos = {k: list(v) for k, v in r.datos.items()}
    m.advertencias = list(r.advertencias)
    m.sugerencias = list(r.sugerencias)
    return m


def consultar_documentos(espacio, pregunta: str, **_) -> Material:
    brain = _brain(espacio)
    m = Material()
    if not brain.rac_tiene_documentos():
        m.advertencias.append("No hay documentos de texto cargados en esta conversación.")
        return m
    m.contexto = brain.rac.buscar(pregunta, k=5, tipos=("documento",))
    if not m.contexto:
        m.advertencias.append("No encontré nada sobre eso en los documentos cargados.")
    return m


def ejecutar_skill(espacio, skill: str, parametros: dict | None = None, tabla: str | None = None, **_) -> Material:
    brain = _brain(espacio)
    m = Material()
    s = brain.registro.obtener(str(skill))
    if s is None:
        m.advertencias.append(f"No existe la herramienta de análisis '{skill}'.")
        return m
    tablas = list(brain.biblioteca.motores)
    if not tablas:
        m.advertencias.append("No hay tablas cargadas para analizar.")
        return m
    if tabla not in tablas:
        candidatas = [t for t in tablas if s.aplica(brain.biblioteca.motor(t).perfil)]
        tabla = brain.tabla_activa if brain.tabla_activa in candidatas else (candidatas[0] if candidatas else None)
    if tabla is None:
        m.advertencias.append(f"Ninguna tabla cargada tiene lo que necesita '{skill}' ({', '.join(s.requiere) or 'columnas de RR. HH.'}).")
        return m
    motor = brain.biblioteca.motor(tabla)
    permitidos = set(s.parametros) | {"filtros"}
    limpios = {k: v for k, v in (parametros or {}).items() if k in permitidos and v not in (None, "")}
    ignorados = set(parametros or {}) - permitidos
    if ignorados:
        m.advertencias.append(f"Se ignoraron parámetros no válidos para {skill}: {sorted(ignorados)}")
    if s.nombre in ("anomalias",) and "metrica" not in limpios:
        metricas = motor.perfil.por_rol("metrica")
        if metricas:
            limpios["metrica"] = metricas[0].nombre
            m.advertencias.append(f"No se indicó el indicador; se usó '{metricas[0].nombre_visible}'.")
    try:
        res = s(motor, limpios)
    except (ParametroInvalido, KeyError, ValueError, TypeError) as exc:
        m.advertencias.append(f"{skill} no pudo ejecutarse: {exc}")
        return m
    brain.evidencias.agregar(res.evidencias)
    m.evidencias = list(res.evidencias)
    m.datos = {s.nombre: list(res.datos)}
    m.advertencias = list(res.advertencias)
    if not res.evidencias and not res.advertencias:
        m.notas.append(f"{skill}: no se encontraron casos que cumplan el criterio.")
    return m


def indicadores_talento(espacio, tabla: str | None = None, dimension: str | None = None, **_) -> Material:
    return ejecutar_skill(espacio, "indicadores_talento", {"dimension": dimension} if dimension else {}, tabla)


def _con_fuentes(espacio, inv) -> Material:
    m = Material(fuentes=list(inv.fuentes), evidencias=list(inv.evidencias), advertencias=list(inv.avisos))
    if inv.evidencias:
        espacio.brain.evidencias.agregar(inv.evidencias)
    if inv.modo == "estadisticas":
        filas = [{"pais": f.titulo.split(" — ")[-1], "anio": d["anio"], "valor": d["valor"]} for f in inv.fuentes for d in f.datos]
        if filas:
            m.datos = {"indicador_pais": filas}
    registro = espacio.guardar_investigacion(inv.a_dict())
    m.investigaciones.append({"id": registro["id"], "modo": inv.modo, "consulta": inv.consulta})
    return m


def investigar_web(espacio, consulta: str, modo: str = "web", **_) -> Material:
    modo = modo if modo in ("web", "academico", "noticias", "tecnica") else "web"
    return _con_fuentes(espacio, investigar(consulta, modo=modo, consulta=consulta))


def buscar_articulos(espacio, consulta: str, **_) -> Material:
    return _con_fuentes(espacio, investigar(consulta, modo="academico", consulta=consulta))


def indicador_pais(espacio, indicador: str | None = None, paises: list | None = None, pregunta: str = "", **_) -> Material:
    paises = [str(p).upper() for p in (paises or []) if str(p).upper() in est.PAISES] or est.paises_en(pregunta)
    ref = espacio.preferencias.get("pais_referencia")
    if ref and ref not in paises and (len(paises) <= 1 or "referencia" in pregunta.lower()):
        paises = paises + [ref]
    indicador = indicador if indicador in est.INDICADORES else est.indicador_en(pregunta)
    return _con_fuentes(espacio, investigar(pregunta or "indicador", modo="estadisticas", paises=paises,
                                            indicador=indicador))


def usar_investigacion(espacio, id: str = "", **_) -> Material:
    """Trae al chat una investigación ya hecha en la sección Investigación (sin volver a buscar)."""
    from dinamo.core.contracts import Evidencia
    inv = next((i for i in espacio.investigaciones if i.get("id") == str(id)), None)
    if inv is None:
        return Material(advertencias=["No encontré esa investigación en esta conversación."])
    campos = set(Fuente.__dataclass_fields__)
    fuentes = [Fuente(**{k: v for k, v in f.items() if k in campos}) for f in inv.get("fuentes", [])]
    evid = [Evidencia(**e) for e in inv.get("evidencias", [])]
    if evid:
        espacio.brain.evidencias.agregar(evid)
    m = Material(fuentes=fuentes, evidencias=evid, advertencias=list(inv.get("avisos", [])))
    m.notas.append(f"Investigación reutilizada: «{inv.get('consulta') or inv.get('pregunta')}» ({inv.get('modo')}, consultada {inv.get('fecha')}).")
    return m


def recordar(espacio, hecho: str, **_) -> Material:
    item = espacio.recordar(hecho)
    return Material(notas=[f"Anotado en la memoria de esta conversación: «{item['hecho']}»."])


def fijar_pais_referencia(espacio, pais: str, **_) -> Material:
    cod = str(pais).upper() if str(pais).upper() in est.PAISES else (est.paises_en(str(pais)) or [None])[0]
    if not cod:
        return Material(advertencias=[f"No reconocí el país «{pais}»."])
    espacio.preferencias["pais_referencia"] = cod
    espacio.guardar()
    return Material(notas=[f"País de referencia de esta conversación: {est.PAISES[cod]} ({cod})."])


HERRAMIENTAS: dict[str, Herramienta] = {h.nombre: h for h in [
    Herramienta("analizar_datos", "Calcula con los archivos de la conversación (tendencias, rankings, comparaciones, "
                "relaciones, perfil de una entidad, describir datos).", {"pregunta": "texto"}, analizar_datos),
    Herramienta("consultar_documentos", "Busca en el texto de los PDF/TXT/MD cargados.", {"pregunta": "texto"},
                consultar_documentos),
    Herramienta("ejecutar_skill", "Ejecuta una Skill concreta: anomalias (metrica, umbral), brecha_pares "
                "(metrica, entidad_objetivo, dimensiones_pares), indicadores_talento (dimension), distribucion (metrica), "
                "ranking (metrica, n, orden), tendencia (metrica), comparar_grupos (metrica, dimension), "
                "relaciones (metrica).", {"skill": "nombre", "parametros": "objeto", "tabla": "opcional"}, ejecutar_skill),
    Herramienta("indicadores_talento", "Rotación, retención, ausentismo y contratación con fórmulas de RR. HH.",
                {"dimension": "opcional", "tabla": "opcional"}, indicadores_talento),
    Herramienta("investigar_web", "Búsqueda real en internet y lectura de páginas. modo: web | noticias | tecnica.",
                {"consulta": "texto de búsqueda", "modo": "web|noticias|tecnica"}, investigar_web),
    Herramienta("buscar_articulos", "Artículos científicos (OpenAlex, Crossref, Semantic Scholar).",
                {"consulta": "texto de búsqueda (mejor en inglés)"}, buscar_articulos),
    Herramienta("indicador_pais", "Indicador oficial por país del Banco Mundial (desempleo, participación laboral, "
                "informalidad, PIB per cápita, inflación...).", {"indicador": "código o vacío", "paises": "lista ISO3"},
                indicador_pais),
    Herramienta("usar_investigacion", "Usa una investigación ya guardada en esta conversación.", {"id": "id de la investigación"},
                usar_investigacion),
    Herramienta("recordar", "Guarda un hecho que el usuario pidió recordar en esta conversación.", {"hecho": "texto"},
                recordar),
    Herramienta("fijar_pais_referencia", "Cambia el país de referencia para comparaciones.", {"pais": "nombre o ISO3"},
                fijar_pais_referencia),
]}


def ejecutar(espacio, nombre: str, argumentos: dict[str, Any], pregunta: str) -> Material:
    h = HERRAMIENTAS.get(nombre)
    if h is None:
        return Material(advertencias=[f"Herramienta no autorizada: {nombre}"])
    args = {k: v for k, v in (argumentos or {}).items() if isinstance(k, str)}
    args.setdefault("pregunta", pregunta)
    if nombre in ("investigar_web", "buscar_articulos"):
        args["consulta"] = str(args.get("consulta") or pregunta)[:300]
    if nombre == "recordar" and not args.get("hecho"):
        return Material(advertencias=["No entendí qué debo recordar."])
    return h.funcion(espacio, **args)


def preguntar_brain(espacio, texto: str):
    """Plan del Brain (sin calcular) para conocer métrica y tabla de una pregunta."""
    try:
        return espacio.brain.interpretar(Pregunta(texto))
    except Exception:
        return None
