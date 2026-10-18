"""Conversaciones aisladas, persistencia y 'subir un archivo no dispara análisis'. Datos sintéticos."""
from pathlib import Path

import pytest

from dinamo.conversacion import Gestor, es_fiel, nombre_seguro, resumir

CSV_A = b"empleado_id,area,salario,renuncio\n" + b"\n".join(
    f"{i},{'Ventas' if i % 2 else 'TI'},{10000 + i * 137},{i % 3 == 0:d}".encode() for i in range(1, 41))
CSV_B = b"tienda,mes,ventas\n" + b"\n".join(f"T{i % 4},{1 + i // 4},{100 + i * 7}".encode() for i in range(24))


@pytest.fixture
def gestor(tmp_path):
    return Gestor(tmp_path)


def test_chats_aislados(gestor):
    a, b = gestor.crear(), gestor.crear()
    a.agregar_archivo("empleados.csv", CSV_A)
    b.agregar_archivo("ventas.csv", CSV_B)
    assert list(a.brain.biblioteca.motores) != list(b.brain.biblioteca.motores)
    assert all(getattr(m, "documento", "") == "empleados.csv" for m in a.brain.biblioteca.motores.values())
    a.recordar("La empresa tiene 300 empleados")
    assert b.memoria == [] and a.brain is not b.brain and a.brain.evidencias is not b.brain.evidencias


def test_subir_no_analiza_ni_llama_al_llm(gestor, monkeypatch):
    llamado = []
    monkeypatch.setattr("dinamo.llm.client.LLMFalso.generar", lambda *a, **k: llamado.append(1) or "")
    e = gestor.crear()
    ficha = e.agregar_archivo("empleados.csv", CSV_A)
    assert ficha["tablas"][0]["filas"] == 40
    assert llamado == [] and e.mensajes == [] and e.brain.evidencias.todas() == []


def test_persistencia_y_recarga(gestor, tmp_path):
    e = gestor.crear()
    e.agregar_archivo("empleados.csv", CSV_A)
    e.agregar_mensaje("usuario", "¿Cuántos renunciaron?")
    e.recordar("País de referencia: Colombia")
    otro = Gestor(tmp_path).obtener(e.id)
    assert otro.titulo == "¿Cuántos renunciaron?"
    assert otro.memoria[0]["hecho"] == "País de referencia: Colombia"
    assert list(otro.brain.biblioteca.motores)            # vuelve a leer el archivo guardado
    assert [c["id"] for c in Gestor(tmp_path).listar()] == [e.id]


def test_quitar_archivo_y_borrar(gestor):
    e = gestor.crear()
    e.agregar_archivo("ventas.csv", CSV_B)
    e.quitar_archivo("ventas.csv")
    assert e.brain.biblioteca.motores == {} and e.archivos == []
    gestor.borrar(e.id)
    with pytest.raises(KeyError):
        gestor.obtener(e.id)


def test_nombres_e_ids_peligrosos(gestor):
    assert nombre_seguro("../../etc/passwd.csv") == "passwd.csv"
    assert nombre_seguro("..\\..\\x.csv") == "x.csv"
    with pytest.raises(KeyError):
        gestor.obtener("../../etc")
    e = gestor.crear()
    with pytest.raises(ValueError, match="no admitido"):
        e.agregar_archivo("malo.exe", b"MZ")
    with pytest.raises(ValueError, match="vacío"):
        e.agregar_archivo("v.csv", b"")


def test_resumen_conserva_cifras_y_verifica_llm():
    mensajes = [{"rol": "usuario", "texto": "¿Cuál es la rotación?"},
                {"rol": "asistente", "texto": "La rotación fue 7.2% [E:ranking:abcd1234]. Saludos."}]
    texto, metodo = resumir(mensajes)
    assert "7.2%" in texto and "[E:ranking:abcd1234]" in texto and metodo == "determinístico"

    class LLMInventa:
        def generar(self, s, u):
            return "La rotación fue 9.9%."
    texto, metodo = resumir(mensajes, llm=LLMInventa())
    assert metodo == "determinístico" and "9.9" not in texto
    assert es_fiel("rotación 7.2% [E:ranking:abcd1234]", "x 7.2 [E:ranking:abcd1234]")
