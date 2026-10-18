"""
PLANIFICADOR: entiende la intención (aunque venga con faltas de ortografía) y arma un plan de
pasos con herramientas autorizadas.

  1. Si hay un LLM, se le pide un plan en JSON; se valida contra la lista blanca de herramientas.
  2. Si no hay LLM, o su plan no es válido, se usa el planificador por reglas (determinístico).
Sólo se pregunta al usuario cuando la ambigüedad cambia materialmente la respuesta.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field

from dinamo.core.texto import texto_plano
from dinamo.investigacion import estadisticas as est
from dinamo.llm import LLMFalso, LLMNoDisponible

from .herramientas import HERRAMIENTAS, preguntar_brain

MAX_PASOS = 4

PISTAS = {
    "academico": ("articulo cientifico", "articulos cientificos", "paper", "papers", "estudios cientificos", "literatura",
                  "evidencia cientifica", "revista cientifica", "investigaciones academicas", "articulos academicos",
                  "estudios academicos", "meta analisis", "metaanalisis", "publicaciones cientificas", "articulos sobre"),
    "noticias": ("noticia", "noticias", "ultimas novedades", "actualidad", "que paso hoy", "recientemente",
                 "esta semana", "este mes", "ultimas tendencias", "nuevas leyes", "reforma laboral"),
    "tecnica": ("documentacion", "documentacion tecnica", "como se usa la libreria", "api de", "manual tecnico"),
    "web": ("investiga", "investigar", "busca en internet", "busca en la web", "buscar en internet", "en internet",
            "en la web", "en linea", "google", "fuentes externas", "benchmark", "mejores practicas", "que dicen los expertos",
            "segun expertos", "busca informacion", "buscame", "busca sobre", "consulta en internet", "promedio del mercado",
            "promedio de la industria", "referencias externas", "tendencias del mercado", "actualmente", "hoy en dia",
            "ultimo dato", "ultimos datos", "dato actual", "cifra actual", "cifras actuales", "pronostico", "temperatura",
            "el tiempo en", "tipo de cambio", "cotizacion", "salario minimo"),
    "anomalias": ("anomalia", "anomalias", "atipico", "atipicos", "inusual", "inusuales", "fuera de lo normal",
                  "comportamiento raro", "valores raros", "algo raro", "anormal"),
    "kpis": ("kpi", "kpis", "indicadores de talento", "indicadores de rrhh", "indicadores de recursos humanos",
             "tasa de rotacion", "retencion", "tasa de ausentismo", "tasa de contratacion", "rotacion", "ausentismo"),
    "graficos": ("grafico", "grafica", "graficar", "visualiza", "visualizacion", "diagrama", "chart"),
    "pares": ("contra sus pares", "frente a sus pares", "brecha contra", "comparada con sus pares", "empresas similares"),
}
VOCABULARIO = sorted({p for frases in PISTAS.values() for f in frases for p in f.split() if len(p) >= 5} |
                     {"rotacion", "ausentismo", "salario", "salarios", "empleados", "compara", "comparar", "tendencia",
                      "ranking", "promedio", "mediana", "datos", "archivo", "documento", "resumen", "resume",
                      "desempleo", "informalidad", "inflacion", "participacion", "laboral", "pais", "paises",
                      "mexico", "colombia", "espana", "argentina", "chile", "peru", "brasil", "capacitacion",
                      "satisfaccion", "renuncias", "contratacion", "productividad", "indicador", "indicadores"})
GRAFICOS = {"barras": ("barra", "barras"), "lineas": ("linea", "lineas", "evolucion"), "pastel": ("pastel", "torta", "circular", "pie"),
            "dispersion": ("dispersion", "scatter", "puntos"), "histograma": ("histograma",), "caja": ("caja", "boxplot", "bigotes"),
            "area": ("area",), "calor": ("mapa de calor", "heatmap")}


@dataclass
class PlanOrquestador:
    pregunta: str                       # original
    normalizada: str                    # con ortografía corregida
    pasos: list[dict] = field(default_factory=list)      # [{"herramienta": ..., "argumentos": {...}}]
    aclaracion: str | None = None
    grafico: str | None = None          # tipo de gráfico pedido explícitamente
    origen: str = "reglas"              # "llm" | "reglas"
    razon: str = ""

    def a_dict(self) -> dict:
        return {"pregunta": self.pregunta, "normalizada": self.normalizada, "pasos": self.pasos,
                "aclaracion": self.aclaracion, "grafico": self.grafico, "origen": self.origen, "razon": self.razon}


def corregir(texto: str) -> str:
    """Corrige palabras clave mal escritas ('rotasion' -> 'rotacion', 'investiga' -> 'investiga')."""
    salida = []
    for palabra in texto_plano(texto).split():
        if len(palabra) >= 5 and palabra not in VOCABULARIO:
            cerca = difflib.get_close_matches(palabra, VOCABULARIO, n=1, cutoff=0.82)
            salida.append(cerca[0] if cerca else palabra)
        else:
            salida.append(palabra)
    return " " + " ".join(salida) + " "


def _tiene(plano: str, clave: str) -> bool:
    return any(f" {texto_plano(f).strip()} " in plano for f in PISTAS[clave])


def tipo_grafico(plano: str) -> str | None:
    especificos = (" histograma", " dispersion", " boxplot", " diagrama de caja", " mapa de calor", " pastel", " grafico")
    if not _tiene(plano, "graficos") and not any(e in plano for e in especificos):
        return None
    for tipo, palabras in GRAFICOS.items():
        if any(f" {p}" in plano for p in palabras):
            return tipo
    return "auto"


SALUDOS = (" hola ", " buenos dias ", " buenas tardes ", " buenas noches ", " gracias ", " como estas ", " que tal ",
           " quien eres ", " que puedes hacer ", " adios ", " hasta luego ", " ok ", " vale ", " perfecto ")
ANALITICAS = (" cuanto", " cuantos", " cuantas", " promedio", " mediana", " compar", " tendencia",
              " evolucion", " ranking", " top ", " mayor", " menor", " mas alt", " mas baj", " distribucion", " resum",
              " datos", " describe", " total", " analiza", " relacion", " correlacion", " grafic", " histograma",
              " dispersion", " tasa", " porcentaje", " proporcion", " muestra", " tabla", " archivo", " documento",
              " informe", " pdf ", " perfil", " anomal", " kpi", " indicador")
PALABRAS_DOC = (" documento", " informe", " pdf ", " reporte", " archivo", " texto", " dice ", " segun el ", " resume")


def es_analitica(plano: str) -> bool:
    if any(s in plano for s in SALUDOS) and len(plano.split()) <= 6:
        return False
    return any(a in plano for a in ANALITICAS)


def _toca_documentos(brain, texto: str) -> bool:
    """¿La pregunta comparte suficiente vocabulario con algún documento cargado?"""
    ctx = brain.rac.buscar(texto, k=1, tipos=("documento",))
    return bool(ctx) and ctx[0].puntaje >= 0.5


def _consulta_busqueda(texto: str) -> str:
    t = re.sub(r"(?i)\b(por favor|investiga(r)?|busca(r|me)?( en)?( internet| la web| google)?|en internet|en la web|"
               r"art[ií]culos? cient[ií]ficos?( sobre| de)?|noticias( sobre| de)?|dime|qu[eé] dicen?|sobre)\b", " ", texto)
    t = re.sub(r"\s+", " ", t).strip(" ¿?.,:;")
    return t or texto


def por_reglas(texto: str, espacio) -> PlanOrquestador:
    plano = corregir(texto)
    plan = PlanOrquestador(texto, plano.strip(), grafico=tipo_grafico(plano))
    brain = espacio.brain
    hay_tablas = bool(brain.biblioteca.motores)
    hay_docs = brain.rac_tiene_documentos()
    pasos = plan.pasos

    ref = re.search(r"\[investigacion:([a-f0-9]{8})\]", texto)
    if ref:
        pasos.append({"herramienta": "usar_investigacion", "argumentos": {"id": ref.group(1)}})
        plan.razon = "Usar una investigación ya hecha."
        return plan
    m = re.match(r"(?is)\s*(recuerda|recuerde|anota|ten en cuenta|toma nota)( que|:)?\s+(.+)", texto)
    if m:
        pasos.append({"herramienta": "recordar", "argumentos": {"hecho": m.group(3).strip()}})
        plan.razon = "El usuario pidió recordar un dato."
        return plan
    m = re.search(r"(?i)pa[ií]s de referencia\s*(es|sea|será|:|a)?\s*([\wÁÉÍÓÚáéíóúñ ]+)", texto)
    if m and est.paises_en(m.group(2)):
        pasos.append({"herramienta": "fijar_pais_referencia", "argumentos": {"pais": est.paises_en(m.group(2))[0]}})
        plan.razon = "Cambio de país de referencia."
        return plan

    indicador = est.indicador_en(plano)
    paises = est.paises_en(texto)
    explicito = any(p in plano for p in (" mis datos ", " mi base ", " mi archivo ", " la base ", " el archivo ",
                                         " nuestros ", " mi empresa ", " nuestra ", " mis sucursales ", " mis empleados "))
    relevancia = max((i.relevancia(texto) for i in brain.interpretes.values()), default=0)
    externo = _tiene(plano, "web") or _tiene(plano, "noticias") or _tiene(plano, "academico")
    # Con una pregunta externa, nombrar sólo una ciudad o categoría de la base no basta: hace falta un indicador.
    if externo:
        from dinamo.core.texto import posicion
        tp = texto_plano(texto)
        relevancia = 1 if any(posicion(term.frase, tp) >= 0 for i in brain.interpretes.values()
                              for term in getattr(i, "_metricas", [])) else 0
    menciona_datos = hay_tablas and (explicito or relevancia > 0)
    if indicador and (paises or " pais" in plano or " banco mundial " in plano or " nacional " in plano):
        pasos.append({"herramienta": "indicador_pais", "argumentos": {"indicador": indicador, "paises": paises}})
    if _tiene(plano, "academico"):
        pasos.append({"herramienta": "buscar_articulos", "argumentos": {"consulta": _consulta_busqueda(texto)}})
    if _tiene(plano, "noticias"):
        pasos.append({"herramienta": "investigar_web", "argumentos": {"consulta": _consulta_busqueda(texto), "modo": "noticias"}})
    elif _tiene(plano, "tecnica"):
        pasos.append({"herramienta": "investigar_web", "argumentos": {"consulta": _consulta_busqueda(texto), "modo": "tecnica"}})
    elif _tiene(plano, "web") and not any(p["herramienta"] in ("buscar_articulos", "indicador_pais") for p in pasos):
        pasos.append({"herramienta": "investigar_web", "argumentos": {"consulta": _consulta_busqueda(texto), "modo": "web"}})

    if hay_tablas and plan.grafico in ("histograma", "dispersion") and not pasos:
        p = preguntar_brain(espacio, texto)
        metricas = list(p.metricas) if p else []
        if p and p.tabla:
            perfil = brain.biblioteca.motor(p.tabla).perfil
            nombrados = [c.nombre for c in perfil.por_rol("metrica") + perfil.por_rol("binaria")
                         if f" {texto_plano(c.nombre).strip()} " in plano or f" {texto_plano(c.nombre_visible).strip()} " in plano]
            metricas = list(dict.fromkeys(metricas + nombrados))
        if plan.grafico == "histograma" and metricas:
            pasos.append({"herramienta": "ejecutar_skill", "argumentos": {
                "skill": "histograma", "parametros": {"metrica": metricas[0]}, "tabla": p.tabla}})
        elif plan.grafico == "dispersion" and len(metricas) >= 2:
            pasos.append({"herramienta": "ejecutar_skill", "argumentos": {
                "skill": "dispersion", "parametros": {"metrica_x": metricas[0], "metrica_y": metricas[1]}, "tabla": p.tabla}})
        else:
            plan.aclaracion = ("¿Qué indicador quieres en el histograma?" if plan.grafico == "histograma"
                               else "¿Qué dos indicadores quieres comparar en el gráfico de dispersión (eje X y eje Y)?")
        if pasos or plan.aclaracion:
            plan.razon = f"Gráfico pedido explícitamente: {plan.grafico}."
            return plan
    if hay_tablas and _tiene(plano, "anomalias"):
        p = preguntar_brain(espacio, texto)
        pasos.insert(0, {"herramienta": "ejecutar_skill", "argumentos": {
            "skill": "anomalias", "parametros": {"metrica": p.metrica if p else None}, "tabla": p.tabla if p else None}})
    elif hay_tablas and _tiene(plano, "kpis") and (menciona_datos or not pasos) and any(
            brain.registro.obtener("indicadores_talento").aplica(mm.perfil) for mm in brain.biblioteca.motores.values()):
        dim = None
        for mm in brain.biblioteca.motores.values():
            for c in mm.perfil.por_rol("dimension"):
                if f" {texto_plano(c.nombre).strip()} " in plano or f" {texto_plano(c.nombre_visible).strip()} " in plano:
                    dim = c.nombre
        pasos.insert(0, {"herramienta": "indicadores_talento", "argumentos": {"dimension": dim}})
    elif hay_tablas and (menciona_datos or (not pasos and es_analitica(plano))):
        pasos.insert(0, {"herramienta": "analizar_datos", "argumentos": {"pregunta": texto}})
    elif hay_docs and not hay_tablas and (any(w in plano for w in PALABRAS_DOC) or _toca_documentos(brain, texto)):
        pasos.insert(0, {"herramienta": "consultar_documentos", "argumentos": {"pregunta": texto}})
    if hay_docs and hay_tablas and not any(p["herramienta"] == "consultar_documentos" for p in pasos) and \
            any(w in plano for w in (" documento ", " informe ", " pdf ", " reporte ", " dice el ")):
        pasos.append({"herramienta": "consultar_documentos", "argumentos": {"pregunta": texto}})
    plan.pasos = pasos[:MAX_PASOS]
    plan.razon = "Plan por reglas (sin modelo de lenguaje)." if pasos else \
        "Pregunta general: se responde con conocimiento general, sin datos ni fuentes."
    return plan


# ----------------------------------------------------------------------------------------- LLM
SISTEMA_PLAN = """Eres el planificador de DINAMO. Decide qué herramientas usar para responder.
Devuelve SOLO un objeto JSON, sin texto adicional, con esta forma:
{"pregunta_normalizada": "la pregunta con la ortografía corregida",
 "pasos": [{"herramienta": "nombre", "argumentos": {...}}],
 "aclaracion": null}
