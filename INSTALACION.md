# Entrega de Diego Castro: RAC y LLM (versión v2)

Copiar cada archivo a la misma ruta dentro del repositorio (`dinamo_analitics_v2`). Las carpetas ya coinciden.
Esta entrega **reemplaza** a la anterior: trae todo lo de la v1 más lo nuevo de la v2.

| Archivo | Qué hace | ¿Reemplaza algo? |
|---|---|---|
| `dinamo/rac/texto.py` | Normaliza texto y sinónimos; ahora con sinónimos generales («recomienda» ~ «recomendaciones») | Reemplaza |
| `dinamo/rac/fragmentos.py` | Convierte carpetas, Excel, **PDF y Word** en fragmentos; los PDF citan `archivo#pN` | Reemplaza |
| `dinamo/rac/retriever.py` | TF-IDF + híbrido; ahora filtra por documento, lista documentos y agrega archivos en caliente | Reemplaza |
| `dinamo/rac/__init__.py` | Exporta lo anterior | Reemplaza (si el tuyo exporta algo más, consérvalo) |
| `dinamo/ingesta/word.py` | **Nuevo.** Lector de Word (.docx) sin dependencias: secciones de texto y tablas | Nuevo |
| `dinamo/llm/prompts.py` | `SISTEMA` con citas `[C:fuente]` y ejemplo de documento; perfil del usuario; validadores | Reemplaza (`citas_invalidas` conserva su firma) |
| `dinamo/llm/guardia.py` | Genera, valida (cifras, `[E:id]` y `[C:fuente]`), reintenta y cae a plantilla; acepta `perfil` | Reemplaza |
| `dinamo/llm/ollama_http.py` | Cliente Ollama robusto + embeddings | Sin cambios |
| `dinamo/story_engine/redaccion.py` | Redacción por sección; la quinta parte se llama «Siguiente paso»; acepta `perfil` | Reemplaza |
| `scripts/evaluar_llm.py` | Llena la tabla de `docs/evaluacion_llm.md` | Sin cambios |
| `docs/conocimiento/*` | Glosario, preguntas frecuentes y sinónimos | Sin cambios |
| `docs/RAC_LLM_v2.md` | Qué cambió, qué supuestos hice y cómo lo usan Brain e Ingesta | Nuevo |
| `tests/test_v2_documentos.py` | 30 tests nuevos (PDF, Word, citas de documento, perfil, varias fuentes) | Nuevo |
| `tests/test_*.py` (los otros 6) | Los de la v1 | Sin cambios |

## Probar
```
python -m pytest -q
```
Los tests nuevos no necesitan Excel ni Ollama. El de PDF real se salta solo si no hay `pypdf`.

## Lo que deben hacer los demás (no cambia ningún contrato)
Ver `docs/RAC_LLM_v2.md`, sección «Cómo lo usan los demás».
