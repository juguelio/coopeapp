#!/usr/bin/env python3
"""Detecta xmlids referenciados ANTES de definirse, según el orden del manifest.

Por qué existe: el 24/08 una instalación desde cero falló porque
`views/coop_pedido_views.xml` (posición 9 del manifest) colgaba dos menuitems
de `menu_coop_economia` y `menu_coop_config`, que se definen en
`views/coop_construction_menus.xml` (posición 11).

Nadie lo había notado en meses porque producción viene de una instalación
vieja y desde entonces solo se hizo `-u`, que no vuelve a resolver el orden.
El bug solo aparece al instalar de cero — o sea, justo el día que haya que
levantar un entorno nuevo o reconstruir después de un desastre.

Corre sin Odoo y sin red:

    python3 scripts/check-xml-order.py
"""

import ast
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'addons')
CONTENEDORES = ('record', 'menuitem', 'template', 'act_window', 'report')
ATRIBUTOS = ('ref', 'parent', 'action', 'search_view_id', 'view_id',
             'binding_model_id')
# Odoo los genera solo a partir de los modelos; no viven en ningún XML.
AUTOGENERADOS = re.compile(r'^model_')


def revisar(modulo: str) -> list:
    ruta = os.path.join(RAIZ, modulo)
    manifest = os.path.join(ruta, '__manifest__.py')
    if not os.path.exists(manifest):
        return []
    datos = ast.literal_eval(io.open(manifest, encoding='utf-8').read())
    archivos = [f for f in datos.get('data', []) if f.endswith('.xml')]
    definidos, problemas = set(), []
    for archivo in archivos:
        p = os.path.join(ruta, archivo)
        if not os.path.exists(p):
            problemas.append((archivo, '(el archivo no existe)', '', ''))
            continue
        root = ET.parse(p).getroot()
        locales = {el.get('id') for el in root.iter()
                   if el.tag in CONTENEDORES and el.get('id')}
        for el in root.iter():
            for attr in ATRIBUTOS:
                v = el.get(attr)
                if not v or not re.fullmatch(r'[A-Za-z_][\w.]*', v):
                    continue
                if '.' in v and not v.startswith(modulo + '.'):
                    continue  # de otro módulo: lo resuelve la dependencia
                base = v.split('.')[-1]
                if AUTOGENERADOS.match(base):
                    continue
                if base in locales or base in definidos:
                    continue
                problemas.append(
                    (archivo, el.get('id') or '<%s>' % el.tag, attr, v))
        definidos |= locales
    return problemas


def main() -> int:
    modulos = sorted(d for d in os.listdir(RAIZ)
                     if os.path.isdir(os.path.join(RAIZ, d)))
    total = 0
    for m in modulos:
        problemas = revisar(m)
        if not problemas:
            continue
        total += len(problemas)
        print('✗ %s' % m)
        for archivo, quien, attr, v in problemas:
            print('    %s → %s tiene %s="%s", que se define después'
                  % (archivo, quien, attr, v))
    if total:
        print('\n%d referencia(s) adelantada(s). El módulo NO se puede '
              'instalar desde cero.' % total)
        print('Solución: mover la definición antes en el manifest, o mover '
              'quien la referencia después.')
        return 1
    print('✓ Ningún xmlid se referencia antes de definirse.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
