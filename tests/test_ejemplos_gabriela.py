
import re
import pytest


def validar_respuesta(respuesta):
    """Valida que una respuesta tenga texto y al menos una cita [E:...]."""
    assert isinstance(respuesta, str), "La respuesta debe ser texto."
    assert respuesta.strip(), "La respuesta no puede estar vacía."
    assert re.search(r"\[E:[^\]]+\]", respuesta), (
        "La respuesta debe contener al menos una cita con formato [E:...]."
    )


@pytest.mark.parametrize(
    "caso",
    [
        "tendencia_rotacion",
        "comparacion_tier",
        "documento_pdf_word",
    ],
)
def test_validacion_respuesta_demo(caso):
    """
    Comprueba los requisitos mínimos de las respuestas de demostración.
    Esta prueba valida el formato, no ejecuta todavía la IA.
    """
    respuesta_ejemplo = (
        f"Resultado provisional para {caso}. "
        "[E:ejemplo-001]"
    )

    validar_respuesta(respuesta_ejemplo)


def test_rechaza_respuesta_vacia():
    with pytest.raises(AssertionError):
        validar_respuesta("")


def test_rechaza_respuesta_sin_citas():
    with pytest.raises(AssertionError):
        validar_respuesta("La rotación aumentó durante el periodo.")
