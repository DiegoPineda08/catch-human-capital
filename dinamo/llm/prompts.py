"""
Construcción de prompts. El LLM INTERPRETA; no calcula.

Por eso:
- los valores llegan ya formateados por código (p.ej. 0.0925 -> "9.3%");
- cada evidencia lleva un id que el LLM debe citar como [E:id];
- cada fragmento de documento lleva su fuente, que el LLM cita como [C:fuente];
- `citas_invalidas` detecta citas inventadas para que el Brain lo advierta;
- el perfil del usuario cambia el TONO de la respuesta, nunca los números.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence

from dinamo.core.contracts import Contexto, Evidencia

SISTEMA = """Eres DINAMO, un analista de datos que explica resultados a personas sin formación técnica.
Reglas obligatorias:
1. Usa SOLO las evidencias y el contexto que se te entregan. No inventes cifras.
2. No hagas cálculos nuevos: copia los valores tal como aparecen en la evidencia.
3. Cita cada cifra con su id entre corchetes, por ejemplo [E:tendencia:1a2b3c4d].
4. Si usas un fragmento de un documento, cítalo con su fuente, por ejemplo [C:informe.pdf#p2].
5. Una correlación NO es causalidad: usa "se asocia con", nunca "causa" o "provoca".
6. Si la evidencia y el contexto no alcanzan para responder, dilo claramente.
7. Adapta el tono a la persona que pregunta (ver PERSONA), pero nunca cambies las cifras.
8. Responde en español, en máximo 6 frases, claro y sin tecnicismos.

EJEMPLO (sólo muestra el formato; tu tema será otro):
PREGUNTA:
¿Cómo van las ventas de la sucursal Norte?

EVIDENCIA:
- [E:ventas:aa11bb22] Ventas del último mes, sucursal Norte: 120.5 miles de pesos (n=1; suma del mes)
- [E:ventas:cc33dd44] Mediana de ventas entre sucursales: 98 miles de pesos (n=12; mediana)
RESPUESTA: La sucursal Norte vendió 120.5 miles de pesos en el último mes [E:ventas:aa11bb22]. La mediana de las 12 sucursales es de 98 miles de pesos [E:ventas:cc33dd44], así que Norte está por encima del centro del grupo. Son datos descriptivos: no explican por qué hay diferencia.

EJEMPLO DE DOCUMENTO (sólo muestra el formato; tu tema será otro):
PREGUNTA:
¿Qué recomienda el manual?

CONTEXTO RECUPERADO:
- [C:manual_tiendas.pdf#p2] Recomendaciones. Conviene revisar el horario de apertura y reforzar la atención en fines de semana.

EVIDENCIA:
(sin evidencia)
RESPUESTA: El manual recomienda revisar el horario de apertura y reforzar la atención en fines de semana [C:manual_tiendas.pdf#p2]. No trae cifras sobre cuánto mejoraría cada medida."""


def _moneda(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def formatear_valor(e: Evidencia) -> str:
    """Convierte el número en texto listo para leer, así el LLM nunca tiene que calcular."""
    v = e.valor
    if isinstance(v, str):
        return v
    formatos = {
        "proporcion": lambda x: f"{x * 100:.1f}%",
        "diferencia_proporcion": lambda x: f"{x * 100:+.1f} puntos porcentuales",
        "cambio_relativo": lambda x: f"{x * 100:+.1f}%",
        "rho": lambda x: f"{x:+.2f}",
        "moneda": _moneda,
        "conteo": lambda x: f"{x:,.0f}",
        "dias": lambda x: f"{x:,.1f} días",
        "escala": lambda x: f"{x:.2f}",
    }
    return formatos.get(e.unidad, lambda x: f"{x:,.4g}" if abs(x) < 1e6 else f"{x:,.0f}")(v)


def construir_mensajes(pregunta: str, contexto: list[Contexto], evidencias: list[Evidencia],
                       advertencias: list[str] | None = None, sobre_la_base: str = "",
                       usuario: str = "") -> tuple[str, str]:
    """Arma los dos mensajes del LLM: el de sistema (reglas) y el de usuario (todo el material).

    `usuario`: el texto de la persona (p.ej. PerfilUsuario.describir()) o el perfil mismo (se convierte)."""
    persona = instruccion_perfil(usuario) if usuario and not isinstance(usuario, str) else usuario
    bloque_ctx = "\n".join(f"- [C:{c.fuente}] " + " ".join(c.texto.split()) for c in contexto) or "(sin contexto)"
    bloque_ev = "\n".join(f"- [E:{e.id}] {_de_tabla(e)}{e.descripcion}: {formatear_valor(e)} (n={e.n}; {e.metodo})"
                          for e in evidencias) or "(sin evidencia)"
    bloque_adv = "\n".join(f"- {a}" for a in (advertencias or [])) or "(ninguna)"
    mensaje = (f"PERSONA:\n{persona or '(sin datos del usuario)'}\n\n"
               f"FUENTES:\n{sobre_la_base or '(sin descripción)'}\n\n"
               f"PREGUNTA:\n{pregunta}\n\nCONTEXTO RECUPERADO:\n{bloque_ctx}\n\n"
               f"EVIDENCIA:\n{bloque_ev}\n\nADVERTENCIAS:\n{bloque_adv}\n\n"
               "Responde la pregunta siguiendo las reglas.")
    return SISTEMA, mensaje


def _de_tabla(e: Evidencia) -> str:
    tabla = e.filtros.get("tabla")
    return f"({tabla}) " if tabla else ""


def _limpio(valor, n: int = 80) -> str:
    """Los campos del perfil vienen del usuario: sin saltos de línea ni corchetes (no pueden fingir una cita ni una orden)."""
    return re.sub(r"[\[\]\r\n]+", " ", str(valor or "")).strip()[:n]


_TONO = {
    "breve": "Responde de forma muy concisa, máximo 3 frases.",
    "detallado": "Puedes dar más contexto y detalles técnicos si ayudan a entender.",
    "directivo": "Prioriza la conclusión y qué hacer; evita detalles de método.",
    "analista": "Incluye el método, el tamaño de muestra y las advertencias.",
}


def instruccion_perfil(perfil: dict | object) -> str:
    """Perfil del usuario -> texto de la sección PERSONA (cambia el TONO; nunca los números).

    Acepta el PerfilUsuario del esqueleto (nombre, rol, nivel, intereses), un dict o un objeto con
    nombre, cargo/rol, nivel_detalle/nivel e intereses. Devuelve '' si no hay nada útil."""
    if not perfil:
        return ""
    if isinstance(perfil, str):
        return _limpio(perfil, 300)

    def campo(*nombres: str):
        for nombre in nombres:
            v = perfil.get(nombre) if isinstance(perfil, Mapping) else getattr(perfil, nombre, None)
            if v:
                return v
        return None

    partes = []
    if (v := campo("nombre")):
        partes.append(f"nombre: {_limpio(v)}")
    if (v := campo("rol", "cargo")):
        partes.append(f"rol: {_limpio(v)}")
    if (v := campo("intereses")):
        lista = [v] if isinstance(v, str) else list(v)[:5]
        partes.append("intereses: " + ", ".join(_limpio(x, 40) for x in lista))
    tonos = [_TONO[n] for n in (_limpio(campo("nivel_detalle")).lower(), _limpio(campo("nivel")).lower()) if n in _TONO]
    if not partes and not tonos:
        return ""
    return "; ".join(partes) + ("." if partes else "") + (" " if partes and tonos else "") + " ".join(tonos)


def citas_invalidas(texto: str, ids_validos, fuentes_validas=None) -> list[str]:
    """Citas del LLM que NO existen: ids de evidencia [E:..] o fuentes de contexto [C:..] inventados.

    Acepta lo que usa el Brain (conjuntos de ids y de fuentes) y también listas de Evidencia/Contexto."""
    ids = {getattr(x, "id", x) for x in ids_validos}
    malas = {c for c in re.findall(r"\[E:([^\]]+)\]", texto) if c not in ids}
    if fuentes_validas is not None:
        fuentes = {getattr(x, "fuente", x) for x in fuentes_validas}
        malas |= {f"C:{c}" for c in re.findall(r"\[C:([^\]]+)\]", texto) if c not in fuentes}
    return sorted(malas)


# ---------------------------------------------------------------- validadores de cifras (tarea C2)
_RE_CITA = re.compile(r"\[E:([^\]]+)\]")
_RE_CITA_C = re.compile(r"\[C:([^\]]+)\]")        # cita de documento: [C:informe.pdf#p2]
_RE_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?|\d+(?:,\d+)?")


def _canon(s: str) -> str | None:
    """'10,4' -> '10.4'; '35,200' -> '35200'; '10.40' -> '10.4'. None si no es un número."""
    s = s.strip().strip(",")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):      # miles con coma
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")                            # coma decimal (escritura en español)
    try:
        d = Decimal(s).normalize()
    except InvalidOperation:
        return None
    return format(d, "f")


def _numeros(texto: str) -> set[str]:
    """Números de un texto, ignorando [E:id], [C:fuente] ('#p2' no es una cifra) y numeración de listas."""
    limpio = _RE_CITA_C.sub(" ", _RE_CITA.sub(" ", texto))
    limpio = re.sub(r"(?m)^\s*\d+[.)]\s+", " ", limpio)
    return {c for c in (_canon(m) for m in _RE_NUM.findall(limpio)) if c is not None}


def _numeros_permitidos(evidencias: Sequence[Evidencia], contexto: Sequence[Contexto], pregunta: str,
                        extras: Iterable[str] = ()) -> set[str]:
    texto = [pregunta, *extras]
    for e in evidencias:
        texto += [e.descripcion, formatear_valor(e), str(e.n), str(e.metodo)]
        if isinstance(e.filtros, dict):
            texto += [str(v) for v in e.filtros.values()]
        if isinstance(e.valor, (int, float)) and not isinstance(e.valor, bool):
            v = float(e.valor)
            texto += [repr(v), f"{v:.4f}", f"{v:.2f}", f"{v * 100:.1f}", f"{v * 100:.2f}"]
            if e.unidad in ("proporcion", "porcentaje", "cambio_relativo", "diferencia_proporcion"):
                texto.append(f"{abs(v) * 100:.1f}")      # el LLM puede omitir el signo
        else:
            texto.append(str(e.valor))
    texto += [c.texto for c in contexto]
    return _numeros(" ".join(texto))


def cifras_sin_respaldo(texto: str, evidencias: Sequence[Evidencia], contexto: Sequence[Contexto] = (),
                        pregunta: str = "", extras: Iterable[str] = ()) -> list[str]:
    """Cifras del texto que no aparecen en ninguna evidencia, en el contexto, en la pregunta ni en `extras`
    (advertencias y descripción de las fuentes, que el LLM también ve).

    Compara números completos (no pedazos de texto): acepta coma decimal (10,4) y miles (35,200), no se
    confunde con los ids de [E:…] ni con '#p2' de [C:…], y rechaza diferencias calculadas por el LLM."""
    permitidas = _numeros_permitidos(evidencias, contexto, pregunta, extras)
    return sorted(_numeros(texto) - permitidas, key=lambda n: (len(n), n))


def cifras_sin_cita(texto: str) -> list[str]:
    """Frases que contienen una cifra pero ninguna cita ([E:id] de evidencia o [C:fuente] de documento)."""
    frases = re.split(r"(?<=[.!?])\s+|\n+", texto)
    return [f.strip() for f in frases if _numeros(f) and not _RE_CITA.search(f) and not _RE_CITA_C.search(f)]


def construir_prompt_usuario(pregunta: str, evidencias: Sequence[Evidencia], contexto: Sequence[Contexto] = (),
                             advertencias: Iterable[str] = (), correcciones: Sequence[str] = (),
                             perfil=None) -> str:
    """Sólo el mensaje de usuario (lo usan scripts/evaluar_llm.py y la redacción por secciones)."""
    _, mensaje = construir_mensajes(pregunta, list(contexto), list(evidencias), list(advertencias), usuario=perfil or "")
    if correcciones:
        mensaje += "\n\nCORRECCIONES NECESARIAS:\n" + "\n".join(f"- {c}" for c in correcciones)
    return mensaje
