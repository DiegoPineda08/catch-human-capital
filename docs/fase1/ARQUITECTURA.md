# Informe de arquitectura — Fase 1

## Punto de partida (auditoría)

- El repositorio (`proyecto.zip`) tenía un núcleo analítico sólido y probado (135 pruebas): Ingesta, Perfilador,
  Data Engine, nueve Skills determinísticas, Evidence trazable, RAC por palabras, Brain con aclaraciones y un LLM
  opcional (Ollama o «falso»). La interfaz era Streamlit.
- `DINAMO_Analytics_PRO_MAX.html` (1,6 MB) era una interfaz independiente que **no usaba ese núcleo**: hacía los
  cálculos en JavaScript, resumía y graficaba automáticamente al subir archivos, tenía tres funciones de búsqueda web
  duplicadas (dos modales y un botón) basadas en Wikipedia/GDELT/Crossref, y textos invisibles en modo claro.
- Decisión: **la interfaz nueva habla con el núcleo Python** mediante un servidor local; no se duplicó lógica analítica
  en el navegador.

## Vista general

```
Navegador (frontend/)                    Servidor local (dinamo/servidor, stdlib)
 ├ Conversación (NDJSON en streaming) ──▶ Orquestador (dinamo/orquestador)
 ├ Datos y limpieza                       ├ Planificador: LLM → plan JSON validado | reglas sin LLM
 ├ Investigación                          ├ Herramientas autorizadas ──▶ Brain + Skills + Evidence (núcleo existente)
 ├ Integraciones                          │                           ──▶ Investigación (dinamo/investigacion)
 └ IA del navegador (WebLLM, opcional)    │                           ──▶ Limpieza (dinamo/limpieza)
                                          ├ Síntesis: LLM redacta con [E:id] [C:fuente] [W:n]
                                          └ Verificación: citas inexistentes y cifras fuera del material
                                         Conversaciones aisladas (dinamo/conversacion) → .dinamo_datos/
```

## Módulos nuevos

| Módulo | Responsabilidad | Pruebas |
|---|---|---|
| `dinamo/llm/proveedores.py` | Ollama, Gemini, Groq, Anthropic, OpenAI-compatible con streaming; selección automática. Cumple el contrato `generar(sistema, usuario)`. | `test_proveedores_llm.py` |
| `dinamo/investigacion/` | `red.py` descarga segura (SSRF), `lector.py` HTML/PDF→texto+metadatos+pasajes, `buscadores.py` (Tavily, Brave, Wikipedia, GDELT, OpenAlex, Crossref, Semantic Scholar, PubMed), `estadisticas.py` (Banco Mundial → Evidencias), `fuentes.py` (clasificación con justificación y estado de lectura), `catalogo.py` (integraciones con estado real). | `test_investigacion.py` |
| `dinamo/conversacion/` | `Espacio` por chat con su propia Biblioteca, RAC, EvidenceStore, Estado, memoria, investigaciones y limpieza; persistencia JSON atómica; resúmenes de contexto verificados. | `test_conversaciones.py` |
| `dinamo/orquestador/` | Plan (LLM o reglas, con corrección ortográfica), herramientas en lista blanca, síntesis con secciones separadas, verificación, modo «IA del navegador». | `test_orquestador.py`, `test_escenarios.py` |
| `dinamo/limpieza/` | Diagnóstico, aplicación sólo de lo aprobado, antes/después, registro, script reproducible. | `test_limpieza.py` |
| `dinamo/skills/indicadores_talento.py` | Rotación, retención, ausentismo, contratación con fórmulas de `conocimiento/…/indicadores.md`; agrega antes de dividir; advierte cuando la tabla es una foto. | `test_indicadores_talento.py` |
| `dinamo/skills/visualizacion.py` | `histograma` y `dispersion` para gráficos pedidos explícitamente (todos los datos, a nivel de entidad). | `test_escenarios.py` (J) |
| `dinamo/servidor/` | HTTP con `ThreadingHTTPServer` + `requests`; sin dependencias nuevas. | `test_servidor.py` |
| `frontend/` | Diseño de **DINAMO Analytics PRO MAX** (barra lateral, avatar a la izquierda del chat, panel de documentos y herramientas a la derecha), conectado al servidor. `estilos.css` = CSS original + capa Fase 1 (colores por tokens, 4 acentos × claro/oscuro, chat a ancho completo), `app.js`, `graficos.js` (SVG propio), `img/`. `DINAMO_Fase1.html` es la versión en un solo archivo. | `tests/interfaz/prueba_interfaz.py` |

## Decisiones técnicas

1. **Sin frameworks nuevos.** FastAPI/httpx no estaban en el proyecto; el servidor usa la biblioteca estándar y
   `requests` (ya era dependencia). Regla del CLAUDE.md: «no añadir dependencias innecesarias».
2. **Contratos intactos.** No se modificó `dinamo/core/contracts.py`. El Brain se usa como herramienta (con el LLM
   falso, para que sólo calcule); la redacción final la hace el orquestador con todo el material junto.
3. **El LLM nunca calcula.** Las cifras vienen de Skills o se copian de una API oficial y se convierten en `Evidencia`
   (`skill="banco_mundial"`). La síntesis exige citar `[E:id]`, `[C:fuente]`, `[W:n]`; después se verifican citas y
   cifras, y los problemas se muestran al usuario («Verificación automática»).
