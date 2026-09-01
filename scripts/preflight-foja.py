#!/usr/bin/env python3
"""Preflight read-only de una foja/cómputo XLSX antes de importarla en Odoo.

Uso:
  .venv/bin/python scripts/preflight-foja.py "archivo.xlsx"
  .venv/bin/python scripts/preflight-foja.py "archivo.xlsx" --output informe.md

No crea registros: solo usa el mismo parser que coop.foja.import para exponer
la hoja elegida, columnas, nivel sugerido, total y avisos que requieren revisión.
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(REPO, 'addons', 'coop_construction', 'models')
sys.path.insert(0, MODELS)
import foja_parser as fp  # noqa: E402


def moneda(valor):
    if valor is None:
        return '—'
    return '$ {:,.2f}'.format(valor).replace(',', 'X').replace('.', ',').replace('X', '.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archivo', help='Ruta a la foja/cómputo .xlsx')
    parser.add_argument('--output', help='Archivo Markdown donde guardar el informe')
    args = parser.parse_args()

    archivo = os.path.abspath(args.archivo)
    if not os.path.isfile(archivo):
        parser.error('No existe el archivo: %s' % archivo)
    if not archivo.lower().endswith('.xlsx'):
        parser.error('El preflight solo acepta archivos .xlsx')

    resultado = fp.parse_foja(archivo)
    nivel = resultado['nivel_sugerido']
    importables = fp.filas_importables(resultado, nivel)
    avisos_filas = [
        'Fila %s (%s): %s' % (fila['fila'], fila['codigo'] or 'sin código', aviso)
        for fila in importables
        for aviso in fila['avisos']
    ]

    lineas = [
        '# Preflight de foja de medición',
        '',
        '- **Archivo:** `%s`' % archivo,
        '- **Hoja elegida:** `%s`' % resultado['hoja'],
        '- **Hojas disponibles:** %s' % ', '.join('`%s`' % h for h in resultado['hojas']),
        '- **Fila de encabezado:** %s' % (resultado['encabezado_fila'] or 'no encontrada'),
        '- **Columnas detectadas:** %s' % (', '.join(sorted(resultado['columnas'])) or 'ninguna'),
        '- **Nivel sugerido:** %s (%s)' % (
            nivel if nivel is not None else 'ninguno',
            resultado.get('nivel_sugerido_motivo') or 'sin filas importables'),
        '- **Total declarado:** %s' % moneda(resultado.get('total_declarado')),
        '- **Filas importables en nivel sugerido:** %d' % len(importables),
        '- **Total importable en nivel sugerido:** %s' % moneda(sum(f['importe_final'] for f in importables)),
        '',
        '## Totales por nivel',
        '',
        '| Nivel | Ítems | Importe |',
        '|---:|---:|---:|',
    ]
    for nivel_num, datos in sorted(resultado['niveles'].items()):
        lineas.append('| %d | %d | %s |' % (nivel_num, datos['n'], moneda(datos['importe'])))

    lineas += ['', '## Avisos del archivo', '']
    if resultado['avisos']:
        lineas.extend('- %s' % aviso for aviso in resultado['avisos'])
    else:
        lineas.append('- Ninguno.')

    lineas += ['', '## Avisos de filas que se importarían', '']
    if avisos_filas:
        lineas.extend('- %s' % aviso for aviso in avisos_filas)
    else:
        lineas.append('- Ninguno.')

    lineas += [
        '',
        '## Decisión humana requerida',
        '',
        'Este informe no importa ni corrige la foja. Antes de crear ítems en una obra,',
        'confirmar que el nivel sugerido no duplica importes y que los avisos de cada fila',
        'representan el cómputo real, no una plantilla o una fórmula rota.',
        '',
    ]
    informe = '\n'.join(lineas)

    if args.output:
        salida = os.path.abspath(args.output)
        with open(salida, 'w', encoding='utf-8') as f:
            f.write(informe)
        print('Informe escrito:', salida)
    else:
        print(informe)


if __name__ == '__main__':
    main()
