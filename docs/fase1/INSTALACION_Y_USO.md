# DINAMO Analytics — Instalación y uso (Fase 1)

## Requisitos

- Windows 10/11, macOS o Linux.
- **Python 3.11 o superior** (en Windows, al instalarlo marca «Add python.exe to PATH»).
- Un navegador moderno (Chrome, Edge o Firefox). Para la IA en el navegador hace falta Chrome o Edge con WebGPU.
- Opcional: [Ollama](https://ollama.com) para tener un modelo de lenguaje local (`ollama pull llama3.2`).

## Arranque rápido

**Windows:** doble clic en `INICIAR_DINAMO.bat`.
La primera vez crea un entorno `.venv`, instala las dependencias mínimas (`requirements-servidor.txt`)
y copia `.env.example` a `.env`. Luego abre `http://127.0.0.1:8765` en el navegador.

**macOS / Linux:** `./iniciar_dinamo.sh`

**Manual:**

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-servidor.txt      # Windows: .venv\Scripts\pip ...
cp .env.example .env                                     # opcional
.venv/bin/python -m dinamo.servidor
```

## Versión en un solo archivo

`frontend/DINAMO_Fase1.html` es la misma interfaz con estilos, scripts y avatares incrustados
(se regenera con `python herramientas/empaquetar_html.py`). Necesita el servidor: con DINAMO abierto, entra a
`http://127.0.0.1:8765/DINAMO_Fase1.html`. Si lo abres con doble clic sólo verás el aviso de que falta el servidor,
porque los cálculos, la investigación y la memoria viven en Python.

## ¿Qué modelo de lenguaje usa?

DINAMO siempre calcula con Python; el modelo de lenguaje sólo **redacta**. El servidor elige así (`DINAMO_LLM=auto`):

1. **Ollama** si está abierto en el equipo → los datos no salen del equipo.
2. Si no, el **primer proveedor en la nube con clave** en `.env` (Gemini → Groq → Anthropic → OpenAI).
   En ese caso la pregunta y el material relevante (cifras calculadas, fragmentos, fuentes) **se envían** al proveedor.
   La interfaz lo indica en la barra lateral.
3. Si no hay ninguno, el botón **«Activar IA del navegador»** descarga un modelo pequeño (Qwen2.5 1.5B, ~1 GB, una sola vez)
   que redacta dentro del navegador.
4. Sin ninguno de los tres, DINAMO responde mostrando los cálculos y las fuentes verificadas tal cual (sin redactar).

## Uso

| Sección | Para qué |
|---|---|
| **Conversación** | Pregunta en lenguaje natural. DINAMO decide qué herramientas usar (tus datos, tus documentos, internet, artículos, estadísticas oficiales) y lo muestra paso a paso. Cada cifra lleva un botón `dato`, `doc` o `W1` que abre su origen. |
| **Datos y limpieza** | Vista previa de cada tabla y revisión de calidad: DINAMO propone, tú apruebas cada cambio, se crea un archivo nuevo (`*_limpio_v1.csv`) con su registro y un script de Python que lo reproduce. El original no se toca. |
| **Investigación** | Una sola sección con pestañas: Web general, Artículos científicos, Noticias, Estadísticas oficiales, Documentación técnica y Guardadas. «Analizar en la conversación» lleva la investigación al chat sin repetir la búsqueda. |
| **Integraciones** | Estado real de cada servicio (sólo dice «disponible» tras comprobarlo). |

Cosas que conviene saber:

- **Subir un archivo no dispara nada**: no hay resumen, gráfico, llamada al LLM, investigación ni voz hasta que preguntes.
- **Cada conversación está aislada**: sus archivos, memoria, investigaciones y evidencias no aparecen en otra.
- **Memoria**: escribe «Recuerda que…» o usa el botón ＋ del panel. Vale sólo para ese chat.
- **País de referencia**: se elige en el panel derecho (México es sólo la sugerencia por defecto; nunca se impone).
- **Gráficos**: pide el tipo («gráfico de dispersión entre X e Y», «histograma de X», «evolución de X») o cámbialo con el selector.
- **Voz**: el avatar lee las respuestas con la voz del navegador sólo si lo pides (botón 🔊 o «Leer automáticamente»).
  No hay sincronización labial. El dictado (🎙) rellena el cuadro de texto pero nunca envía solo.
- **Temas**: claro / oscuro / sistema y cuatro acentos (azul, violeta, verde azulado, ámbar) en la barra lateral.

## Variables de entorno

| Variable | Función | Por defecto |
|---|---|---|
| `DINAMO_PUERTO` | Puerto del servidor | `8765` |
| `DINAMO_HOST` | Interfaz de red. Fuera de `127.0.0.1` exige `DINAMO_TOKEN` | `127.0.0.1` |
| `DINAMO_TOKEN` | Token de acceso (cabecera `X-DINAMO-TOKEN` o `/?token=` que deja una cookie HttpOnly) | vacío |
| `DINAMO_DATOS` | Carpeta de conversaciones y archivos subidos | `.dinamo_datos/` |
| `DINAMO_ABRIR_NAVEGADOR` | Abrir el navegador al arrancar (`1`/`0`) | `1` |
| `DINAMO_LLM` | `auto`, `ollama`, `gemini`, `groq`, `anthropic`, `openai` (o `falso` para el CLI) | `auto` |
| `OLLAMA_URL`, `OLLAMA_MODELO` | Servidor y modelo de Ollama (vacío = el primero instalado) | `http://localhost:11434` |
| `GEMINI_API_KEY`, `GEMINI_MODELO` | Google Gemini | `gemini-2.5-flash` |
| `GROQ_API_KEY`, `GROQ_MODELO` | Groq | `llama-3.3-70b-versatile` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODELO` | Claude | `claude-haiku-4-5-20251001` |
| `OPENAI_API_KEY`, `OPENAI_MODELO`, `OPENAI_BASE_URL` | OpenAI o compatible (LM Studio, vLLM…) | `gpt-4o-mini` |
| `TAVILY_API_KEY` | Búsqueda web y noticias sin el límite del modo sin clave | vacío (modo keyless) |
| `BRAVE_API_KEY`, `DINAMO_BUSCADOR` | Brave Search opcional (`DINAMO_BUSCADOR=brave` lo prioriza) | vacío |
| `OPENALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` | Amplían límites académicos | vacío |
| `DINAMO_CORREO_CONTACTO` | Correo para el «polite pool» de Crossref/OpenAlex | vacío |

## Cómo obtener las claves (todas opcionales)

| Servicio | Dónde | Notas |
|---|---|---|
| Gemini | https://aistudio.google.com/apikey | Plan gratuito con límites por minuto/día. Los datos del plan gratuito pueden usarse para mejorar productos de Google: no lo uses con datos confidenciales. |
| Groq | https://console.groq.com/keys | Plan gratuito con límites de frecuencia. |
| Anthropic | https://console.anthropic.com | De pago por uso. |
| OpenAI | https://platform.openai.com/api-keys | De pago por uso. |
| Tavily | https://app.tavily.com | Plan gratuito: 1.000 créditos al mes (búsqueda básica = 1 crédito). |
| Brave Search | https://api-dashboard.search.brave.com | Requiere registro; revisa la cuota gratuita vigente. |
| OpenAlex | https://openalex.org/settings/api | Funciona sin clave; la clave gratuita amplía el presupuesto diario. |

Pega cada clave en `.env` (por ejemplo `GROQ_API_KEY=gsk_...`) y reinicia el servidor.
**Nunca** pegues claves en el chat, en el código ni en GitHub.

## Datos confidenciales

- `.env`, `.dinamo_datos/` y `.venv/` están en `.gitignore`.
- La base del concurso (`data/raw/*.xlsx`) no se usa en las pruebas ni en la demo, y nunca se debe subir.
- Si usas un proveedor en la nube, las preguntas y el material relevante de tus archivos salen del equipo.
  Para datos confidenciales usa Ollama o la IA del navegador.
- Las búsquedas web envían **el texto de la consulta** (no tus archivos) al buscador.
