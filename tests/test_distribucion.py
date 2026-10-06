"""Pruebas para la Skill distribucion."""

import unittest

import pandas as pd

from dinamo.data_engine.engine import DataEngine
from dinamo.evidence.store import EvidenceStore
from dinamo.skills.distribucion import DistribucionSkill


class TestDistribucionSkill(unittest.TestCase):
    """Pruebas de comportamiento de DistribucionSkill."""

    def crear_datos(
        self,
        valores: list[object],
    ) -> DataEngine:
        """Crea un DataEngine con datos sintéticos."""
        dataframe = pd.DataFrame(
            {
                "empresa": [
                    f"Empresa {i + 1}"
                    for i in range(len(valores))
                ],
                "ventas": valores,
            }
        )

        return DataEngine(dataframe)

    def test_calcula_estadisticos_basicos(self) -> None:
        """Calcula correctamente los principales estadísticos."""
        datos = self.crear_datos(
            [10, 20, 30, 40, 50]
        )

        skill = DistribucionSkill()

        resultado = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        estadisticos = resultado["resultado"]

        self.assertEqual(
            estadisticos["n"],
            5,
        )
        self.assertEqual(
            estadisticos["min"],
            10.0,
        )
        self.assertEqual(
            estadisticos["q1"],
            20.0,
        )
        self.assertEqual(
            estadisticos["mediana"],
            30.0,
        )
        self.assertEqual(
            estadisticos["q3"],
            40.0,
        )
        self.assertEqual(
            estadisticos["max"],
            50.0,
        )
        self.assertEqual(
            estadisticos["rango"],
            40.0,
        )
        self.assertEqual(
            estadisticos["iqr"],
            20.0,
        )

        self.assertAlmostEqual(
            estadisticos["desviacion_estandar"],
            15.811388300841896,
        )

    def test_excluye_valores_faltantes_y_no_numericos(self) -> None:
        """Excluye valores que no pueden convertirse a número."""
        datos = self.crear_datos(
            [10, 20, None, "30", "invalido"]
        )

        skill = DistribucionSkill()

        resultado = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        estadisticos = resultado["resultado"]

        self.assertEqual(
            estadisticos["n"],
            3,
        )
        self.assertEqual(
            estadisticos["min"],
            10.0,
        )
        self.assertEqual(
            estadisticos["mediana"],
            20.0,
        )
        self.assertEqual(
            estadisticos["max"],
            30.0,
        )

        self.assertEqual(
            len(resultado["advertencias"]),
            1,
        )

        self.assertIn(
            "excluyeron",
            resultado["advertencias"][0],
        )

    def test_metricas_inexistente_genera_error(self) -> None:
        """Una métrica inexistente debe generar ValueError."""
        datos = self.crear_datos(
            [10, 20, 30]
        )

        skill = DistribucionSkill()

        with self.assertRaises(ValueError):
            skill.ejecutar(
                datos,
                {"metrica": "beneficios"},
            )

    def test_parametro_metrica_obligatorio(self) -> None:
        """La ejecución exige el parámetro metrica."""
        datos = self.crear_datos(
            [10, 20, 30]
        )

        skill = DistribucionSkill()

        with self.assertRaises(ValueError):
            skill.ejecutar(
                datos,
                {},
            )

    def test_dataset_sin_valores_numericos(self) -> None:
        """Devuelve advertencia cuando no existen valores válidos."""
        datos = self.crear_datos(
            ["alto", "medio", "bajo"]
        )

        skill = DistribucionSkill()

        resultado = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        self.assertEqual(
            resultado["n"],
            0,
        )

        self.assertEqual(
            resultado["resultado"]["mediana"],
            None,
        )

        self.assertEqual(
            resultado["datos_visualizacion"],
            [],
        )

        self.assertGreaterEqual(
            len(resultado["advertencias"]),
            1,
        )

    def test_devuelve_datos_para_visualizacion(self) -> None:
        """Devuelve datos estructurados para una visualización."""
        datos = self.crear_datos(
            [10, 20, 30, 40, 50]
        )

        skill = DistribucionSkill()

        resultado = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        self.assertEqual(
            resultado["tipo_grafico"],
            "boxplot",
        )

        self.assertEqual(
            len(resultado["datos_visualizacion"]),
            1,
        )

        visual = resultado["datos_visualizacion"][0]

        self.assertEqual(
            visual["metrica"],
            "ventas",
        )
        self.assertEqual(
            visual["min"],
            10.0,
        )
        self.assertEqual(
            visual["q1"],
            20.0,
        )
        self.assertEqual(
            visual["mediana"],
            30.0,
        )
        self.assertEqual(
            visual["q3"],
            40.0,
        )
        self.assertEqual(
            visual["max"],
            50.0,
        )

    def test_genera_evidence(self) -> None:
        """Genera evidencia estructurada con trazabilidad."""
        datos = self.crear_datos(
            [10, 20, 30, 40, 50]
        )

        evidence_store = EvidenceStore()

        skill = DistribucionSkill(
            evidence_store=evidence_store
        )

        resultado = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        evidencia = resultado["evidencia"]

        self.assertEqual(
            len(evidencia),
            9,
        )

        self.assertEqual(
            evidence_store.cantidad(),
            9,
        )

        for registro in evidencia:
            self.assertEqual(
                registro["skill"],
                "distribucion",
            )

        registros_store = evidence_store.filtrar(
            skill="distribucion"
        )

        self.assertEqual(
            len(registros_store),
            9,
        )

    def test_resultado_es_determinista(self) -> None:
        """La misma entrada produce el mismo resultado."""
        datos = self.crear_datos(
            [10, 20, 30, 40, 50]
        )

        skill = DistribucionSkill()

        resultado_1 = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        resultado_2 = skill.ejecutar(
            datos,
            {"metrica": "ventas"},
        )

        self.assertEqual(
            resultado_1,
            resultado_2,
        )


if __name__ == "__main__":
    unittest.main()