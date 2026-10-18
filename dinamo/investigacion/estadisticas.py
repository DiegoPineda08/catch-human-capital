"""
ESTADÍSTICAS OFICIALES POR PAÍS (API pública del Banco Mundial, sin clave).

Los valores se copian tal cual de la API y se convierten en Evidencias trazables (skill "banco_mundial"):
el LLM sólo puede citarlos con [E:id]. Ningún número se estima ni se completa: si un país no tiene
dato para un año, se dice que falta.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from dinamo.core.contracts import Evidencia, crear_evidencia
from dinamo.core.texto import texto_plano

from .buscadores import AGENTE, TIEMPO, ErrorBuscador

API = "https://api.worldbank.org/v2"

# código -> (nombre visible, unidad, palabras clave para reconocerlo en una pregunta)
INDICADORES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "SL.UEM.TOTL.ZS": ("Desempleo (% de la población activa, estimación OIT)", "porcentaje", ("desempleo", "paro", "desocupacion")),
    "SL.UEM.1524.ZS": ("Desempleo juvenil 15-24 años (%)", "porcentaje", ("desempleo juvenil", "jovenes desempleados")),
    "SL.UEM.TOTL.FE.ZS": ("Desempleo de mujeres (%)", "porcentaje", ("desempleo mujeres", "desempleo femenino")),
    "SL.TLF.CACT.ZS": ("Tasa de participación laboral, 15+ (%)", "porcentaje", ("participacion laboral", "tasa de actividad")),
    "SL.TLF.CACT.FE.ZS": ("Participación laboral de mujeres, 15+ (%)", "porcentaje", ("participacion laboral mujeres", "participacion femenina")),
    "SL.TLF.TOTL.IN": ("Población activa total (personas)", "personas", ("fuerza laboral", "poblacion activa")),
    "SL.EMP.VULN.ZS": ("Empleo vulnerable (% del empleo total)", "porcentaje", ("empleo vulnerable",)),
    "SL.ISV.IFRM.ZS": ("Empleo informal (% del empleo no agrícola)", "porcentaje", ("informalidad", "empleo informal")),
    "SL.EMP.WORK.ZS": ("Asalariados (% del empleo total)", "porcentaje", ("asalariados", "trabajadores asalariados")),
    "SL.SRV.EMPL.ZS": ("Empleo en servicios (% del empleo total)", "porcentaje", ("empleo en servicios",)),
    "SL.IND.EMPL.ZS": ("Empleo en industria (% del empleo total)", "porcentaje", ("empleo en industria", "empleo industrial")),
    "NY.GDP.PCAP.CD": ("PIB per cápita (US$ corrientes)", "US$", ("pib per capita", "ingreso per capita")),
    "NY.GDP.MKTP.KD.ZG": ("Crecimiento del PIB (% anual)", "porcentaje", ("crecimiento del pib", "crecimiento economico")),
    "FP.CPI.TOTL.ZG": ("Inflación, precios al consumidor (% anual)", "porcentaje", ("inflacion",)),
    "SP.POP.TOTL": ("Población total", "personas", ("poblacion",)),
    "SE.XPD.TOTL.GD.ZS": ("Gasto público en educación (% del PIB)", "porcentaje", ("gasto en educacion",)),
}

PAISES: dict[str, str] = {
    "MEX": "México", "COL": "Colombia", "ESP": "España", "ARG": "Argentina", "CHL": "Chile", "PER": "Perú",
    "BRA": "Brasil", "USA": "Estados Unidos", "CAN": "Canadá", "ECU": "Ecuador", "URY": "Uruguay",
    "PRY": "Paraguay", "BOL": "Bolivia", "VEN": "Venezuela", "GTM": "Guatemala", "CRI": "Costa Rica",
    "PAN": "Panamá", "DOM": "República Dominicana", "SLV": "El Salvador", "HND": "Honduras", "NIC": "Nicaragua",
    "CUB": "Cuba", "DEU": "Alemania", "FRA": "Francia", "GBR": "Reino Unido", "ITA": "Italia", "PRT": "Portugal",
    "CHN": "China", "JPN": "Japón", "IND": "India", "KOR": "Corea del Sur",
    "LCN": "América Latina y el Caribe", "OED": "Miembros OCDE", "WLD": "Mundo",
}
ALIAS = {"mexico": "MEX", "estados unidos": "USA", "eeuu": "USA", "ee uu": "USA", "usa": "USA",
         "reino unido": "GBR", "inglaterra": "GBR", "latinoamerica": "LCN", "america latina": "LCN",
         "ocde": "OED", "oecd": "OED", "mundo": "WLD", "corea": "KOR", "republica dominicana": "DOM"}

PAIS_REFERENCIA_SUGERIDO = "MEX"     # se sugiere, nunca se impone: el usuario elige el país de referencia


def paises_en(texto: str) -> list[str]:
    plano = texto_plano(texto)
    hallados: list[tuple[int, str]] = []
    nombres = {texto_plano(v).strip(): k for k, v in PAISES.items()} | {texto_plano(k).strip(): v for k, v in ALIAS.items()}
    for nombre, cod in nombres.items():
        i = plano.find(f" {nombre} ")
        if i >= 0 and cod not in [c for _, c in hallados]:
            hallados.append((i, cod))
    for cod in PAISES:                     # códigos ISO escritos en mayúsculas: "MEX vs COL"
        if f" {cod} " in f" {texto} " and cod not in [c for _, c in hallados]:
            hallados.append((texto.find(cod), cod))
    return [c for _, c in sorted(hallados)]


def indicador_en(texto: str) -> str | None:
    plano = texto_plano(texto)
    mejor, largo = None, 0
    for cod, (_, _, claves) in INDICADORES.items():
        for c in claves:
            c2 = texto_plano(c).strip()
            if f" {c2} " in plano and len(c2) > largo:
                mejor, largo = cod, len(c2)
    return mejor


@dataclass
class Serie:
    indicador: str
    nombre: str
    unidad: str
    pais: str
    pais_nombre: str
    valores: list[tuple[int, float]]          # (año, valor) sólo años con dato, orden ascendente
    url: str

    def ultimo(self) -> tuple[int, float] | None:
        return self.valores[-1] if self.valores else None


def consultar(indicador: str, paises: list[str], desde: int = 2010, hasta: int | None = None) -> list[Serie]:
    if indicador not in INDICADORES:
        raise ErrorBuscador(f"Indicador no reconocido: {indicador}")
    paises = [p for p in paises if p in PAISES]
    if not paises:
        raise ErrorBuscador("No se indicó ningún país reconocido.")
    rango = f"{desde}:{hasta}" if hasta else f"{desde}:2030"
    url = f"{API}/country/{';'.join(paises)}/indicator/{indicador}"
    try:
        r = requests.get(url, params={"format": "json", "per_page": 1000, "date": rango}, headers=AGENTE, timeout=TIEMPO)
        r.raise_for_status()
        d = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise ErrorBuscador(f"Banco Mundial: no se pudo consultar ({type(exc).__name__}).") from exc
    if not isinstance(d, list) or len(d) < 2 or not d[1]:
        mensaje = (d[0].get("message") if isinstance(d, list) and d and isinstance(d[0], dict) else None)
        raise ErrorBuscador(f"Banco Mundial: sin datos ({mensaje or 'respuesta vacía'}).")
    nombre, unidad, _ = INDICADORES[indicador]
    por_pais: dict[str, list[tuple[int, float]]] = {p: [] for p in paises}
    for fila in d[1]:
        cod = fila.get("countryiso3code") or (fila.get("country") or {}).get("id")
        if cod in por_pais and fila.get("value") is not None and str(fila.get("date", "")).isdigit():
            por_pais[cod].append((int(fila["date"]), float(fila["value"])))
    publica = f"https://data.worldbank.org/indicator/{indicador}?locations=" + "-".join(paises)
    return [Serie(indicador, nombre, unidad, p, PAISES[p], sorted(v), publica) for p, v in por_pais.items()]


def evidencias_de(series: list[Serie]) -> list[Evidencia]:
    """Último valor disponible de cada país (y el primero del rango, para ver la evolución)."""
    salida = []
    for s in series:
        if not s.valores:
            continue
        for anio, valor in ([s.valores[0], s.valores[-1]] if len(s.valores) > 1 else [s.valores[-1]]):
            salida.append(crear_evidencia(
                "banco_mundial", f"{s.nombre} — {s.pais_nombre}, {anio}", round(valor, 4), s.unidad, 1,
                "valor publicado por el Banco Mundial (World Development Indicators), sin transformar",
                {"indicador": s.indicador, "pais": s.pais, "anio": anio, "fuente": s.url}))
    return salida
