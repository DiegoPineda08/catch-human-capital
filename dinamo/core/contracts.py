"""
CONTRATOS de DINAMO_ANALITICS.

Este archivo es la "ley" entre módulos: cada componente RECIBE y DEVUELVE sólo estos tipos.
Si dos personas respetan el contrato, pueden trabajar en paralelo sin pisarse.

Reglas:
- Sólo UN contrato contiene DataFrames de pandas: `TablaExtraida`, que viaja de la Ingesta al
  Data Engine y nunca llega al Brain (el Brain no manipula DataFrames). En el resto, las tablas
  viajan como `tuple[dict]` (registros), que se pueden convertir a JSON.
- Ningún contrato menciona columnas de una base concreta: cada tabla se describe con un
  `PerfilDataset`, que se construye al cargar CUALQUIER archivo (Excel, CSV o PDF).
- Cambiar un contrato requiere acuerdo del equipo (ver README, "Cambios de contrato").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:                                # sólo para anotar tipos; no importa pandas al cargar
    import pandas as pd

# ---------------------------------------------------------------------------------------
# 0. Lo que sale de la Ingesta: un archivo convertido en tablas y fragmentos de texto
# ---------------------------------------------------------------------------------------
TIPOS_DOCUMENTO = ("excel", "csv", "pdf", "texto")


@dataclass(frozen=True)
class Fragmento:
    """Un pedazo de texto de un documento (un párrafo de un PDF, una sección de un .md)."""
    fuente: str                                 # dónde está: "informe.pdf#p2" (página 2)
    texto: str


@dataclass(frozen=True)
class TablaExtraida:
    """Una tabla encontrada en un archivo: una hoja de Excel, un CSV o una tabla dentro de un PDF.

    Es el ÚNICO contrato con un DataFrame: va de la Ingesta al Data Engine y no sale de ahí."""
    nombre: str                                 # identificador único: "ventas_tiendas", "informe_p2_t1"
    origen: str                                 # de dónde salió, para citarlo: "informe.pdf, página 2"
    tabla: "pd.DataFrame" = field(repr=False, compare=False)
    hoja: str | None = None                     # hoja del Excel, si aplica


@dataclass(frozen=True)
class Documento:
    """Un archivo ya leído. Lo produce la Ingesta; lo consumen el Data Engine (tablas) y el RAC (textos)."""
    nombre: str                                 # nombre del archivo: "informe_clima.pdf"
    tipo: str                                   # uno de TIPOS_DOCUMENTO
    tablas: tuple[TablaExtraida, ...] = ()
    fragmentos: tuple[Fragmento, ...] = ()
    advertencias: tuple[str, ...] = ()          # p.ej. "El PDF parece escaneado: no tiene texto"


# ---------------------------------------------------------------------------------------
# 1. Descripción de la base de datos (el "Perfil")
# ---------------------------------------------------------------------------------------
ROLES = (
    "entidad",          # identificador de lo que se analiza: empresa, tienda, empleado...
    "nombre_entidad",   # nombre legible de la entidad (opcional)
    "tiempo",           # columna ordenable que marca el periodo: fecha, mes, bimestre...
    "etiqueta_tiempo",  # texto legible del periodo, p.ej. "Julio - Agosto 2024" (opcional)
    "metrica",          # número que tiene sentido promediar o comparar: ventas, rotación...
    "dimension",        # categoría para agrupar: región, tier, área...
    "binaria",          # sí/no codificado como 1/0
    "validez",          # 1 = la fila es dato real, 0 = imputada o no reportada (opcional)
    "texto",            # texto libre
    "ignorar",          # columnas técnicas que no se analizan
)

UNIDADES = ("proporcion", "moneda", "numero", "conteo", "dias", "escala", "texto")
AGREGACIONES = ("mediana", "promedio", "suma")


@dataclass(frozen=True)
class Columna:
    """Qué significa una columna de la tabla. Lo produce el Perfilador (o un JSON editado a mano)."""
    nombre: str                                 # nombre exacto en la tabla
    rol: str                                    # uno de ROLES
    etiqueta: str = ""                          # cómo se nombra al usuario: "tasa de rotación"
    descripcion: str = ""
    unidad: str = "numero"                      # una de UNIDADES
    agregacion: str = "mediana"                 # cómo resumir varias entidades (AGREGACIONES)
    sinonimos: tuple[str, ...] = ()             # palabras con las que el usuario la nombra
    valores: tuple[str, ...] = ()               # categorías posibles (dimensiones con pocas)
    mayor_es_mejor: bool | None = None          # True: ventas; False: rotación; None: no se sabe
    describe_a: tuple[str, ...] = ()            # columnas de las que ésta es una parte o un desglose
                                                # (p.ej. "% de bajas por abandono" describe a "rotación"):
                                                # no se presenta como un factor que las explique

    def __post_init__(self):
        if self.rol not in ROLES:
            raise ValueError(f"Rol inválido '{self.rol}' en la columna '{self.nombre}'. Usa uno de {ROLES}")
        if self.unidad not in UNIDADES:
            raise ValueError(f"Unidad inválida '{self.unidad}' en '{self.nombre}'. Usa una de {UNIDADES}")
        if self.agregacion not in AGREGACIONES:
            raise ValueError(f"Agregación inválida '{self.agregacion}' en '{self.nombre}'")

    @property
    def nombre_visible(self) -> str:
        return self.etiqueta or self.nombre.replace("_", " ")


@dataclass(frozen=True)
class PerfilDataset:
    """Descripción completa de una base: con esto el sistema sabe qué preguntar y cómo responder."""
    nombre: str                                 # identificador corto: "catch_capital_humano"
    descripcion: str
    columnas: tuple[Columna, ...]
    entidad_singular: str = "registro"          # "empresa", "tienda", "empleado"
    entidad_plural: str = "registros"
    filas: int = 0
    hoja: str | None = None                     # hoja del Excel de donde se leyó

    # ---- consultas cómodas (no tocan datos, sólo la descripción) ----
    def por_rol(self, rol: str) -> tuple[Columna, ...]:
        return tuple(c for c in self.columnas if c.rol == rol)

    def una(self, rol: str) -> Columna | None:
        cols = self.por_rol(rol)
        return cols[0] if cols else None

    def columna(self, nombre: str) -> Columna:
        for c in self.columnas:
            if c.nombre == nombre:
                return c
        raise KeyError(f"La columna '{nombre}' no está en el perfil '{self.nombre}'")

    def tiene(self, rol: str) -> bool:
        return bool(self.por_rol(rol))

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict[str, Any]) -> "PerfilDataset":
        cols = tuple(Columna(**{**c, "sinonimos": tuple(c.get("sinonimos", ())),
                                "valores": tuple(c.get("valores", ())),
                                "describe_a": tuple(c.get("describe_a", ()))}) for c in d["columnas"])
        return cls(**{**d, "columnas": cols})

    def con_columna(self, nueva: Columna) -> "PerfilDataset":
        """Devuelve un perfil igual pero con una columna reemplazada (los perfiles no se modifican)."""
        return replace(self, columnas=tuple(nueva if c.nombre == nueva.nombre else c for c in self.columnas))


# ---------------------------------------------------------------------------------------
# 2. Flujo de una pregunta
# ---------------------------------------------------------------------------------------
INTENCIONES = (
    "consultar_documentos",  # ¿qué dice el informe sobre...? (se responde con texto, no con cálculos)
    "describir_datos",   # ¿qué datos tienes? ¿qué puedo preguntar?
    "tendencia",         # ¿cómo evolucionó X en el tiempo?
    "ranking",           # ¿qué entidades tienen mayor/menor X?
    "comparar_grupos",   # ¿cómo se compara X entre grupos de una dimensión?
    "relaciones",        # ¿qué se relaciona con X?
    "perfil_entidad",    # cuéntame de la entidad 12
    "desconocida",
)


@dataclass(frozen=True)
class Pregunta:
    texto: str


@dataclass(frozen=True)
class Plan:
    """Salida del Brain al interpretar una pregunta. Sólo nombres de columnas, nunca datos."""
    intencion: str                              # una de INTENCIONES
    metricas: tuple[str, ...] = ()              # columnas con rol "metrica"
    dimension: str | None = None                # columna con rol "dimension" o "binaria"
    filtros: dict[str, Any] = field(default_factory=dict)   # {"columna": valor}
    skills: tuple[str, ...] = ()
    confianza: float = 0.0
    orden: str = "desc"                         # "desc" = mayores primero; "asc" = menores primero
    tabla: str | None = None                    # qué tabla (fuente) responde; la elige el Brain
    supuestos: tuple[str, ...] = ()             # lo que el Intérprete tuvo que suponer, p.ej. ("metrica",)

    @property
    def metrica(self) -> str | None:
        return self.metricas[0] if self.metricas else None


TIPOS_CONTEXTO = ("conocimiento", "perfil", "documento")


@dataclass(frozen=True)
class Contexto:
    fuente: str                                 # p.ej. "perfil#ventas" o "informe.pdf#p2"
    texto: str
    puntaje: float
    tipo: str = "conocimiento"                  # uno de TIPOS_CONTEXTO


@dataclass(frozen=True)
class Aclaracion:
    """Cuando la pregunta es ambigua, DINAMO pregunta antes de calcular (conversación interactiva)."""
    pregunta: str                               # "¿Sobre qué indicador quieres saber?"
    opciones: tuple[str, ...]                   # cada opción es una pregunta completa que sí se entiende


@dataclass
class PerfilUsuario:
    """Quién está preguntando. Cambia el tono de la respuesta, nunca los números."""
    nombre: str = ""
    rol: str = ""                               # "Gerente de RR. HH.", "Analista de datos"...
    nivel: str = "general"                      # "directivo" | "analista" | "general"
    intereses: tuple[str, ...] = ()             # temas que le importan: ("rotación", "salarios")

    def describir(self) -> str:
        if not (self.nombre or self.rol):
            return "(sin datos del usuario)"
        quien = ", ".join(x for x in (self.nombre, self.rol) if x)
        guia = {"directivo": "prioriza la conclusión y qué hacer; evita detalles de método",
                "analista": "incluye el método, el tamaño de muestra y las advertencias",
                }.get(self.nivel, "explica con palabras sencillas")
        extra = f" Le interesa: {', '.join(self.intereses)}." if self.intereses else ""
        return f"{quien}. Nivel: {self.nivel} ({guia}).{extra}"


@dataclass(frozen=True)
class Evidencia:
    """Un resultado calculado por código determinístico (nunca por el LLM)."""
    id: str                                     # mismo cálculo => mismo id
    skill: str
    descripcion: str
    valor: float | int | str
    unidad: str                                 # UNIDADES + "diferencia_proporcion", "cambio_relativo", "rho"
    n: int                                      # tamaño de muestra
    metodo: str
    filtros: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


def crear_evidencia(skill: str, descripcion: str, valor, unidad: str, n: int, metodo: str,
                    filtros: dict | None = None) -> Evidencia:
    """Fábrica recomendada: genera un id determinístico a partir del contenido del cálculo."""
    filtros = filtros or {}
    if isinstance(valor, float):
        valor = round(valor, 6)
    huella = json.dumps([skill, descripcion, filtros, metodo], sort_keys=True, default=str)
    eid = f"{skill}:{hashlib.sha1(huella.encode()).hexdigest()[:8]}"
    return Evidencia(eid, skill, descripcion, valor, unidad, int(n), metodo, dict(filtros))


@dataclass(frozen=True)
class ResultadoSkill:
    skill: str
    evidencias: tuple[Evidencia, ...]
    datos: tuple[dict[str, Any], ...] = ()      # tabla para gráficos (registros)
    advertencias: tuple[str, ...] = ()


@dataclass(frozen=True)
class Insight:
    """(Fase 2) Hallazgo priorizado por el Insight Engine."""
    titulo: str
    mensaje: str
    evidencias: tuple[str, ...]
    puntaje: float
    tipo: str                                   # "cambio", "extremo", "asociacion", "alerta"


@dataclass(frozen=True)
class Historia:
    """(Fase 2) Narrativa construida por el Story Engine."""
    titulo: str
    secciones: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Respuesta:
    """Salida final del pipeline; es lo único que consume el Presentation Engine."""
    pregunta: Pregunta
    plan: Plan
    texto: str
    evidencias: tuple[Evidencia, ...]
    contexto: tuple[Contexto, ...]
    datos: dict[str, tuple[dict[str, Any], ...]]
    advertencias: tuple[str, ...] = ()
    sugerencias: tuple[str, ...] = ()           # siguientes preguntas que el usuario puede hacer
    aclaracion: Aclaracion | None = None        # si no es None, DINAMO necesita que el usuario elija
    insights: tuple[Insight, ...] = ()          # Fase 2
    historia: Historia | None = None            # Fase 2
