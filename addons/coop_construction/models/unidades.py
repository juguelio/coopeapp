"""Cómo se escriben las cantidades con su unidad en la app.

Las etiquetas de los `selection` son descriptivas y sirven para el backoffice
("Hora trabajada", "Unidad"), pero quedan mal pegadas a un número: "7 Hora
trabajada", "6 Unidad". Acá viven singular y plural de cada unidad, en un solo
lugar, para que la app hable como habla la gente en la obra.

Vive suelto y no colgado de un modelo porque lo usan dos modelos distintos
(`coop.trabajo.otro` y `coop.pedido.material`) y antes cada uno resolvía —o no
resolvía— el problema por su cuenta.
"""

# Unidades de trabajo (coop.avance.medicion, coop.trabajo.otro)
MEDIDA_CORTA = {
    'jornal': ('jornal', 'jornales'),
    'hora': ('hora', 'horas'),
    'tarea': ('tarea', 'tareas'),
}

# Unidades de compra (coop.material, coop.pedido.material). Las que ya son
# símbolo —m², m³— no se pluralizan: "6 m²", no "6 m²s".
UOM_COMPRA_CORTA = {
    'bolsa': ('bolsa', 'bolsas'),
    'm3': ('m³', 'm³'),
    'unidad': ('unidad', 'unidades'),
    'barra': ('barra', 'barras'),
    'lata': ('lata', 'latas'),
    'ml': ('metro lineal', 'metros lineales'),
    'm2': ('m²', 'm²'),
    'otro': ('unidad', 'unidades'),
}


def texto_cantidad(cantidad, clave, tabla) -> str:
    """'7 horas', '1 jornal', '6 unidades', '5 m³'.

    Si aparece una clave que no está en la tabla, la devuelve cruda en vez de
    romper: es una etiqueta de pantalla, no vale tirar una excepción por eso.
    """
    singular, plural = tabla.get(clave, (clave, clave))
    return '%g %s' % (cantidad, singular if abs(cantidad) == 1 else plural)


def texto_trabajo(cantidad, medida) -> str:
    """Cantidad de trabajo: jornales, horas o tareas."""
    return texto_cantidad(cantidad, medida, MEDIDA_CORTA)


def texto_compra(cantidad, uom) -> str:
    """Cantidad de material: bolsas, barras, m³…"""
    return texto_cantidad(cantidad, uom, UOM_COMPRA_CORTA)
