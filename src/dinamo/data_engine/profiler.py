"""Perfilador automático de datasets para DINAMO_ANALYTICS.

Este módulo infiere información estructural de un DataFrame sin conocer
columnas específicas de una base concreta.

El Perfilador no define el contrato compartido PerfilDataset. Su función
es producir inferencias que posteriormente pueden convertirse al contrato
oficial definido en dinamo.core.contracts.

Reglas principales:
- detectar tiempo mediante fechas o nombres que sugieran periodos;
- detectar entidad mediante repetición por periodo o unicidad;
- detectar métricas numéricas con más de cinco valores distintos;
- detectar dimensiones con pocas categorías;
- ignorar columnas vacías, constantes o redundantes;
- mantener un comportamiento determinístico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


ROLES = frozenset(
    {
        "entidad",
        "tiempo",
        "métrica",
        "dimensión",
        "calidad",
        "ignorar",
    }
)

# Términos genéricos relacionados con periodos.
# No contienen nombres de columnas específicos de Catch.
INDICADORES_TIEMPO = (
    "fecha",
    "periodo",
    "período",
    "mes",
    "bimestre",
    "trimestre",
    "semestre",
    "año",
    "anio",
    "year",
    "month",
    "quarter",
    "semester",
)

# Términos que suelen indicar identificadores.
INDICADORES_ID = (
    "id",
    "codigo",
    "código",
    "code",
    "identificador",
)

# Nombres que suelen indicar una columna legible de entidad.
INDICADORES_ENTIDAD = (
    "empresa",
    "compañía",
    "compania",
    "organización",
    "organizacion",
    "cliente",
    "tienda",
    "empleado",
    "entidad",
    "nombre",
)


@dataclass(frozen=True)
class InferenciaColumna:
    """Representa la inferencia realizada sobre una columna."""

    nombre: str
    rol: str
    tipo: str
    formato: str | None
    etiqueta: str
    sinonimos: tuple[str, ...]
    valores_posibles: tuple[Any, ...]

    def __post_init__(self) -> None:
        if self.rol not in ROLES:
            raise ValueError(
                f"Rol de columna no soportado: '{self.rol}'."
            )


@dataclass(frozen=True)
class PerfilInferido:
    """Resultado interno del Perfilador antes de adaptarlo al contrato oficial."""

    columnas: tuple[InferenciaColumna, ...]

    def columnas_por_rol(
        self,
        rol: str,
    ) -> tuple[InferenciaColumna, ...]:
        """Devuelve las columnas que fueron asignadas a un rol."""
        return tuple(
            columna
            for columna in self.columnas
            if columna.rol == rol
        )

    def nombres_por_rol(
        self,
        rol: str,
    ) -> tuple[str, ...]:
        """Devuelve los nombres de las columnas de un rol."""
        return tuple(
            columna.nombre
            for columna in self.columnas_por_rol(rol)
        )


class Perfilador:
    """Infiere un perfil estructural de un DataFrame."""

    def __init__(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError(
                "dataframe debe ser un pandas.DataFrame."
            )

        self._dataframe = dataframe.copy(deep=True)

    def perfilar(self) -> PerfilInferido:
        """Construye un perfil inferido de todas las columnas."""
        if self._dataframe.empty and len(self._dataframe.columns) == 0:
            return PerfilInferido(columnas=())

        columnas = [
            self._analizar_columna(nombre)
            for nombre in self._dataframe.columns
        ]

        columnas = self._asignar_entidad_y_tiempo(columnas)

        return PerfilInferido(columnas=tuple(columnas))

    def _analizar_columna(
        self,
        nombre: str,
    ) -> InferenciaColumna:
        """Analiza una columna antes de resolver roles globales."""
        serie = self._dataframe[nombre]

        etiqueta = str(nombre).replace("_", " ").strip()

        if serie.dropna().empty:
            return self._crear_inferencia(
                nombre=nombre,
                rol="ignorar",
                tipo=self._tipo_pandas(serie),
                formato=None,
                etiqueta=etiqueta,
                valores=(),
            )

        if serie.nunique(dropna=True) <= 1:
            return self._crear_inferencia(
                nombre=nombre,
                rol="ignorar",
                tipo=self._tipo_pandas(serie),
                formato=None,
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        # Una columna datetime es una candidata directa a tiempo.
        if pd.api.types.is_datetime64_any_dtype(serie):
            return self._crear_inferencia(
                nombre=nombre,
                rol="tiempo",
                tipo=self._tipo_pandas(serie),
                formato="fecha",
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        # Un número cuyo nombre indica periodo se trata como periodo,
        # no como fecha.
        if self._es_periodo_numerico(serie, nombre):
            return self._crear_inferencia(
                nombre=nombre,
                rol="tiempo",
                tipo=self._tipo_pandas(serie),
                formato="periodo",
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        # Una columna de texto que realmente contiene fechas también
        # puede ser tiempo.
        if self._es_fecha_textual(serie, nombre):
            return self._crear_inferencia(
                nombre=nombre,
                rol="tiempo",
                tipo=self._tipo_pandas(serie),
                formato="fecha",
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        if self._es_numerica(serie):
            valores_distintos = serie.dropna().nunique()

            if valores_distintos > 5:
                return self._crear_inferencia(
                    nombre=nombre,
                    rol="métrica",
                    tipo=self._tipo_pandas(serie),
                    formato=self._formato_metrica(serie, nombre),
                    etiqueta=etiqueta,
                    valores=(),
                )

            return self._crear_inferencia(
                nombre=nombre,
                rol="dimensión",
                tipo=self._tipo_pandas(serie),
                formato=None,
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        if self._es_dimension_categorica(serie):
            return self._crear_inferencia(
                nombre=nombre,
                rol="dimensión",
                tipo=self._tipo_pandas(serie),
                formato=None,
                etiqueta=etiqueta,
                valores=self._valores_posibles(serie),
            )

        return self._crear_inferencia(
            nombre=nombre,
            rol="ignorar",
            tipo=self._tipo_pandas(serie),
            formato=None,
            etiqueta=etiqueta,
            valores=self._valores_posibles(serie),
        )

    def _asignar_entidad_y_tiempo(
        self,
        columnas: list[InferenciaColumna],
    ) -> list[InferenciaColumna]:
        """Resuelve los roles globales de entidad y tiempo."""
        resultado = list(columnas)

        indice_tiempo = self._seleccionar_tiempo(resultado)

        if indice_tiempo is not None:
            resultado = self._reasignar(
                resultado,
                indice_tiempo,
                rol="tiempo",
            )

        indice_entidad = self._seleccionar_entidad(
            resultado,
            indice_tiempo=indice_tiempo,
        )

        if indice_entidad is not None:
            resultado = self._reasignar(
                resultado,
                indice_entidad,
                rol="entidad",
            )

        return resultado

    def _seleccionar_tiempo(
        self,
        columnas: list[InferenciaColumna],
    ) -> int | None:
        """Selecciona determinísticamente la mejor columna temporal.

        Una columna no se considera tiempo únicamente por ser numérica
        u ordenable. Debe existir evidencia temporal explícita:
        - ya fue clasificada como tiempo; o
        - su nombre sugiere un periodo y puede ordenarse.
        """
        candidatos: list[tuple[int, int, str]] = []

        for indice, columna in enumerate(columnas):
            if columna.rol == "ignorar":
                continue

            serie = self._dataframe[columna.nombre]

            es_tiempo_confirmado = columna.rol == "tiempo"
            nombre_sugiere_tiempo = self._nombre_sugiere_tiempo(
                columna.nombre
            )

            # Evitamos convertir una métrica o dimensión cualquiera
            # en tiempo sólo porque sus valores sean ordenables.
            if not es_tiempo_confirmado and not nombre_sugiere_tiempo:
                continue

            puntuacion = 0

            if es_tiempo_confirmado:
                puntuacion += 100

            if columna.formato == "fecha":
                puntuacion += 50

            if columna.formato == "periodo":
                puntuacion += 40

            if nombre_sugiere_tiempo:
                puntuacion += 30

            if self._puede_ordenar_observaciones(
                serie,
                nombre=columna.nombre,
            ):
                puntuacion += 20
            else:
                # Una variable sugerida por nombre pero no ordenable
                # no constituye una variable temporal válida.
                continue

            candidatos.append(
                (
                    -puntuacion,
                    indice,
                    columna.nombre,
                )
            )

        if not candidatos:
            return None

        candidatos.sort()

        return candidatos[0][1]

    def _seleccionar_entidad(
        self,
        columnas: list[InferenciaColumna],
        *,
        indice_tiempo: int | None,
    ) -> int | None:
        """Selecciona la columna que mejor representa la entidad."""
        candidatos: list[tuple[int, int, str]] = []

        nombre_tiempo = (
            columnas[indice_tiempo].nombre
            if indice_tiempo is not None
            else None
        )

        for indice, columna in enumerate(columnas):
            if columna.rol == "ignorar":
                continue

            if columna.nombre == nombre_tiempo:
                continue

            serie = self._dataframe[columna.nombre]

            if not self._puede_ser_entidad(serie):
                continue

            puntuacion = 0

            if self._nombre_sugiere_entidad_legible(
                columna.nombre
            ):
                puntuacion += 50

            if self._nombre_parece_id(columna.nombre):
                puntuacion += 20

            if indice_tiempo is not None:
                if self._entidad_se_repite_por_tiempo(
                    serie,
                    self._dataframe.iloc[:, indice_tiempo],
                ):
                    puntuacion += 40
            else:
                if serie.nunique(dropna=True) == len(
                    serie.dropna()
                ):
                    puntuacion += 30

            if puntuacion > 0:
                candidatos.append(
                    (
                        -puntuacion,
                        indice,
                        columna.nombre,
                    )
                )

        if not candidatos:
            return None

        candidatos.sort()

        return candidatos[0][1]

    def _puede_ser_entidad(
        self,
        serie: pd.Series,
    ) -> bool:
        """Comprueba si una columna puede representar entidades."""
        if serie.dropna().empty:
            return False

        valores = serie.dropna()

        if valores.nunique() <= 1:
            return False

        return True

    def _entidad_se_repite_por_tiempo(
        self,
        entidad: pd.Series,
        tiempo: pd.Series,
    ) -> bool:
        """Comprueba si una entidad aparece en varios periodos."""
        auxiliar = pd.DataFrame(
            {
                "entidad": entidad,
                "tiempo": tiempo,
            }
        ).dropna()

        if auxiliar.empty:
            return False

        if auxiliar["entidad"].nunique() <= 1:
            return False

        pares = auxiliar.drop_duplicates(
            subset=["entidad", "tiempo"]
        )

        repeticiones = pares.groupby("entidad").size()

        return bool((repeticiones > 1).any())

    def _es_periodo_numerico(
        self,
        serie: pd.Series,
        nombre: str,
    ) -> bool:
        """Detecta un número que representa un periodo ordenable."""
        if not self._nombre_sugiere_tiempo(nombre):
            return False

        if not pd.api.types.is_numeric_dtype(serie):
            return False

        return self._numerico_parece_periodo(serie)

    def _es_fecha_textual(
        self,
        serie: pd.Series,
        nombre: str,
    ) -> bool:
        """Detecta fechas almacenadas como texto."""
        if not self._nombre_sugiere_tiempo(nombre):
            return False

        valores = serie.dropna()

        if valores.empty:
            return False

        if pd.api.types.is_numeric_dtype(valores):
            return False

        convertida = self._convertir_a_fecha(valores)

        return bool(convertida.notna().mean() >= 0.8)

    def _numerico_parece_periodo(
        self,
        serie: pd.Series,
    ) -> bool:
        """Comprueba si un número puede representar un periodo."""
        valores = serie.dropna()

        if valores.empty:
            return False

        unicos = sorted(
            pd.unique(valores)
        )

        if len(unicos) < 2:
            return False

        if all(
            float(valor).is_integer()
            for valor in unicos
            if pd.notna(valor)
        ):
            minimo = float(min(unicos))
            maximo = float(max(unicos))

            # Meses.
            if 1 <= minimo <= 12 and maximo <= 12:
                return True

            # Años.
            if 1900 <= minimo <= 2200 and maximo <= 2200:
                return True

            # Periodos ordinales pequeños.
            if 1 <= minimo <= 20 and maximo <= 20:
                return True

        return False

    def _puede_ordenar_observaciones(
        self,
        serie: pd.Series,
        *,
        nombre: str,
    ) -> bool:
        """Comprueba que una columna tenga un orden útil."""
        valores = serie.dropna()

        if len(valores) < 2:
            return False

        if pd.api.types.is_datetime64_any_dtype(valores):
            return valores.nunique() > 1

        if pd.api.types.is_numeric_dtype(valores):
            return valores.nunique() > 1

        # Sólo intentamos interpretar texto como fecha cuando el nombre
        # aporta evidencia de que se trata de una variable temporal.
        if not self._nombre_sugiere_tiempo(nombre):
            return False

        convertida = self._convertir_a_fecha(valores)

        if convertida.notna().mean() >= 0.8:
            return convertida.nunique() > 1

        return False

    def _convertir_a_fecha(
        self,
        serie: pd.Series,
    ) -> pd.Series:
        """Convierte una serie a fechas evitando warnings de inferencia."""
        return pd.to_datetime(
            serie,
            format="mixed",
            errors="coerce",
        )

    def _es_numerica(
        self,
        serie: pd.Series,
    ) -> bool:
        """Indica si la columna es numérica."""
        return pd.api.types.is_numeric_dtype(serie)

    def _es_dimension_categorica(
        self,
        serie: pd.Series,
    ) -> bool:
        """Comprueba si una columna puede ser una dimensión."""
        valores = serie.dropna()

        if valores.empty:
            return False

        unicos = valores.nunique()

        if unicos <= 50:
            return True

        return False

    def _formato_metrica(
        self,
        serie: pd.Series,
        nombre: str,
    ) -> str:
        """Infiere el formato de presentación de una métrica."""
        valores = serie.dropna()

        if valores.empty:
            return "numérico"

        if self._parece_porcentaje(valores):
            return "porcentaje"

        nombre_normalizado = self._normalizar_nombre(nombre)

        palabras_moneda = (
            "salario",
            "venta",
            "ventas",
            "costo",
            "coste",
            "precio",
            "ingreso",
            "ingresos",
            "sueldo",
            "valor",
        )

        if any(
            palabra in nombre_normalizado
            for palabra in palabras_moneda
        ):
            return "moneda"

        if self._solo_enteros(valores):
            return "entero"

        return "numérico"

    def _parece_porcentaje(
        self,
        serie: pd.Series,
    ) -> bool:
        """Detecta una métrica expresada entre 0 y 1."""
        valores = serie.dropna()

        if valores.empty:
            return False

        return bool(
            valores.min() >= 0
            and valores.max() <= 1
        )

    def _solo_enteros(
        self,
        serie: pd.Series,
    ) -> bool:
        """Indica si todos los valores numéricos son enteros."""
        valores = serie.dropna()

        if valores.empty:
            return False

        return bool(
            ((valores % 1) == 0).all()
        )

    def _nombre_sugiere_tiempo(
        self,
        nombre: str,
    ) -> bool:
        """Indica si el nombre contiene un indicador temporal."""
        normalizado = self._normalizar_nombre(nombre)

        return any(
            indicador in normalizado
            for indicador in INDICADORES_TIEMPO
        )

    def _nombre_sugiere_entidad_legible(
        self,
        nombre: str,
    ) -> bool:
        """Indica si el nombre parece una entidad legible."""
        normalizado = self._normalizar_nombre(nombre)

        return any(
            indicador in normalizado
            for indicador in INDICADORES_ENTIDAD
        )

    def _nombre_parece_id(
        self,
        nombre: str,
    ) -> bool:
        """Indica si el nombre parece representar un identificador."""
        normalizado = self._normalizar_nombre(nombre)

        return any(
            normalizado == indicador
            or normalizado.startswith(f"{indicador}_")
            or normalizado.endswith(f"_{indicador}")
            for indicador in INDICADORES_ID
        )

    def _tipo_pandas(
        self,
        serie: pd.Series,
    ) -> str:
        """Devuelve una descripción estable del tipo de pandas."""
        if pd.api.types.is_datetime64_any_dtype(serie):
            return "datetime"

        if pd.api.types.is_bool_dtype(serie):
            return "boolean"

        if pd.api.types.is_integer_dtype(serie):
            return "integer"

        if pd.api.types.is_float_dtype(serie):
            return "float"

        if pd.api.types.is_numeric_dtype(serie):
            return "numeric"

        if pd.api.types.is_string_dtype(serie):
            return "string"

        return str(serie.dtype)

    def _valores_posibles(
        self,
        serie: pd.Series,
        limite: int = 50,
    ) -> tuple[Any, ...]:
        """Devuelve categorías posibles en orden determinístico."""
        valores = serie.dropna().unique().tolist()

        if len(valores) > limite:
            return ()

        try:
            valores = sorted(
                valores,
                key=lambda valor: str(valor),
            )
        except TypeError:
            valores = [
                str(valor)
                for valor in valores
            ]

        return tuple(
            self._valor_serializable(valor)
            for valor in valores
        )

    def _valor_serializable(
        self,
        valor: Any,
    ) -> Any:
        """Convierte valores comunes de pandas a tipos serializables."""
        if isinstance(
            valor,
            (
                pd.Timestamp,
                pd.Timedelta,
            ),
        ):
            return valor.isoformat()

        if hasattr(valor, "item"):
            try:
                return valor.item()
            except (ValueError, TypeError):
                pass

        return valor

    def _crear_inferencia(
        self,
        *,
        nombre: str,
        rol: str,
        tipo: str,
        formato: str | None,
        etiqueta: str,
        valores: tuple[Any, ...],
    ) -> InferenciaColumna:
        """Construye una inferencia de columna."""
        return InferenciaColumna(
            nombre=str(nombre),
            rol=rol,
            tipo=tipo,
            formato=formato,
            etiqueta=etiqueta,
            sinonimos=(),
            valores_posibles=valores,
        )

    def _reasignar(
        self,
        columnas: list[InferenciaColumna],
        indice: int,
        *,
        rol: str,
    ) -> list[InferenciaColumna]:
        """Reasigna una columna manteniendo sus metadatos."""
        resultado = list(columnas)
        anterior = resultado[indice]

        formato = anterior.formato

        if rol == "tiempo" and formato is None:
            formato = "periodo"

        resultado[indice] = InferenciaColumna(
            nombre=anterior.nombre,
            rol=rol,
            tipo=anterior.tipo,
            formato=formato,
            etiqueta=anterior.etiqueta,
            sinonimos=anterior.sinonimos,
            valores_posibles=anterior.valores_posibles,
        )

        return resultado

    @staticmethod
    def _normalizar_nombre(
        nombre: str,
    ) -> str:
        """Normaliza un nombre para comparar indicadores."""
        return (
            str(nombre)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )