"""
Skill INDICADORES DE TALENTO: rotación, retención, ausentismo y contratación calculados con
las fórmulas estándar de Recursos Humanos (ver conocimiento/catch_capital_humano/indicadores.md):

  rotación      = bajas / plantilla (headcount)
  retención     = 1 − rotación                                (complemento de la rotación del periodo)
  ausentismo    = faltas / (plantilla × días hábiles)
  contratación  = contrataciones / plantilla
  salida (foto) = proporción de personas con la marca de salida = 1   (tablas de empleados, sin tiempo)

Es genérica: busca las columnas de CONTEO por vocabulario general de RR. HH. (bajas, plantilla,
faltas…), nunca por nombres de una base concreta, y el usuario puede indicarlas a mano.
No usa columnas que ya son tasas (tasa_, pct_, porcentaje): esas ya están calculadas.
Las razones se calculan agregando primero (suma de bajas / suma de plantilla), no promediando tasas.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from dinamo.core.contracts import PerfilDataset, ResultadoSkill, crear_evidencia
from dinamo.core.texto import texto_plano
from dinamo.data_engine import DataEngine

from .base import ParametroInvalido, Skill, _con_fuente, filtros_de

VOCABULARIO = {
    "bajas": ("bajas", "renuncias", "separaciones", "salidas", "egresos", "desvinculaciones"),
    "plantilla": ("headcount", "plantilla", "empleados", "colaboradores", "dotacion", "trabajadores"),
    "faltas": ("faltas", "ausencias", "inasistencias"),
    "dias_habiles": ("dias habiles", "dias laborables"),
    "contrataciones": ("contrataciones", "altas", "contratados", "ingresos de personal", "nuevos ingresos"),
    "salida_binaria": ("renuncio", "renuncia", "se fue", "salio", "baja", "abandono", "rotacion", "dejo la empresa"),
}
ES_TASA = (" tasa ", " pct ", " porcentaje ", " ratio ", " indice ", " proporcion ")
MIN_GRUPO = 10


def _es_tasa(nombre: str) -> bool:
    return any(t in texto_plano(nombre) for t in ES_TASA)


def detectar_columnas(perfil: PerfilDataset) -> dict[str, str]:
    encontrado: dict[str, str] = {}
    for col in perfil.columnas:
        plano = texto_plano(col.nombre + " " + col.nombre_visible)
        if _es_tasa(col.nombre):
            continue
        for clave, palabras in VOCABULARIO.items():
            if clave in encontrado:
                continue
            if clave == "salida_binaria" and col.rol != "binaria":
                continue
            if clave != "salida_binaria" and col.rol not in ("metrica", "dimension", "ignorar"):
                continue
            if any(f" {texto_plano(p).strip()}" in plano for p in palabras):
                encontrado[clave] = col.nombre
                break
    return encontrado


class IndicadoresTalento(Skill):
    nombre = "indicadores_talento"
    descripcion = "Rotación, retención, ausentismo y contratación con fórmulas estándar de RR. HH."
    intenciones = ()
    parametros = {
        "bajas": "Columna con el número de bajas (opcional: se detecta)",
        "plantilla": "Columna con la plantilla / headcount",
        "faltas": "Columna con el número de faltas",
        "dias_habiles": "Columna con los días hábiles del periodo",
        "contrataciones": "Columna con el número de contrataciones",
        "salida_binaria": "Columna 0/1 que marca si la persona dejó la empresa (tablas sin tiempo)",
        "dimension": "Opcional: columna para desglosar (p.ej. área)",
        "filtros": "Opcional: {columna: valor}",
    }

    def aplica(self, perfil: PerfilDataset) -> bool:
        c = detectar_columnas(perfil)
        return ("bajas" in c and "plantilla" in c) or "salida_binaria" in c or \
            ("faltas" in c and "plantilla" in c and "dias_habiles" in c)

    def __call__(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        cols = {**detectar_columnas(datos.perfil),
                **{k: v for k, v in parametros.items() if k in VOCABULARIO and v}}
        for k, v in cols.items():
            try:
                datos.perfil.columna(v)
            except KeyError as exc:
                raise ParametroInvalido(f"indicadores_talento: no existe la columna '{v}' ({k})") from exc
        if not (("bajas" in cols and "plantilla" in cols) or "salida_binaria" in cols
                or ("faltas" in cols and "plantilla" in cols and "dias_habiles" in cols)):
            raise ParametroInvalido("indicadores_talento: no encontré columnas de bajas y plantilla, de faltas, "
                                    "ni una marca de salida 0/1. Indícalas como parámetros.")
        return _con_fuente(self._calcular(datos, {**parametros, **cols}), datos)

    def ejecutar(self, datos: DataEngine, parametros: dict[str, Any]) -> ResultadoSkill:
        return self._calcular(datos, parametros)

    # ------------------------------------------------------------------------------------------
    def _calcular(self, datos: DataEngine, p: dict[str, Any]) -> ResultadoSkill:
        perfil = datos.perfil
        filtros = filtros_de(p)
        df = datos.filas(solo_validas=True, **filtros)
        tiempo = perfil.una("tiempo")
        dim = p.get("dimension")
        if dim:
            perfil.columna(dim)
        evid, filas, adv = [], [], []

        def razon(num: str, den: str, sub: pd.DataFrame, factor: str | None = None):
            d = sub[[num, den] + ([factor] if factor else [])].apply(pd.to_numeric, errors="coerce").dropna()
            denominador = (d[den] * d[factor]).sum() if factor else d[den].sum()
            if d.empty or denominador <= 0:
                return None, 0
            return float(d[num].sum() / denominador), int(len(d))

        def emitir(nombre: str, valor: float, n: int, metodo: str, extra: dict):
            descripcion = nombre + "".join(f" — {k} {v}" for k, v in extra.items() if k != "_orden")
            evid.append(crear_evidencia(self.nombre, descripcion, round(valor, 6), "proporcion", n, metodo,
                                        {**{k: v for k, v in extra.items() if k != "_orden"}, **filtros}))
            filas.append({"indicador": nombre, "valor": round(valor, 6), "n": n,
                          **{k: v for k, v in extra.items() if k != "_orden"}})

        grupos: list[tuple[dict, pd.DataFrame]] = []
        if tiempo is not None and ("bajas" in p or "faltas" in p):
            for periodo, sub in sorted(df.groupby(tiempo.nombre), key=lambda x: x[0]):
                grupos.append(({"periodo": _simple(periodo)}, sub))
        else:
            grupos.append(({}, df))
        if dim:
            grupos = [({**g, dim: _simple(v)}, s2) for g, sub in grupos for v, s2 in sorted(sub.groupby(dim), key=lambda x: str(x[0]))]

        for extra, sub in grupos:
            if "bajas" in p and "plantilla" in p:
                r, n = razon(p["bajas"], p["plantilla"], sub)
                if r is not None:
                    emitir("Rotación", r, n, f"suma de {p['bajas']} / suma de {p['plantilla']}", extra)
                    emitir("Retención", 1 - r, n, "1 − rotación del mismo periodo", extra)
            if "faltas" in p and "plantilla" in p and "dias_habiles" in p:
                r, n = razon(p["faltas"], p["plantilla"], sub, p["dias_habiles"])
                if r is not None:
                    emitir("Ausentismo", r, n, f"suma de {p['faltas']} / suma de ({p['plantilla']} × {p['dias_habiles']})", extra)
            if "contrataciones" in p and "plantilla" in p:
                r, n = razon(p["contrataciones"], p["plantilla"], sub)
                if r is not None:
                    emitir("Contratación", r, n, f"suma de {p['contrataciones']} / suma de {p['plantilla']}", extra)
            if "salida_binaria" in p and "bajas" not in p:
                s = pd.to_numeric(sub[p["salida_binaria"]], errors="coerce").dropna()
                if len(s):
                    emitir("Proporción de personas que dejaron la empresa (foto, no tasa por periodo)", float(s.mean()),
                           int(len(s)), f"promedio de la columna 0/1 {p['salida_binaria']}", extra)
                    if dim and len(s) < MIN_GRUPO:
                        adv.append(f"El grupo {extra.get(dim)} tiene sólo {len(s)} personas: el resultado es poco estable.")
        if "salida_binaria" in p and "bajas" not in p:
            adv.append("La tabla es una foto de personas: la proporción de salidas no equivale a una tasa de rotación "
                       "por periodo, porque no se conoce el tiempo en que ocurrieron.")
        if not evid:
            adv.append("No hubo datos válidos para calcular los indicadores.")
        return ResultadoSkill(self.nombre, tuple(evid), tuple(filas), tuple(adv))


def _simple(v):
    return v.item() if hasattr(v, "item") else v
