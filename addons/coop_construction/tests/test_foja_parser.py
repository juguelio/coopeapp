"""Tests del parser de cómputos.

Corren sin Odoo — `foja_parser` no lo importa a propósito. Se pueden correr con
`python3 -m pytest addons/coop_construction/tests/test_foja_parser.py` o con
`python3 addons/coop_construction/tests/test_foja_parser.py`.

Los casos no son inventados: son los cuatro problemas que aparecieron al leer
el cómputo real de Carriqueo.
"""

import datetime
import io
import os
import sys
import unittest

try:  # corriendo dentro de Odoo
    from odoo.addons.coop_construction.models import foja_parser as fp
except ImportError:  # corriendo suelto, sin Odoo
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'models'))
    import foja_parser as fp  # noqa: E402


class TestCodigos(unittest.TestCase):

    def test_rubro_es_una_letra(self):
        self.assertEqual(fp.codigo_de_celda('A')[:2], ('A', 0))
        self.assertEqual(fp.codigo_de_celda('B')[1], 0)

    def test_nivel_1_llega_como_numero(self):
        cod, nivel, _ = fp.codigo_de_celda(1.0)
        self.assertEqual((cod, nivel), ('1.0', 1))
        cod, nivel, _ = fp.codigo_de_celda(5)
        self.assertEqual((cod, nivel), ('5.0', 1))

    def test_subitem_como_texto(self):
        cod, nivel, aviso = fp.codigo_de_celda('2.10')
        self.assertEqual((cod, nivel), ('2.10', 2))
        self.assertIsNone(aviso)

    def test_excel_convirtio_el_codigo_en_fecha(self):
        """5.1 quedó guardado como 05/01/2023. Se recupera y se avisa."""
        cod, nivel, aviso = fp.codigo_de_celda(
            datetime.datetime(2023, 1, 5))
        self.assertEqual(cod, '5.1')
        self.assertEqual(nivel, 2)
        self.assertIn('fecha', aviso)

    def test_excel_se_comio_el_cero_final(self):
        """1.10 llega como el float 1.1 y se pierde el orden. Avisa."""
        cod, nivel, aviso = fp.codigo_de_celda(1.1)
        self.assertEqual(nivel, 2)
        self.assertIsNotNone(aviso)
        self.assertIn('cero', aviso)


class TestNumeros(unittest.TestCase):

    def test_formatos_de_numero(self):
        self.assertEqual(fp._num('1.234,56'), 1234.56)
        self.assertEqual(fp._num('1,234.56'), 1234.56)
        self.assertEqual(fp._num('$ 1.000'), 1000.0)
        self.assertEqual(fp._num(''), None)
        self.assertEqual(fp._num('no es un número'), None)

    def test_unidades(self):
        self.assertEqual(fp.normalizar_uom('Gl'), ('gl', False))
        self.assertEqual(fp.normalizar_uom('m²'), ('m2', False))
        self.assertEqual(fp.normalizar_uom('ML'), ('ml', False))
        self.assertEqual(fp.normalizar_uom('bolsa')[0], 'otro')
        self.assertTrue(fp.normalizar_uom('bolsa')[1], 'avisa que adivinó')


