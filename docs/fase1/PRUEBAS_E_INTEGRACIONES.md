# Resultados de pruebas e integraciones — Fase 1

Fecha de ejecución: 17 de octubre de 2026. Entorno: Linux, Python 3.13, pandas 3.0, Chromium (Playwright).

> **Importante:** el entorno donde se construyó no tenía salida a internet hacia las APIs. Todas las pruebas de
> búsqueda, artículos, estadísticas y modelos en la nube son **simuladas** (respuestas HTTP falsas con el formato
> documentado de cada servicio). Ninguna se ejecutó contra el servicio real. Ver `PENDIENTES.md`.

## Pruebas automáticas (`pytest`)

```
python -m pytest -q          → 214 pasan, 1 omitida (necesita la base real confidencial, que no se usa)
```

| Archivo | Qué prueba | Tipo |
|---|---|---|
| 23 archivos previos del repositorio | Núcleo analítico (Ingesta, Perfilador, Skills, Brain, RAC…) | Unitarias/integración, datos sintéticos |
| `test_proveedores_llm.py` (9) | Streaming de Ollama/Gemini/Anthropic/OpenAI/Groq, errores HTTP, selección `auto`, que el catálogo no expone claves | Simulada |
| `test_investigacion.py` (24) | SSRF (esquemas, IP privadas, redirección a red interna, tamaño, tipo), lector HTML, clasificación, estados de lectura honestos, respaldo cuando falla Tavily, OpenAlex, deduplicación académica, Banco Mundial → Evidencias, país de referencia | Simulada |
| `test_conversaciones.py` (6) | Aislamiento entre chats, subir no analiza, persistencia y recarga, nombres peligrosos, resumen verificado | Integración local |
| `test_indicadores_talento.py` (4) | Fórmulas (agregar antes de dividir), reproducibilidad, tabla «foto», errores claros | Unitaria |
| `test_limpieza.py` (5) | Diagnóstico, sólo lo aprobado, original intacto, script reproduce el resultado, archivo nuevo en el chat | Unitaria/integración |
| `test_orquestador.py` (12) | Corrección ortográfica, plan JSON validado, sin LLM, citas válidas e inventadas, cifras fuera del material, investigación integrada, memoria, IA del navegador, charla general | Simulada |
| `test_servidor.py` (6) | Servidor HTTP real local: estáticos seguros (`.env`, `..`, código), cabecera anti-CSRF y origen, flujo completo, validaciones, token, negativa a escuchar fuera sin token | Integración local |
| `test_escenarios.py` (14) | Escenarios A, B, C (éxito y fallo), D, E, F, G, I, J (×4), N de la especificación | Simulada |
| `test_comparar_grupos.py` (+1) | Métrica 0/1 compara proporciones | Unitaria |

## Prueba de interfaz (Playwright, servidor real local, sin internet)

`python tests/interfaz/prueba_interfaz.py http://127.0.0.1:8765` → **todas las comprobaciones pasaron**:

- **A**: subir `empleados.csv` no crea mensajes.
- **J**: «histograma del salario mensual» muestra un histograma con los 120 empleados (no el top 5).
- **L**: detener la voz no deshabilita el dictado (controles independientes).
- **O**: 4 acentos × claro/oscuro: contraste ≥ 4,5:1 en texto normal y ≥ 3:1 en etiquetas/insignias/citas
  para cuerpo, navegación, botones, burbujas, insignias, citas, chips y títulos. Capturas en `.dinamo_datos/tema_*.png`.
- Sin errores de JavaScript; a 390 px de ancho no hay desplazamiento horizontal y aparece el menú ☰.
- IA del navegador **simulada** (motor falso inyectado): el texto se transmite, se guarda y la cita inventada se marca.

## Tabla de integraciones

| Servicio | Uso en DINAMO | Requisito | Costo conocido* | Prueba realizada |
|---|---|---|---|---|
| Ollama | Redacción local | Instalar Ollama + modelo | Gratis | Simulada (formato `/api/chat` stream) |
| Gemini | Redacción (nube) | `GEMINI_API_KEY` | Plan gratuito con límites | Simulada (SSE `streamGenerateContent`) |
| Groq | Redacción (nube) | `GROQ_API_KEY` | Plan gratuito con límites | Simulada (OpenAI-compatible) |
| Anthropic | Redacción (nube) | `ANTHROPIC_API_KEY` | Pago por uso | Simulada (SSE Messages) |
| OpenAI / compatible | Redacción (nube o servidor propio) | `OPENAI_API_KEY` | Pago por uso | Simulada |
| WebLLM (`@mlc-ai/web-llm@0.2.81`) | Redacción en el navegador | WebGPU | Gratis (descarga ~1 GB una vez) | Simulada (motor falso); carga real no probada |
| Tavily | Búsqueda web y noticias con texto extraído | Sin clave (keyless, limitado) o `TAVILY_API_KEY` | 1.000 créditos/mes gratis con clave | Simulada |
| Brave Search | Búsqueda web alternativa | `BRAVE_API_KEY` | Cuota gratuita mensual (verificar) | Simulada (sólo error sin clave) |
| Wikipedia | Respaldo de búsqueda | — | Gratis | Simulada |
| GDELT | Respaldo de noticias | — | Gratis | Sin prueba específica |
| OpenAlex | Artículos científicos (resumen reconstruido, citas, acceso abierto) | — (clave opcional) | Gratis | Simulada |
| Crossref | Metadatos y DOI | — | Gratis | Simulada |
| Semantic Scholar | Artículos y PDF abiertos | — | Gratis con límite | Simulada |
| PubMed | Salud ocupacional | — | Gratis | Sin prueba específica |
| Banco Mundial | Indicadores oficiales por país | — | Gratis | Simulada (formato v2 JSON) |
| Voz del navegador | Lectura y dictado | — | Gratis (el dictado puede usar el servicio en línea del navegador) | Manual parcial (Chromium sin voces en el entorno) |
| D-ID / HeyGen | Avatar con sincronización labial | — | De pago | **No implementado** (decisión del usuario) |
| Supabase | Usuarios y sesiones multidispositivo | — | Plan gratuito | **Fase 2** |

\* Precios y cuotas cambian; verifícalos en la página de cada proveedor antes de la demo.
