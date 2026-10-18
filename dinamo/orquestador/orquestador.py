"""
ORQUESTADOR: el flujo completo de un mensaje del usuario, emitido como eventos para la interfaz.

  mensaje → (resumen de contexto si hace falta) → plan → herramientas → material →
  síntesis con LLM (en streaming) → verificación de citas y cifras → mensaje guardado.

Eventos (dict con "tipo"): plan · herramienta · evidencias · fuentes · datos · texto · aclaracion ·
necesita_llm (el navegador debe redactar con su propia IA) · final · error.
"""
from __future__ import annotations

from typing import Iterator

from dinamo.llm import LLMFalso, LLMNoDisponible

from .herramientas import HERRAMIENTAS, Material, ejecutar
from .planificador import describir_archivos, planificar
from .sintesis import construir_mensajes, sin_llm, verificar


def _historial_corto(recientes: list[dict]) -> str:
    return "\n".join(f"{'Usuario' if m['rol'] == 'usuario' else 'DINAMO'}: {m['texto'][:300]}" for m in recientes[-4:])


ETIQUETAS = {"analizar_datos": "Calculando con tus datos", "consultar_documentos": "Buscando en tus documentos",
             "indicadores_talento": "Calculando indicadores de talento", "investigar_web": "Investigando en internet",
             "buscar_articulos": "Buscando artículos científicos", "indicador_pais": "Consultando estadísticas oficiales",
             "usar_investigacion": "Usando una investigación guardada", "recordar": "Guardando en la memoria del chat",
             "fijar_pais_referencia": "Cambiando el país de referencia"}


def _etiqueta(nombre: str, args: dict) -> str:
    if nombre == "ejecutar_skill":
        return f"Ejecutando el análisis «{str(args.get('skill', '')).replace('_', ' ')}»"
    if nombre == "investigar_web" and args.get("modo") == "noticias":
        return "Buscando noticias"
    return ETIQUETAS.get(nombre, nombre)


def _evidencia_dict(e) -> dict:
    return e.a_dict()


