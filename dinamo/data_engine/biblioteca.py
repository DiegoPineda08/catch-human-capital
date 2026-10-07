"""
BIBLIOTECA: todas las fuentes que el usuario ha cargado en esta sesión.

Un usuario puede cargar varios archivos a la vez (un Excel de rotación, un CSV de salarios y
un PDF con el informe anual). La Biblioteca:
  - lee cada archivo con la Ingesta (que devuelve tablas y fragmentos de texto);
  - crea un DataEngine (con su PerfilDataset) por cada tabla que tenga indicadores numéricos;
  - guarda los fragmentos de texto para el RAC;
  - permite agregar archivos en cualquier momento (por ejemplo, desde la interfaz).

El Brain usa la Biblioteca para elegir QUÉ tabla responde cada pregunta. Nunca toca las tablas.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dinamo.core.contracts import Documento, Fragmento, TablaExtraida
from dinamo.ingesta import leer_documento, leer_excel

from .cargador import configs_de_archivo
from .engine import DataEngine


class Biblioteca:
    def __init__(self, carpeta_perfiles: str | Path | None = None):
        self.carpeta_perfiles = carpeta_perfiles
        self.motores: dict[str, DataEngine] = {}          # nombre de la tabla -> su DataEngine
        self.fragmentos: list[Fragmento] = []             # textos de PDFs, .md y .txt
        self.documentos: list[str] = []                   # nombres de archivo cargados
        self.advertencias: list[str] = []

    # ------------------------------------------------------------------ cargar
    @classmethod
    def desde_archivos(cls, rutas, carpeta_perfiles: str | Path | None = None) -> "Biblioteca":
        bib = cls(carpeta_perfiles)
        for ruta in rutas:
            bib.agregar_archivo(ruta)
        return bib

    @classmethod
    def desde_motores(cls, *motores: DataEngine) -> "Biblioteca":
        """Biblioteca hecha con tablas ya cargadas en memoria (útil en tests y notebooks)."""
        bib = cls()
        for m in motores:
            bib.motores[m.perfil.nombre] = m
        return bib

    def agregar_archivo(self, ruta: str | Path) -> list[str]:
        """Lee un archivo y agrega sus tablas y textos. Devuelve los nombres de las tablas nuevas."""
        ruta = Path(ruta)
        configs = configs_de_archivo(self.carpeta_perfiles, ruta.name)
        hojas = sorted({c["hoja"] for c in configs if c.get("hoja")})
        # Si un perfil dice qué hoja usar, sólo se lee esa hoja (más rápido y sin tablas auxiliares)
        doc = leer_excel(ruta, hojas=hojas) if hojas and ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls") \
            else leer_documento(ruta)
        return self.agregar_documento(doc, configs)

    def agregar_documento(self, doc: Documento, configs: list[dict] | None = None) -> list[str]:
        configs = configs or []
        if doc.nombre in self.documentos:                 # volver a cargar = reemplazar la versión anterior
            self.quitar_documento(doc.nombre)
        self.documentos.append(doc.nombre)
        self.fragmentos += list(doc.fragmentos)
        self.advertencias += list(doc.advertencias)
        nuevas = []
        for t in doc.tablas:
            config = _config_para(t, configs)
            motor = DataEngine.desde_tabla(t.tabla, nombre=t.nombre, config=config, hoja=t.hoja)
            if not motor.perfil.tiene("metrica"):
                self.advertencias.append(f"Tabla '{t.nombre}' ({t.origen}) sin indicadores numéricos: no se analiza.")
                continue
            motor.origen, motor.documento = t.origen, doc.nombre
            nombre = motor.perfil.nombre
            if nombre in self.motores:                    # dos tablas con el mismo nombre: se distingue
                nombre = f"{nombre}_{len(self.motores) + 1}"
                motor.perfil = replace(motor.perfil, nombre=nombre)
            self.motores[nombre] = motor
            nuevas.append(nombre)
        return nuevas

    def quitar_documento(self, nombre_documento: str) -> None:
        self.motores = {k: m for k, m in self.motores.items() if getattr(m, "documento", None) != nombre_documento}
        self.fragmentos = [f for f in self.fragmentos if not f.fuente.startswith(nombre_documento + "#")
                           and f.fuente != nombre_documento]
        self.documentos = [d for d in self.documentos if d != nombre_documento]

    # ------------------------------------------------------------------ consultar
    def tablas(self) -> list[str]:
        return list(self.motores)

    def motor(self, nombre: str) -> DataEngine:
        if nombre not in self.motores:
            raise KeyError(f"No hay una tabla '{nombre}'. Tablas cargadas: {self.tablas()}")
        return self.motores[nombre]

    def resumen(self) -> list[dict]:
        """Lista simple (sin DataFrames) para mostrar qué se cargó."""
        return [{"tabla": n, "origen": m.origen, "filas": m.num_filas(),
                 "indicadores": len(m.perfil.por_rol("metrica")), "tiene_tiempo": m.perfil.tiene("tiempo")}
                for n, m in self.motores.items()]


def _config_para(t: TablaExtraida, configs: list[dict]) -> dict | None:
    """El perfil que corresponde a esta tabla (por hoja o por nombre de tabla), si existe."""
    for c in configs:
        if c.get("hoja") and c["hoja"] != t.hoja:
            continue
        if c.get("tabla") and c["tabla"] != t.nombre:
            continue
        return c
    return None
