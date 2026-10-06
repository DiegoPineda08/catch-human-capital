# DINAMO_ANALITICS

## Objetivo

Construir un sistema inteligente, local y genérico para análisis de datos y
data storytelling para el reto de innovación de Catch Consulting.

El sistema debe transformar los datos en:

Datos
→ Perfil del dataset
→ Análisis
→ Evidencia
→ Interpretación
→ Historia
→ Visualización
→ Exploración

El producto NO es un dashboard tradicional ni un chatbot simple.

El sistema debe comprender la pregunta del usuario, recuperar el contexto
relevante, seleccionar la capacidad analítica apropiada, calcular los
resultados de forma determinística, almacenar la evidencia, interpretar los
resultados mediante un LLM y presentar la información de forma clara.

---

# Principio fundamental

El sistema sigue estas reglas:

- Python y los métodos estadísticos calculan los hechos.
- El Brain coordina el flujo.
- El RAC recupera el contexto relevante.
- Las Skills ejecutan los análisis.
- Evidence almacena los resultados numéricos trazables.
- El LLM interpreta y comunica los resultados.
- El Story Engine construye la narrativa.
- El Presentation Engine muestra los resultados.

El LLM NUNCA debe:

- calcular valores estadísticos críticos;
- inventar estadísticas;
- modificar valores calculados;
- inventar evidencias;
- inventar citas o referencias;
- afirmar causalidad cuando el análisis solamente demuestra asociación.

Todo número importante que llegue al usuario debe poder rastrearse hasta una
Evidence estructurada.

---

# Arquitectura actual

El flujo principal es:

Usuario
↓
Presentation
↓
Brain
↓
RAC
↓
Skills
↓
Data Engine
↓
Evidence
↓
LLM
↓
Sugerencias
↓
Presentation

En la Fase 2 se incorporan:

Evidence
↓
Insight Engine
↓
Story Engine
↓
Presentation

El State mantiene el contexto de la conversación y de los análisis realizados.

---

# Módulos principales

## Brain

Responsabilidades:

- comprender la pregunta del usuario;
- determinar la intención;
- identificar la métrica relevante;
- identificar dimensiones y filtros;
- seleccionar las Skills;
- coordinar la ejecución;
- construir la Respuesta final.

El Brain NO debe manipular directamente DataFrames.

---

## RAC

RAC significa Retrieval-Augmented Context.

Su responsabilidad es recuperar contexto relevante para la pregunta actual.

Puede recuperar:

- documentación del dataset;
- definiciones;
- notas metodológicas;
- fragmentos de la base de conocimiento;
- información contextual relevante.

El RAC NO realiza los cálculos estadísticos.

---

## Data Engine

Responsabilidades:

- cargar datasets Excel y CSV;
- acceder al dataset;
- proporcionar datos a las Skills;
- proporcionar metadatos;
- proporcionar periodos y entidades;
- proporcionar variables según su rol;
- proporcionar el Perfil del dataset.

El Data Engine es la interfaz controlada entre los datasets y las Skills.

Las Skills pueden utilizar pandas y DataFrames internamente.

Los contratos compartidos NO deben contener DataFrames.

---

# Perfil del dataset

El Perfil del dataset hace que el sistema sea genérico.

El sistema NO debe quedar amarrado a las columnas de una única base.

El Perfil describe cada columna mediante información como:

- nombre;
- rol;
- tipo;
- formato;
- etiqueta;
- sinónimos;
- valores posibles.

Los roles principales son:

- entidad;
- tiempo;
- métrica;
- dimensión;
- información de calidad o filtrado.

El Perfil es utilizado por:

- Brain;
- Skills;
- RAC;
- sugerencias.

El sistema debe poder trabajar con diferentes datasets sin reescribir la
lógica analítica para cada nombre de columna.

---

# Perfilador

El Perfilador es responsable de inferir el Perfil del dataset.

Reglas generales:

## Tiempo

- identificar columnas de fecha;
- identificar columnas cuyo nombre sugiera un periodo;
- comprobar que la variable realmente permite ordenar las observaciones.

## Entidad

- identificar la columna que representa la entidad a través de los periodos;
- cuando sea posible, preferir una columna legible frente a su identificador.

## Métrica

- variable numérica con más de cinco valores distintos.

## Dimensión

- texto con un número reducido de categorías;
- variables booleanas o de tipo sí/no;
- variables numéricas con pocos valores distintos.

## Ignorar

- columnas vacías;
- columnas constantes;
- identificadores duplicados;
- otras formas redundantes de representar entidad o tiempo.

Si el Perfilador automático se equivoca, la corrección debe hacerse mediante
una configuración del perfil y NO mediante lógica específica de una base dentro
de las Skills.

---

# Skills

Una Skill es una capacidad analítica determinística.

Cada Skill:

- recibe el Data Engine y los parámetros;
- valida los parámetros;
- realiza los cálculos mediante código;
- devuelve un ResultadoSkill;
- genera Evidence estructurada;
- puede devolver registros para visualización;
- puede generar advertencias.

