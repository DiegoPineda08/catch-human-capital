# Banco de preguntas DINAMO

Este documento contiene las preguntas que se utilizarán para probar la capacidad
de DINAMO para interpretar preguntas de usuarios de Recursos Humanos.

Cada pregunta contiene:
- La pregunta formulada de manera natural.
- La intención que debe identificar el sistema.
- El KPI o métrica involucrada.
- Los filtros que debe aplicar.
- La Skill esperada.

---

## Pregunta 1

**Pregunta:** ¿Qué datos tienes?

- **Intención:** explorar_datos
- **KPI:** No aplica
- **Filtros:** Ninguno
- **Skill esperada:** describir_dataset

---

## Pregunta 2

**Pregunta:** ¿Cómo ha evolucionado la rotación?

- **Intención:** tendencia
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** tendencia

---

## Pregunta 3

**Pregunta:** ¿Qué empresas tienen la mayor rotación?

- **Intención:** ranking
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** ranking

---

## Pregunta 4

**Pregunta:** ¿Qué empresas tienen el menor ausentismo en julio-agosto de 2025?

- **Intención:** ranking
- **KPI:** ausentismo_anio
- **Filtros:** periodo = julio-agosto 2025
- **Skill esperada:** ranking

---

## Pregunta 5

**Pregunta:** Compara la rotación de Tier 1 vs Tier 2.

- **Intención:** comparar
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** grupo = Tier 1 vs Tier 2
- **Skill esperada:** comparar_grupos

---

## Pregunta 6

**Pregunta:** ¿Las empresas con sindicato tienen menos ausentismo?

- **Intención:** comparar
- **KPI:** ausentismo_anio
- **Filtros:** tiene_sindicato = sí vs no
- **Skill esperada:** comparar_grupos

---

## Pregunta 7

**Pregunta:** ¿Qué factores se asocian con la rotación?

- **Intención:** relacion
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** relacion

---

## Pregunta 8

**Pregunta:** Cuéntame de la compañía 12.

- **Intención:** perfil_entidad
- **KPI:** Métricas disponibles para la compañía
- **Filtros:** entidad = compañía 12
- **Skill esperada:** perfil_entidad

---

## Pregunta 9

**Pregunta:** ¿Cómo se distribuye el salario diario inicial?

- **Intención:** resumen
- **KPI:** salario_diario_inicial
- **Filtros:** Ninguno
- **Skill esperada:** distribucion

---

## Pregunta 10

**Pregunta:** ¿Y el ausentismo?

- **Intención:** tendencia
- **KPI:** ausentismo_anio
- **Filtros:** Depende del contexto de la conversación anterior
- **Skill esperada:** tendencia

---

# Preguntas adicionales

## Pregunta 11

**Pregunta:** ¿Qué empresas tienen el salario diario inicial más alto?

- **Intención:** ranking
- **KPI:** salario_diario_inicial
- **Filtros:** Ninguno
- **Skill esperada:** ranking

---

## Pregunta 12

**Pregunta:** ¿Cómo ha cambiado el salario diario inicial entre los diferentes periodos?

- **Intención:** tendencia
- **KPI:** salario_diario_inicial
- **Filtros:** Ninguno
- **Skill esperada:** tendencia

---

## Pregunta 13

**Pregunta:** ¿Hay diferencia en el ausentismo entre empresas con sindicato y sin sindicato?

- **Intención:** comparar
- **KPI:** ausentismo_anio
- **Filtros:** tiene_sindicato = sí vs no
- **Skill esperada:** comparar_grupos

---

## Pregunta 14

**Pregunta:** ¿Qué empresas tienen la mayor tasa de rotación?

- **Intención:** ranking
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** ranking

---

## Pregunta 15

**Pregunta:** ¿Qué relación hay entre el salario y la rotación?

- **Intención:** relacion
- **KPI:** salario_diario_inicial y tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** relacion

---

## Pregunta 16

**Pregunta:** ¿Cómo se distribuyen los salarios diarios iniciales?

- **Intención:** resumen
- **KPI:** salario_diario_inicial
- **Filtros:** Ninguno
- **Skill esperada:** distribucion

---

## Pregunta 17

**Pregunta:** Cuéntame sobre la compañía 10.

- **Intención:** perfil_entidad
- **KPI:** Métricas disponibles para la compañía
- **Filtros:** entidad = compañía 10
- **Skill esperada:** perfil_entidad

---

## Pregunta 18

**Pregunta:** ¿Qué empresas tienen menor rotación?

- **Intención:** ranking
- **KPI:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** ranking

---

## Pregunta 19

**Pregunta:** Compara el salario de las empresas de Tier 1 y Tier 2.

- **Intención:** comparar
- **KPI:** salario_diario_inicial
- **Filtros:** grupo = Tier 1 vs Tier 2
- **Skill esperada:** comparar_grupos

---

## Pregunta 20

**Pregunta:** ¿Qué está pasando con el ausentismo?

- **Intención:** tendencia
- **KPI:** ausentismo_anio
- **Filtros:** Ninguno
- **Skill esperada:** tendencia

---

# Preguntas mal escritas o ambiguas

Estas preguntas sirven para comprobar que DINAMO pueda interpretar preguntas
informales, con errores de escritura o con información incompleta.

## Caso ambiguo 1

**Pregunta:** ¿cuales empresa tiene mas rotacion?

- **Intención esperada:** ranking
- **KPI esperado:** tasa_rotacion_bimestral
- **Filtros:** Ninguno
- **Skill esperada:** ranking

---

## Caso ambiguo 2

**Pregunta:** ¿Y los salarios?

- **Intención esperada:** Depende del contexto de la conversación
- **KPI esperado:** salario_diario_inicial
- **Filtros:** Dependen del contexto anterior
- **Skill esperada:** tendencia o ranking según el contexto

---

## Caso ambiguo 3

**Pregunta:** empresas que estan peor en eso

- **Intención esperada:** Depende del contexto de la conversación
- **KPI esperado:** Depende de la métrica mencionada anteriormente
- **Filtros:** Dependen del contexto anterior
- **Skill esperada:** ranking

---

# Observación

Las preguntas 1 a 10 corresponden al banco inicial definido para el proyecto.

Las preguntas 11 a 20 estas son preguntas inventadas para poder probar todas las capacidaddes de dinamo.

Los ultimas 3 preguntas están diseñados para evaluar preguntas informales,
mal escritas o dependientes del contexto de la conversación.