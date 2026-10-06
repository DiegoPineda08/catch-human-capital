"""Pruebas del Perfilador de DINAMO_ANALYTICS."""

from __future__ import annotations

import unittest

import pandas as pd

from dinamo.data_engine.profiler import Perfilador


class TestPerfilador(unittest.TestCase):
    """Pruebas de inferencia estructural del Perfilador."""

    def test_detecta_entidad_y_periodo_numerico(self) -> None:
        """Debe detectar entidad y periodo numérico correctamente."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "A", "B", "B", "C", "C"],
                "mes": [1, 2, 1, 2, 1, 2],
                "salario": [1000, 1100, 1200, 1250, 900, 950],
                "region": [
                    "Norte",
                    "Norte",
                    "Sur",
                    "Sur",
                    "Centro",
                    "Centro",
                ],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["empresa"].rol,
            "entidad",
        )
        self.assertEqual(
            columnas["mes"].rol,
            "tiempo",
        )
        self.assertEqual(
            columnas["mes"].formato,
            "periodo",
        )

    def test_detecta_fecha_datetime(self) -> None:
        """Debe detectar una columna datetime como tiempo."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "A", "B", "B"],
                "fecha": pd.to_datetime(
                    [
                        "2025-01-01",
                        "2025-02-01",
                        "2025-01-01",
                        "2025-02-01",
                    ]
                ),
                "ventas": [1000, 1100, 1200, 1300],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["fecha"].rol,
            "tiempo",
        )
        self.assertEqual(
            columnas["fecha"].tipo,
            "datetime",
        )
        self.assertEqual(
            columnas["fecha"].formato,
            "fecha",
        )

    def test_detecta_metrica_con_mas_de_cinco_valores_distintos(
        self,
    ) -> None:
        """Una variable numérica con más de cinco valores es métrica."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C", "D", "E", "F"],
                "salario": [
                    1000,
                    1200,
                    900,
                    1500,
                    1800,
                    2100,
                ],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["salario"].rol,
            "métrica",
        )

    def test_detecta_dimension_numerica_con_hasta_cinco_valores(
        self,
    ) -> None:
        """Una variable numérica con hasta cinco valores es dimensión."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C", "D", "E"],
                "nivel": [1, 2, 3, 1, 2],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["nivel"].rol,
            "dimensión",
        )

    def test_detecta_dimension_categorica(self) -> None:
        """Una variable categórica con pocas categorías es dimensión."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C", "D", "E", "F"],
                "region": [
                    "Norte",
                    "Sur",
                    "Centro",
                    "Norte",
                    "Sur",
                    "Centro",
                ],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["region"].rol,
            "dimensión",
        )

    def test_ignora_columna_vacia(self) -> None:
        """Una columna completamente vacía debe ignorarse."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C"],
                "vacia": [None, None, None],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["vacia"].rol,
            "ignorar",
        )

    def test_ignora_columna_constante(self) -> None:
        """Una columna constante debe ignorarse."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C"],
                "constante": ["X", "X", "X"],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["constante"].rol,
            "ignorar",
        )

    def test_no_inventa_tiempo(self) -> None:
        """Una métrica numérica no debe convertirse en tiempo."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C", "D", "E", "F"],
                "ventas": [
                    100,
                    200,
                    300,
                    400,
                    500,
                    600,
                ],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertNotEqual(
            columnas["ventas"].rol,
            "tiempo",
        )
        self.assertEqual(
            columnas["ventas"].rol,
            "métrica",
        )

    def test_detecta_fecha_textual(self) -> None:
        """Debe detectar fechas almacenadas como texto."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "A", "B", "B"],
                "fecha": [
                    "2025-01-01",
                    "2025-02-01",
                    "2025-01-01",
                    "2025-02-01",
                ],
                "ventas": [1000, 1100, 1200, 1300],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["fecha"].rol,
            "tiempo",
        )
        self.assertEqual(
            columnas["fecha"].formato,
            "fecha",
        )

    def test_inferencia_es_deterministica(self) -> None:
        """La misma entrada debe producir el mismo perfil."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "A", "B", "B", "C", "C"],
                "mes": [1, 2, 1, 2, 1, 2],
                "ventas": [100, 200, 300, 400, 500, 600],
                "region": [
                    "Norte",
                    "Norte",
                    "Sur",
                    "Sur",
                    "Centro",
                    "Centro",
                ],
            }
        )

        perfil_1 = Perfilador(dataframe).perfilar()
        perfil_2 = Perfilador(dataframe).perfilar()

        self.assertEqual(
            perfil_1,
            perfil_2,
        )

    def test_valores_posibles_dimension(self) -> None:
        """Las dimensiones deben conservar sus valores posibles."""
        dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C", "D"],
                "region": [
                    "Norte",
                    "Sur",
                    "Centro",
                    "Norte",
                ],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["region"].valores_posibles,
            ("Centro", "Norte", "Sur"),
        )

    def test_etiqueta_reemplaza_guiones_bajos(self) -> None:
        """La etiqueta debe convertir guiones bajos en espacios."""
        dataframe = pd.DataFrame(
            {
                "empresa_nombre": ["A", "B", "C"],
            }
        )

        perfil = Perfilador(dataframe).perfilar()

        columnas = {
            columna.nombre: columna
            for columna in perfil.columnas
        }

        self.assertEqual(
            columnas["empresa_nombre"].etiqueta,
            "empresa nombre",
        )


if __name__ == "__main__":
    unittest.main()