4. **Honestidad de lectura.** Cada fuente externa tiene estado: leída, leída parcialmente, solo resumen, solo
   fragmento, solo metadatos, no se pudo leer, datos oficiales. El prompt prohíbe afirmar lectura completa si no la hubo.
5. **Clasificación sin puntuaciones inventadas.** Tipo de fuente (oficial, organismo internacional, académica,
   noticia, enciclopedia, documentación técnica, sitio web) por reglas explícitas, siempre con su justificación.
6. **Subir ≠ analizar.** `Espacio.agregar_archivo` sólo guarda y perfila (columnas/roles). No crea mensajes.
7. **IA siempre presente sin descargar nada en el servidor**: proveedor local o nube si existe; si no, WebLLM en el
   navegador recibe los mensajes ya preparados por el servidor y devuelve el texto para verificarlo y guardarlo.
8. **Corrección metodológica en `comparar_grupos`**: con una métrica 0/1 (p. ej. «renunció») la mediana por grupo sólo
   puede ser 0 o 1 y ocultaba diferencias (todas las áreas salían 0 %). Ahora usa la proporción. Cambio acotado,
   con prueba nueva; conviene que Diego Pineda lo revise.
9. **Avatar**: se conservaron Sofía y Mateo (extraídos del HTML original a `frontend/img/`). Las animaciones «que
   hablan» del HTML original (GIF de 1,1 MB) no se incluyeron porque no eran sincronización labial real; la foto sólo se
   ilumina mientras suena la voz. El avatar ocupa una tarjeta plegable del panel derecho y no reduce el chat.

## Seguridad

| Riesgo | Medida |
|---|---|
| Exposición del servidor | Escucha en `127.0.0.1`; fuera de ahí exige `DINAMO_TOKEN` (cookie HttpOnly, SameSite=Strict). |
| CSRF desde otros sitios | Toda escritura exige la cabecera `X-DINAMO: 1` (fuerza preflight CORS, que no se concede) y `Origin` igual al host. |
| Archivos estáticos | Sólo desde `frontend/`, extensiones en lista blanca, sin archivos ocultos, ruta resuelta dentro de la carpeta. `.env`, código y datos no se sirven. |
| Path traversal | IDs con regex estricta; nombres saneados (`nombre_seguro`); descargas sólo de `archivos/` o `scripts/` del chat. |
| SSRF al leer páginas | Sólo http/https; DNS resuelto y bloqueo de IP privadas/loopback/link-local/reservadas (incl. 169.254.169.254); redirecciones manuales (máx. 3) revalidadas; tamaño máx. 3 MB; tipos permitidos; tiempos límite. Riesgo residual: DNS rebinding (documentado). |
| Claves | Sólo en `.env` del servidor; `/api/estado` e `/api/integraciones` dicen si existen, nunca su valor (probado). |
| Código del LLM | Nunca se ejecuta. El plan del LLM se valida contra la lista blanca de herramientas y parámetros. |
| Inyección HTML | La interfaz escapa todo texto; el markdown es un subconjunto propio; enlaces sólo http(s) con `noopener`. |
| Cabeceras | CSP restrictiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`. |
| Registro | `registro_operaciones.log`: método, ruta, estado y duración; sin contenidos ni nombres de archivo. |
| Selección de personal | Regla en el prompt: nunca usar ni recomendar atributos protegidos (Fase 2 añade la herramienta específica). |

## API del servidor

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/estado` | Modelo activo (sin claves), aviso de privacidad. |
| GET | `/api/integraciones?comprobar=1` | Catálogo con estado real. |
| GET | `/api/paises` | Países, indicadores y país sugerido. |
| GET/POST | `/api/conversaciones` | Listar / crear. |
| GET/DELETE | `/api/conversaciones/{id}` | Abrir / borrar. |
| POST | `/api/conversaciones/{id}/titulo` · `/preferencias` | Renombrar · país de referencia. |
| POST | `/api/conversaciones/{id}/archivos` | Subir (cuerpo binario + `X-Nombre-Archivo`). Máx. 25 MB. |
| DELETE | `/api/conversaciones/{id}/archivos/{nombre}` | Quitar. |
| GET | `/api/conversaciones/{id}/tablas/{tabla}/vista?filas=N` | Vista previa. |
| POST | `/api/conversaciones/{id}/mensajes` | Pregunta → eventos NDJSON: `plan`, `herramienta`, `evidencias`, `fuentes`, `datos`, `texto`, `aclaracion`, `necesita_llm`, `final`, `error`. |
| POST | `/api/conversaciones/{id}/mensajes/{mid}/completar` | Texto redactado por la IA del navegador (se verifica y guarda). |
| POST | `/api/conversaciones/{id}/investigacion` | Investigación directa (`modo`, `consulta`, `paises`, `indicador`). |
| POST | `/api/conversaciones/{id}/investigaciones/{iid}/guardar` | Marcar como guardada. |
| POST/DELETE | `/api/conversaciones/{id}/memoria[/{mid}]` | Recordar / olvidar. |
| POST | `/api/conversaciones/{id}/limpieza/proponer` · `/aplicar` | Limpieza con aprobación. |
| GET | `/api/conversaciones/{id}/descargas/(archivos|scripts)/{nombre}` | CSV limpio o script. |

## Lo que no cambió

`app/streamlit_app.py`, `app/cli.py` y el resto del núcleo siguen funcionando igual (todas las pruebas previas pasan).
`crear_cliente("falso" | "ollama")` se comporta como antes; se añadieron `"auto"` y los proveedores en la nube.
