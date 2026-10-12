
"""
Demo inicial de DINAMO.

Prepara los tres casos que se conectarán a la lógica real:
1. Tendencia de rotación.
2. Comparación entre Tier 1 y Tier 2.
3. Consulta basada en un documento PDF o Word.
"""

CASOS_DEMO = [
    {
        "nombre": "Tendencia",
        "pregunta": "¿Cómo ha evolucionado la rotación entre los periodos?",
        "objetivo": "Identificar la evolución de la tasa de rotación.",
        "skill_esperado": "tasa_rotacion_bimestral",
    },
    {
        "nombre": "Comparación",
        "pregunta": "Compara la rotación de las empresas Tier 1 y Tier 2.",
        "objetivo": "Comparar la tasa de rotación entre ambos grupos.",
        "skill_esperado": "comparar",
    },
    {
        "nombre": "Documento",
        "pregunta": "¿Qué conclusiones relevantes aparecen en el documento?",
        "objetivo": "Responder con evidencia extraída de un PDF o Word.",
        "skill_esperado": "consulta_documental",
    },
]


def mostrar_casos():
    """Muestra las preguntas preparadas para la demostración."""
    print("=" * 60)
    print("DINAMO — CASOS PREPARADOS PARA LA DEMOSTRACIÓN")
    print("=" * 60)

    for numero, caso in enumerate(CASOS_DEMO, start=1):
        print(f"\nCASO {numero}: {caso['nombre']}")
        print(f"Pregunta: {caso['pregunta']}")
        print(f"Objetivo: {caso['objetivo']}")
        print(f"Skill esperado: {caso['skill_esperado']}")

    print("\nNota: estos casos están preparados, pero aún no ejecutan")
    print("consultas reales ni generan resultados de la empresa.")


if __name__ == "__main__":
    mostrar_casos()
