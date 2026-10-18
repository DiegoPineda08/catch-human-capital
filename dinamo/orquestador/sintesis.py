"""
SÍNTESIS: el LLM redacta la respuesta con TODO el material, separando claramente:
  tus datos [E:id] · tus documentos [C:fuente] · fuentes externas [W:n] · interpretación · recomendaciones.

Después se verifica: citas inexistentes y cifras que no aparecen en el material se reportan.
Sin LLM, se arma una respuesta determinística con el material (nunca se inventa nada).
"""
from __future__ import annotations

import re

from dinamo.llm.prompts import formatear_valor

from .herramientas import Material

SISTEMA = """Eres DINAMO, asistente de análisis de capital humano y datos para consultoría.
Respondes en español, claro y directo, adaptando la extensión a la pregunta (una pregunta corta merece una respuesta corta).

REGLAS DE VERACIDAD (obligatorias):
1. Las cifras sobre los datos del usuario sólo pueden venir de EVIDENCIA; cópialas tal cual y cita su id: [E:id].
2. Lo que tomes de los documentos del usuario, cítalo así: [C:fuente].
3. Lo que tomes de fuentes externas, cítalo así: [W:n]. Si su estado es "solo fragmento" o "solo resumen",
   di que te basas en el fragmento o el resumen: no afirmes haber leído el documento completo.
4. No calcules cifras nuevas ni inventes estadísticas, autores, estudios o enlaces.
5. Puedes usar conocimiento general para explicar conceptos, pero márcalo como "(conocimiento general)"
   y nunca lo presentes como dato del usuario ni como cifra verificada.
6. Correlación no es causalidad: usa "se asocia con".
7. En temas de personal, nunca uses ni recomiendes criterios basados en edad, sexo, embarazo, estado civil,
   origen étnico, religión, discapacidad, orientación sexual u otros atributos protegidos.
8. Si el material no alcanza, dilo y sugiere qué dato o búsqueda haría falta.
9. Si piden datos actuales (hoy, cifras recientes, precios, clima, leyes vigentes) y no hay FUENTES EXTERNAS en el
   material, no los inventes: explica que necesitas investigarlo y sugiere pedir «investiga…».
10. Si el usuario cargó archivos pero la pregunta no trata de ellos, responde la pregunta; no fuerces el archivo.

FORMATO (markdown). Empieza con la respuesta directa en 1-3 frases, sin encabezado. Después, SOLO si hay contenido:
### Según tus datos
### Según tus documentos
### Fuentes externas
### Interpretación  (aquí van tus inferencias; señálalas como tales)
### Recomendaciones
### Limitaciones
No incluyas una sección vacía. No repitas el material completo: sintetiza."""


def _fuente_txt(f) -> str:
    cabecera = (f"[{f.id}] {f.titulo} — {f.tipo}; {f.dominio}; estado: {f.estado}"
                + (f"; publicado: {f.fecha_publicacion}" if f.fecha_publicacion else "")
                + (f"; autores: {', '.join(f.autores[:3])}" if f.autores else "")
                + (f"; revista/medio: {f.medio}" if f.medio else ""))
    if f.datos:
        cuerpo = "datos: " + ", ".join(f"{d['anio']}: {d['valor']:g}" for d in f.datos[-8:])
    elif f.pasajes:
        cuerpo = "pasajes leídos: " + " … ".join(p[:600] for p in f.pasajes[:3])
    elif f.fragmento:
        cuerpo = "fragmento: " + f.fragmento[:700]
    else:
        cuerpo = f"sin contenido ({f.motivo or 'no disponible'})"
    return f"- {cabecera}\n  {cuerpo}"


def bloque_material(m: Material) -> str:
    ev = "\n".join(f"- [E:{e.id}] {('(' + e.filtros['tabla'] + ') ') if e.filtros.get('tabla') else ''}{e.descripcion}: "
                   f"{formatear_valor(e)} (n={e.n}; {e.metodo})" for e in m.evidencias[:60])
    docs = "\n".join(f"- [C:{c.fuente}] {' '.join(c.texto.split())[:700]}" for c in m.contexto[:8])
    web = "\n".join(_fuente_txt(f) for f in m.fuentes[:12])
    adv = "\n".join(f"- {a}" for a in m.advertencias)
    notas = "\n".join(f"- {n}" for n in m.notas)
    return (f"EVIDENCIA (calculada por Python):\n{ev or '(ninguna)'}\n\n"
            f"DOCUMENTOS DEL USUARIO:\n{docs or '(ninguno)'}\n\n"
            f"FUENTES EXTERNAS:\n{web or '(ninguna)'}\n\n"
            f"NOTAS DEL SISTEMA:\n{notas or '(ninguna)'}\n\nADVERTENCIAS:\n{adv or '(ninguna)'}")


