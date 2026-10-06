"""Pruebas del almacenamiento de Evidence de DINAMO_ANALYTICS."""

from __future__ import annotations

import unittest

from dinamo.evidence.store import EvidenceStore, RegistroEvidencia


class TestEvidenceStore(unittest.TestCase):
    """Pruebas del almacenamiento estructurado de evidencia."""

    def setUp(self) -> None:
        """Crea un almacenamiento nuevo para cada prueba."""
        self.store = EvidenceStore()

    def _agregar_evidencia(
        self,
        *,
        skill: str = "ranking",
        metodo: str = "promedio_por_entidad",
        n: int = 10,
    ) -> RegistroEvidencia:
        """Agrega una evidencia de prueba."""
        return self.store.agregar(
            skill=skill,
            metodo=metodo,
            n=n,
            resultado={
                "entidad": "A",
                "valor": 95.5,
            },
            metadatos={
                "variable": "ventas",
            },
            advertencias=(),
        )

    def test_store_nuevo_esta_vacio(self) -> None:
        """Un EvidenceStore nuevo debe estar vacío."""
        self.assertTrue(self.store.esta_vacio())
        self.assertEqual(
            self.store.cantidad(),
            0,
        )
        self.assertEqual(
            self.store.todos(),
            (),
        )

    def test_agregar_evidencia(self) -> None:
        """Debe almacenar una evidencia correctamente."""
        evidencia = self._agregar_evidencia()

        self.assertEqual(
            evidencia.skill,
            "ranking",
        )
        self.assertEqual(
            evidencia.metodo,
            "promedio_por_entidad",
        )
        self.assertEqual(
            evidencia.n,
            10,
        )
        self.assertEqual(
            self.store.cantidad(),
            1,
        )
        self.assertFalse(
            self.store.esta_vacio()
        )

    def test_agregar_registro(self) -> None:
        """Debe permitir agregar un RegistroEvidencia existente."""
        registro = RegistroEvidencia(
            skill="relacion",
            metodo="spearman",
            n=20,
            resultado={
                "variable_1": "x",
                "variable_2": "y",
                "rho": 0.72,
            },
            metadatos={
                "unidad_analisis": "entidad",
            },
            advertencias=(),
        )

        agregado = self.store.agregar_registro(registro)

        self.assertEqual(
            agregado,
            registro,
        )
        self.assertEqual(
            self.store.cantidad(),
            1,
        )

    def test_filtrar_por_skill(self) -> None:
        """Debe filtrar correctamente por Skill."""
        self._agregar_evidencia(
            skill="ranking",
        )

        self._agregar_evidencia(
            skill="relacion",
            metodo="spearman",
            n=20,
        )

        resultados = self.store.filtrar(
            skill="ranking",
        )

        self.assertEqual(
            len(resultados),
            1,
        )
        self.assertEqual(
            resultados[0].skill,
            "ranking",
        )

    def test_filtrar_por_metodo(self) -> None:
        """Debe filtrar correctamente por método."""
        self._agregar_evidencia(
            skill="ranking",
            metodo="promedio_por_entidad",
        )

        self._agregar_evidencia(
            skill="ranking",
            metodo="mediana_por_entidad",
        )

        resultados = self.store.filtrar(
            metodo="mediana_por_entidad",
        )

        self.assertEqual(
            len(resultados),
            1,
        )
        self.assertEqual(
            resultados[0].metodo,
            "mediana_por_entidad",
        )

    def test_filtrar_por_skill_y_metodo(self) -> None:
        """Debe permitir filtrar simultáneamente por Skill y método."""
        self._agregar_evidencia(
            skill="ranking",
            metodo="promedio_por_entidad",
        )

        self._agregar_evidencia(
            skill="ranking",
            metodo="mediana_por_entidad",
        )

        self._agregar_evidencia(
            skill="relacion",
            metodo="promedio_por_entidad",
        )

        resultados = self.store.filtrar(
            skill="ranking",
            metodo="promedio_por_entidad",
        )

        self.assertEqual(
            len(resultados),
            1,
        )
        self.assertEqual(
            resultados[0].skill,
            "ranking",
        )
        self.assertEqual(
            resultados[0].metodo,
            "promedio_por_entidad",
        )

    def test_filtro_sin_coincidencias(self) -> None:
        """Un filtro sin coincidencias debe devolver una tupla vacía."""
        self._agregar_evidencia()

        resultados = self.store.filtrar(
            skill="distribucion",
        )

        self.assertEqual(
            resultados,
            (),
        )

    def test_todos_conserva_orden_de_insercion(self) -> None:
        """Las evidencias deben recuperarse en orden de inserción."""
        primera = self._agregar_evidencia(
            skill="ranking",
        )

        segunda = self._agregar_evidencia(
            skill="relacion",
            metodo="spearman",
            n=20,
        )

        resultados = self.store.todos()

        self.assertEqual(
            len(resultados),
            2,
        )
        self.assertEqual(
            resultados[0],
            primera,
        )
        self.assertEqual(
            resultados[1],
            segunda,
        )

    def test_resultado_recuperado_es_independiente(self) -> None:
        """Modificar un resultado recuperado no debe afectar el almacenado."""
        self._agregar_evidencia()

        recuperada = self.store.todos()[0]

        recuperada.resultado["valor"] = 9999

        almacenada = self.store.todos()[0]

        self.assertEqual(
            almacenada.resultado["valor"],
            95.5,
        )

    def test_metadatos_recuperados_son_independientes(self) -> None:
        """Modificar metadatos recuperados no debe afectar el almacenado."""
        self._agregar_evidencia()

        recuperada = self.store.todos()[0]

        recuperada.metadatos["variable"] = "edad"

        almacenada = self.store.todos()[0]

        self.assertEqual(
            almacenada.metadatos["variable"],
            "ventas",
        )

    def test_advertencias_se_conservan(self) -> None:
        """Las advertencias deben formar parte de la evidencia."""
        self.store.agregar(
            skill="comparar_grupos",
            metodo="diferencia_de_medias",
            n=18,
            resultado={
                "diferencia": 4.2,
            },
            metadatos={
                "grupo_1": "A",
                "grupo_2": "B",
            },
            advertencias=(
                "Un grupo tiene menos de 10 observaciones.",
            ),
        )

        evidencia = self.store.todos()[0]

        self.assertEqual(
            evidencia.advertencias,
            (
                "Un grupo tiene menos de 10 observaciones.",
            ),
        )

    def test_limpiar_elimina_toda_la_evidencia(self) -> None:
        """Limpiar debe dejar el almacenamiento vacío."""
        self._agregar_evidencia()

        self.assertEqual(
            self.store.cantidad(),
            1,
        )

        self.store.limpiar()

        self.assertEqual(
            self.store.cantidad(),
            0,
        )
        self.assertTrue(
            self.store.esta_vacio()
        )
        self.assertEqual(
            self.store.todos(),
            (),
        )

    def test_rechaza_skill_vacia(self) -> None:
        """Debe rechazar una Skill vacía."""
        with self.assertRaises(ValueError):
            self.store.agregar(
                skill="",
                metodo="spearman",
                n=10,
                resultado={},
            )

    def test_rechaza_metodo_vacio(self) -> None:
        """Debe rechazar un método vacío."""
        with self.assertRaises(ValueError):
            self.store.agregar(
                skill="relacion",
                metodo="",
                n=10,
                resultado={},
            )

    def test_rechaza_n_negativo(self) -> None:
        """No debe aceptar tamaños de muestra negativos."""
        with self.assertRaises(ValueError):
            self.store.agregar(
                skill="ranking",
                metodo="promedio",
                n=-1,
                resultado={},
            )

    def test_rechaza_n_no_entero(self) -> None:
        """Debe rechazar tamaños de muestra que no sean enteros."""
        with self.assertRaises(TypeError):
            self.store.agregar(
                skill="ranking",
                metodo="promedio",
                n=10.5,
                resultado={},
            )

    def test_rechaza_resultado_no_mapping(self) -> None:
        """El resultado debe ser un Mapping."""
        with self.assertRaises(TypeError):
            self.store.agregar(
                skill="ranking",
                metodo="promedio",
                n=10,
                resultado=["incorrecto"],
            )

    def test_rechaza_registro_invalido(self) -> None:
        """agregar_registro debe validar el tipo recibido."""
        with self.assertRaises(TypeError):
            self.store.agregar_registro(
                "no es un registro",
            )


if __name__ == "__main__":
    unittest.main()