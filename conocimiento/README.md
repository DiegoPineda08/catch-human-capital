# Base de conocimiento del RAC

Textos escritos por el equipo que el RAC le entrega al LLM como contexto.

- `general/`: reglas que sirven para CUALQUIER fuente (cómo interpretar, qué no afirmar).
- `<nombre de la tabla>/`: conocimiento escrito a mano para UNA tabla. La carpeta debe llamarse
  igual que el `"nombre"` de su perfil (por ejemplo `catch_capital_humano/`).

Cada archivo `.md` se divide en fragmentos por sus títulos `## `. Escribe 2 a 6 frases por título.

Además, el RAC indexa solo (sin escribir nada aquí):
- un fragmento por cada columna de cada tabla cargada (sale del perfil);
- el texto de los documentos que cargue el usuario (PDF, .md, .txt).
