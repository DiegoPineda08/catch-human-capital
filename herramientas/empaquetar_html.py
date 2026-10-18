"""
Genera frontend/DINAMO_Fase1.html: la interfaz completa en UN solo archivo
(estilos, scripts e imágenes del avatar incrustados).

    python herramientas/empaquetar_html.py

El archivo necesita el servidor local para funcionar (python -m dinamo.servidor):
ábrelo en http://127.0.0.1:8765/DINAMO_Fase1.html. Abierto con doble clic sólo muestra
el aviso de que falta el servidor, porque el análisis se hace en Python.
"""
import base64
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def incrustar_img(texto: str) -> str:
    def repl(m):
        ruta = FRONT / "img" / m.group(1)
        datos = base64.b64encode(ruta.read_bytes()).decode()
        return f"data:image/webp;base64,{datos}"
    return re.sub(r"img/(\w+\.webp)", repl, texto)


def main():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    css = (FRONT / "estilos.css").read_text(encoding="utf-8")
    graficos = (FRONT / "graficos.js").read_text(encoding="utf-8")
    app = incrustar_img((FRONT / "app.js").read_text(encoding="utf-8"))
    html = html.replace('<link rel="stylesheet" href="estilos.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="graficos.js"></script>', f"<script>\n{graficos}\n</script>")
    html = html.replace('<script src="app.js"></script>', f"<script>\n{app}\n</script>")
    html = incrustar_img(html)
    salida = FRONT / "DINAMO_Fase1.html"
    salida.write_text(html, encoding="utf-8")
    print(f"Generado {salida} ({salida.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
