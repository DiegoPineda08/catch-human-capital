"""Normalización de texto en español, compartida por el RAC y por los validadores del LLM.

Es la pieza que hace al sistema tolerante a cómo escribe la gente: acentos, mayúsculas,
plurales, guiones bajos de los nombres de variable ("tasa_rotacion_bimestral") y sinónimos.
No depende de ningún tema: sirve igual para Capital Humano que para ventas o logística.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# Palabras gramaticales sin carga temática. No se incluye "no" ni los números:
# "no aplica" y "Tier 1" necesitan conservarlos.
STOPWORDS_ES = frozenset("""
a al algo ante aqui con contra cual cuales cuando cuanto cuantos cuantas como de del desde donde
durante e el ella ellas ellos en entre era eran es esa ese eso esta estan este esto estos fue ha han
hay la las le les lo los mas me mi mis muy ni nos o otra otro para pero por porque que quien quienes
se ser si sin sobre son su sus te tu tus un una uno unas unos y ya hacer hace
""".split())

_RE_TOKEN = re.compile(r"[a-z0-9]+")


def quitar_acentos(texto: str) -> str:
    """'Rotación' -> 'Rotacion'. También 'ñ' -> 'n', igual en preguntas y en documentos."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def raiz(tok: str) -> str:
    """Stemmer mínimo y conservador (plurales y terminaciones comunes).

    Es deliberadamente simple: los n-gramas de caracteres del retriever cubren el resto
    (p. ej. 'puntual' vs 'puntualidad')."""
    if len(tok) <= 4 or tok.isdigit():
        return tok
    for sufijo, reemplazo in (("ciones", "cion"), ("dades", "dad"), ("ores", "or")):
        if tok.endswith(sufijo):
            return tok[: -len(sufijo)] + reemplazo
    if tok.endswith("ones") and len(tok) > 5:
        return tok[:-4] + "on"
    if tok.endswith("mente") and len(tok) > 7:
        return tok[:-5]
    if tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenizar(texto: str) -> list[str]:
    """Minúsculas, sin acentos, sólo letras y dígitos. Los '_' separan palabras."""
    return _RE_TOKEN.findall(quitar_acentos(texto).lower())


def normalizar(texto: str, *, quitar_stop: bool = True, usar_raiz: bool = True) -> list[str]:
    """Lista de tokens normalizados. Es la función `normalizar` que usa el RAC."""
    salida = []
    for tok in tokenizar(texto):
        if quitar_stop and tok in STOPWORDS_ES:
            continue
        salida.append(raiz(tok) if usar_raiz else tok)
    return salida


def texto_plano(texto: str) -> str:
    """Texto sin acentos ni stopwords y sin raíz, para los n-gramas de caracteres."""
    return " ".join(normalizar(texto, usar_raiz=False))


# ---------------------------------------------------------------- sinónimos
# Grupos de términos equivalentes. Sólo se usan para AMPLIAR LA PREGUNTA, nunca los documentos.
# Son un punto de partida para Capital Humano: se pueden reemplazar o ampliar con un JSON
# (docs/conocimiento/sinonimos.json) sin tocar código, y así el RAC se adapta a otro dominio.
GRUPOS_SINONIMOS_RRHH: list[list[str]] = [
    ["rotación", "bajas", "renuncias", "salidas", "attrition", "turnover"],
    ["ausentismo", "faltas", "inasistencias", "ausencias"],
    ["incapacidad", "incapacidades", "licencia médica", "enfermedad"],
    ["contratación", "reclutamiento", "ingresos", "altas", "vacantes"],
    ["salario", "sueldo", "remuneración", "paga"],
    ["bono", "incentivo", "premio"],
    ["prestaciones", "beneficios", "compensaciones"],
    ["sindicato", "sindical", "gremio"],
    ["contrato colectivo", "cct", "revisión contractual"],
    ["capacitación", "entrenamiento", "formación"],
    ["transporte", "camión", "ruta de personal"],
    ["jornada", "turno", "horario"],
    ["antigüedad", "permanencia", "tiempo en la empresa"],
    ["seguro de gastos médicos", "sgmm", "gastos médicos mayores"],
    ["vales de despensa", "despensa", "vales"],
    ["participación de utilidades", "ptu", "reparto de utilidades"],
]


class Sinonimos:
    """Expande una lista de tokens con los de sus términos equivalentes."""

    def __init__(self, grupos: list[list[str]] | None = None):
        self._grupos: list[list[tuple[str, ...]]] = []
        for grupo in grupos or []:
            entradas = [tuple(normalizar(t)) for t in grupo]
            entradas = [e for e in entradas if e]
            if len(entradas) > 1:
                self._grupos.append(entradas)

    @classmethod
    def desde_json(cls, ruta: str | Path) -> "Sinonimos":
        """JSON: lista de listas, p. ej. [["rotación","bajas"],["salario","sueldo"]]."""
        return cls(json.loads(Path(ruta).read_text(encoding="utf-8")))

    def expandir(self, tokens: list[str]) -> list[str]:
        presentes = set(tokens)
        extra: list[str] = []
        for grupo in self._grupos:
            if any(set(e) <= presentes for e in grupo):  # algún término del grupo está en la pregunta
                for entrada in grupo:
                    for tok in entrada:
                        if tok not in presentes and tok not in extra:
                            extra.append(tok)
        return tokens + extra
