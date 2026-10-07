# DINAMO_ANALITICS

DINAMO_ANALITICS es un agente inteligente local para análisis y data storytelling.
Recibe archivos de **cualquier tema** (Excel, CSV, PDF, Markdown o texto), descubre solo qué
contienen y conversa con el usuario sobre ellos: responde, pregunta cuando algo es ambiguo,
sugiere qué explorar después y cita la evidencia de cada cifra.

## PRINCIPIO FUNDAMENTAL

La Ingesta lee cualquier archivo.
El Perfil explica cada tabla.
El código calcula.
El LLM interpreta.
El Brain coordina.
El RAC recupera contexto.
Las Skills ejecutan análisis.
Evidence conserva resultados.
Insight Engine prioriza hallazgos.
Story Engine construye la narrativa.
Presentation Engine muestra los resultados.

## ARQUITECTURA

| Componente | Carpeta | Responsable | Fase |
|---|---|---|---|
| Core (contratos, configuración, texto) | `dinamo/core/` | Samuel | 0 |
| Ingesta (Excel, CSV, PDF, texto) | `dinamo/ingesta/` | Diego Castro | 1 (MVP) |
| Data Engine (Biblioteca, Perfilador, perfiles) | `dinamo/data_engine/` + `perfiles/` | Diego Pineda | 1 (MVP) |
| Skills | `dinamo/skills/` | Diego Pineda | 1 (MVP) |
| Evidence | `dinamo/evidence/` | Diego Pineda | 1 (MVP) |
| Brain (elegir fuente, entender, aclarar, sugerir) | `dinamo/brain/` | Samuel | 1 (MVP) |
| State (conversación y usuario) | `dinamo/state/` | Samuel | 1 (MVP) |
| RAC | `dinamo/rac/` + `conocimiento/` | Diego Castro | 1 (MVP) |
| LLM | `dinamo/llm/` | Diego Castro | 1 (MVP) |
| Presentation Engine | `app/` + `dinamo/presentation/` | Gabriela | 1 (MVP) |
| Insight Engine | `dinamo/insight_engine/` | Samuel | 2 |
| Story Engine | `dinamo/story_engine/` | Gabriela + Diego Castro | 2 |

## REGLAS

1. El LLM no debe realizar cálculos estadísticos críticos.
2. Los cálculos deben realizarse mediante código determinístico.
3. El Brain coordina, no manipula directamente DataFrames.
4. Las Skills deben ser modulares.
5. Los resultados numéricos deben quedar registrados como Evidence.
6. El LLM debe recibir contexto recuperado y evidencia.
7. No afirmar causalidad a partir de correlaciones.
8. Evitar dependencias innecesarias entre módulos.
9. Mantener interfaces claras entre componentes.
10. No introducir código arbitrario generado por el LLM y ejecutarlo directamente.
11. Ningún módulo puede depender de una base de datos concreta: lo que se sabe de una fuente
    vive en su perfil (`perfiles/`) y en su conocimiento (`conocimiento/`), nunca en el código.

## FUENTES DE DATOS

DINAMO no está atado a una base. Al iniciar carga todo lo que haya en `data/` (o, si está vacía,
los archivos de `ejemplos/`), y se pueden agregar archivos en plena conversación.

- **Tablas** (hojas de Excel, CSV, tablas dentro de un PDF): cada una recibe un *Perfil* que dice
  qué es cada columna (entidad, tiempo, métrica, categoría...). Se deduce solo; se puede corregir
  con un JSON en `perfiles/` (ver `python -m app.perfilar <archivo>`).
- **Textos** (párrafos de PDF, .md, .txt): el RAC los indexa para responder "¿qué dice el informe sobre...?".

La base del concurso (`BASE_HISTORICA_LIMPIA.xlsx`) es una fuente más: tiene su perfil en
`perfiles/catch_capital_humano.json` y su conocimiento en `conocimiento/catch_capital_humano/`.

