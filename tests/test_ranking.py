"""Pruebas para la Skill ranking."""

import unittest

import pandas as pd

from dinamo.data_engine.engine import DataEngine
from dinamo.evidence.store import EvidenceStore
from dinamo.skills.ranking import RankingSkill


class TestRankingSkill(unittest.TestCase):
    """Pruebas de comportamiento de RankingSkill."""

    @staticmethod
    def crear_datos(
        entidades: list[str],
        periodos: list[int],
        valores: list[object],
    ) -> DataEngine:
        """Crea un DataEngine con datos sintéticos."""
        dataframe = pd.DataFrame(
            {
                "entidad": entidades,
                "periodo": periodos,
                "ventas": valores,
            }
        )

        return DataEngine(dataframe)

    def test_ordena_de_mayor_a_menor(self) -> None:
        """El ranking por defecto debe ser descendente."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
                "C", "C", "C",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
                20, 30, 40,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "tiempo": "periodo",
                "n": 3,
            },
        )

        entidades = [
            registro["entidad"]
            for registro in resultado["resultado"]
        ]

        valores = [
            registro["valor"]
            for registro in resultado["resultado"]
        ]

        self.assertEqual(
            entidades,
            ["B", "C", "A"],
        )

        self.assertEqual(
            valores,
            [50.0, 30.0, 20.0],
        )

    def test_ordena_de_menor_a_mayor(self) -> None:
        """El parámetro ascendente invierte el orden."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
                "C", "C", "C",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
                20, 30, 40,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "tiempo": "periodo",
                "n": 3,
                "ascendente": True,
            },
        )

        entidades = [
            registro["entidad"]
            for registro in resultado["resultado"]
        ]

        self.assertEqual(
            entidades,
            ["A", "C", "B"],
        )

    def test_respeta_n(self) -> None:
        """Solo devuelve como máximo n entidades."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
                "C", "C", "C",
                "D", "D", "D",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 10, 10,
                20, 20, 20,
                30, 30, 30,
                40, 40, 40,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "n": 2,
            },
        )

        self.assertEqual(
            len(resultado["resultado"]),
            2,
        )

        self.assertEqual(
            [
                registro["entidad"]
                for registro in resultado["resultado"]
            ],
            ["D", "C"],
        )

    def test_excluye_entidades_con_pocos_periodos(self) -> None:
        """Excluye entidades con menos de 3 observaciones por defecto."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
                "C",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
                100,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "tiempo": "periodo",
            },
        )

        entidades = [
            registro["entidad"]
            for registro in resultado["resultado"]
        ]

        self.assertEqual(
            entidades,
            ["B", "A"],
        )

        self.assertTrue(
            any(
                "menos de 3 observaciones"
                in advertencia
                for advertencia in resultado["advertencias"]
            )
        )

        self.assertNotIn(
            "C",
            entidades,
        )

    def test_min_periodos_personalizado(self) -> None:
        """Permite cambiar el mínimo de observaciones."""
        datos = self.crear_datos(
            entidades=[
                "A", "A",
                "B", "B", "B",
                "C", "C", "C", "C",
            ],
            periodos=[
                1, 2,
                1, 2, 3,
                1, 2, 3, 4,
            ],
            valores=[
                10, 20,
                20, 30, 40,
                30, 40, 50, 60,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "min_periodos": 4,
            },
        )

        entidades = [
            registro["entidad"]
            for registro in resultado["resultado"]
        ]

        self.assertEqual(
            entidades,
            ["C"],
        )

        self.assertTrue(
            any(
                "Se excluyeron 2 entidades"
                in advertencia
                for advertencia in resultado["advertencias"]
            )
        )

        self.assertTrue(
            any(
                "menos de 4 observaciones"
                in advertencia
                for advertencia in resultado["advertencias"]
            )
        )

    def test_desempate_determinista(self) -> None:
        """Los empates deben resolverse con una segunda clave fija."""
        datos = self.crear_datos(
            entidades=[
                "B", "B", "B",
                "A", "A", "A",
                "C", "C", "C",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                50, 50, 50,
                50, 50, 50,
                20, 20, 20,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "n": 2,
            },
        )

        entidades = [
            registro["entidad"]
            for registro in resultado["resultado"]
        ]

        self.assertEqual(
            entidades,
            ["A", "B"],
        )

    def test_excluye_metricas_no_numericas(self) -> None:
        """Las observaciones no numéricas generan advertencia."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, "20", "invalido",
                40, 50, 60,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
            },
        )

        self.assertEqual(
            resultado["resultado"],
            [
                {
                    "entidad": "B",
                    "valor": 50.0,
                    "periodos": 3,
                }
            ],
        )

        self.assertTrue(
            any(
                "métrica faltante o no numérica"
                in advertencia
                for advertencia in resultado["advertencias"]
            )
        )

    def test_metrica_inexistente_genera_error(self) -> None:
        """Una métrica inexistente debe generar ValueError."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
            ],
            periodos=[
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
            ],
        )

        skill = RankingSkill()

        with self.assertRaises(ValueError):
            skill.ejecutar(
                datos,
                {
                    "metrica": "beneficios",
                    "entidad": "entidad",
                },
            )

    def test_entidad_inexistente_genera_error(self) -> None:
        """Una entidad inexistente debe generar ValueError."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
            ],
            periodos=[
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
            ],
        )

        skill = RankingSkill()

        with self.assertRaises(ValueError):
            skill.ejecutar(
                datos,
                {
                    "metrica": "ventas",
                    "entidad": "empresa",
                },
            )

    def test_genera_evidence(self) -> None:
        """Genera Evidence para las entidades y la mediana."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
            ],
        )

        evidence_store = EvidenceStore()

        skill = RankingSkill(
            evidence_store=evidence_store
        )

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
                "n": 2,
            },
        )

        self.assertEqual(
            len(resultado["evidencia"]),
            3,
        )

        self.assertEqual(
            evidence_store.cantidad(),
            3,
        )

        registros = evidence_store.filtrar(
            skill="ranking"
        )

        self.assertEqual(
            len(registros),
            3,
        )

    def test_devuelve_datos_para_visualizacion(self) -> None:
        """Devuelve registros estructurados para el gráfico."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
            ],
        )

        skill = RankingSkill()

        resultado = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
            },
        )

        self.assertEqual(
            resultado["tipo_grafico"],
            "bar_horizontal",
        )

        self.assertEqual(
            len(resultado["datos_visualizacion"]),
            2,
        )

        self.assertEqual(
            resultado["datos_visualizacion"][0],
            {
                "entidad": "B",
                "valor": 50.0,
                "periodos": 3,
            },
        )

    def test_resultado_es_determinista(self) -> None:
        """La misma entrada produce el mismo resultado."""
        datos = self.crear_datos(
            entidades=[
                "A", "A", "A",
                "B", "B", "B",
                "C", "C", "C",
            ],
            periodos=[
                1, 2, 3,
                1, 2, 3,
                1, 2, 3,
            ],
            valores=[
                10, 20, 30,
                40, 50, 60,
                20, 30, 40,
            ],
        )

        skill = RankingSkill()

        resultado_1 = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
            },
        )

        resultado_2 = skill.ejecutar(
            datos,
            {
                "metrica": "ventas",
                "entidad": "entidad",
            },
        )

        self.assertEqual(
            resultado_1,
            resultado_2,
        )


if __name__ == "__main__":
    unittest.main()