def _planilla(filas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['FOJA DE MEDICIÓN'])
    ws.append([])
    ws.append(['Ítem', 'Descripción', 'U.', 'Cant.', 'Precio Unitario',
               'Precio Total'])
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestParseo(unittest.TestCase):

    def test_doble_conteo_se_detecta_y_no_se_decide_solo(self):
        """El rubro y sus subítems traen importe los dos: sumarlos cuenta la
        obra dos veces. El parser avisa, no elige por su cuenta."""
        r = fp.parse_foja(_planilla([
            ['A', 'ALBAÑILERÍA'],
            [1.0, 'Mampostería', 'Gl', 1, None, 1000.0],
            ['1.1', 'Pared exterior', 'm2', 100, None, 600.0],
            ['1.2', 'Pared interior', 'm2', 50, None, 400.0],
        ]))
        self.assertEqual(r['niveles'][1]['importe'], 1000.0)
        self.assertEqual(r['niveles'][2]['importe'], 1000.0)
        self.assertTrue(any('dos veces' in a for a in r['avisos']))

    def test_el_total_declarado_desempata(self):
        r = fp.parse_foja(_planilla([
            ['A', 'ALBAÑILERÍA'],
            [1.0, 'Mampostería', 'Gl', 1, None, 1000.0],
            ['1.1', 'Pared', 'm2', 100, None, 250.0],
            ['', 'Total', '', '', '', 1000.0],
        ]))
        self.assertEqual(r['total_declarado'], 1000.0)
        self.assertEqual(r['nivel_sugerido'], 1)
        self.assertIn('total declarado', r['nivel_sugerido_motivo'])

    def test_sin_total_la_sugerencia_se_declara_corazonada(self):
        r = fp.parse_foja(_planilla([
            [1.0, 'Mampostería', 'Gl', 1, None, 1000.0],
        ]))
        self.assertIn('corazonada', r['nivel_sugerido_motivo'])

    def test_el_importe_le_gana_al_unitario_roto(self):
        """En el archivo real, la columna de unitario traía 2.47e-08 mientras
        la de importe tenía el número bueno. Confiar en el unitario habría
        importado la obra en cero."""
        r = fp.parse_foja(_planilla([
            [1.0, 'Pintura', 'Gl', 1, 2.47408397e-08, 5200000.0],
        ]))
        filas = fp.filas_importables(r, nivel=1)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['precio_unitario_final'], 5200000.0)
        self.assertTrue(any('Revisalo' in a for a in filas[0]['avisos']),
                        'tiene que avisar que los dos números no cierran')

    def test_una_fila_sin_importe_no_entra(self):
        r = fp.parse_foja(_planilla([
            [1.0, 'Sin plata', 'Gl', 1, None, None],
        ]))
        self.assertEqual(fp.filas_importables(r, nivel=1), [])

    def test_rubro_no_es_item(self):
        r = fp.parse_foja(_planilla([
            ['A', 'REMODELACIÓN'],
            [1.0, 'Desarme', 'Gl', 1, None, 100.0],
        ]))
        clases = [f['clase'] for f in r['filas']]
        self.assertEqual(clases, ['rubro', 'item'])
        self.assertEqual(r['filas'][1]['rubro'], 'REMODELACIÓN')


class TestArchivoReal(unittest.TestCase):
    """Contra el cómputo de Carriqueo, si está disponible."""

    RUTA = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                        'carriqueo foja medicion.xlsx')

    def setUp(self):
        if not os.path.exists(self.RUTA):
            self.skipTest('no está el archivo de Carriqueo')

    def test_lee_la_solapa_correcta_y_encuentra_los_rubros(self):
        r = fp.parse_foja(self.RUTA)
        self.assertEqual(r['hoja'], 'FOJA_MEDICION')
        self.assertEqual(r['encabezado_fila'], 15)
        filas = fp.filas_importables(r, nivel=1)
        codigos = [f['codigo'] for f in filas]
        self.assertIn('1.0', codigos)
        self.assertIn('2.0', codigos)
        # el total de nivel 1 coincide con el de la solapa RESUMEN:
        # 13.519.000 materiales + 16.500.000 mano de obra + 10.400.000 gastos
        self.assertAlmostEqual(
            sum(f['importe_final'] for f in filas), 40419000.0, places=2)

    def test_detecta_los_codigos_comidos_por_excel(self):
        r = fp.parse_foja(self.RUTA)
        recuperados = [f for f in r['filas']
                       if any('fecha' in a for a in f['avisos'])]
        self.assertTrue(recuperados, 'tiene filas con el código hecho fecha')
        self.assertIn('5.1', [f['codigo'] for f in recuperados])


if __name__ == '__main__':
    unittest.main(verbosity=2)
