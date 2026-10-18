"""
ESPACIO DE CONVERSACIÓN: cada chat tiene su propio mundo, aislado de los demás.

Un Espacio tiene SU biblioteca de archivos, SU RAC, SU registro de evidencias, SU estado de sesión
y SU memoria. Nada de lo que se sube o se dice en un chat aparece en otro.

Subir un archivo sólo lo guarda y lo deja listo (se leen sus columnas y su texto). NO se genera
ningún resumen, gráfico, llamada al LLM ni investigación: eso ocurre sólo cuando el usuario pregunta.

Persistencia: .dinamo_datos/conversaciones/<id>/ (carpeta ignorada por git), con
  conversacion.json   mensajes, memoria, investigaciones, resúmenes de contexto, registro de limpieza
  archivos/           copia de los archivos subidos (los originales del usuario nunca se modifican)
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dinamo.core.config import Config
from dinamo.data_engine import Biblioteca
from dinamo.ingesta import EXTENSIONES
from dinamo.llm import LLMFalso

MAX_ARCHIVO = 25 * 1024 * 1024
MENSAJES_RECIENTES = 8           # los últimos N mensajes van completos al LLM; los anteriores, resumidos
UMBRAL_RESUMEN = 14


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nombre_seguro(nombre: str) -> str:
    """Quita rutas y caracteres peligrosos: '../../x.csv' -> 'x.csv'."""
    base = Path(str(nombre).replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑüÜ]", "_", base).strip(" .")
    return base[:120] or "archivo"


def id_valido(cid: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{12}", cid or ""))


@dataclass
class Espacio:
    id: str
    carpeta: Path
    titulo: str = "Nueva conversación"
    creada: str = field(default_factory=ahora)
    actualizada: str = field(default_factory=ahora)
    mensajes: list[dict] = field(default_factory=list)
    memoria: list[dict] = field(default_factory=list)          # hechos que el usuario pidió recordar
    preferencias: dict = field(default_factory=dict)          # p.ej. {"pais_referencia": "COL"}
    investigaciones: list[dict] = field(default_factory=list)
    resumen: str = ""                                          # resumen de los mensajes antiguos
    resumen_hasta: int = 0                                     # cuántos mensajes cubre el resumen
    limpieza: list[dict] = field(default_factory=list)         # registro de cambios de limpieza
    archivos: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.candado = threading.RLock()
        self._brain = None

    # ------------------------------------------------------------------ sistema analítico propio
    @property
    def brain(self):
        """Brain propio del chat (con LLM falso: el Brain sólo calcula; el orquestador redacta)."""
        if self._brain is None:
            from dinamo.sistema import construir_sistema
            config = Config(archivos=())
            self._brain = construir_sistema(config, archivos=[], llm=LLMFalso(),
                                            biblioteca=Biblioteca(config.carpeta_perfiles))
            for a in self.archivos:
                ruta = self.carpeta_archivos / a["nombre"]
                if ruta.exists():
                    try:
                        self._brain.cargar_archivo(ruta)
                    except Exception as exc:          # archivo dañado: se informa, no se cae el chat
                        a["error"] = f"No se pudo volver a leer: {type(exc).__name__}"
        return self._brain

    @property
    def carpeta_archivos(self) -> Path:
        return self.carpeta / "archivos"

    # ------------------------------------------------------------------ archivos
    def agregar_archivo(self, nombre: str, contenido: bytes) -> dict:
        nombre = nombre_seguro(nombre)
        ext = Path(nombre).suffix.lower()
        if ext not in EXTENSIONES:
            raise ValueError(f"Tipo de archivo no admitido ({ext}). Admitidos: {', '.join(sorted(EXTENSIONES))}")
        if len(contenido) > MAX_ARCHIVO:
            raise ValueError(f"El archivo supera el máximo de {MAX_ARCHIVO // (1024 * 1024)} MB.")
        if not contenido:
            raise ValueError("El archivo está vacío.")
        with self.candado:
            self.carpeta_archivos.mkdir(parents=True, exist_ok=True)
            ruta = self.carpeta_archivos / nombre
            ruta.write_bytes(contenido)
            brain = self.brain
            try:
                brain.cargar_archivo(ruta)
            except Exception as exc:
                ruta.unlink(missing_ok=True)
                raise ValueError(f"No pude leer el archivo: {exc}") from exc
            tablas = [t for t, m in brain.biblioteca.motores.items() if getattr(m, "documento", None) == nombre]
            ficha = self._ficha(nombre, len(contenido), tablas)
            self.archivos = [a for a in self.archivos if a["nombre"] != nombre] + [ficha]
            self.guardar()
            return ficha

    def _ficha(self, nombre: str, tamano: int, tablas: list[str]) -> dict:
        bib = self.brain.biblioteca
        frag = [f for f in bib.fragmentos if f.fuente == nombre or f.fuente.startswith(nombre + "#")]
        return {"nombre": nombre, "tamano": tamano, "subido": ahora(),
                "tablas": [{"tabla": t, "filas": bib.motor(t).num_filas(),
                            "columnas": len(bib.motor(t).perfil.columnas)} for t in tablas],
                "fragmentos_texto": len(frag)}

    def quitar_archivo(self, nombre: str) -> None:
        nombre = nombre_seguro(nombre)
        with self.candado:
            if not any(a["nombre"] == nombre for a in self.archivos):
                raise KeyError(nombre)
            self.brain.biblioteca.quitar_documento(nombre)
            self.brain._preparar()
            (self.carpeta_archivos / nombre).unlink(missing_ok=True)
            self.archivos = [a for a in self.archivos if a["nombre"] != nombre]
            self.guardar()

    def vista_previa(self, tabla: str, filas: int = 20) -> dict:
        motor = self.brain.biblioteca.motor(tabla)
        df = motor.filas(solo_validas=False).head(max(1, min(filas, 200)))
        return {"tabla": tabla, "total_filas": motor.num_filas(),
                "columnas": [{"nombre": c.nombre, "rol": c.rol, "unidad": c.unidad} for c in motor.perfil.columnas],
                "filas": json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))}

    # ------------------------------------------------------------------ limpieza con aprobación
    def proponer_limpieza(self, nombre: str) -> dict:
        from dinamo.limpieza import diagnosticar, leer_crudo
        nombre = nombre_seguro(nombre)
        ruta = self.carpeta_archivos / nombre
        if not ruta.exists():
            raise KeyError(nombre)
        df = leer_crudo(ruta)
        problemas = diagnosticar(df)
        self._pendientes = getattr(self, "_pendientes", {})
        self._pendientes[nombre] = (df, problemas)
        return {"archivo": nombre, "filas": int(len(df)), "columnas": int(df.shape[1]),
                "problemas": [p.a_dict() for p in problemas]}

    def aplicar_limpieza(self, nombre: str, aprobadas: dict[str, str]) -> dict:
        from dinamo.limpieza import aplicar, comparar, script_python
        nombre = nombre_seguro(nombre)
        if nombre not in getattr(self, "_pendientes", {}):
            self.proponer_limpieza(nombre)
        df, problemas = self._pendientes[nombre]
        if not aprobadas:
            raise ValueError("No aprobaste ningún cambio: el archivo queda como está.")
        limpio, registro = aplicar(df, problemas, aprobadas)
        version = 1 + sum(1 for r in self.limpieza if r["origen"] == nombre)
        salida = f"{Path(nombre).stem}_limpio_v{version}.csv"
        ficha = self.agregar_archivo(salida, limpio.to_csv(index=False).encode("utf-8"))
        script = script_python(nombre, registro)
        (self.carpeta / "scripts").mkdir(exist_ok=True)
        (self.carpeta / "scripts" / f"{Path(salida).stem}.py").write_text(script, encoding="utf-8")
        entrada = {"fecha": ahora(), "origen": nombre, "resultado": salida, "registro": registro,
                   "comparacion": comparar(df, limpio), "script": f"{Path(salida).stem}.py"}
        with self.candado:
            self.limpieza.append(entrada)
            self._pendientes.pop(nombre, None)
            self.guardar()
        return {**entrada, "archivo": ficha, "script_texto": script}

    # ------------------------------------------------------------------ mensajes y memoria
    def agregar_mensaje(self, rol: str, texto: str, **extra) -> dict:
        with self.candado:
            m = {"id": uuid.uuid4().hex[:10], "rol": rol, "texto": texto, "fecha": ahora(), **extra}
            self.mensajes.append(m)
            if rol == "usuario" and self.titulo == "Nueva conversación":
                self.titulo = (texto.strip().split("\n")[0][:60] or self.titulo)
            self.actualizada = ahora()
            self.guardar()
            return m

    def recordar(self, hecho: str) -> dict:
        with self.candado:
            item = {"id": uuid.uuid4().hex[:8], "hecho": hecho.strip()[:500], "fecha": ahora()}
            self.memoria.append(item)
            self.guardar()
            return item

    def olvidar(self, mid: str) -> None:
        with self.candado:
            self.memoria = [m for m in self.memoria if m["id"] != mid]
            self.guardar()

    def historial_para_llm(self) -> tuple[str, list[dict]]:
        """(resumen de lo antiguo, últimos mensajes completos)."""
        recientes = [m for m in self.mensajes[self.resumen_hasta:] if m["rol"] in ("usuario", "asistente")]
        return self.resumen, recientes[-MENSAJES_RECIENTES:]

    def necesita_resumen(self) -> bool:
        return len(self.mensajes) - self.resumen_hasta > UMBRAL_RESUMEN

    def guardar_investigacion(self, inv: dict) -> dict:
        with self.candado:
            inv = {"id": uuid.uuid4().hex[:8], "guardada": False, **inv}
            self.investigaciones.append(inv)
            self.investigaciones = self.investigaciones[-50:]
            self.guardar()
            return inv

    # ------------------------------------------------------------------ persistencia
    def a_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "titulo", "creada", "actualizada", "mensajes", "memoria",
                                              "preferencias", "investigaciones", "resumen", "resumen_hasta",
                                              "limpieza", "archivos")}

    def guardar(self) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        tmp = self.carpeta / "conversacion.json.tmp"
        tmp.write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.carpeta / "conversacion.json")

    @classmethod
    def cargar(cls, carpeta: Path) -> "Espacio":
        d = json.loads((carpeta / "conversacion.json").read_text(encoding="utf-8"))
        campos = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "carpeta"}
        return cls(carpeta=carpeta, **campos)

    def ficha(self) -> dict:
        return {"id": self.id, "titulo": self.titulo, "creada": self.creada, "actualizada": self.actualizada,
                "mensajes": len(self.mensajes), "archivos": len(self.archivos)}


class Gestor:
    """Crea, lista y recupera conversaciones. Cada una vive en su propia carpeta."""

    def __init__(self, carpeta: str | Path):
        self.carpeta = Path(carpeta) / "conversaciones"
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._abiertas: dict[str, Espacio] = {}
        self._candado = threading.Lock()

    def crear(self, titulo: str | None = None) -> Espacio:
        cid = uuid.uuid4().hex[:12]
        e = Espacio(id=cid, carpeta=self.carpeta / cid, titulo=(titulo or "Nueva conversación")[:80])
        e.guardar()
        with self._candado:
            self._abiertas[cid] = e
        return e

    def obtener(self, cid: str) -> Espacio:
        if not id_valido(cid):
            raise KeyError(cid)
        with self._candado:
            if cid not in self._abiertas:
                carpeta = self.carpeta / cid
                if not (carpeta / "conversacion.json").exists():
                    raise KeyError(cid)
                self._abiertas[cid] = Espacio.cargar(carpeta)
            return self._abiertas[cid]

    def listar(self) -> list[dict]:
        fichas = []
        for c in self.carpeta.iterdir():
            if c.is_dir() and id_valido(c.name) and (c / "conversacion.json").exists():
                try:
                    fichas.append(self.obtener(c.name).ficha())
                except (ValueError, KeyError, OSError):
                    continue
        return sorted(fichas, key=lambda f: f["actualizada"], reverse=True)

    def borrar(self, cid: str) -> None:
        if not id_valido(cid):
            raise KeyError(cid)
        with self._candado:
            self._abiertas.pop(cid, None)
        carpeta = self.carpeta / cid
        if carpeta.exists():
            shutil.rmtree(carpeta)