Una Skill NO debe devolver conclusiones narrativas.

La misma Skill ejecutada dos veces con los mismos datos y parámetros debe
producir exactamente el mismo resultado.

El orden debe ser determinístico.

Cuando existan empates, debe utilizarse una segunda clave fija, como el ID
de la entidad.

---

# Skills de Diego Pineda - Fase 1

Las Skills analíticas requeridas son:

1. ranking
2. comparar_grupos
3. relacion
4. perfil_entidad
5. distribucion

Estas corresponden a las tareas detalladas en la guía anterior:

- ranking_empresas;
- comparar_segmentos;
- correlacion_drivers;
- perfil_empresa;

más la nueva Skill genérica de distribución introducida por la arquitectura
actual.

La arquitectura ACTUAL utiliza los nombres genéricos.

NO debemos amarrar el código genérico a los nombres antiguos específicos de
Catch.

---

# Reglas estadísticas

Debe respetarse correctamente la unidad de análisis.

Cuando se comparen empresas o grupos a través de varios periodos:

1. filtrar observaciones válidas o reportadas;
2. agregar los periodos al nivel de entidad cuando corresponda;
3. realizar la comparación al nivel de entidad.

NO se debe permitir que una empresa con siete periodos tenga siete veces más
peso que una empresa con un solo periodo.

Siempre considerar:

- tamaño de muestra;
- valores faltantes;
- significancia estadística;
- relevancia de negocio;
- diferencia entre correlación y causalidad;
- diferencia entre porcentajes y puntos porcentuales.

Para análisis de asociación se debe utilizar lenguaje como:

"se asocia con"

y NO:

"causa"

a menos que exista un diseño causal válido que lo justifique.

---

# Skill: ranking

Objetivo:

Responder preguntas como:

"¿Qué entidades tienen los valores más altos de una métrica?"

Comportamiento:

- recibir una métrica;
- recibir opcionalmente un periodo;
- recibir opcionalmente el número de entidades;
- permitir ordenar ascendente o descendente;
- agregar periodos por entidad cuando corresponda;
- ordenar las entidades;
- devolver Evidence;
- devolver registros para visualización.

Para la base de Catch, la guía detallada exige un mínimo de periodos reportados
para evitar que entidades con muy poca información dominen el ranking.

Valor por defecto:

min_bimestres = 3

Las entidades que no cumplan ese mínimo deben excluirse y dicha exclusión
debe aparecer como advertencia.

---

# Skill: comparar_grupos

Objetivo:

Comparar una métrica entre grupos definidos por una dimensión.

Ejemplos:

- Tier 1 vs Tier 2;
- empresas con sindicato vs empresas sin sindicato;
- categorías de una variable industrial.

Flujo general:

agregación a nivel de entidad
→ agrupación por dimensión
→ resumen por grupo
→ diferencia
→ Evidence

Debe generarse una advertencia cuando un grupo tenga un tamaño de muestra
insuficiente.

Para Catch, la guía establece una advertencia cuando un grupo tiene menos de
10 empresas.

---

# Skill: relacion

Objetivo:

Medir la asociación entre una métrica y otras variables relevantes.

Para Catch:

- utilizar correlación de Spearman;
- trabajar a nivel de entidad;
- utilizar variables identificadas mediante el Perfil y los roles definidos
  para el proyecto;
- devolver las relaciones más fuertes según el valor absoluto de rho.

Las variables que describen directamente el objetivo no deben tratarse como
drivers independientes.

La descripción debe utilizar lenguaje de asociación y nunca de causalidad.

---

# Skill: perfil_entidad

Objetivo:

Responder preguntas como:

"Cuéntame de la compañía 12."

Debe proporcionar Evidence para:

- el último periodo válido de la entidad;
- métricas relevantes;
- comparación contra la mediana de la población o de sus pares;
- percentil o posición cuando corresponda;
- atributos relevantes.

Para Catch pueden incluirse, por ejemplo:

- Tier;
- salario inicial;
- transporte;
- sindicato.

La Skill debe mantenerse lo suficientemente genérica para trabajar con otras
bases que también tengan una entidad identificable.

---

# Skill: distribucion

Objetivo:

Describir cómo se distribuye una métrica.

Puede producir Evidence para:

- número de observaciones;
- mínimo;
- cuartil 1;
- mediana;
- cuartil 3;
- máximo;
- medidas de dispersión.

Debe devolver datos estructurados que puedan utilizarse para visualización.

---

# Skills de Fase 2

Después de estabilizar la Fase 1 se implementarán:

- anomalías;
- brecha contra pares.

Las anomalías de la especificación de Catch utilizan medidas robustas como
mediana y MAD.

La brecha contra pares compara una entidad con la mediana de su grupo de pares
relevante, por ejemplo, mismo Tier y misma categoría.

---

# Evidence

Evidence representa el resultado numérico trazable producido por una Skill.

Debe contener:

