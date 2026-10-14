"""
dinamo/presentation/narrativa.py
---------------------------------
Transforma la respuesta técnica de brain.responder() en:
  1. Un párrafo narrativo legible (como si alguien lo leyera en voz alta)
  2. Datos estructurados para gráficas
  3. Metadatos de la intención para que el frontend sepa qué gráfica mostrar

No cambia la lógica del motor — solo reformatea la salida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tipos de salida
# ---------------------------------------------------------------------------

@dataclass
class DatoGrafica:
    """Un punto o barra en una gráfica."""
    etiqueta: str          # eje X: "2024-01", "Tienda Norte", etc.
    valor: float           # eje Y
    extra: dict = field(default_factory=dict)   # metadatos opcionales


@dataclass
class Grafica:
    """Todo lo que el frontend necesita para renderizar una gráfica."""
    tipo: str              # "linea" | "barras" | "barras_horizontales" | "ninguna"
    titulo: str
    unidad: str            # "$", "%", "unidades", etc.
    datos: list[DatoGrafica]


@dataclass
class RespuestaNarrativa:
    """Salida enriquecida lista para el frontend."""
    narrativa: str                    # párrafo en lenguaje natural
    grafica: Grafica                  # datos para Chart.js
    sugerencias: list[str]            # preguntas siguientes
    intencion: str                    # "tendencia" | "ranking" | etc.
    metrica: str                      # "ventas", "ausentismo", etc.
    confianza: float = 1.0


# ---------------------------------------------------------------------------
# Extracción de evidencias desde el texto técnico
# ---------------------------------------------------------------------------

# Patrón: [E:tendencia:65579013] (ventas_tiendas) Ventas en 2024-01: $105,543 ...
_RE_EVIDENCIA = re.compile(
    r'\[E:[^\]]+\]\s*\([^)]+\)\s*(.+?)(?=\[E:|$)', re.DOTALL
)

# Patrón para extraer periodo + valor monetario o numérico
_RE_PERIODO_VALOR = re.compile(
    r'(\d{4}-\d{2})[^:]*:\s*\$?([\d,]+(?:\.\d+)?)'
)

# Patrón para cambio relativo: "+24.7%"
_RE_CAMBIO = re.compile(r'([+-]?\d+\.?\d*)\s*%')

# Patrón para periodo máximo/mínimo: "2024-11"
_RE_PERIODO = re.compile(r'(\d{4}-\d{2})')


def _limpiar_numero(texto: str) -> float:
    """Convierte '105,543' → 105543.0"""
    try:
        return float(texto.replace(',', ''))
    except ValueError:
        return 0.0


def _extraer_puntos_serie(texto_tecnico: str) -> list[DatoGrafica]:
    """Saca pares (periodo, valor) de las líneas de evidencia."""
    puntos: list[DatoGrafica] = []
    for match in _RE_PERIODO_VALOR.finditer(texto_tecnico):
        periodo, valor_str = match.group(1), match.group(2)
        # Evitar duplicados (el texto puede repetir el mismo periodo)
        if not any(p.etiqueta == periodo for p in puntos):
            puntos.append(DatoGrafica(etiqueta=periodo, valor=_limpiar_numero(valor_str)))
    puntos.sort(key=lambda p: p.etiqueta)
    return puntos


# ---------------------------------------------------------------------------
# Constructores de narrativa por intención
# ---------------------------------------------------------------------------

def _narrativa_tendencia(texto: str, metrica: str) -> str:
    """Genera un párrafo de tendencia a partir del texto técnico."""
    periodos = _RE_PERIODO.findall(texto)
    valores_match = _RE_PERIODO_VALOR.findall(texto)
    cambio_match = _RE_CAMBIO.search(texto)

    if not valores_match:
        return texto  # fallback: devuelve el texto original

    inicio_periodo = valores_match[0][0] if valores_match else "el inicio"
    inicio_valor = _limpiar_numero(valores_match[0][1]) if valores_match else 0

    # Buscar el valor final (último par periodo-valor antes de las líneas de cambio)
    # Los primeros dos suelen ser inicio y fin
    fin_periodo = valores_match[1][0] if len(valores_match) > 1 else "el cierre"
    fin_valor = _limpiar_numero(valores_match[1][1]) if len(valores_match) > 1 else 0

    cambio = float(cambio_match.group(1)) if cambio_match else None

    # Tono: positivo, negativo o neutro
    if cambio is not None and cambio > 0:
        tono = "creció"
        descripcion_cambio = f"un aumento del **{cambio:.1f}%**"
    elif cambio is not None and cambio < 0:
        tono = "disminuyó"
        descripcion_cambio = f"una caída del **{abs(cambio):.1f}%**"
    else:
        tono = "se mantuvo"
        descripcion_cambio = "sin cambios significativos"

    # Periodos máximo y mínimo
    max_match = re.search(r'valor m.s alto[^:]*:\s*(\d{4}-\d{2})', texto, re.IGNORECASE)
    min_match = re.search(r'valor m.s bajo[^:]*:\s*(\d{4}-\d{2})', texto, re.IGNORECASE)
    periodo_max = max_match.group(1) if max_match else None
    periodo_min = min_match.group(1) if min_match else None

    partes = [
        f"En **{inicio_periodo}**, {metrica} arrancó en **${inicio_valor:,.0f}**. "
        f"Para **{fin_periodo}** había {tono} hasta **${fin_valor:,.0f}** — {descripcion_cambio} durante el período."
    ]

    if periodo_max:
        partes.append(
            f"El mejor mes fue **{periodo_max}**, mientras que **{periodo_min}** "
            f"registró el punto más bajo." if periodo_min else
            f"El mejor mes del período fue **{periodo_max}**."
        )

    return " ".join(partes)


def _narrativa_ranking(texto: str, metrica: str) -> str:
    """Párrafo para rankings de entidades."""
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    items = []
    for linea in lineas:
        m = re.search(r'(.+?)[:\-]\s*\$?([\d,]+)', linea)
        if m:
            items.append((m.group(1).strip(), _limpiar_numero(m.group(2))))

    if not items:
        return texto

    items.sort(key=lambda x: x[1], reverse=True)
    top = items[0]
    bottom = items[-1] if len(items) > 1 else None

    partes = [
        f"**{top[0]}** lidera con **${top[1]:,.0f}** en {metrica}."
    ]
    if bottom and bottom[0] != top[0]:
        diferencia = top[1] - bottom[1]
        partes.append(
            f"La diferencia entre el primero y el último es de **${diferencia:,.0f}**, "
            f"lo que muestra una brecha importante que vale la pena explorar."
        )
    return " ".join(partes)


def _narrativa_generica(texto: str, metrica: str) -> str:
    """Fallback: limpia el texto técnico y lo presenta más legible."""
    # Quitar IDs entre corchetes
    limpio = re.sub(r'\[E:[^\]]+\]\s*\([^)]+\)\s*', '', texto)
    limpio = re.sub(r'\s+', ' ', limpio).strip()
    return limpio if limpio else texto


# Mapa de intención → constructor de narrativa
_NARRADORES = {
    'tendencia': _narrativa_tendencia,
    'ranking': _narrativa_ranking,
    'comparar_grupos': _narrativa_ranking,
}


# ---------------------------------------------------------------------------
# Constructor de gráfica
# ---------------------------------------------------------------------------

def _construir_grafica(intencion: str, metrica: str, texto: str) -> Grafica:
    """Decide qué gráfica mostrar y extrae sus datos."""

    if intencion == 'tendencia':
        puntos = _extraer_puntos_serie(texto)
        return Grafica(
            tipo='linea' if len(puntos) > 2 else 'barras',
            titulo=f'Evolución de {metrica}',
            unidad='$',
            datos=puntos,
        )

    if intencion in ('ranking', 'comparar_grupos'):
        # Extraer entidad + valor
        puntos = []
        for m in re.finditer(r'(.+?)[:\-]\s*\$?([\d,]+)', texto):
            nombre = m.group(1).strip()
            if len(nombre) < 40:  # filtrar líneas largas
                puntos.append(DatoGrafica(etiqueta=nombre, valor=_limpiar_numero(m.group(2))))
        puntos.sort(key=lambda p: p.valor, reverse=True)
        return Grafica(
            tipo='barras_horizontales',
            titulo=f'{metrica} por entidad',
            unidad='$',
            datos=puntos[:10],  # top 10
        )

    return Grafica(tipo='ninguna', titulo='', unidad='', datos=[])


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def enriquecer_respuesta(
    texto_tecnico: str,
    intencion: str,
    metrica: str,
    sugerencias: list[str],
    confianza: float = 1.0,
) -> RespuestaNarrativa:
    """
    Punto de entrada principal.

    Parameters
    ----------
    texto_tecnico:
        El campo `respuesta` o `texto` devuelto por brain.responder().
    intencion:
        La intención detectada: 'tendencia', 'ranking', 'describir_datos', etc.
    metrica:
        La métrica principal: 'ventas', 'ausentismo', etc.
    sugerencias:
        Lista de preguntas sugeridas del motor.
    confianza:
        Nivel de confianza del plan (0–1).

    Returns
    -------
    RespuestaNarrativa
        Objeto listo para serializar a JSON y enviar al frontend.

    Examples
    --------
    >>> r = enriquecer_respuesta(
    ...     texto_tecnico="[E:tendencia:abc] (ventas) Ventas en 2024-01: $105,543 ...",
    ...     intencion="tendencia",
    ...     metrica="ventas",
    ...     sugerencias=["¿Qué tiendas tienen mayor ventas?"],
    ... )
    >>> assert r.grafica.tipo == "linea"
    >>> assert "$" in r.narrativa or "ventas" in r.narrativa.lower()
    """
    narrador = _NARRADORES.get(intencion, _narrativa_generica)
    narrativa = narrador(texto_tecnico, metrica)
    grafica = _construir_grafica(intencion, metrica, texto_tecnico)

    return RespuestaNarrativa(
        narrativa=narrativa,
        grafica=grafica,
        sugerencias=sugerencias,
        intencion=intencion,
        metrica=metrica,
        confianza=confianza,
    )


# ---------------------------------------------------------------------------
# Serialización a dict (para JSON en la API)
# ---------------------------------------------------------------------------

def a_dict(r: RespuestaNarrativa) -> dict[str, Any]:
    """Convierte RespuestaNarrativa a dict serializable por FastAPI/json."""
    return {
        'narrativa': r.narrativa,
        'grafica': {
            'tipo': r.grafica.tipo,
            'titulo': r.grafica.titulo,
            'unidad': r.grafica.unidad,
            'datos': [
                {'etiqueta': d.etiqueta, 'valor': d.valor}
                for d in r.grafica.datos
            ],
        },
        'sugerencias': r.sugerencias,
        'intencion': r.intencion,
        'metrica': r.metrica,
        'confianza': r.confianza,
    }
