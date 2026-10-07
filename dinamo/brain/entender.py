"""
INTÉRPRETE: convierte una pregunta en un Plan, usando el vocabulario de la base cargada.

No tiene NINGUNA palabra de una base concreta. El vocabulario se arma al cargar la base:
  - métricas y dimensiones: nombre, etiqueta y sinónimos de cada columna del perfil;
  - valores de las dimensiones: "Norte", "Tier 1", "Grande"...;
  - entidades: "COMPAÑIA 12", "Tienda Centro", o "<entidad> <número>";
  - periodos: "Julio - Agosto 2025", "2024-03", "último periodo".
Con otra base, el mismo código entiende otras palabras.

Las palabras de INTENCIÓN ("evolución", "ranking", "compara"...) sí son fijas: son español
común, no dependen de la base.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from dinamo.core.contracts import PerfilDataset, Plan
from dinamo.core.texto import posicion, raiz, texto_plano

# Orden = prioridad (la primera intención que coincide gana).
REGLAS_INTENCION: list[tuple[str, tuple[str, ...]]] = [
    ("consultar_documentos", ("que dice", "que dicen", "segun el documento", "segun el informe", "en el documento",
                              "en el informe", "en el pdf", "resume el", "resumen del", "que menciona",
                              "que recomienda", "recomendaciones", "conclusiones", "metodologia",
                              "limitaciones", "hallazgos")),
    ("describir_datos", ("que datos", "que informacion", "que puedo preguntar", "que tienes", "que hay en",
                         "describe", "resumen de la base", "de que trata", "que variables", "que columnas",
                         "que indicadores", "ayuda")),
    ("perfil_entidad", ("cuentame de", "cuentame sobre", "hablame de", "hablame sobre", "perfil de",
                        "ficha de", "como esta la", "como esta el", "como le va")),
    ("relaciones", ("factor", "relacion", "relaciona", "asocia", "influye", "influyen", "por que",
                    "depende", "explica", "correlacion", "impacta")),
    ("comparar_grupos", ("compar", "versus", "vs", "frente a", "diferencia entre", "segun")),
    ("ranking", ("ranking", "top", "mayor", "mayores", "menor", "menores", "menos", "mas alto", "mas alta",
                 "mas bajo", "mas baja", "mejor", "mejores", "peor", "peores", "lider", "lideres")),
    ("tendencia", ("evolu", "tendencia", "en el tiempo", "a lo largo", "historic", "cambio", "cambiado",
                   "subio", "bajo", "aumento", "aumentado", "disminu", "como va", "como ha",
                   "comportamiento", "mes a mes", "por periodo", "crecio", "crecimiento")),
]
PALABRAS_ASCENDENTE = ("menor", "menores", "menos", "mas bajo", "mas baja", "minimo", "minima")
PALABRAS_ULTIMO = ("ultimo periodo", "ultimo bimestre", "ultimo mes", "ultimo trimestre", "ultimo ano",
                   "periodo mas reciente", "ultima medicion")


def contiene_frase(frase: str, plano: str) -> int:
    """Posición de la frase completa (con bordes de palabra a ambos lados) o -1."""
    frase = texto_plano(frase).strip()
    if not frase:
        return -1
    m = re.search(r"(?<![a-z0-9])" + re.escape(frase) + r"(?![a-z0-9])", plano)
    return m.start() if m else -1


@dataclass(frozen=True)
class Termino:
    columna: str
    frase: str            # ya normalizada
    peso: int             # número de palabras: una frase más larga es más específica


class Interprete:
    def __init__(self, perfil: PerfilDataset, periodos: list[tuple[Any, str]] | None = None,
                 entidades: list[tuple[Any, str]] | None = None):
        self.perfil = perfil
        self.periodos = periodos or []
        self.entidades = entidades or []
        self._metricas = self._terminos(("metrica", "binaria"))
        self._dimensiones = self._terminos(("dimension", "binaria"))
        self._valores = [(c.nombre, v, texto_plano(v).strip()) for c in perfil.columnas
                         if c.rol in ("dimension",) for v in c.valores if texto_plano(v).strip()]
        self._nombres_entidad = sorted(((texto_plano(nom).strip(), ent) for ent, nom in self.entidades
                                        if texto_plano(nom).strip()), key=lambda x: -len(x[0]))

    def _terminos(self, roles: tuple[str, ...]) -> list[Termino]:
        terms = []
        for c in self.perfil.columnas:
            if c.rol not in roles:
                continue
            frases = {c.nombre_visible, c.nombre.replace("_", " "), *c.sinonimos}
            frases |= {raiz(f) for f in frases}          # "renuncio" también reconoce "renuncia"
            for frase in frases:
                plano = texto_plano(frase).strip()
                if plano:
                    terms.append(Termino(c.nombre, plano, len(plano.split())))
        return terms

    # ------------------------------------------------------------------ piezas
    def detectar_metricas(self, t: str, excluir: set[str] = frozenset()) -> list[str]:
        mejores: dict[str, tuple[int, int]] = {}
        for term in self._metricas:
            if term.columna in excluir:
                continue
            pos = posicion(term.frase, t)
            if pos >= 0 and (term.peso, -pos) > mejores.get(term.columna, (0, 0)):
                mejores[term.columna] = (term.peso, -pos)
        return [c for c, _ in sorted(mejores.items(), key=lambda x: (-x[1][0], -x[1][1], x[0]))]

    def detectar_dimension_agrupar(self, t: str) -> str | None:
        """'ventas por región' / 'según formato' / 'con sindicato' -> columna para agrupar."""
        for term in sorted(self._dimensiones, key=lambda x: -x.peso):
            # "que areas tienen mayor salario" también agrupa por área ("que"/"cuales" + dimensión)
            for prefijo in ("por ", "segun ", "entre ", "con ", "sin ", "tienen ", "tiene ", "que ", "cuales ",
                            "cual "):
                if posicion(prefijo + term.frase, t) >= 0:
                    return term.columna
        return None

    def detectar_valores(self, t: str) -> dict[str, list[str]]:
        encontrados: dict[str, list[str]] = {}
        for col, valor, plano in self._valores:
            if contiene_frase(plano, t) >= 0:
                encontrados.setdefault(col, []).append(valor)
        return encontrados

    def detectar_entidad(self, t: str) -> Any | None:
        for nombre, ent in self._nombres_entidad:
            if contiene_frase(nombre, t) >= 0:
                return ent
        m = re.search(r"(?<![a-z0-9])" + re.escape(texto_plano(self.perfil.entidad_singular).strip())
                      + r"\s+(?:numero\s+|no\s+)?(\d+)(?![0-9])", t)
        if m:
            ids = {str(e): e for e, _ in self.entidades}
            return ids.get(m.group(1), int(m.group(1)))
        return None

    def detectar_periodo(self, t: str) -> Any | None:
        if not self.periodos:
            return None
        if any(posicion(p, t) >= 0 for p in PALABRAS_ULTIMO):
            return self.periodos[-1][0]
        for valor, etiqueta in sorted(self.periodos, key=lambda x: -len(x[1])):
            if contiene_frase(etiqueta, t) >= 0 or contiene_frase(str(valor), t) >= 0 and len(str(valor)) >= 4:
                return valor
        return None

    # ------------------------------------------------------------------ ¿esta tabla sirve?
    def relevancia(self, texto: str) -> float:
        """Qué tanto habla la pregunta de ESTA tabla (0 = nada). El Brain la usa para elegir la fuente.

        Suma puntos por: nombrar una métrica (más si la frase es larga), un valor de categoría
        ("Norte"), una entidad ("Tienda Centro"), una forma de agrupar ("por región") o el nombre
        de las entidades en plural ("tiendas")."""
        t = texto_plano(texto)
        puntos = 0.0
        pesos = [term.peso for term in self._metricas if posicion(term.frase, t) >= 0]
        if pesos:
            puntos += 2 + max(pesos)
        puntos += len(self.detectar_valores(t))
        if any(contiene_frase(nombre, t) >= 0 for nombre, _ in self._nombres_entidad):
            puntos += 2
        if self.detectar_dimension_agrupar(t):
            puntos += 1
        plural = texto_plano(self.perfil.entidad_plural).strip()
        if plural and contiene_frase(plural, t) >= 0:
            puntos += 1.5
        return puntos

    # ------------------------------------------------------------------ todo junto
    def interpretar(self, texto: str, plan_anterior: Plan | None = None) -> Plan:
        t = texto_plano(texto)
        intencion = next((nombre for nombre, claves in REGLAS_INTENCION
                          if any(posicion(c, t) >= 0 for c in claves)), None)
        # "¿Qué tiendas ...?" / "¿Cuáles empresas ...?" pide un ranking de entidades (sea cual sea la base)
        plural = texto_plano(self.perfil.entidad_plural).strip()
        if intencion is None and plural and any(contiene_frase(f"{q} {plural}", t) >= 0 for q in ("que", "cuales")):
            intencion = "ranking"
        confianza = 0.4 if intencion else 0.0

        # 1) Entidad primero, y se borra su nombre del texto: así "Tienda Centro" no se confunde
        #    con la región "Centro".
        entidad = self.detectar_entidad(t)
        t_sin_entidad = t
        for nombre, ent in self._nombres_entidad:
            if ent == entidad:
                t_sin_entidad = t_sin_entidad.replace(f" {nombre} ", " ")

        # 2) Agrupación y valores de categorías ("por región", "Tier 1 vs Tier 2", "región Norte")
        dimension = self.detectar_dimension_agrupar(t_sin_entidad)
        valores = self.detectar_valores(t_sin_entidad)
        filtros: dict[str, Any] = {}
        for col, vals in valores.items():
            if len(vals) >= 2:                       # "Tier 1 vs Tier 2" -> comparar por esa columna
                dimension = dimension or col
            else:
                filtros[col] = vals[0]
        if dimension and intencion in (None, "tendencia", "ranking") and not valores.get(dimension):
            intencion, confianza = "comparar_grupos", max(confianza, 0.4)

        ent_col = self.perfil.una("entidad")
        if entidad is not None and ent_col is not None:
            filtros[ent_col.nombre] = entidad
        periodo = self.detectar_periodo(t_sin_entidad)
        tiempo = self.perfil.una("tiempo")

        metricas = self.detectar_metricas(t_sin_entidad, excluir={dimension} if dimension else set())
        if metricas:
            confianza += 0.4
        if filtros or dimension or periodo is not None:
            confianza += 0.2

        # 3) Pregunta de seguimiento ("¿y sólo en la región Norte?"): sin intención propia pero con
        #    algo nuevo (filtro, periodo, métrica o agrupación) -> se completa con el turno anterior.
        aporta = bool(filtros or metricas or dimension or periodo is not None)
        if plan_anterior is not None and intencion is None and aporta:
            intencion = plan_anterior.intencion
            filtros = {**plan_anterior.filtros, **filtros}
            dimension = dimension or plan_anterior.dimension
            metricas = metricas or list(plan_anterior.metricas)
        elif plan_anterior is not None and intencion is not None and not metricas:
            metricas = list(plan_anterior.metricas)     # "¿y qué empresas lo tienen más alto?"

        if intencion is None:
            if entidad is not None:
                intencion = "perfil_entidad"            # "ventas de la Tienda Centro"
            elif metricas and periodo is not None:
                intencion = "ranking"                   # "rotación en Julio - Agosto 2025"
            elif metricas:
                intencion = "tendencia" if tiempo is not None else "ranking"
            else:
                intencion = "desconocida"               # "Hola": no hay nada que analizar
        if periodo is not None and tiempo is not None and intencion != "tendencia":
            filtros[tiempo.nombre] = periodo
        supuestos: tuple[str, ...] = ()
        if not metricas and intencion in ("tendencia", "ranking", "comparar_grupos", "relaciones", "perfil_entidad"):
            primera = self.perfil.una("metrica")
            if primera is not None:          # se supone la primera métrica; el Brain puede preguntar cuál
                metricas, confianza, supuestos = [primera.nombre], confianza * 0.5, ("metrica",)

        orden = "asc" if any(posicion(p, t) >= 0 for p in PALABRAS_ASCENDENTE) else "desc"
        if metricas and any(posicion(p, t) >= 0 for p in ("mejor", "mejores", "peor", "peores")):
            col = self.perfil.columna(metricas[0])
            pide_mejor = any(posicion(p, t) >= 0 for p in ("mejor", "mejores"))
            if col.mayor_es_mejor is not None:
                orden = "desc" if pide_mejor == col.mayor_es_mejor else "asc"

        return Plan(intencion=intencion, metricas=tuple(metricas), dimension=dimension, filtros=filtros,
                    confianza=round(min(confianza, 1.0), 2), orden=orden, supuestos=supuestos)
