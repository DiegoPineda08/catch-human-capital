"""
RAC (Recuperación Aumentada de Contexto) — versión 0.

Antes de que el LLM escriba, el RAC le busca los párrafos más relevantes para la pregunta.
El LLM sólo sabe lo que le damos: sin RAC, inventaría definiciones.

Indexa cuatro fuentes (cada fragmento lleva su `tipo`):
  1. conocimiento/general/*.md              (tipo "conocimiento") reglas para CUALQUIER base
  2. conocimiento/<nombre de la tabla>/*.md  (tipo "conocimiento") escrito a mano para UNA base
  3. el PerfilDataset de cada tabla          (tipo "perfil") un fragmento automático por columna
  4. los textos de los documentos cargados   (tipo "documento") párrafos de PDFs, .md y .txt
Las fuentes 3 y 4 hacen que un archivo nuevo tenga contexto desde el primer minuto.

v0 (este archivo): cuenta palabras en común. v1 (TODO Diego Castro): TF-IDF.
El CONTRATO no cambia: buscar(texto, k) -> list[Contexto].
"""
from __future__ import annotations

from pathlib import Path

from dinamo.core.contracts import Contexto, PerfilDataset
from dinamo.core.texto import palabras, texto_plano
from dinamo.ingesta import fragmentar_markdown

DESCRIPCION_ROL = {
    "entidad": "identifica cada", "tiempo": "marca el periodo", "metrica": "es un indicador numérico",
    "dimension": "es una categoría para agrupar", "binaria": "vale 1 (sí) o 0 (no)",
    "validez": "indica si la fila es dato real (1) o imputado (0)",
}


def fragmentos_de_carpeta(carpeta: Path) -> list[tuple[str, str, str]]:
    salida = []
    for ruta in sorted(carpeta.glob("*.md")) if carpeta.exists() else []:
        salida += [(f.fuente, f.texto, "conocimiento")
                   for f in fragmentar_markdown(ruta.read_text(encoding="utf-8"), ruta.name)]
    return salida


def fragmentos_del_perfil(perfil: PerfilDataset, origen: str = "") -> list[tuple[str, str, str]]:
    """Un fragmento por columna útil + uno general de la tabla."""
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


class Retriever:
    def __init__(self, fragmentos=(), carpeta_conocimiento: str | Path | None = None):
        """`fragmentos`: lista de (fuente, texto) o (fuente, texto, tipo) que siempre estarán."""
        self.carpeta = Path(carpeta_conocimiento) if carpeta_conocimiento else None
        fijos = [f if len(f) == 3 else (f[0], f[1], "perfil" if f[0].startswith("perfil#") else "conocimiento")
                 for f in fragmentos]
        if self.carpeta:
            fijos += fragmentos_de_carpeta(self.carpeta / "general")
        self._fijos = fijos
        self._indexar(fijos)

    def _indexar(self, fragmentos: list[tuple[str, str, str]]) -> None:
        self._fragmentos = fragmentos
        self._tokens = [set(palabras(t)) for _, t, _ in fragmentos]

    def sincronizar(self, biblioteca) -> None:
        """Vuelve a indexar cuando cambian las fuentes cargadas (se llama al agregar un archivo)."""
        dinamicos = []
        for nombre, motor in biblioteca.motores.items():
            if self.carpeta:
                dinamicos += fragmentos_de_carpeta(self.carpeta / nombre)
            dinamicos += fragmentos_del_perfil(motor.perfil, getattr(motor, "origen", ""))
        dinamicos += [(f.fuente, f.texto, "documento") for f in biblioteca.fragmentos]
        self._indexar(self._fijos + dinamicos)

    def __len__(self) -> int:
        return len(self._fragmentos)

    def fragmentos_de(self, documento: str) -> list[Contexto]:
        """Todos los fragmentos de un documento, en orden (sirve para resumirlo completo)."""
        return [Contexto(f, t, 1.0, tipo) for f, t, tipo in self._fragmentos
                if tipo == "documento" and (f == documento or f.startswith(documento + "#"))]

    def buscar(self, texto: str, k: int = 3, tipos: tuple[str, ...] | None = None,
               documento: str | None = None) -> list[Contexto]:
        """Los k fragmentos con más palabras en común con `texto` (opcional: sólo ciertos tipos o un documento)."""
        q = set(palabras(texto))
        if not q:
            return []
        puntajes = []
        for i, toks in enumerate(self._tokens):
            fuente, _, tipo = self._fragmentos[i]
            if tipos and tipo not in tipos:
                continue
            if documento and not (fuente == documento or fuente.startswith(documento + "#")):
                continue
            comunes = len(q & toks)
            if comunes:
                puntajes.append((comunes / len(q), i))
        puntajes.sort(key=lambda x: (-x[0], x[1]))        # determinístico ante empates
        return [Contexto(self._fragmentos[i][0], self._fragmentos[i][1], round(p, 4), self._fragmentos[i][2])
                for p, i in puntajes[:k]]

    def documentos(self) -> list[str]:
        """Nombres de los documentos con texto indexado (p.ej. 'informe_clima_laboral.pdf')."""
        vistos = []
        for f, _, tipo in self._fragmentos:
            nombre = f.split("#")[0]
            if tipo == "documento" and nombre not in vistos:
                vistos.append(nombre)
        return vistos


def documento_mencionado(texto: str, documentos: list[str]) -> str | None:
    """¿La pregunta nombra un documento? ('el informe de clima laboral' -> 'informe_clima_laboral.pdf')."""
    t = texto_plano(texto)
    mejor, mejor_n = None, 0
    for doc in documentos:
        claves = [p for p in palabras(Path(doc).stem.replace("_", " ")) if len(p) > 3]
        n = sum(1 for p in claves if f" {p}" in t)
        if claves and n >= max(1, len(claves) // 2) and n > mejor_n:
            mejor, mejor_n = doc, n
    return mejor
