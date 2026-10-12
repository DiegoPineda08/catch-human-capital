"""
Presentación v0: conversación por la terminal (consola).

    python -m app.cli                                    # carga todo lo que haya en data/ (o en ejemplos/)
    python -m app.cli --archivo ejemplos/ventas_tiendas.csv --archivo ejemplos/informe_clima_laboral.pdf
    python -m app.cli --usuario "Ana" --rol "Gerente de RR. HH." --nivel directivo
    python -m app.cli --llm ollama "¿Cómo han evolucionado las ventas?"     # una sola pregunta

Dentro de la conversación:
    escribe una pregunta, o el número de una sugerencia/opción (1, 2, 3...)
    cargar <ruta>   agrega un archivo sin reiniciar
    salir           termina
"""
from __future__ import annotations

import argparse
from dataclasses import replace

from dinamo.core.config import Config
from dinamo.core.contracts import PerfilUsuario
from dinamo.llm import formatear_valor
from dinamo.sistema import construir_sistema


def imprimir(resp, detalle: bool = True) -> None:
    p = resp.plan
    if detalle:
        print(f"\n[Plan] fuente={p.tabla} | intención={p.intencion} | métricas={list(p.metricas)} | "
              f"agrupar por={p.dimension} | filtros={p.filtros} | skills={list(p.skills)} | confianza={p.confianza}")
        print(f"[Contexto] {[c.fuente for c in resp.contexto]}")
    print("\n" + resp.texto + "\n")
    if detalle and resp.evidencias:
        print("[Evidencia]")
        for e in resp.evidencias:
            print(f"  {e.id:<26} {formatear_valor(e):>26}  {e.descripcion} (n={e.n})")
    for a in resp.advertencias:
        print(f"  ⚠ {a}")
    if resp.sugerencias and resp.aclaracion is None:
        print("\n[Puedes preguntar]")
        for i, s in enumerate(resp.sugerencias, start=1):
            print(f"  {i}. {s}")


def main() -> None:
    ap = argparse.ArgumentParser(description="DINAMO_ANALITICS — conversación por consola")
    ap.add_argument("pregunta", nargs="*")
    ap.add_argument("--archivo", action="append", default=None,
                    help="Excel, CSV, PDF, .md o .txt. Repite --archivo para cargar varios")
    ap.add_argument("--llm", choices=["falso", "ollama"], default=None)
    ap.add_argument("--usuario", default="", help="Nombre de quien pregunta")
    ap.add_argument("--rol", default="", help="Cargo de quien pregunta, p.ej. 'Gerente de RR. HH.'")
    ap.add_argument("--nivel", choices=["general", "directivo", "analista"], default="general")
    ap.add_argument("--simple", action="store_true", help="Oculta plan, contexto y evidencia")
    args = ap.parse_args()

    config = Config()
    if args.llm:
        config = replace(config, llm_proveedor=args.llm)
    usuario = PerfilUsuario(nombre=args.usuario, rol=args.rol, nivel=args.nivel)
    brain = construir_sistema(config, archivos=args.archivo, usuario=usuario)
    detalle = not args.simple

    if args.pregunta:
        imprimir(brain.responder(" ".join(args.pregunta)), detalle)
        return
    inicio = brain.bienvenida()
    imprimir(inicio, detalle=False)
    sugerencias = inicio.sugerencias
    print("Escribe tu pregunta, el número de una opción, 'cargar <ruta>' o 'salir'.")
    while True:
        q = input("\nPregunta: ").strip()
        if q.lower() in {"salir", "exit", "q"}:
            break
        if q.lower().startswith("cargar "):
            nuevas = brain.cargar_archivo(q[7:].strip().strip('"'))
            print(f"Cargado. Tablas nuevas: {nuevas or 'ninguna (sólo texto)'}")
            continue
        pendiente = brain.estado.aclaracion_pendiente
        if q.isdigit() and pendiente is None and 1 <= int(q) <= len(sugerencias):
            q = sugerencias[int(q) - 1]
            print(f"→ {q}")
        if q:
            resp = brain.responder(q)
            imprimir(resp, detalle)
            sugerencias = resp.sugerencias or sugerencias


if __name__ == "__main__":
    main()
