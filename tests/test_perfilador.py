import pytest

from dinamo.data_engine import inferir_perfil


def roles(perfil):
    return {c.nombre: c.rol for c in perfil.columnas}


def test_deduce_los_roles_de_una_base_con_tiempo(tabla_panel):
    p = inferir_perfil(tabla_panel, "tiendas")
    assert roles(p) == {"tienda_id": "entidad", "tienda": "nombre_entidad", "mes": "tiempo",
                        "region": "dimension", "ventas": "metrica", "tasa_quejas": "metrica",
                        "valido": "binaria"}
    assert p.entidad_singular == "tienda" and p.entidad_plural == "tiendas"
    assert p.columna("ventas").unidad == "moneda"
    assert p.columna("tasa_quejas").unidad == "proporcion"
    assert p.columna("region").valores == ("Norte", "Sur")


def test_deduce_los_roles_de_una_base_sin_tiempo(tabla_simple):
    p = inferir_perfil(tabla_simple, "empleados")
    assert roles(p) == {"empleado_id": "entidad", "area": "dimension", "salario_mensual": "metrica",
                        "renuncio": "binaria"}
    assert not p.tiene("tiempo")


def test_la_configuracion_manda_sobre_lo_deducido(tabla_panel):
    config = {"nombre": "mis_tiendas", "entidad_singular": "local", "entidad_plural": "locales",
              "columnas": [{"nombre": "valido", "rol": "validez"},
                           {"nombre": "ventas", "rol": "metrica", "etiqueta": "ingresos", "sinonimos": ["facturacion"]}]}
    p = inferir_perfil(tabla_panel, config=config)
    assert p.nombre == "mis_tiendas" and p.entidad_plural == "locales"
    assert p.columna("valido").rol == "validez"
    assert p.columna("ventas").etiqueta == "ingresos" and p.columna("ventas").sinonimos == ("facturacion",)
    assert p.columna("region").rol == "dimension"          # lo no configurado se sigue deduciendo


def test_configuracion_con_columna_inexistente_da_error_claro(tabla_panel):
    with pytest.raises(KeyError):
        inferir_perfil(tabla_panel, config={"columnas": [{"nombre": "no_existe", "rol": "metrica"}]})


def test_verbos_no_se_vuelven_sinonimos(tabla_panel):
    tabla = tabla_panel.assign(tiene_promocion=[0, 1] * 4 + [0])
    p = inferir_perfil(tabla)
    assert "tiene" not in p.columna("tiene_promocion").sinonimos


def test_columnas_sin_variacion_se_ignoran(tabla_simple):
    p = inferir_perfil(tabla_simple.assign(pais="México"))
    assert p.columna("pais").rol == "ignorar"
