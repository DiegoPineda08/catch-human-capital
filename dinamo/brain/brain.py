"""
BRAIN — coordina todo el flujo. No calcula ni manipula DataFrames.

Flujo de una pregunta:
  1. ¿Responde a una aclaración pendiente? ("2" -> la opción 2 completa)
  2. ¿De qué FUENTE habla?      -> elegir_tabla() compara la pregunta con el vocabulario de cada tabla
  3. ¿Qué QUIERE saber?         -> el Intérprete arma un Plan (intención, métrica, filtros...)
  4. ¿Falta algo para responder? -> si es ambigua, devuelve una Aclaración con opciones (no adivina)
  5. Contexto                   -> RAC (conocimiento, perfiles y textos de documentos)
  6. Cálculo                    -> Skills -> Evidencias -> EvidenceStore
  7. Interpretación             -> LLM (con evidencias, contexto y perfil del usuario)
  8. Verificación               -> ¿el LLM citó evidencias o fuentes que no existen?
  9. Sugerencias                -> siguientes preguntas que sí se pueden responder

Funciona con cualquier fuente porque todo lo que sabe de ella viene de la Biblioteca:
perfiles (descripciones de columnas), listas de periodos y entidades, y fragmentos de texto.
"""
from __future__ import annotations

import re

from dinamo.core.contracts import Aclaracion, Plan, Pregunta, Respuesta
from dinamo.core.texto import texto_plano
from dinamo.evidence import EvidenceStore
from dinamo.llm import LLMFalso, LLMNoDisponible, citas_invalidas, construir_mensajes
from dinamo.rac import documento_mencionado
from dinamo.skills import ParametroInvalido, Registro
from dinamo.state import EstadoSesion

from .entender import Interprete
from .sugerencias import sugerir

# Si no existe Skill para una intención, se responde con la más cercana disponible.
RESPALDO = {
    "comparar_grupos": ("tendencia", "ranking", "describir_datos"),
    "relaciones": ("tendencia", "ranking", "describir_datos"),
    "perfil_entidad": ("tendencia", "describir_datos"),
    "tendencia": ("ranking", "describir_datos"),
    "ranking": ("describir_datos",),
    "desconocida": ("describir_datos",),
}
NECESITAN_METRICA = ("tendencia", "ranking", "comparar_grupos", "relaciones")
MAX_OPCIONES = 4
PATRON_FUENTE = re.compile(r"\(?\s*fuente\s*:\s*([\w.\-]+)\s*\)?", re.IGNORECASE)


