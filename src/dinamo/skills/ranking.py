"""Skill genérica para construir rankings por entidad.

La Skill:
- recibe un DataEngine;
- recibe una métrica;
- recibe la columna que identifica la entidad;
- puede recibir una columna de tiempo;
- agrega las observaciones a nivel de entidad;
- aplica un mínimo de observaciones válidas por entidad;
- ordena de forma determinista;
- devuelve los primeros N resultados;
- genera Evidence estructurada;
- devuelve datos estructurados para visualización.

La implementación no contiene nombres de columnas específicos de Catch.

No define ni modifica los contratos compartidos de dinamo.core.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

import pandas as pd

from dinamo.data_engine.engine import DataEngine
from dinamo.evidence.store import EvidenceStore


class RankingSkill:
    """Construye un ranking de entidades a partir de una métrica."""

    nombre = "ranking"
    intenciones = ("ranking",)
    requeridos = ("metrica", "entidad")

    def __init__(
        self,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        """Inicializa la Skill.

        Parameters
        ----------
        evidence_store:
            Almacenamiento opcional para registrar Evidence.
        """
        self._evidence_store = evidence_store

    def ejecutar(
        self,
        datos: DataEngine,
        parametros: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Ejecuta el ranking.

        Parámetros esperados
        --------------------
        metrica:
            Nombre de la columna numérica que se desea rankear.

        entidad:
            Nombre de la columna que identifica la entidad.

        tiempo:
            Nombre opcional de la columna temporal.

        periodo:
            Valor opcional de la columna temporal que se desea filtrar.

        n:
            Número máximo de entidades a devolver. Por defecto 5.

        ascendente:
            False ordena de mayor a menor.
            True ordena de menor a mayor.

        min_periodos:
            Mínimo de observaciones válidas que debe tener una entidad.
            Por defecto 3.
        """
        self._validar_entrada(datos, parametros)

        dataframe = datos.dataframe()

        metrica = str(parametros["metrica"])
        entidad = str(parametros["entidad"])

        tiempo = parametros.get("tiempo")
        periodo = parametros.get("periodo")

        n = self._obtener_entero_positivo(
            parametros,
            "n",
            defecto=5,
        )

        min_periodos = self._obtener_entero_positivo(
            parametros,
            "min_periodos",
            defecto=3,
        )

        ascendente = self._obtener_booleano(
            parametros,
            "ascendente",
            defecto=False,
        )

        self._validar_columnas(
            dataframe=dataframe,
            metrica=metrica,
            entidad=entidad,
            tiempo=tiempo,
        )

        df = dataframe.copy(deep=True)

        advertencias: list[str] = []

        # Convertimos la métrica a numérica sin modificar el DataEngine.
        df[metrica] = pd.to_numeric(
            df[metrica],
            errors="coerce",
        )

        invalidos = int(df[metrica].isna().sum())

        if invalidos > 0:
            advertencias.append(
                f"Se excluyeron {invalidos} observaciones "
                "con métrica faltante o no numérica."
            )

        # También eliminamos valores infinitos.
        mascara_finitos = df[metrica].map(
            lambda valor: (
                False
                if pd.isna(valor)
                else isfinite(float(valor))
            )
        )

        infinitos = int(
            (df[metrica].notna() & ~mascara_finitos).sum()
        )

        if infinitos > 0:
            advertencias.append(
                f"Se excluyeron {infinitos} observaciones "
                "con valores infinitos."
            )

        df = df[mascara_finitos].copy()

        # Las entidades faltantes no permiten construir un ranking.
        entidades_faltantes = int(
            df[entidad].isna().sum()
        )

        if entidades_faltantes > 0:
            advertencias.append(
                f"Se excluyeron {entidades_faltantes} "
                "observaciones sin entidad identificable."
            )

        df = df.dropna(subset=[entidad]).copy()

        if tiempo is not None and periodo is not None:
            df = df[
                df[tiempo] == periodo
            ].copy()

        if df.empty:
            advertencias.append(
                "No hay datos válidos para construir el ranking."
            )

            return self._resultado_vacio(
                metrica=metrica,
                entidad=entidad,
                tiempo=tiempo,
                periodo=periodo,
                n=n,
                ascendente=ascendente,
                min_periodos=min_periodos,
                advertencias=advertencias,
            )

        # Agregación a nivel de entidad.
        #
        # El comportamiento estadístico de Guía CZ exige que el ranking
        # compare entidades a partir del promedio de sus observaciones
        # válidas. El conteo se conserva para controlar el mínimo requerido.
        por_entidad = (
            df.groupby(
                entidad,
                sort=False,
                dropna=False,
            )[metrica]
            .agg(
                valor="mean",
                periodos="count",
            )
            .reset_index()
        )

        excluidas = por_entidad[
            por_entidad["periodos"] < min_periodos
        ].copy()

        if not excluidas.empty:
            cantidad_excluidas = int(
                excluidas.shape[0]
            )

            advertencias.append(
                f"Se excluyeron {cantidad_excluidas} entidades "
                f"con menos de {min_periodos} observaciones válidas."
            )

        por_entidad = por_entidad[
            por_entidad["periodos"] >= min_periodos
        ].copy()

        if por_entidad.empty:
            advertencias.append(
                "Ninguna entidad cumple el mínimo de "
                f"{min_periodos} observaciones."
            )

            return self._resultado_vacio(
                metrica=metrica,
                entidad=entidad,
                tiempo=tiempo,
                periodo=periodo,
                n=n,
                ascendente=ascendente,
                min_periodos=min_periodos,
                advertencias=advertencias,
            )

        # Clave secundaria determinista.
        #
        # La guía exige un desempate fijo. Como el identificador puede ser
        # texto, entero o cualquier otro tipo comparable, construimos una
        # representación estable.
        por_entidad["_clave_entidad"] = (
            por_entidad[entidad].map(
                self._clave_determinista
            )
        )

        por_entidad = por_entidad.sort_values(
            by=["valor", "_clave_entidad"],
            ascending=[
                ascendente,
                True,
            ],
            kind="mergesort",
        )

        top = por_entidad.head(n).copy()

        top = top.drop(
            columns=["_clave_entidad"]
        )

        # Redondeo únicamente para la salida estructurada.
        # Los cálculos se realizaron con los valores originales.
        top["valor"] = top["valor"].astype(float).round(6)

        mediana_poblacion = float(
            por_entidad["valor"].median()
        )

        evidencia = self._generar_evidencia(
            top=top,
            metrica=metrica,
            n_observaciones=len(df),
            mediana_poblacion=mediana_poblacion,
            cantidad_entidades=len(por_entidad),
        )

        datos_visualizacion = [
            {
                entidad: self._serializar_valor(
                    fila[entidad]
                ),
                "valor": float(fila["valor"]),
                "periodos": int(fila["periodos"]),
            }
            for _, fila in top.iterrows()
        ]

        registros = [
            {
                entidad: self._serializar_valor(
                    fila[entidad]
                ),
                "valor": float(fila["valor"]),
                "periodos": int(fila["periodos"]),
            }
            for _, fila in top.iterrows()
        ]

        return {
            "skill": self.nombre,
            "metrica": metrica,
            "entidad": entidad,
            "tiempo": tiempo,
            "periodo": periodo,
            "n": len(df),
            "resultado": registros,
            "datos_visualizacion": datos_visualizacion,
            "advertencias": advertencias,
            "evidencia": evidencia,
            "tipo_grafico": "bar_horizontal",
            "parametros": {
                "n": n,
                "ascendente": ascendente,
                "min_periodos": min_periodos,
            },
        }

    @staticmethod
    def _validar_entrada(
        datos: DataEngine,
        parametros: Mapping[str, Any],
    ) -> None:
        """Valida el tipo y los parámetros mínimos."""
        if not isinstance(datos, DataEngine):
            raise TypeError(
                "datos debe ser una instancia de DataEngine."
            )

        if not isinstance(parametros, Mapping):
            raise TypeError(
                "parametros debe ser un Mapping."
            )

        for parametro in (
            "metrica",
            "entidad",
        ):
            if parametro not in parametros:
                raise ValueError(
                    f"Falta el parámetro requerido: "
                    f"'{parametro}'."
                )

            valor = parametros[parametro]

            if not isinstance(valor, str):
                raise TypeError(
                    f"{parametro} debe ser una cadena."
                )

            if not valor.strip():
                raise ValueError(
                    f"{parametro} no puede ser una cadena vacía."
                )

        tiempo = parametros.get("tiempo")

        if tiempo is not None:
            if not isinstance(tiempo, str):
                raise TypeError(
                    "tiempo debe ser una cadena o None."
                )

            if not tiempo.strip():
                raise ValueError(
                    "tiempo no puede ser una cadena vacía."
                )

    @staticmethod
    def _validar_columnas(
        dataframe: pd.DataFrame,
        *,
        metrica: str,
        entidad: str,
        tiempo: str | None,
    ) -> None:
        """Comprueba que las columnas solicitadas existan."""
        if metrica not in dataframe.columns:
            raise ValueError(
                f"La métrica '{metrica}' no existe "
                "en el dataset."
            )

        if entidad not in dataframe.columns:
            raise ValueError(
                f"La entidad '{entidad}' no existe "
                "en el dataset."
            )

        if tiempo is not None and tiempo not in dataframe.columns:
            raise ValueError(
                f"La columna de tiempo '{tiempo}' "
                "no existe en el dataset."
            )

    @staticmethod
    def _obtener_entero_positivo(
        parametros: Mapping[str, Any],
        nombre: str,
        *,
        defecto: int,
    ) -> int:
        """Obtiene un entero positivo de los parámetros."""
        valor = parametros.get(
            nombre,
            defecto,
        )

        if isinstance(valor, bool):
            raise TypeError(
                f"{nombre} debe ser un entero positivo."
            )

        try:
            entero = int(valor)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"{nombre} debe ser un entero positivo."
            ) from exc

        if entero <= 0:
            raise ValueError(
                f"{nombre} debe ser mayor que cero."
            )

        return entero

    @staticmethod
    def _obtener_booleano(
        parametros: Mapping[str, Any],
        nombre: str,
        *,
        defecto: bool,
    ) -> bool:
        """Obtiene un booleano de los parámetros."""
        valor = parametros.get(
            nombre,
            defecto,
        )

        if isinstance(valor, bool):
            return valor

        if isinstance(valor, str):
            texto = valor.strip().lower()

            if texto in {
                "true",
                "1",
                "si",
                "sí",
            }:
                return True

            if texto in {
                "false",
                "0",
                "no",
            }:
                return False

        raise TypeError(
            f"{nombre} debe ser booleano."
        )

    @staticmethod
    def _clave_determinista(
        valor: Any,
    ) -> tuple[str, str]:
        """Construye una clave estable para desempatar."""
        return (
            type(valor).__name__,
            str(valor),
        )

    @staticmethod
    def _serializar_valor(
        valor: Any,
    ) -> Any:
        """Convierte valores pandas/numpy a valores simples."""
        if pd.isna(valor):
            return None

        if hasattr(valor, "item"):
            try:
                return valor.item()
            except ValueError:
                pass

        return valor

    def _generar_evidencia(
        self,
        *,
        top: pd.DataFrame,
        metrica: str,
        n_observaciones: int,
        mediana_poblacion: float,
        cantidad_entidades: int,
    ) -> list[dict[str, Any]]:
        """Genera Evidence para las entidades rankeadas y la mediana."""
        evidencia: list[dict[str, Any]] = []

        for _, fila in top.iterrows():
            entidad = self._serializar_valor(
                fila[top.columns[0]]
            )

            valor = float(fila["valor"])
            periodos = int(fila["periodos"])

            registro = {
                "skill": self.nombre,
                "descripcion": (
                    f"{entidad}: promedio de {metrica}"
                ),
                "valor": valor,
                "unidad": "unidad de la métrica",
                "n": periodos,
                "metodo": (
                    "promedio de observaciones válidas "
                    "por entidad"
                ),
            }

            evidencia.append(registro)

            if self._evidence_store is not None:
                self._evidence_store.agregar(
                    skill=self.nombre,
                    metodo=registro["metodo"],
                    n=periodos,
                    resultado={
                        "descripcion": registro["descripcion"],
                        "valor": valor,
                        "unidad": registro["unidad"],
                    },
                )

        registro_mediana = {
            "skill": self.nombre,
            "descripcion": (
                f"Mediana de los promedios de {metrica} "
                "entre las entidades incluidas"
            ),
            "valor": mediana_poblacion,
            "unidad": "unidad de la métrica",
            "n": cantidad_entidades,
            "metodo": (
                "mediana de los promedios "
                "calculados por entidad"
            ),
        }

        evidencia.append(registro_mediana)

        if self._evidence_store is not None:
            self._evidence_store.agregar(
                skill=self.nombre,
                metodo=registro_mediana["metodo"],
                n=cantidad_entidades,
                resultado={
                    "descripcion": registro_mediana[
                        "descripcion"
                    ],
                    "valor": mediana_poblacion,
                    "unidad": registro_mediana[
                        "unidad"
                    ],
                },
            )

        return evidencia

    @staticmethod
    def _resultado_vacio(
        *,
        metrica: str,
        entidad: str,
        tiempo: str | None,
        periodo: Any,
        n: int,
        ascendente: bool,
        min_periodos: int,
        advertencias: list[str],
    ) -> dict[str, Any]:
        """Construye una respuesta estructurada sin resultados."""
        return {
            "skill": "ranking",
            "metrica": metrica,
            "entidad": entidad,
            "tiempo": tiempo,
            "periodo": periodo,
            "n": 0,
            "resultado": [],
            "datos_visualizacion": [],
            "advertencias": advertencias,
            "evidencia": [],
            "tipo_grafico": "bar_horizontal",
            "parametros": {
                "n": n,
                "ascendente": ascendente,
                "min_periodos": min_periodos,
            },
        }