## OBJETIVO

Construir progresivamente un sistema que pueda:

1. recibir una pregunta;
2. interpretar la intención;
3. recuperar contexto relevante;
4. seleccionar Skills;
5. ejecutar análisis;
6. almacenar Evidence;
7. generar Insights;
8. interpretar mediante un LLM;
9. construir una narrativa;
10. presentar los resultados.

## METODOLOGÍA DE DESARROLLO

No implementar toda la arquitectura de una vez.

Primero construir un MVP end-to-end:

Archivos → Ingesta → Biblioteca → Pregunta → Brain → RAC → Skill → Evidence → LLM → respuesta

**Estado actual: el MVP ya corre de punta a punta** con 3 Skills (describir, tendencia, ranking),
lectura de Excel, CSV y PDF, aclaraciones, sugerencias y perfil del usuario. Cada integrante mejora
sus módulos sin cambiar los contratos de `dinamo/core/contracts.py`.

Después agregar: Insight Engine → Story Engine → Presentation Engine completo.

## INICIO RÁPIDO

```bash
git clone <url-del-repo>
cd dinamo_analitics
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pytest                                        # todos los tests deben pasar
python -m app.cli                             # conversación por consola con los ejemplos
streamlit run app/streamlit_app.py            # conversación en el navegador
python -m app.cli --llm ollama                # con el LLM local (requiere Ollama)
python -m app.perfilar ejemplos/informe_clima_laboral.pdf   # qué entiende DINAMO de un archivo
```

## CONTRATOS (lo que conecta a los módulos)

Definidos en `dinamo/core/contracts.py`:

| Módulo | Recibe | Devuelve |
|---|---|---|
| Ingesta (`leer_documento`) | ruta de un archivo | `Documento` (tablas + fragmentos) |
| Biblioteca (`agregar_archivo`) | ruta | nombres de tablas; un `DataEngine` + `PerfilDataset` por tabla |
| Brain.interpretar | `Pregunta` | `Plan` (incluye la tabla elegida) |
| RAC (`Retriever.buscar`) | texto, k | `list[Contexto]` |
| Skill (`skill(datos, parametros)`) | `DataEngine`, `dict` | `ResultadoSkill` (con `Evidencia`) |
| EvidenceStore.agregar | `Evidencia` | ids |
| LLM (`generar`) | sistema, usuario (texto) | texto que cita `[E:id]` y `[C:fuente]` |
| Brain.responder | texto | `Respuesta` (con `aclaracion` y `sugerencias`) |
| Insight Engine (fase 2) | `list[Evidencia]`, `Plan` | `list[Insight]` |
| Story Engine (fase 2) | Insights, Evidencias, Contexto | `Historia` |
| Presentation | `Respuesta` | pantalla |

**Cambios de contrato:** se proponen en un Issue de GitHub, se discuten en el equipo y
los aprueba Samuel (dueño de Core). Nadie cambia un contrato dentro de un PR de otra cosa.

## DESARROLLO

Antes de implementar una funcionalidad:

1. revisar la arquitectura;
2. revisar los contratos;
3. revisar el código existente;
4. proponer cambios;
5. implementar solamente después de entender el contexto.

No duplicar funcionalidades existentes.
No crear abstracciones innecesarias.
No modificar arquitectura sin justificarlo.

Flujo Git: una rama por tarea (`feat/skill-comparar`, `fix/brain-periodos`), Pull Request
hacia `main`, al menos 1 revisión de otro integrante y `pytest` en verde antes de unir.

## CALIDAD

Todo componente importante debe tener tests (`tests/`). Los tests usan datos inventados
(`tests/conftest.py`) y los archivos de `ejemplos/`, y prueban cada pieza con **al menos dos
fuentes distintas**: si algo sólo funciona con una base, el test lo detecta.

Priorizar:

- modularidad
- determinismo
- testabilidad
- extensibilidad
- trazabilidad
- separación de responsabilidades