def procesar(espacio, texto: str, llm=None, llm_en_navegador: bool = False, persona: str = "") -> Iterator[dict]:
    texto = (texto or "").strip()
    if not texto:
        yield {"tipo": "error", "mensaje": "El mensaje está vacío."}
        return
    real = llm if (llm is not None and not isinstance(llm, LLMFalso)) else None
    espacio.agregar_mensaje("usuario", texto)

    # 1. Resumen de contexto si la conversación ya es larga
    if espacio.necesita_resumen():
        from dinamo.conversacion import resumir
        hasta = len(espacio.mensajes) - 8
        viejos = espacio.mensajes[espacio.resumen_hasta:hasta]
        espacio.resumen, metodo = resumir(viejos, espacio.resumen, real)
        espacio.resumen_hasta = hasta
        espacio.guardar()
        yield {"tipo": "contexto", "mensaje": f"Resumí {len(viejos)} mensajes anteriores ({metodo}) para mantener el contexto."}

    resumen, recientes = espacio.historial_para_llm()
    recientes = recientes[:-1]                       # sin el mensaje que acabamos de agregar

    # 2. Plan
    plan = planificar(texto, espacio, real, _historial_corto(recientes))
    yield {"tipo": "plan", "plan": plan.a_dict()}
    if plan.aclaracion:
        m = espacio.agregar_mensaje("asistente", plan.aclaracion, tipo="aclaracion", plan=plan.a_dict())
        yield {"tipo": "aclaracion", "pregunta": plan.aclaracion, "opciones": []}
        yield {"tipo": "final", "mensaje": m}
        return

    # 3. Herramientas
    material = Material()
    for paso in plan.pasos:
        nombre = paso["herramienta"]
        yield {"tipo": "herramienta", "nombre": nombre, "estado": "inicio",
               "etiqueta": _etiqueta(nombre, paso.get("argumentos", {})), "argumentos": paso.get("argumentos", {})}
        try:
            parcial = ejecutar(espacio, nombre, paso.get("argumentos", {}), plan.normalizada if plan.origen == "llm" else texto)
        except Exception as exc:                      # una herramienta rota no tumba la respuesta
            parcial = Material(advertencias=[f"{nombre} falló: {type(exc).__name__}: {exc}"])
        material.sumar(parcial)
        resumen_paso = {"evidencias": len(parcial.evidencias), "fragmentos": len(parcial.contexto),
                        "fuentes": len(parcial.fuentes), "avisos": parcial.advertencias[:3]}
        yield {"tipo": "herramienta", "nombre": nombre, "estado": "fin", "resultado": resumen_paso}

    if material.aclaracion is not None and material.vacio():
        a = material.aclaracion
        espacio.brain.estado.aclaracion_pendiente = a
        texto_a = a.pregunta + "\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(a.opciones, 1))
        m = espacio.agregar_mensaje("asistente", texto_a, tipo="aclaracion", opciones=list(a.opciones), plan=plan.a_dict())
        yield {"tipo": "aclaracion", "pregunta": a.pregunta, "opciones": list(a.opciones)}
        yield {"tipo": "final", "mensaje": m}
        return

    if material.evidencias:
        yield {"tipo": "evidencias", "items": [_evidencia_dict(e) for e in material.evidencias]}
    if material.fuentes:
        yield {"tipo": "fuentes", "items": [f.a_dict() for f in material.fuentes]}
    if material.datos:
        yield {"tipo": "datos", "datos": material.datos, "grafico": plan.grafico}

    # 4. Síntesis
    mensajes = construir_mensajes(texto, plan.normalizada, material, espacio.memoria, resumen, recientes,
                                  describir_archivos(espacio), persona)
    extra = {"plan": plan.a_dict(), "evidencias": [_evidencia_dict(e) for e in material.evidencias],
             "fuentes": [f.a_dict() for f in material.fuentes], "documentos": [c.fuente for c in material.contexto],
             "contexto": [{"fuente": c.fuente, "texto": c.texto[:600], "tipo": c.tipo} for c in material.contexto],
             "datos": material.datos, "grafico": plan.grafico, "sugerencias": material.sugerencias[:4],
             "investigaciones": material.investigaciones}

    if real is not None:
        partes = []
        try:
            for trozo in real.chat(mensajes) if hasattr(real, "chat") else [real.generar(mensajes[0]["content"],
                                                                                          mensajes[-1]["content"])]:
                partes.append(trozo)
                yield {"tipo": "texto", "delta": trozo}
            respuesta = "".join(partes).strip()
            modelo = getattr(real, "describir", lambda: {"proveedor": "llm"})()
        except LLMNoDisponible as exc:
            material.advertencias.append(f"El modelo de lenguaje no respondió ({exc}); muestro el material verificado.")
            respuesta = sin_llm(texto, material) if not partes else "".join(partes)
            modelo = {"proveedor": "ninguno"}
            yield {"tipo": "texto", "reemplazar": True, "delta": respuesta}
    elif llm_en_navegador:
        m = espacio.agregar_mensaje("asistente", "", pendiente=True, advertencias=material.advertencias,
                                    modelo={"proveedor": "navegador"}, **extra)
        espacio._material_pendiente = getattr(espacio, "_material_pendiente", {})
        espacio._material_pendiente[m["id"]] = material
        yield {"tipo": "necesita_llm", "mensaje_id": m["id"], "mensajes": mensajes,
               "respaldo": sin_llm(texto, material)}
        return
    else:
        respuesta = sin_llm(texto, material)
        modelo = {"proveedor": "ninguno"}
        yield {"tipo": "texto", "delta": respuesta}

    problemas = verificar(respuesta, material) if modelo.get("proveedor") != "ninguno" else []
    m = espacio.agregar_mensaje("asistente", respuesta, advertencias=material.advertencias, verificacion=problemas,
                                modelo=modelo, **extra)
    yield {"tipo": "final", "mensaje": m}


def completar_desde_navegador(espacio, mensaje_id: str, texto: str) -> dict:
    """El navegador redactó la respuesta con su IA local: se verifica y se guarda."""
    m = next((x for x in espacio.mensajes if x["id"] == mensaje_id and x.get("pendiente")), None)
    if m is None:
        raise KeyError(mensaje_id)
    material = getattr(espacio, "_material_pendiente", {}).pop(mensaje_id, None)
    if material is None:                                 # el servidor se reinició: verificación con lo guardado
        from dinamo.core.contracts import Contexto, Evidencia
        from dinamo.investigacion.fuentes import Fuente
        material = Material(evidencias=[Evidencia(**e) for e in m.get("evidencias", [])],
                            contexto=[Contexto(c["fuente"], c["texto"], 1.0, c["tipo"]) for c in m.get("contexto", [])],
                            fuentes=[Fuente(**{k: v for k, v in f.items() if k != "dominio"}) for f in m.get("fuentes", [])])
    with espacio.candado:
        m["texto"] = (texto or "").strip()[:20000]
        m["pendiente"] = False
        m["verificacion"] = verificar(m["texto"], material)
        espacio.guardar()
    return m