Reglas:
- Usa sólo las herramientas de la lista. Máximo 4 pasos. Puede ser una lista vacía si es charla general.
- Si la pregunta es sobre los archivos del usuario, usa analizar_datos o consultar_documentos.
- Si pide información externa (internet, noticias, artículos, cifras de un país), usa la herramienta de investigación.
- Para buscar_articulos, escribe la consulta en inglés académico.
- Pon "aclaracion" (una sola pregunta corta) SOLO si sin ella la respuesta cambiaría materialmente.
- Nunca inventes nombres de columnas: usa sólo los que aparecen en ARCHIVOS."""


def _catalogo() -> str:
    return "\n".join(f"- {h.nombre}({', '.join(f'{k}: {v}' for k, v in h.argumentos.items())}): {h.descripcion}"
                     for h in HERRAMIENTAS.values())


def describir_archivos(espacio) -> str:
    brain = espacio.brain
    lineas = []
    for n, m in brain.biblioteca.motores.items():
        cols = ", ".join(f"{c.nombre} ({c.rol})" for c in m.perfil.columnas if c.rol != "ignorar")[:900]
        lineas.append(f"- tabla {n} [{m.documento}], {m.num_filas()} filas: {cols}")
    for d in brain.rac.documentos() if hasattr(brain.rac, "documentos") else []:
        lineas.append(f"- documento de texto {d}")
    return "\n".join(lineas) or "(ningún archivo cargado)"


def extraer_json(texto: str) -> dict | None:
    texto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M)
    inicio = texto.find("{")
    while inicio >= 0:
        nivel = 0
        for i in range(inicio, len(texto)):
            nivel += {"{": 1, "}": -1}.get(texto[i], 0)
            if nivel == 0:
                try:
                    return json.loads(texto[inicio:i + 1])
                except json.JSONDecodeError:
                    break
        inicio = texto.find("{", inicio + 1)
    return None


def validar(d: dict | None, texto: str) -> PlanOrquestador | None:
    if not isinstance(d, dict) or not isinstance(d.get("pasos", []), list):
        return None
    pasos = []
    for p in d.get("pasos", [])[:MAX_PASOS]:
        if not isinstance(p, dict) or p.get("herramienta") not in HERRAMIENTAS:
            return None
        args = p.get("argumentos") if isinstance(p.get("argumentos"), dict) else {}
        pasos.append({"herramienta": p["herramienta"], "argumentos": args})
    acl = d.get("aclaracion")
    norm = d.get("pregunta_normalizada") if isinstance(d.get("pregunta_normalizada"), str) else texto
    return PlanOrquestador(texto, norm[:500], pasos, acl if isinstance(acl, str) and acl.strip() else None,
                           tipo_grafico(corregir(texto)), "llm", "Plan propuesto por el modelo y validado.")


def planificar(texto: str, espacio, llm=None, historial: str = "") -> PlanOrquestador:
    reglas = por_reglas(texto, espacio)
    if llm is None or isinstance(llm, LLMFalso) or reglas.pasos and reglas.pasos[0]["herramienta"] in (
            "recordar", "fijar_pais_referencia", "usar_investigacion"):
        return reglas
    usuario = (f"HERRAMIENTAS:\n{_catalogo()}\n\nARCHIVOS:\n{describir_archivos(espacio)}\n\n"
               f"CONVERSACIÓN RECIENTE:\n{historial or '(inicio)'}\n\nPREGUNTA:\n{texto}")
    try:
        plan = validar(extraer_json(llm.generar(SISTEMA_PLAN, usuario)), texto)
    except LLMNoDisponible:
        plan = None
    if plan is None:
        reglas.razon += " (el plan del modelo no fue válido)"
        return reglas
    if not plan.pasos and reglas.pasos and not plan.aclaracion:     # red de seguridad
        reglas.normalizada = plan.normalizada
        return reglas
    return plan
