# Entrega de Diego Castro: RAC y LLM

Copiar cada archivo a la misma ruta dentro de `dinamo_analitics/` (las carpetas ya coinciden).

| Archivo | Qué hace | ¿Reemplaza algo? |
|---|---|---|
| `dinamo/rac/texto.py` | Normaliza texto (acentos, plurales, stopwords) y sinónimos | Nuevo (si ya tienes `normalizar`, usa esta) |
| `dinamo/rac/fragmentos.py` | Convierte carpeta `docs/conocimiento/` y Excel en fragmentos | Nuevo |
| `dinamo/rac/retriever.py` | `RetrieverTfidf` + `RetrieverHibrido`; alias `Retriever` | **Reemplaza** el retriever v0 |
| `dinamo/rac/__init__.py` | Exporta lo anterior | Reemplaza; si el tuyo exporta algo más, consérvalo |
| `dinamo/llm/prompts.py` | `SISTEMA` con few-shot, validadores, plantilla de respaldo | **Reemplaza** (conserva `citas_invalidas` con la misma firma) |
| `dinamo/llm/guardia.py` | Genera, valida, reintenta y cae a plantilla | Nuevo |
| `dinamo/llm/ollama_http.py` | Cliente Ollama robusto + embeddings | Nuevo (no toca `LLMOllama`) |
| `dinamo/story_engine/redaccion.py` | Redacción por sección (fase 2) | Nuevo; ver supuesto sobre `Historia` |
| `scripts/evaluar_llm.py` | Llena la tabla de `docs/evaluacion_llm.md` | Nuevo |
| `docs/conocimiento/*` | Glosario, preguntas frecuentes y sinónimos | Nuevo |
| `tests/test_*.py` | 48 tests | Nuevos |

## Lo que debe hacer Samuel (no se cambia ningún contrato)
1. En `Brain.responder`, reemplazar la llamada directa al LLM por:
   `r = responder_con_guardia(self.llm, pregunta, evidencias, contexto, advertencias)`
   y usar `r.texto` y `r.advertencias`.
2. En `dinamo/sistema.py` la llamada `Retriever.desde_carpeta(...)` no cambia.

## Opcional: búsqueda semántica
`ollama pull nomic-embed-text` y `set OLLAMA_EMBED_MODELO=nomic-embed-text` (Windows) o `export OLLAMA_EMBED_MODELO=nomic-embed-text`.
Sin esa variable el RAC usa sólo TF-IDF.
