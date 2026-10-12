"""
Muestra qué entiende DINAMO de un archivo nuevo (cada tabla que encuentra y el rol de cada
columna), y opcionalmente guarda el perfil de una tabla en JSON para corregirlo a mano.

    python -m app.perfilar ejemplos/informe_clima_laboral.pdf
    python -m app.perfilar mi_base.xlsx --tabla mi_base_datos --guardar perfiles/mi_base.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dinamo.data_engine import DataEngine
from dinamo.ingesta import leer_documento


def main() -> None:
    ap = argparse.ArgumentParser(description="Muestra el perfil que DINAMO deduce de un archivo")
    ap.add_argument("archivo")
    ap.add_argument("--tabla", default=None, help="Nombre de la tabla a guardar (si el archivo tiene varias)")
    ap.add_argument("--guardar", default=None, help="Ruta del JSON donde guardar el perfil para editarlo")
    args = ap.parse_args()

    ruta = Path(args.archivo)
    doc = leer_documento(ruta)
    print(f"Archivo: {doc.nombre} ({doc.tipo}) | tablas: {len(doc.tablas)} | fragmentos de texto: {len(doc.fragmentos)}")
    for a in doc.advertencias:
        print(f"  ⚠ {a}")
    elegida = None
    for t in doc.tablas:
        p = DataEngine.desde_tabla(t.tabla, nombre=t.nombre, hoja=t.hoja).perfil
        print(f"\n== Tabla '{t.nombre}' ({t.origen}) | {p.filas} filas | entidad: {p.entidad_singular}")
        print(f"{'columna':<40}{'rol':<17}{'unidad':<12}sinónimos")
        for c in p.columnas:
            print(f"{c.nombre[:38]:<40}{c.rol:<17}{c.unidad:<12}{', '.join(c.sinonimos[:4])}")
        if args.tabla in (None, t.nombre) and elegida is None:
            elegida = (t, p)
    if args.guardar and elegida:
        t, p = elegida
        config = {"archivo": ruta.name, **({"hoja": t.hoja} if t.hoja else {}),
                  **({"tabla": t.nombre} if doc.tipo == "pdf" else {}), **p.a_dict()}
        config.pop("filas", None)
        Path(args.guardar).parent.mkdir(parents=True, exist_ok=True)
        Path(args.guardar).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nPerfil de '{t.nombre}' guardado en {args.guardar}. Edítalo y vuelve a cargar el archivo: "
              "se usará automáticamente.")


if __name__ == "__main__":
    main()
