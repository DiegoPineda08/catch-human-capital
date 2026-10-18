# Guía de demostración para el concurso (datos sintéticos)

Duración sugerida: 10–12 minutos. Todos los datos son **sintéticos** (inventados por un generador con semilla fija);
no contienen información real de personas ni de empresas.

| Archivo | Contenido |
|---|---|
| `ejemplos/demo_rrhh_sucursales.csv` | 6 sucursales × 12 meses de 2025: headcount, bajas, contrataciones, faltas, días hábiles, horas de capacitación. Incluye una **anomalía sembrada** (Puebla, diciembre). |
| `ejemplos/demo_personal_sucio.csv` | 62 filas de personal con problemas a propósito: duplicados, «Ventas / ventas / VENTAS», salarios como texto, fechas en texto, vacíos. |
| `ejemplos/empleados.csv` | 120 empleados (foto): área, nivel, antigüedad, salario, capacitación, satisfacción, renunció. |
| `ejemplos/informe_clima_laboral.pdf` | Informe de clima laboral (texto). |

## Antes de empezar (5 minutos antes)

1. `INICIAR_DINAMO.bat`. En **Integraciones → Comprobar conexiones** confirma búsqueda y Banco Mundial.
2. Elige el modelo: Ollama (si está instalado), una clave de Groq/Gemini en `.env`, o «Activar IA del navegador».
3. Tema y acento a gusto (sugerencia: oscuro + verde azulado para proyector).

## Guion

**1. «Subir no es analizar» (30 s).** Nueva conversación → sube `demo_rrhh_sucursales.csv`.
Muestra que sólo aparece «listo (sin analizar)». *Mensaje: DINAMO no consume IA ni inventa resúmenes sin que lo pidas.*

**2. Indicadores de capital humano reproducibles (1,5 min).**
> «Calcula la rotación, la retención y el ausentismo por mes»

Abre un botón `dato` → panel con fórmula, n y método. Repite la pregunta: mismos ids. *Las cifras salen de Python, no del modelo.*

**3. Detección de anomalías (1 min).**
> «¿Hay anomalías en las bajas?»

Aparece Puebla (S04) en el último mes, con mediana histórica y MAD. *Señales, no causas.*

**4. Gráfico pedido (45 s).**
> «Gráfico de dispersión entre capacitacion horas promedio y bajas»

Correlación de Spearman con lenguaje de asociación. Cambia el tipo con el selector.

**5. Comparación internacional con país de referencia (1,5 min).** En el panel elige **México** como país de referencia.
> «Compara la tasa de participación laboral de Colombia y España con el país de referencia»

Fuentes «datos oficiales» del Banco Mundial con año, unidad y enlace. *México se sugiere, nunca se impone.*

**6. Investigación verificable (2 min).**
> «Investiga en internet buenas prácticas para reducir la rotación en centros logísticos»

Muestra los pasos, las fuentes con su tipo (oficial, académica, noticia…) y su **estado de lectura**.
Luego **Investigación → Artículos científicos**: «employee turnover logistics warehouse» → «Analizar en la conversación».

**7. Memoria y contexto (45 s).**
> «Recuerda que la meta de rotación mensual de la empresa es 3%»
> «¿Cómo está la rotación de cada mes frente a esa meta?»

**8. Limpieza con aprobación (2 min).** Sube `demo_personal_sucio.csv` → **Datos y limpieza → Revisar calidad**.
Desmarca una propuesta, aplica, muestra antes/después, el registro y el script de Python. El original queda intacto.

**9. Chats aislados (30 s).** Nueva conversación: no tiene archivos, memoria ni evidencias de la anterior.

**10. Honestidad (30 s).** Pregunta «¿Qué temperatura hace hoy en Monterrey?» sin internet → DINAMO dice que no pudo
consultar fuentes y no inventa. En Integraciones, Brave aparece «sin configurar» con instrucciones.

## Preguntas de respaldo

- «Compara las bajas por giro» (advierte grupos pequeños).
- «¿Qué se relaciona con las bajas?» (Spearman, asociación ≠ causa).
- «Ranking de sucursales por faltas».
- «¿Qué dice el informe sobre el liderazgo?» (con el PDF cargado).
- «Busca artículos científicos sobre ausentismo y burnout».