class Brain:
    def __init__(self, biblioteca, registro: Registro, rac, llm, evidencias: EvidenceStore | None = None,
                 estado: EstadoSesion | None = None, top_k: int = 3):
        self.biblioteca = biblioteca    # sólo se pasa a las Skills; el Brain no consulta tablas
        self.registro = registro
        self.rac = rac
        self.llm = llm
        self.evidencias = evidencias or EvidenceStore()
        self.estado = estado or EstadoSesion()
        self.top_k = top_k
        self._preparar()

    # ------------------------------------------------------------------ fuentes
    def _preparar(self) -> None:
        """(Re)construye el vocabulario de cada tabla. Se llama al inicio y al cargar un archivo."""
        motores = self.biblioteca.motores
        self.interpretes = {n: Interprete(m.perfil, m.periodos(), m.entidades()) for n, m in motores.items()}
        self.disponibles = {n: self.registro.intenciones_disponibles(m.perfil) for n, m in motores.items()}
        if hasattr(self.rac, "sincronizar"):
            self.rac.sincronizar(self.biblioteca)
        if self.estado.tabla_activa not in motores:
            self.estado.tabla_activa = next(iter(motores), None)

    def cargar_archivo(self, ruta) -> list[str]:
        """Agrega un archivo en plena conversación. Devuelve las tablas nuevas que se pueden analizar."""
        nuevas = self.biblioteca.agregar_archivo(ruta)
        self._preparar()
        if nuevas:
            self.estado.tabla_activa = nuevas[0]
        return nuevas

    def cambiar_usuario(self, **datos) -> None:
        """p.ej. cambiar_usuario(nombre="Ana", rol="Gerente de RR. HH.", nivel="directivo")."""
        for clave, valor in datos.items():
            setattr(self.estado.usuario, clave, tuple(valor) if clave == "intereses" else valor)

    @property
    def tabla_activa(self) -> str | None:
        return self.estado.tabla_activa

    @property
    def datos(self):
        """DataEngine de la tabla activa (para quien necesite su perfil, p.ej. la interfaz)."""
        return self.biblioteca.motor(self.tabla_activa) if self.tabla_activa else None

    @property
    def perfil(self):
        return self.datos.perfil if self.datos else None

    def elegir_tabla(self, texto: str) -> tuple[str | None, list[str]]:
        """Devuelve (tabla elegida, tablas empatadas). Si hay empate entre fuentes, la lista trae >1."""
        m = PATRON_FUENTE.search(texto)
        if m and m.group(1) in self.interpretes:
            return m.group(1), []
        puntajes = sorted(((i.relevancia(texto), n) for n, i in self.interpretes.items()), key=lambda x: -x[0])
        if not puntajes or puntajes[0][0] == 0:
            return self.tabla_activa, []                 # no nombra ninguna fuente: se sigue con la activa
        empatadas = [n for p, n in puntajes if p == puntajes[0][0]]
        if self.tabla_activa in empatadas:
            return self.tabla_activa, []
        return empatadas[0], empatadas if len(empatadas) > 1 else []

    # ------------------------------------------------------------------ interpretar
    def interpretar(self, pregunta: Pregunta) -> Plan:
        texto = PATRON_FUENTE.sub(" ", pregunta.texto)
        tabla, _ = self.elegir_tabla(pregunta.texto)
        if tabla is None:                                # sólo hay documentos de texto
            intencion = "consultar_documentos" if self.rac_tiene_documentos() else "desconocida"
            return Plan(intencion)
        plan = self.interpretes[tabla].interpretar(texto, self.estado.ultimo_plan_de(tabla))
        perfil = self.biblioteca.motor(tabla).perfil
        skills = tuple(s.nombre for s in self.registro.para_intencion(plan.intencion, perfil))
        return Plan(plan.intencion, plan.metricas, plan.dimension, plan.filtros, skills, plan.confianza,
                    plan.orden, tabla, plan.supuestos)

    def rac_tiene_documentos(self) -> bool:
        return bool(getattr(self.rac, "documentos", lambda: [])())

    def _skills_a_ejecutar(self, plan: Plan, advertencias: list[str]) -> list[str]:
        if plan.skills:
            return list(plan.skills)
        perfil = self.biblioteca.motor(plan.tabla).perfil
        if plan.intencion == "desconocida":
            advertencias.append("No entendí del todo la pregunta. Te muestro qué datos tengo; "
                                "prueba con una de las sugerencias.")
        existentes = self.registro.para_intencion(plan.intencion)          # sin mirar la base
        for alternativa in RESPALDO.get(plan.intencion, ()):
            skills = self.registro.para_intencion(alternativa, perfil)
            if skills:
                if existentes:                     # la Skill existe, pero a esta base le falta algo
                    faltan = sorted({r for s in existentes for r in s.requiere if not perfil.tiene(r)})
                    advertencias.append(f"Esta base no tiene columnas de tipo {faltan}, así que no puedo "
                                        f"responder '{plan.intencion}'; te muestro '{alternativa}'.")
                elif plan.intencion != "desconocida":
                    advertencias.append(f"Todavía no existe una Skill para '{plan.intencion}'; "
                                        f"te muestro '{alternativa}'.")
                return [s.nombre for s in skills]
        return []

    # ------------------------------------------------------------------ aclaraciones
    def _aclaracion(self, texto: str, plan: Plan, empatadas: list[str]) -> Aclaracion | None:
        """¿Hace falta preguntarle algo al usuario antes de calcular?"""
        base = re.sub(r"[¿?]", "", PATRON_FUENTE.sub(" ", texto)).strip()
        if empatadas:
            return Aclaracion("Esa pregunta podría responderse con varias fuentes. ¿Cuál quieres usar?",
                              tuple(f"{base} (fuente: {t})" for t in empatadas[:MAX_OPCIONES]))
        if plan.tabla and "metrica" in plan.supuestos and plan.intencion in NECESITAN_METRICA:
            metricas = self.biblioteca.motor(plan.tabla).perfil.por_rol("metrica")
            if len(metricas) > 1:
                return Aclaracion("¿Sobre qué indicador quieres saber?",
                                  tuple(f"{base} — {c.nombre_visible}" for c in metricas[:MAX_OPCIONES]))
        return None

    # ------------------------------------------------------------------ responder
    def responder(self, texto: str) -> Respuesta:
        texto = self.estado.resolver_opcion(texto)
        self.estado.aclaracion_pendiente = None
        pregunta = Pregunta(texto)
        plan = self.interpretar(pregunta)
        _, empatadas = self.elegir_tabla(texto)

        aclaracion = self._aclaracion(texto, plan, empatadas)
        if aclaracion is not None:
            self.estado.aclaracion_pendiente = aclaracion
            lineas = "\n".join(f"{i}. {o}" for i, o in enumerate(aclaracion.opciones, start=1))
            return Respuesta(pregunta, plan, f"{aclaracion.pregunta}\n{lineas}", (), (), {},
                             sugerencias=aclaracion.opciones, aclaracion=aclaracion)

        if plan.intencion == "consultar_documentos" and self.rac_tiene_documentos():
            return self._responder_con_documentos(pregunta, plan)
        if plan.tabla is None:
            return Respuesta(pregunta, plan, "Todavía no hay datos cargados. Sube un Excel, CSV o PDF.", (), (), {})
        if plan.intencion == "consultar_documentos":           # pidió un documento pero sólo hay tablas
            plan = Plan("describir_datos", tabla=plan.tabla,
                        skills=tuple(s.nombre for s in self.registro.para_intencion("describir_datos")))
        return self._responder_con_datos(pregunta, plan)

    def _responder_con_datos(self, pregunta: Pregunta, plan: Plan) -> Respuesta:
        advertencias: list[str] = []
        skills = self._skills_a_ejecutar(plan, advertencias)
        contexto = self.rac.buscar(pregunta.texto, k=self.top_k)

        # "¿Qué datos tienes?" con varias fuentes: se describen todas
        tablas = list(self.biblioteca.motores) if plan.intencion == "describir_datos" else [plan.tabla]
        evidencias, datos = [], {}
        parametros = {"metrica": plan.metrica, "dimension": plan.dimension, "filtros": dict(plan.filtros),
                      "orden": plan.orden}
        for tabla in tablas:
            motor = self.biblioteca.motor(tabla)
            for nombre in skills:
                skill = self.registro.obtener(nombre)
                if not skill.aplica(motor.perfil):
                    continue
                try:
                    res = skill(motor, parametros)
                except (ParametroInvalido, KeyError) as exc:
                    advertencias.append(f"La Skill {nombre} no pudo ejecutarse: {exc}")
                    continue
                self.evidencias.agregar(res.evidencias)
                evidencias.extend(res.evidencias)
                datos[nombre if len(tablas) == 1 else f"{nombre}:{tabla}"] = res.datos
                advertencias.extend(res.advertencias)

        fuentes = "\n".join(f"- {n}: {m.perfil.descripcion} (origen: {m.origen})"
                            for n, m in self.biblioteca.motores.items() if n in tablas)
        texto_llm = self._interpretar_con_llm(pregunta.texto, contexto, evidencias, advertencias, fuentes)
        sugerencias = sugerir(self.biblioteca.motor(plan.tabla).perfil, plan, self.disponibles[plan.tabla], datos)
        self.estado.registrar(pregunta.texto, plan, [e.id for e in evidencias])
        return Respuesta(pregunta, plan, texto_llm, tuple(evidencias), tuple(contexto), datos,
                         tuple(advertencias), sugerencias)

    def _responder_con_documentos(self, pregunta: Pregunta, plan: Plan) -> Respuesta:
        """Preguntas sobre el TEXTO de los documentos: no hay cálculo, el LLM resume lo que dicen."""
        advertencias: list[str] = []
        doc = documento_mencionado(pregunta.texto, self.rac.documentos())
        pide_resumen = any(p in texto_plano(pregunta.texto) for p in (" resume ", " resumen ", " de que trata "))
        if doc and pide_resumen:
            contexto = self.rac.fragmentos_de(doc)[:6]
        else:
            contexto = self.rac.buscar(pregunta.texto, k=max(self.top_k, 4), tipos=("documento",), documento=doc)
        if not contexto:
            advertencias.append("No encontré nada sobre eso en los documentos cargados.")
        texto_llm = self._interpretar_con_llm(pregunta.texto, contexto, [], advertencias,
                                              "Documentos: " + ", ".join(self.rac.documentos()))
        plan = Plan("consultar_documentos", tabla=None, confianza=plan.confianza)
        self.estado.registrar(pregunta.texto, plan, [])
        sugerencias = [f"Resume el documento {d}" for d in self.rac.documentos() if d != doc][:2]
        if self.tabla_activa:                             # y una pregunta sobre los datos, para seguir
            sugerencias += list(sugerir(self.perfil, Plan("describir_datos", tabla=self.tabla_activa),
                                        self.disponibles[self.tabla_activa])[:1])
        sugerencias = tuple(sugerencias)
        return Respuesta(pregunta, plan, texto_llm, (), tuple(contexto), {}, tuple(advertencias), sugerencias)

    def _interpretar_con_llm(self, texto, contexto, evidencias, advertencias, fuentes) -> str:
        sistema, usuario = construir_mensajes(texto, contexto, evidencias, advertencias, sobre_la_base=fuentes,
                                              usuario=self.estado.usuario.describir())
        try:
            respuesta = self.llm.generar(sistema, usuario)
        except LLMNoDisponible as exc:
            advertencias.append(str(exc))
            respuesta = LLMFalso().generar(sistema, usuario)
        inventadas = citas_invalidas(respuesta, {e.id for e in evidencias}, {c.fuente for c in contexto})
        if inventadas:
            advertencias.append(f"El LLM citó evidencias o fuentes que no existen: {inventadas}")
        return respuesta

    # ------------------------------------------------------------------ inicio de la conversación
    def bienvenida(self) -> Respuesta:
        """Primer mensaje: qué fuentes hay y qué se puede preguntar (para que nadie empiece en blanco)."""
        tablas = self.biblioteca.resumen()
        docs = self.rac.documentos() if hasattr(self.rac, "documentos") else []
        lineas = [f"- {t['tabla']} ({t['origen']}): {t['filas']} filas, {t['indicadores']} indicadores"
                  for t in tablas] + [f"- {d}: texto" for d in docs]
        sugerencias: list[str] = ["¿Qué datos tienes?"]
        for nombre in list(self.biblioteca.motores)[:2]:
            perfil = self.biblioteca.motor(nombre).perfil
            sugerencias += [s for s in sugerir(perfil, Plan("describir_datos", tabla=nombre),
                                               self.disponibles[nombre])[:1] if s not in sugerencias]
        if docs:
            sugerencias.append(f"Resume el documento {docs[0]}")
        saludo = f"Hola{', ' + self.estado.usuario.nombre if self.estado.usuario.nombre else ''}. "
        texto = saludo + ("Tengo estas fuentes cargadas:\n" + "\n".join(lineas) if lineas
                          else "Todavía no tengo fuentes. Sube un Excel, CSV o PDF.")
        return Respuesta(Pregunta(""), Plan("describir_datos"), texto, (), (), {}, tuple(self.biblioteca.advertencias),
                         tuple(sugerencias[:4]))
