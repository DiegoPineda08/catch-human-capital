# Banco de preguntas (responsable: Gabriela)

Preguntas que DINAMO debe responder bien. Samuel las convierte en tests; Diego Castro las usa para
evaluar el LLM. Cada fila: la pregunta tal como la diría un usuario, la fuente, la intención esperada
y el estado (Funciona / Parcial / Pendiente).

| # | Pregunta | Fuente | Intención esperada | Estado |
|---|---|---|---|---|
| 1 | ¿Qué datos tienes? | todas | describir_datos | Funciona |
| 2 | ¿Cómo han evolucionado las ventas? | ventas_tiendas.csv | tendencia | Funciona |
| 3 | ¿Y en la región Sur? (después de la 2) | ventas_tiendas.csv | tendencia + filtro | Funciona |
| 4 | ¿Qué tiendas son las mejores? | ventas_tiendas.csv | aclaración (¿cuál indicador?) | Funciona |
| 5 | Compara las ventas por región | ventas_tiendas.csv | comparar_grupos | Pendiente (Skill) |
| 6 | ¿Qué áreas tienen mayor salario? | empleados.csv | comparar_grupos | Pendiente (Skill) |
| 7 | ¿Qué factores se relacionan con la renuncia? | empleados.csv | relaciones | Pendiente (Skill) |
| 8 | ¿Cómo ha evolucionado la rotación trimestral? | informe_clima_laboral.pdf (tabla) | tendencia | Funciona |
| 9 | ¿Qué recomienda el informe? | informe_clima_laboral.pdf (texto) | consultar_documentos | Parcial (RAC v0) |
| 10 | Cuéntame de la Tienda Centro | ventas_tiendas.csv | perfil_entidad | Pendiente (Skill) |
