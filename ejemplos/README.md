# Carpeta ejemplos/

Archivos PÚBLICOS e INVENTADOS para probar que DINAMO funciona con fuentes distintas a la del
concurso. Sí se suben a GitHub (no tienen datos reales) y los usan los tests.

| Archivo | Formato | Qué contiene | Para probar |
|---|---|---|---|
| `ventas_tiendas.csv` | CSV | 8 tiendas x 12 meses: ventas, clientes, ticket, satisfacción, devoluciones | tiempo + entidades + categorías |
| `empleados.csv` | CSV | 120 empleados: área, nivel, salario, antigüedad, satisfacción, si renunció | una base SIN tiempo |
| `informe_clima_laboral.pdf` | PDF | Informe ficticio de 2 páginas con texto y una tabla (4 áreas x 4 trimestres) | leer PDF: tabla y texto |

Si agregas un ejemplo nuevo, que sea inventado, súmalo a esta tabla y escribe un test en `tests/test_ejemplos.py`.
