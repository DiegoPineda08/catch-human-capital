"""Pruebas del Data Engine de DINAMO_ANALYTICS."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dinamo.data_engine.engine import DataEngine


class TestDataEngine(unittest.TestCase):
    """Pruebas de comportamiento del Data Engine."""

    def setUp(self) -> None:
        """Crea un DataFrame base para las pruebas."""
        self.dataframe = pd.DataFrame(
            {
                "empresa": ["A", "B", "C"],
                "valor": [10, 20, 30],
            }
        )

    def test_construccion_desde_dataframe(self) -> None:
        """Debe construir el motor a partir de un DataFrame."""
        engine = DataEngine(self.dataframe)

        self.assertEqual(engine.forma(), (3, 2))
        self.assertEqual(
            engine.columnas(),
            ["empresa", "valor"],
        )
        self.assertEqual(
            engine.numero_filas(),
            3,
        )
        self.assertEqual(
            engine.numero_columnas(),
            2,
        )

    def test_dataframes_entregados_son_copias(self) -> None:
        """Modificar una copia no debe alterar los datos internos."""
        engine = DataEngine(self.dataframe)

        resultado = engine.dataframe()
        resultado.loc[0, "valor"] = 9999

        interno = engine.dataframe()

        self.assertEqual(
            interno.loc[0, "valor"],
            10,
        )

    def test_dataframe_original_no_se_modifica(self) -> None:
        """El motor debe conservar una copia independiente del original."""
        engine = DataEngine(self.dataframe)

        self.dataframe.loc[0, "valor"] = 9999

        resultado = engine.dataframe()

        self.assertEqual(
            resultado.loc[0, "valor"],
            10,
        )

    def test_fuente_por_defecto_es_none(self) -> None:
        """Una instancia creada directamente no debe tener fuente."""
        engine = DataEngine(self.dataframe)

        self.assertIsNone(engine.fuente())

    def test_fuente_desde_dataframe(self) -> None:
        """Debe conservar la fuente cuando se proporciona."""
        fuente = Path("data") / "ejemplo.xlsx"

        engine = DataEngine(
            self.dataframe,
            fuente=fuente,
        )

        self.assertEqual(
            engine.fuente(),
            fuente,
        )

    def test_carga_desde_excel(self) -> None:
        """Debe cargar correctamente un archivo Excel."""
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "datos.xlsx"

            self.dataframe.to_excel(
                ruta,
                index=False,
            )

            engine = DataEngine.desde_excel(ruta)

            pd.testing.assert_frame_equal(
                engine.dataframe(),
                self.dataframe,
            )

            self.assertEqual(
                engine.fuente(),
                ruta,
            )

    def test_carga_desde_csv(self) -> None:
        """Debe cargar correctamente un archivo CSV."""
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "datos.csv"

            self.dataframe.to_csv(
                ruta,
                index=False,
            )

            engine = DataEngine.desde_csv(ruta)

            pd.testing.assert_frame_equal(
                engine.dataframe(),
                self.dataframe,
            )

            self.assertEqual(
                engine.fuente(),
                ruta,
            )

    def test_carga_automatica_desde_archivo_excel(self) -> None:
        """Debe detectar automáticamente un archivo Excel."""
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "datos.xlsx"

            self.dataframe.to_excel(
                ruta,
                index=False,
            )

            engine = DataEngine.desde_archivo(ruta)

            pd.testing.assert_frame_equal(
                engine.dataframe(),
                self.dataframe,
            )

    def test_carga_automatica_desde_archivo_csv(self) -> None:
        """Debe detectar automáticamente un archivo CSV."""
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "datos.csv"

            self.dataframe.to_csv(
                ruta,
                index=False,
            )

            engine = DataEngine.desde_archivo(ruta)

            pd.testing.assert_frame_equal(
                engine.dataframe(),
                self.dataframe,
            )

    def test_tipo_de_dato_invalido(self) -> None:
        """Debe rechazar objetos que no sean DataFrame."""
        with self.assertRaises(TypeError):
            DataEngine(["A", "B", "C"])

    def test_archivo_inexistente(self) -> None:
        """Debe informar cuando la fuente no existe."""
        ruta = Path("archivo_que_no_existe.xlsx")

        with self.assertRaises(FileNotFoundError):
            DataEngine.desde_excel(ruta)

    def test_extension_no_soportada(self) -> None:
        """Debe rechazar extensiones que no soporta el Data Engine."""
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "datos.txt"
            ruta.write_text(
                "empresa,valor\nA,10\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                DataEngine.desde_archivo(ruta)


if __name__ == "__main__":
    unittest.main()