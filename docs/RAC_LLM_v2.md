# RAC y LLM en la v2: qué cambió y cómo se usa

## Qué pide la guía v2 a esta parte
| La guía v2 dice | Qué se hizo | Dónde |
|---|---|---|
| Lee PDF; los párrafos se consultan como texto y se cita la página (`[C:informe.pdf#p2]`) | Cada página es un fragmento con fuente `archivo#pN`; el LLM cita esa fuente y la guardia comprueba que exista | `rac/fragmentos.py`, `llm/prompts.py`, `llm/guardia.py` |
| Word es tarea de Diego Castro | Lector `.docx` sin dependencias: secciones (texto) y tablas (datos) | `ingesta/word.py` |
| Varias fuentes a la vez; la pregunta puede nombrar un documento («el informe») | `buscar(pregunta, k, fuentes=[...])`, `documentos()`, `documentos_mencionados(pregunta)` | `rac/retriever.py` |
| «Resume el documento» | `contexto_de_documento(nombre, k)`: primeros fragmentos en orden de página | `rac/retriever.py` |
| El usuario sube archivos mientras conversa | `agregar_archivo(ruta)` indexa PDF, Word, md, txt o csv sin reiniciar (también en el híbrido) | `rac/retriever.py` |
| Perfil del usuario: cambia el tono, nunca los números | `perfil` en `responder_con_guardia`; los campos se limpian (sin saltos de línea ni corchetes) | `llm/prompts.py` |
| La quinta parte de la historia es «siguiente paso» | La guía de redacción la reconoce | `story_engine/redaccion.py` |
| «Recomienda» debe encontrar «Recomendaciones» | Grupos de sinónimos generales (recomienda, sugiere, propone...; resumen; conclusiones...) | `rac/texto.py` |

## Cómo lo usan los demás
**Brain (Samuel)**
```python
docs = self.retriever.documentos_mencionados(pregunta)            # ['informe_clima_laboral.pdf'] o []
if intencion == "consultar_documentos":
    contexto = (self.retriever.contexto_de_documento(docs[0], 5) if es_resumen and docs
                else self.retriever.buscar(pregunta, 3, fuentes=docs or None))
r = responder_con_guardia(self.llm, pregunta, evidencias, contexto, advertencias, perfil=perfil_usuario)
# r.texto, r.advertencias
```
`perfil_usuario` puede ser un dict o un objeto con `nombre`, `cargo`, `nivel_detalle` («breve», «normal», «detallado») e `intereses`.
Use `documentos_mencionados` sólo cuando la intención sea consultar documentos: una pregunta sobre «ventas» también coincide con un archivo llamado `manual_ventas.pdf`.

**Ingesta (Diego Pineda)**
- Registrar `leer_word(ruta)` en `lectores.py`: devuelve `secciones` (texto) y `tablas` (use `tabla_a_dataframe` para pasarlas al Perfilador).
- Si `pdf.py` ya extrae el texto por página, puede llamar `fragmentos_paginas(nombre, [pagina1, pagina2, ...])` y pasar el resultado a `retriever.agregar(...)`.

## Supuestos a confirmar
1. La fuente de un fragmento de PDF es exactamente `archivo.pdf#pN` (así se ve en la guía: `[C:informe_clima_laboral.pdf#p2]`). Si Ingesta usa otro formato, la guardia sigue funcionando: sólo valida que la fuente citada exista en el contexto.
2. `Contexto` sigue siendo `(fuente, texto, puntaje)` y `Evidencia` no cambió salvo el formato del id (la guardia acepta cualquier id).
3. No vi la pestaña personal de Diego Castro de la v2 ni el repositorio `dinamo_analitics_v2.zip`; todo lo anterior sale de la pestaña «Inicio». Si la pestaña trae tareas con otros nombres, se ajusta.

## Límites
- Las tablas de un PDF o Word no entran al RAC: son datos y los analiza el Perfilador.
- Un Word no tiene páginas fijas: se cita el título de la sección (`informe.docx#Recomendaciones`).
- No probé con un modelo real de Ollama (`llama3.2:3b`); `scripts/evaluar_llm.py` dice cuánto pasa el validador.
