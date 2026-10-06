"""RAC v1: recuperación de contexto con TF-IDF (palabras + caracteres) y modo híbrido opcional.

Contrato (no cambia): buscar(pregunta, k) -> list[Contexto]

Mejoras sobre la guía, todas dentro del contrato:
  1. Dos índices TF-IDF fusionados: palabras normalizadas (1-2 gramas) y n-gramas de caracteres.
     El segundo tolera erratas y variantes ("puntualdad", "puntual" ~ "puntualidad").
  2. Conserva los dígitos sueltos: "Tier 1" y "Tier 2" ya no se confunden.
  3. Ampliación de la pregunta con sinónimos configurables (sólo en la pregunta, nunca en los documentos).
  4. Umbral de relevancia: si nada se parece lo suficiente, devuelve [] (el Brain/LLM sabe que no hay
     contexto y no inventa). Es la base para decir "no tengo información sobre eso".
  5. RetrieverHibrido: suma búsqueda semántica con embeddings de Ollama (fusión RRF). Si Ollama falla,
     cae solo al TF-IDF.
  6. Desempate fijo por posición -> mismos resultados siempre.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from dinamo.core.contracts import Contexto

from .fragmentos import Fragmento, construir_fragmentos
from .texto import GRUPOS_SINONIMOS_RRHH, Sinonimos, normalizar, texto_plano

try:  # la ruta del Excel vive en Config; en tests sin Config se ignora
    from dinamo.core.config import Config
except Exception:  # pragma: no cover
    Config = None  # type: ignore


def _legible(fuente: str) -> str:
    """'diccionario:tasa_rotacion_bimestral' -> 'diccionario tasa rotacion bimestral' (también se indexa)."""
    return " ".join(normalizar(fuente.replace(".md", ""), quitar_stop=False))


class RetrieverTfidf:
    def __init__(self, fragmentos: Sequence[Fragmento], *, sinonimos: Sinonimos | None = None,
                 peso_palabras: float = 0.6, min_score: float = 0.20, relativo: float = 0.35):
        """
        peso_palabras: 0.6 = el índice de palabras pesa 60% y el de caracteres 40%.
        min_score:     puntaje mínimo absoluto para devolver un fragmento.
        relativo:      además debe alcanzar este % del mejor puntaje (evita colas de resultados flojos).
        """
        self._fragmentos = list(fragmentos)
        self._sin = sinonimos if sinonimos is not None else Sinonimos(GRUPOS_SINONIMOS_RRHH)
        self._peso = peso_palabras
        self._min, self._rel = min_score, relativo
        self._vec_pal = self._vec_car = self._m_pal = self._m_car = None
        self._ajustar()

    # ---- construcción -------------------------------------------------------------
    @property
    def fragmentos(self) -> list[Fragmento]:
        return list(self._fragmentos)

    def _doc_pal(self, fuente: str, texto: str) -> str:
        return " ".join(normalizar(f"{_legible(fuente)} {texto}"))

    def _doc_car(self, fuente: str, texto: str) -> str:
        return texto_plano(f"{_legible(fuente)} {texto}")

    def _ajustar(self) -> None:
        if not self._fragmentos:
            return
        self._vec_pal = TfidfVectorizer(preprocessor=None, tokenizer=str.split, token_pattern=None,
                                        lowercase=False, ngram_range=(1, 2), sublinear_tf=True)
        self._vec_car = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self._m_pal = self._vec_pal.fit_transform([self._doc_pal(f, t) for f, t in self._fragmentos])
        self._m_car = self._vec_car.fit_transform([self._doc_car(f, t) for f, t in self._fragmentos])

    def agregar(self, nuevos: Sequence[Fragmento]) -> None:
        """Suma conocimiento en caliente (p. ej. un documento que el usuario sube) y reindexa."""
        existentes = set(self._fragmentos)
        self._fragmentos += [f for f in nuevos if f not in existentes]
        self._ajustar()

    # ---- búsqueda -----------------------------------------------------------------
    def _consulta_pal(self, pregunta: str) -> str:
        # Las palabras originales entran dos veces (originales + inicio de la lista ampliada) y los
        # sinónimos una: lo que el usuario escribió pesa más que lo que adivinamos.
        tokens = normalizar(pregunta)
        return " ".join(tokens + self._sin.expandir(tokens))

    def puntuar(self, pregunta: str) -> np.ndarray:
        """Puntaje combinado (0-1 aprox.) de la pregunta contra cada fragmento."""
        if not self._fragmentos or not pregunta.strip():
            return np.zeros(len(self._fragmentos))
        q_pal = self._vec_pal.transform([self._consulta_pal(pregunta)])
        q_car = self._vec_car.transform([texto_plano(pregunta)])
        s_pal = (self._m_pal @ q_pal.T).toarray().ravel()   # filas TF-IDF ya normalizadas -> coseno
        s_car = (self._m_car @ q_car.T).toarray().ravel()
        return self._peso * s_pal + (1 - self._peso) * s_car

    def _contextos(self, sims: np.ndarray, k: int) -> list[Contexto]:
        orden = sorted(range(len(sims)), key=lambda i: (-sims[i], i))[:k]   # desempate fijo
        if not orden:
            return []
        piso = max(self._min, self._rel * float(sims[orden[0]]))
        return [Contexto(self._fragmentos[i][0], self._fragmentos[i][1], round(float(sims[i]), 4))
                for i in orden if sims[i] >= piso]

    def buscar(self, pregunta: str, k: int = 3) -> list[Contexto]:
        return self._contextos(self.puntuar(pregunta), k)

    # ---- fábrica (la usa dinamo/sistema.py: no cambia su llamada) --------------------
    @classmethod
    def desde_carpeta(cls, carpeta: str | Path, ruta_excel: str | Path | None = None, *,
                      sinonimos_json: str | Path | None = None, embedder=None, **opciones):
        """Indexa docs/conocimiento/ + diccionario y LEEME del Excel. Devuelve el híbrido si hay embedder
        (explícito o por la variable de entorno OLLAMA_EMBED_MODELO)."""
        if ruta_excel is None and Config is not None:
            try:
                ruta_excel = Config().ruta_datos
            except Exception:
                ruta_excel = None
        carpeta = Path(carpeta)
        json_sin = Path(sinonimos_json) if sinonimos_json else carpeta / "sinonimos.json"
        sin = Sinonimos.desde_json(json_sin) if json_sin.exists() else None
        base = cls(construir_fragmentos(carpeta, ruta_excel), sinonimos=sin, **opciones)
        if embedder is None and os.environ.get("OLLAMA_EMBED_MODELO"):
            from dinamo.llm.ollama_http import OllamaEmbedder
            embedder = OllamaEmbedder()
        return RetrieverHibrido(base, embedder, cache_dir=carpeta / ".cache") if embedder else base


class RetrieverHibrido:
    """TF-IDF + embeddings, fusionados con Reciprocal Rank Fusion (RRF).

    Por qué: TF-IDF sólo encuentra palabras que se parecen. Con embeddings, "¿por qué la gente se
    va de la empresa?" encuentra el fragmento de 'motivos de baja' aunque no comparta palabras.
    RRF usa posiciones en vez de puntajes, así no hay que calibrar escalas distintas.
    Si el embedder falla (Ollama apagado, modelo sin descargar) todo sigue funcionando con TF-IDF.
    """

    def __init__(self, base: RetrieverTfidf, embedder, *, cache_dir: str | Path | None = None,
                 k_rrf: int = 60, min_denso: float = 0.45, candidatos: int = 20):
        self.base, self.embedder = base, embedder
        self._k_rrf, self._min_denso, self._cand = k_rrf, min_denso, candidatos
        self.degradado = False
        self._matriz = None
        try:
            self._matriz = self._cargar_o_calcular(Path(cache_dir) if cache_dir else None)
        except Exception:
            self.degradado = True

    @property
    def fragmentos(self) -> list[Fragmento]:
        return self.base.fragmentos

    def _cargar_o_calcular(self, cache: Path | None):
        textos = [f"{t}" for _, t in self.base.fragmentos]
        if not textos:
            return None
        huella = hashlib.md5(("|".join(textos) + self.embedder.modelo).encode()).hexdigest()[:12]
        archivo = cache / f"emb_{huella}.npy" if cache else None
        if archivo and archivo.exists():
            return np.load(archivo)
        m = self.embedder.documentos(textos)
        if archivo:
            archivo.parent.mkdir(parents=True, exist_ok=True)
            np.save(archivo, m)
        return m

    def buscar(self, pregunta: str, k: int = 3) -> list[Contexto]:
        if self._matriz is None:
            return self.base.buscar(pregunta, k)
        try:
            q = self.embedder.pregunta(pregunta)
        except Exception:
            self.degradado = True
            return self.base.buscar(pregunta, k)

        esparcido = self.base.puntuar(pregunta)
        denso = self._matriz @ q
        top_e = sorted(range(len(esparcido)), key=lambda i: (-esparcido[i], i))[:self._cand]
        top_d = sorted(range(len(denso)), key=lambda i: (-denso[i], i))[:self._cand]
        rrf: dict[int, float] = {}
        for lista in (top_e, top_d):
            for pos, i in enumerate(lista):
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (self._k_rrf + pos + 1)

        relevantes = {i for i in rrf if esparcido[i] >= self.base._min or denso[i] >= self._min_denso}
        orden = sorted(relevantes, key=lambda i: (-rrf[i], i))[:k]
        maximo = 2.0 / (self._k_rrf + 1)       # puntaje RRF máximo posible -> escala 0-1
        frags = self.base.fragmentos
        return [Contexto(frags[i][0], frags[i][1], round(rrf[i] / maximo, 4)) for i in orden]


# Alias: dinamo/sistema.py y los tests actuales importan `Retriever` y llaman Retriever.desde_carpeta(...)
Retriever = RetrieverTfidf
