"""
RAC — Retriever v2 (TF-IDF + sinónimos, soporte multi-fuente y hot-add).

Mantiene el mismo contrato de v0: buscar(texto, k) -> list[Contexto].
Se reemplaza el conteo simple de palabras por TF-IDF con n-gramas de caracteres para mayor
robustez ante errores de escritura, plurales y variantes morfológicas.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from dinamo.core.contracts import Contexto, PerfilDataset

from .fragmentos import cargar_archivo, construir_fragmentos
from .texto import Sinonimos, normalizar, texto_plano

DESCRIPCION_ROL = {
    "entidad": "identifica cada", "tiempo": "marca el periodo", "metrica": "es un indicador numérico",
    "dimension": "es una categoría para agrupar", "binaria": "vale 1 (sí) o 0 (no)",
    "validez": "indica si la fila es dato real (1) o imputado (0)",
}


# ------------------------------------------------------------------ helpers de indexado
def _tokens_palabra(texto: str) -> list[str]:
    return normalizar(texto)


def _tokens_char(texto: str, n: int = 3) -> list[str]:
    plano = texto_plano(texto).replace(" ", "_")
    return [plano[i:i + n] for i in range(len(plano) - n + 1)] if len(plano) >= n else []


def _tfidf(corpus: list[list[str]]) -> tuple[dict[str, float], list[dict[str, float]]]:
    """IDF global + TF normalizado por documento. Devuelve (idf, [tf_por_doc])."""
    N = len(corpus)
    df: Counter[str] = Counter()
    for doc in corpus:
        df.update(set(doc))
    idf = {t: math.log((N + 1) / (n + 1)) + 1 for t, n in df.items()}
    tfs = []
    for doc in corpus:
        c = Counter(doc)
        total = sum(c.values()) or 1
        tfs.append({t: v / total for t, v in c.items()})
    return idf, tfs


def _score(q_tokens: list[str], tf: dict[str, float], idf: dict[str, float]) -> float:
    return sum(tf.get(t, 0.0) * idf.get(t, 0.0) for t in q_tokens)


# ------------------------------------------------------------------ fragmentos de perfil (compatibilidad v0)
def fragmentos_de_carpeta(carpeta: Path) -> list[tuple[str, str, str]]:
    from dinamo.ingesta import fragmentar_markdown
    salida = []
    for ruta in sorted(carpeta.glob("*.md")) if carpeta.exists() else []:
        salida += [(f.fuente, f.texto, "conocimiento")
                   for f in fragmentar_markdown(ruta.read_text(encoding="utf-8"), ruta.name)]
    return salida


def fragmentos_del_perfil(perfil: PerfilDataset, origen: str = "") -> list[tuple[str, str, str]]:
    de_donde = f" Origen: {origen}." if origen else ""
    general = (f"Base '{perfil.nombre}': {perfil.descripcion} Cada fila es un(a) {perfil.entidad_singular} "
               f"en un periodo.{de_donde}" if perfil.tiene("tiempo")
               else f"Base '{perfil.nombre}': {perfil.descripcion}{de_donde}")
    frag = [(f"perfil#{perfil.nombre}", general, "perfil")]
    for c in perfil.columnas:
        if c.rol in ("ignorar", "texto", "nombre_entidad", "etiqueta_tiempo"):
            continue
        rol = DESCRIPCION_ROL.get(c.rol, c.rol)
        if c.rol == "entidad":
            rol += f" {perfil.entidad_singular}"
        partes = [f"Columna '{c.nombre}' ({c.nombre_visible}) de la base '{perfil.nombre}' {rol}."]
        if c.descripcion:
            partes.append(c.descripcion)
        if c.rol == "metrica":
            partes.append(f"Unidad: {c.unidad}. Se resume con la {c.agregacion}.")
            if c.mayor_es_mejor is not None:
                partes.append("Un valor más alto es mejor." if c.mayor_es_mejor else "Un valor más bajo es mejor.")
        if c.valores:
            partes.append("Valores: " + ", ".join(c.valores[:12]) + ".")
        if c.sinonimos:
            partes.append("También se le llama: " + ", ".join(c.sinonimos) + ".")
        frag.append((f"perfil#{perfil.nombre}.{c.nombre}", " ".join(partes), "perfil"))
    return frag


# ------------------------------------------------------------------ RetrieverTfidf
class RetrieverTfidf:
    """TF-IDF con n-gramas de palabras (1-2) y de caracteres (3-5), fusionados por suma."""

    MIN_SCORE = 0.01

    def __init__(self, fragmentos=(), carpeta_conocimiento: str | Path | None = None,
                 sinonimos: Sinonimos | None = None):
        self.carpeta = Path(carpeta_conocimiento) if carpeta_conocimiento else None
        self._sinonimos = sinonimos
        fijos = [f if len(f) == 3 else (f[0], f[1], "perfil" if f[0].startswith("perfil#") else "conocimiento")
                 for f in fragmentos]
        if self.carpeta:
            fijos += fragmentos_de_carpeta(self.carpeta / "general")
        self._fijos = fijos
        self._indexar(fijos)

    def _indexar(self, fragmentos: list[tuple[str, str, str]]) -> None:
        self._fragmentos = fragmentos
        textos = [t for _, t, _ in fragmentos]
        corpus_pal = [_tokens_palabra(t) for t in textos]
        corpus_chr = [_tokens_char(t) for t in textos]
        self._idf_pal, self._tf_pal = _tfidf(corpus_pal)
        self._idf_chr, self._tf_chr = _tfidf(corpus_chr)

    def sincronizar(self, biblioteca) -> None:
        """Vuelve a indexar cuando cambian las fuentes cargadas."""
        dinamicos = []
        for nombre, motor in biblioteca.motores.items():
            if self.carpeta:
                dinamicos += fragmentos_de_carpeta(self.carpeta / nombre)
            dinamicos += fragmentos_del_perfil(motor.perfil, getattr(motor, "origen", ""))
        dinamicos += [(f.fuente, f.texto, "documento") for f in biblioteca.fragmentos]
        self._indexar(self._fijos + dinamicos)

    def __len__(self) -> int:
        return len(self._fragmentos)

    def agregar_archivo(self, ruta: str | Path) -> None:
        """Indexa un documento en caliente sin reiniciar."""
        nuevos = [(f, t, "documento") for f, t in cargar_archivo(ruta)]
        self._indexar(self._fragmentos + nuevos)

    def documentos(self) -> list[str]:
        vistos = []
        for f, _, tipo in self._fragmentos:
            nombre = f.split("#")[0]
            if tipo == "documento" and nombre not in vistos:
                vistos.append(nombre)
        return vistos

    def documentos_mencionados(self, pregunta: str) -> list[str]:
        """Nombres de documentos que la pregunta menciona."""
        t = texto_plano(pregunta)
        docs = self.documentos()
        encontrados = []
        for doc in docs:
            claves = [p for p in _tokens_palabra(Path(doc).stem.replace("_", " ")) if len(p) > 3]
            if claves and sum(1 for p in claves if p in t) >= max(1, len(claves) // 2):
                encontrados.append(doc)
        return encontrados

    def fragmentos_de(self, documento: str) -> list[Contexto]:
        return [Contexto(f, t, 1.0, tipo) for f, t, tipo in self._fragmentos
                if tipo == "documento" and (f == documento or f.startswith(documento + "#"))]

    def contexto_de_documento(self, nombre: str, k: int = 5) -> list[Contexto]:
        """Primeros k fragmentos de un documento en orden de página (para resúmenes)."""
        return self.fragmentos_de(nombre)[:k]

    def buscar(self, texto: str, k: int = 3,
               tipos: tuple[str, ...] | None = None,
               documento: str | None = None,
               fuentes: list[str] | None = None) -> list[Contexto]:
        """Los k fragmentos más relevantes.

        Args:
            fuentes: lista de nombres de documentos para filtrar (None = todos).
        """
        q_pal = _tokens_palabra(texto)
        if self._sinonimos:
            q_pal = self._sinonimos.expandir(q_pal)
        q_chr = _tokens_char(texto)
        if not q_pal and not q_chr:
            return []

        puntajes = []
        for i, (fuente, _, tipo) in enumerate(self._fragmentos):
            if tipos and tipo not in tipos:
                continue
            if documento and not (fuente == documento or fuente.startswith(documento + "#")):
                continue
            if fuentes:
                nombre_doc = fuente.split("#")[0]
                if nombre_doc not in fuentes:
                    continue
            s_pal = _score(q_pal, self._tf_pal[i], self._idf_pal)
            s_chr = _score(q_chr, self._tf_chr[i], self._idf_chr)
            score = s_pal + 0.3 * s_chr
            if score >= self.MIN_SCORE:
                puntajes.append((score, i))

        puntajes.sort(key=lambda x: (-x[0], x[1]))
        return [Contexto(self._fragmentos[i][0], self._fragmentos[i][1],
                         round(p, 4), self._fragmentos[i][2])
                for p, i in puntajes[:k]]


# ------------------------------------------------------------------ alias de compatibilidad
Retriever = RetrieverTfidf


# ------------------------------------------------------------------ fábrica
def desde_carpeta(
    carpeta: str | Path,
    ruta_excel: str | Path | None = None,
    sinonimos_json: str | Path | None = None,
) -> RetrieverTfidf:
    """Construye un RetrieverTfidf desde una carpeta de conocimiento y un Excel opcional."""
    sinonimos = Sinonimos.desde_json(sinonimos_json) if sinonimos_json else None
    frags = construir_fragmentos(carpeta, ruta_excel)
    # Los fragmentos de construir_fragmentos son (fuente, texto); los marcamos como "conocimiento"
    fijos = [(f, t, "conocimiento") for f, t in frags]
    retriever = RetrieverTfidf(sinonimos=sinonimos)
    retriever._fijos = fijos
    retriever._indexar(fijos)
    return retriever


# ------------------------------------------------------------------ compatibilidad v0: documento_mencionado
def documento_mencionado(texto: str, documentos: list[str]) -> str | None:
    """¿La pregunta nombra un documento? Compatibilidad con brain.py v0."""
    t = texto_plano(texto)
    mejor, mejor_n = None, 0
    for doc in documentos:
        claves = [p for p in _tokens_palabra(Path(doc).stem.replace("_", " ")) if len(p) > 3]
        n = sum(1 for p in claves if p in t)
        if claves and n >= max(1, len(claves) // 2) and n > mejor_n:
            mejor, mejor_n = doc, n
    return mejor