def construir_mensajes(pregunta: str, normalizada: str, material: Material, memoria: list[dict], resumen: str,
                       recientes: list[dict], archivos: str, persona: str = "") -> list[dict]:
    mensajes = [{"role": "system", "content": SISTEMA}]
    for m in recientes:
        rol = "assistant" if m["rol"] == "asistente" else "user"
        mensajes.append({"role": rol, "content": m["texto"][:1500]})
    mem = "\n".join(f"- {x['hecho']}" for x in memoria) or "(nada)"
    contenido = (f"MEMORIA DE ESTA CONVERSACIÓN (hechos que el usuario pidió recordar):\n{mem}\n\n"
                 f"RESUMEN DE LO CONVERSADO ANTES:\n{resumen or '(nada)'}\n\n"
                 f"ARCHIVOS CARGADOS:\n{archivos}\n\nPERSONA:\n{persona or '(sin datos)'}\n\n"
                 f"{bloque_material(material)}\n\n"
                 f"PREGUNTA DEL USUARIO:\n{pregunta}\n"
                 + (f"(interpretada como: {normalizada})\n" if normalizada and normalizada != pregunta else "")
                 + "\nResponde siguiendo las reglas.")
    if mensajes[-1]["role"] == "user":                     # no dejar dos mensajes de usuario seguidos
        mensajes.append({"role": "assistant", "content": "(continúo)"})
    mensajes.append({"role": "user", "content": contenido})
    return mensajes


NUM = re.compile(r"(?<![\w:])-?\d+(?:[.,]\d+)?\s?%|(?<![\w:])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w:.])\d+\.\d+")


def _normal(x: str) -> str:
    return x.replace(" ", "").replace(",", "")


def verificar(texto: str, material: Material) -> list[str]:
    """Devuelve problemas: citas inexistentes y cifras que no salen del material."""
    problemas = []
    ids = {e.id for e in material.evidencias}
    fuentes = {c.fuente for c in material.contexto}
    webs = {f.id for f in material.fuentes}
    malas = sorted({f"E:{c}" for c in re.findall(r"\[E:([^\]]+)\]", texto) if c not in ids}
                   | {f"C:{c}" for c in re.findall(r"\[C:([^\]]+)\]", texto) if c not in fuentes}
                   | {f"W:{c}" for c in re.findall(r"\[W:(\d+)\]", texto) if f"W:{c}" not in webs})
    if malas:
        problemas.append(f"Citas que no corresponden a ningún material: {', '.join(malas)}")
    sin_ids = re.sub(r"\[(?:E|C|W):[^\]]+\]", " ", bloque_material(material))
    referencia = {x.replace(",", "") for x in re.findall(r"\d[\d,]*(?:\.\d+)?", sin_ids)}
    referencia |= {x.rstrip("0").rstrip(".") for x in referencia if "." in x}
    sueltas = []
    for n in NUM.findall(re.sub(r"\[[EWC]:[^\]]+\]", " ", texto)):
        limpio = _normal(n).rstrip("%")
        if limpio not in referencia and limpio.rstrip("0").rstrip(".") not in referencia:
            sueltas.append(n.strip())
    if sueltas:
        problemas.append("Cifras que no aparecen en el material verificado (revísalas): " + ", ".join(sorted(set(sueltas))[:8]))
    return problemas


def sin_llm(pregunta: str, material: Material) -> str:
    """Respuesta determinística cuando no hay modelo de lenguaje: muestra el material verificado."""
    partes = []
    if material.notas:
        partes += material.notas
    if material.evidencias:
        partes.append("### Según tus datos")
        partes += [f"- {e.descripcion}: **{formatear_valor(e)}** (n={e.n}) [E:{e.id}]" for e in material.evidencias[:15]]
        if len(material.evidencias) > 15:
            partes.append(f"- … y {len(material.evidencias) - 15} resultados más en el panel de evidencias.")
    docs = [c for c in material.contexto if c.tipo == "documento"]
    if docs:
        partes.append("### Según tus documentos")
        partes += [f"- {' '.join(c.texto.split())[:300]} [C:{c.fuente}]" for c in docs[:4]]
    if material.fuentes:
        partes.append("### Fuentes externas")
        for f in material.fuentes[:8]:
            extracto = (f.pasajes[0] if f.pasajes else f.fragmento)[:280]
            partes.append(f"- **{f.titulo}** ({f.tipo}, {f.estado}) [{f.id}]" + (f": {extracto}" if extracto else ""))
    if not partes:
        return ("No tengo un modelo de lenguaje activo para conversar libremente, y esta pregunta no se refiere a tus "
                "archivos ni pide una búsqueda. Sube un archivo, pide una investigación (por ejemplo, «investiga en "
                "internet…») o activa un modelo en Integraciones.")
    encabezado = "Esto es lo que encontré (sin modelo de lenguaje activo, muestro el material verificado tal cual):"
    return encabezado + "\n\n" + "\n".join(partes)
