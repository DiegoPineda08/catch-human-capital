"""
Prueba de interfaz con Playwright (Escenarios A, J, L y O). Se ejecuta aparte de pytest:

    python -m dinamo.servidor            (en otra terminal; DINAMO_ABRIR_NAVEGADOR=0)
    python tests/interfaz/prueba_interfaz.py http://127.0.0.1:8765

Usa sólo ejemplos/empleados.csv (sintético). No necesita internet ni modelo de lenguaje.
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[2]

CONTRASTE_JS = r"""() => {
  const rgb = c => { const m = c.match(/[\d.]+/g).map(Number); return m.slice(0, 3); };
  const lum = c => { const v = rgb(c).map(x => { x /= 255; return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4); });
                     return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
  const fondo = el => { while (el) { const b = getComputedStyle(el).backgroundColor; const a = (b.match(/rgba\([^)]*,\s*([\d.]+)\)/) || [0, 1])[1]; if (b && b !== 'transparent' && +a >= 0.5) return b; el = el.parentElement; } return 'rgb(255,255,255)'; };
  const sel = ['body', '.nav-item', '.nav-item.activo', '#tituloConv', '.btn.primario', '.burbuja-usuario .txt', '.capitulo .relato p',
               '.cap-tag', '.ref', '.kpi .k-val', '.rail-card-head strong', '.rail-fact span', '.rail-tool b', '.avatar-panel-id strong',
               '.assistant-avatar-option span', '.research-head-btn', '.reciente', '#estadoLLM', '.sugerencia', '.rail-doc-text b'];
  return sel.map(s => { const el = document.querySelector(s); if (!el) return null;
    return [s, +ratio(getComputedStyle(el).color, fondo(el)).toFixed(2)]; }).filter(Boolean);
}"""


async def main():
    fallos = []
    async with async_playwright() as p:
        nav = await p.chromium.launch()
        ctx = await nav.new_context(viewport={"width": 1440, "height": 900}, bypass_csp=True)
        pg = await ctx.new_page()
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        await pg.goto(BASE)
        await pg.click("#btnNueva")
        await pg.wait_for_selector(".bienvenida")
        await pg.wait_for_timeout(500)

        # A: subir no genera mensajes
        await pg.set_input_files("#inputArchivos", str(RAIZ / "ejemplos" / "empleados.csv"))
        await pg.wait_for_timeout(1500)
        if await pg.locator("#hilo .capitulo, #hilo .burbuja-usuario").count() != 0:
            fallos.append("A: subir un archivo generó mensajes")

        # J: histograma pedido explícitamente
        await pg.fill("#entrada", "muéstrame un histograma del salario mensual por empleado")
        await pg.keyboard.press("Enter")
        await pg.wait_for_selector(".capitulo .cap-acciones", timeout=30000)
        await pg.wait_for_timeout(500)
        tipo = await pg.locator(".grafica-bloque .barra-graf select").last.input_value() if await pg.locator(".grafica-bloque .barra-graf select").count() else None
        print("J: tipo de gráfico mostrado:", tipo)

        # L: callar la voz no desactiva el dictado (controles independientes)
        await pg.click("#btnAvatarStop")
        if await pg.locator("#btnDictar").is_disabled():
            fallos.append("L: el dictado quedó deshabilitado al callar la voz")

        # O: 4 acentos × claro/oscuro, contraste mínimo 4.5 (texto) / 3 (insignias y citas)
        for tema in ("light", "dark"):
            if await pg.evaluate("document.documentElement.dataset.theme") != tema:
                await pg.click("#btnTema")
            for acento in ("azul", "violeta", "verde", "ambar"):
                await pg.click(f'.acentos button[data-acento="{acento}"]')
                await pg.wait_for_timeout(120)
                for selector, r in await pg.evaluate(CONTRASTE_JS):
                    minimo = 3.0 if selector in (".ref", ".cap-tag", ".rail-fact span", "#estadoLLM", ".reciente") else 4.5
                    if r < minimo:
                        fallos.append(f"O: {tema}/{acento} {selector} contraste {r} < {minimo}")
                await pg.screenshot(path=str(RAIZ / ".dinamo_datos" / f"tema_{tema}_{acento}.png"))
        if errores:
            fallos.append("Errores de JavaScript: " + "; ".join(errores))
        await nav.close()
    print("\n".join(fallos) if fallos else "Interfaz: todas las comprobaciones pasaron.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
