"""
Utilidades de texto compartidas (Brain, RAC y Perfilador las usan igual).

Normalizar = minúsculas, sin acentos ni signos. Así "¿Cómo va la ROTACIÓN?" y
"como va la rotacion" se tratan como la misma frase.
"""
from __future__ import annotations

import re
import unicodedata

PALABRAS_VACIAS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o", "en", "que",
    "por", "para", "con", "se", "es", "son", "su", "sus", "al", "lo", "como", "cual", "cuales",
    "mas", "menos", "a", "me", "mi", "nos", "le", "les", "este", "esta", "estos", "estas", "hay",
    "entre", "sobre", "the", "of", "and", "id", "pct", "bin", "total", "num", "nro", "tasa", "dato",
    # verbos frecuentes en nombres de columnas sí/no ("tiene_promocion", "otorga_transporte"):
    # si fueran sinónimos, "¿qué datos tienes?" apuntaría a la columna "tiene_promocion".
    "tiene", "tienen", "otorga", "otorgan", "reporta", "reportan", "usa", "usan", "cuenta", "cuentan",
}

# Palabras que aparecen en muchos nombres de columnas y no sirven para distinguir una de otra.
PALABRAS_GENERICAS = {
    "promedio", "mensual", "bimestral", "anual", "semanal", "porcentaje", "tasa", "total", "numero",
    "cantidad", "valor", "nivel", "indice", "ratio", "monto", "personal", "operativo", "dias",
}


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c))


def texto_plano(texto: str) -> str:
    """'¿Cómo va la ROTACIÓN?' -> ' como va la rotacion ' (con espacios en los bordes)."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", sin_acentos(str(texto).lower()))) + " "


def palabras(texto: str) -> list[str]:
    """Palabras significativas (sin palabras vacías y de al menos 3 letras)."""
    return [p for p in texto_plano(texto).split() if p not in PALABRAS_VACIAS and len(p) > 2]


def posicion(clave: str, plano: str) -> int:
    """Posición donde una palabra EMPIEZA con `clave` (-1 si no aparece).

    Evita falsos positivos: 'bajo' no coincide con 'trabajo'."""
    clave = texto_plano(clave).strip()
    if not clave:
        return -1
    m = re.search(r"(?<![a-z0-9])" + re.escape(clave), plano)
    return m.start() if m else -1


def humanizar(nombre_columna: str) -> str:
    """'tasa_rotacion_bimestral' -> 'tasa rotacion bimestral'."""
    t = re.sub(r"_+", " ", str(nombre_columna)).strip()
    return re.sub(r"\s+", " ", t)


def raiz(palabra: str) -> str:
    """Raíz sencilla para que 'renuncia', 'renuncio' y 'renuncias' coincidan ('renunci').

    Quita una 's'/'es' final y luego una vocal final. Sólo se usa si la raíz queda de 5+ letras,
    para no generar coincidencias demasiado cortas."""
    p = texto_plano(palabra).strip()
    if " " in p or len(p) < 6:
        return p
    r = p[:-2] if p.endswith("es") else p[:-1] if p.endswith("s") else p
    r = r[:-1] if r[-1:] in "aeiou" else r
    return r if len(r) >= 5 else p