- id;
- skill;
- descripción;
- valor;
- unidad;
- n;
- método.

Todo número importante presentado al usuario debe provenir de Evidence.

Evidence debe ser inmutable.

Los IDs de Evidence deben permitir que el LLM, el Insight Engine y
Presentation puedan rastrear un resultado hasta su origen analítico.

---

# ResultadoSkill

Cada Skill devuelve un ResultadoSkill que contiene:

- Evidence;
- datos para visualización;
- advertencias;
- información del tipo de gráfico cuando corresponda.

ResultadoSkill debe ser estructurado.

No se debe utilizar texto libre como sustituto del resultado analítico.

---

# Reglas genéricas de diseño

NO hacer:

- hardcodear columnas de Catch dentro de módulos genéricos;
- manipular DataFrames desde el Brain;
- permitir que el LLM realice cálculos estadísticos;
- incluir DataFrames dentro de contratos;
- devolver conclusiones narrativas desde las Skills;
- cambiar contratos sin aprobación;
- añadir dependencias innecesarias;
- modificar módulos que no pertenecen a la tarea.

Preferir:

- módulos pequeños;
- funciones reutilizables;
- cálculos determinísticos;
- contratos explícitos;
- tests;
- Evidence trazable;
- soluciones simples.

---

# Contratos

Los contratos compartidos estarán definidos en:

src/dinamo/core/contracts.py

Los contratos son las interfaces entre los diferentes módulos.

NO cambiar un contrato dentro de un Pull Request que resuelve otra tarea.

Para cambiar un contrato se requiere:

1. crear un Issue en GitHub;
2. acordarlo con el equipo;
3. obtener la aprobación de Samuel.

Los contratos deben mantenerse inmutables cuando así se especifique.

---

# Pruebas

Toda Skill analítica importante debe tener tests.

Los tests deben comprobar:

- cálculos correctos;
- filtrado correcto;
- agregación correcta;
- orden esperado;
- desempate determinístico;
- advertencias;
- manejo de muestras insuficientes;
- generación de Evidence;
- reproducibilidad.

Para los tests unitarios utilizar datos sintéticos.

Los tests unitarios no deben depender del dataset real del concurso.

---

# Reglas de datos

Datos originales:

data/raw/

Datos procesados:

data/processed/

Diccionarios y metadatos:

data/dictionary/

Perfiles:

perfiles/

Los datos del concurso NO deben subirse a GitHub.

Nunca modificar directamente los datos originales.

---

# Flujo de desarrollo

Antes de implementar una funcionalidad importante:

1. inspeccionar el repositorio;
2. revisar los contratos relevantes;
3. revisar los módulos relacionados;
4. comparar el cambio solicitado con las dos guías del proyecto;
5. proponer la implementación compatible más pequeña;
6. implementar;
7. ejecutar los tests;
8. verificar que la funcionalidad existente siga funcionando.

Trabajar en una tarea claramente definida a la vez.

NO implementar todo el proyecto de una sola vez.

NO introducir frameworks externos sin justificación.

---

# Guías oficiales del proyecto

El desarrollo debe basarse en las dos guías oficiales:

## Guía 2

Es la referencia para:

- arquitectura actual;
- PerfilDataset;
- Perfilador;
- Skills genéricas;
- contratos;
- funcionamiento con diferentes datasets.

## Guía CZ

Es la referencia para:

- comportamiento estadístico;
- reglas de cálculo;
- lógica de las Skills;
- Evidence;
- restricciones metodológicas;
- anomalías;
- brecha contra pares.

Cuando exista una diferencia:

1. utilizar la Guía 2 para la arquitectura y los contratos ACTUALES;
2. utilizar la Guía CZ para el comportamiento estadístico detallado;
3. no combinar silenciosamente interfaces antiguas y nuevas.

---

# Alcance de Diego Pineda

Diego Pineda es responsable de:

- Data Engine;
- Perfil del dataset;
- Perfilador;
- Skills analíticas;
- Evidence;
- tests analíticos.

Debe coordinar con Samuel los nombres y parámetros de las Skills cuando estos
se conecten con el Brain.

NO implementar RAC, Ollama, Presentation, Story Engine o lógica del Brain como
parte de este módulo salvo que el equipo lo solicite explícitamente.

---

# Prioridad actual de desarrollo

El proyecto empieza desde cero.

NO asumir que los archivos mencionados en las guías ya existen.

Orden de construcción:

1. estructura compartida del proyecto;
2. contratos compartidos;
3. PerfilDataset;
4. Data Engine;
5. Perfilador;
6. base de Skills;
7. Evidence;
8. Skills analíticas;
9. tests;
10. integración con Brain, RAC, LLM y Presentation.

Construir primero un núcleo pequeño, confiable y comprobable.

---

# Regla final

Cada número que vea el jurado debe poder responder:

"¿Qué Skill lo calculó, con qué datos, con qué método y con qué tamaño de muestra?"

Si no podemos responder eso, el resultado todavía no está listo.