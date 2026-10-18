# Funcionalidades no validadas o pendientes

## Construido pero NO validado contra el servicio real

Se construyeron siguiendo la documentación de cada proveedor y se probaron con respuestas simuladas, pero el entorno
de desarrollo no tenía salida a internet. **Antes de la demo, ejecuta «Comprobar conexiones» en Integraciones y
haz una pregunta de cada tipo.**

1. Búsqueda real con Tavily (modo sin clave y con clave), Brave, Wikipedia y GDELT.
2. Lectura real de páginas (HTML/PDF de sitios reales: codificaciones raras, sitios que bloquean bots, muros de pago).
3. OpenAlex, Crossref, Semantic Scholar y PubMed reales (cambios de formato o límites de frecuencia).
4. Banco Mundial real (códigos de indicadores verificados con la documentación pública; los datos dependen de la API).
5. Gemini, Groq, Anthropic y OpenAI reales (nombres de modelos por defecto pueden cambiar: se ajustan en `.env`).
6. Ollama real (la prueba usa respuestas simuladas del formato `/api/chat`).
7. Descarga y ejecución real de WebLLM en un navegador con WebGPU.
8. Calidad de la redacción con modelos pequeños (1–3B): pueden ignorar el formato o citar mal; la verificación
   automática lo marca, pero no lo corrige.
9. Voces del sintetizador en Windows/Chrome (el navegador de pruebas no tenía voces en español).
10. `INICIAR_DINAMO.bat` en un Windows real (se revisó el script, no se ejecutó en Windows).

## Pendiente (Fase 2, acordado)

1. **Usuarios y multidispositivo con Supabase** (Escenario M): autenticación, sesiones, conversaciones por usuario.
   Hoy el servidor es local de un solo usuario (con `DINAMO_TOKEN` opcional).
2. **Selección de personal** (Escenario H): comparar perfiles con requisitos explícitos, evaluación explicable,
   sin atributos protegidos. Hoy sólo existe la regla en el prompt.
3. **Informes de consultoría** exportables (documento con hallazgos, gráficos y fuentes). Hoy: exportación del chat a Markdown.
4. **Comparación de países con metodología**: se muestran unidad, año y fuente; falta incorporar notas metodológicas
   del indicador (metadatos del Banco Mundial) y fuentes nacionales (INEGI, DANE, INE).

## No implementado por decisión

- **Sincronización labial** (Escenario K): el usuario pidió no ponerla si no era real. El avatar conserva la foto y
  la voz del navegador; no simula movimiento de labios.

## Limitaciones conocidas

- El planificador por reglas (cuando no hay LLM) entiende bien las intenciones frecuentes, pero no todas las
  formulaciones. Con LLM, el plan lo propone el modelo y se valida.
- Algunas preguntas sobre «qué entidad tiene más X» el Brain existente las interpreta como tendencia; «ranking de
  … por X» funciona siempre.
- Riesgo residual de DNS rebinding en la lectura de páginas (aceptable en un servidor local de un usuario).
- La verificación de cifras compara números literales: puede marcar redondeos distintos como «no verificadas».
- El resumen de contexto con LLM se descarta si contiene una cifra que no estaba en la conversación (se usa el
  resumen determinístico).
