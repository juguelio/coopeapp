"""Tests de integración del wizard `coop.foja.import`.

El parser ya está cubierto por `test_foja_parser.py`, que corre sin Odoo. Acá
se prueba el wizard: lo que pasa cuando alguien aprieta el botón sobre una
obra de verdad, con ítems que ya pueden tener trabajo medido encima.

El caso que sostiene todo lo demás es el de `reemplazar=True`: la foja no es
una tabla cualquiera. La incidencia de cada ítem mueve el % de avance de la
obra y el aporte de cada socio, y un ítem con avances cargados es trabajo que
alguien ya midió. La guarda que impide borrarlo es lo único que separa una
reimportación de perder la producción de un socio.
"""

import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def _planilla(filas):
    """Arma un .xlsx en memoria con el mismo encabezado que espera el parser."""
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


@tagged('post_install', '-at_install')
class TestFojaImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra Import', 'is_coop_obra': True})
        partner = cls.env['res.partner'].create({'name': 'Socio Foja'})
        cls.socio = cls.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': 'Socio Foja', 'dni': '31555444',
                'partner_id': partner.id})

    # ── helpers ──────────────────────────────────────────────────────
    def _wizard(self, filas, **extra):
        vals = {
            'obra_id': self.obra.id,
            'nombre_archivo': 'computo.xlsx',
            'archivo': base64.b64encode(_planilla(filas).read()),
        }
        vals.update(extra)
        return self.env['coop.foja.import'].create(vals)

    def _filas_base(self):
        return [
            ['A', 'ALBAÑILERÍA'],
            [1.0, 'Mampostería', 'm2', 100, 500.0, 50000.0],
            [2.0, 'Revoque', 'm2', 80, 300.0, 24000.0],
        ]

    def _items(self):
        return self.env['coop.foja.item'].search(
            [('obra_id', '=', self.obra.id)])

    # ── el camino feliz, para que lo demás signifique algo ───────────
    def test_importa_los_items_del_computo(self):
        w = self._wizard(self._filas_base())
        w.action_analizar()
        self.assertTrue(w.analizado)
        self.assertTrue(w.linea_ids, 'el análisis tiene que traer filas')
        w.action_importar()
        items = self._items()
        self.assertEqual(len(items), 2)
        self.assertEqual(sorted(items.mapped('item')), ['1.0', '2.0'])
        m = items.filtered(lambda i: i.item == '1.0')
        self.assertEqual(m.name, 'Mampostería')
        self.assertEqual(m.cantidad, 100)
        self.assertEqual(m.precio_unitario, 500.0)

    # ── LA GUARDA: no borrar trabajo medido ──────────────────────────
    def test_reemplazar_no_borra_items_con_avances(self):
        """Reimportar con reemplazar=True sobre un ítem que ya tiene avances
        tiene que fallar, y no borrar NADA."""
        w = self._wizard(self._filas_base())
        w.action_analizar()
        w.action_importar()
        item = self._items().filtered(lambda i: i.item == '1.0')

        self.env['coop.avance.medicion'].create({
            'foja_item_id': item.id, 'member_id': self.socio.id,
            'cantidad': 10, 'medida_trabajo': 'jornal',
            'cantidad_trabajo': 2})

        ids_antes = set(self._items().ids)
        w2 = self._wizard(self._filas_base(), reemplazar=True)
        w2.action_analizar()
        with self.assertRaises(UserError) as cm:
            w2.action_importar()
        self.assertIn('avances cargados', str(cm.exception))
        # que falle no alcanza: lo que importa es que no se borró nada
        self.assertEqual(set(self._items().ids), ids_antes,
                         'no se puede borrar ningún ítem si la guarda saltó')
        self.assertTrue(item.exists(), 'el ítem con avances sigue vivo')
        self.assertEqual(len(item.avance_ids), 1, 'el avance sigue vivo')

    def test_reemplazar_sin_avances_si_borra(self):
        """Sin trabajo medido encima, reemplazar es seguro y tiene que andar."""
        w = self._wizard(self._filas_base())
        w.action_analizar()
        w.action_importar()
        viejos = set(self._items().ids)
        self.assertEqual(len(viejos), 2)

        w2 = self._wizard([
            ['A', 'ALBAÑILERÍA'],
            [9.0, 'Otra cosa', 'ml', 5, 100.0, 500.0],
        ], reemplazar=True)
        w2.action_analizar()
        w2.action_importar()
        items = self._items()
        self.assertEqual(items.mapped('item'), ['9.0'])
        self.assertFalse(set(items.ids) & viejos, 'los viejos se borraron')

    def test_reimportar_sin_reemplazar_actualiza_y_no_duplica(self):
        """El mismo código de ítem se actualiza en lugar de duplicarse: si no,
        cada reimportación inflaría la foja y con ella el total de la obra."""
        w = self._wizard(self._filas_base())
        w.action_analizar()
        w.action_importar()
        self.assertEqual(len(self._items()), 2)

        w2 = self._wizard([
            ['A', 'ALBAÑILERÍA'],
            [1.0, 'Mampostería corregida', 'm2', 120, 550.0, 66000.0],
        ])
        w2.action_analizar()
        w2.action_importar()
        items = self._items()
        self.assertEqual(len(items), 2, 'no se duplica el 1.0')
        m = items.filtered(lambda i: i.item == '1.0')
        self.assertEqual(m.name, 'Mampostería corregida')
        self.assertEqual(m.cantidad, 120)

    # ── el wizard no deja apretar el botón fuera de orden ────────────
    def test_importar_sin_analizar_no_se_puede(self):
        w = self._wizard(self._filas_base())
        with self.assertRaises(UserError) as cm:
            w.action_importar()
        self.assertIn('Analizá el archivo', str(cm.exception))
        self.assertFalse(self._items(), 'no se creó ningún ítem')

    def test_sin_filas_tildadas_no_importa(self):
        w = self._wizard(self._filas_base())
        w.action_analizar()
        w.linea_ids.write({'importar': False})
        with self.assertRaises(UserError) as cm:
            w.action_importar()
        self.assertIn('tildada', str(cm.exception))
        self.assertFalse(self._items())

    def test_archivo_ilegible_avisa_que_tiene_que_ser_xlsx(self):
        w = self.env['coop.foja.import'].create({
            'obra_id': self.obra.id, 'nombre_archivo': 'foto.jpg',
            'archivo': base64.b64encode(b'esto no es un xlsx')})
        with self.assertRaises(UserError) as cm:
            w.action_analizar()
        self.assertIn('.xlsx', str(cm.exception))

    def test_las_filas_con_aviso_llegan_destildadas(self):
        """El precio unitario roto (2.47e-08 en el archivo real) tiene que
        llegar marcado y SIN tildar: que la persona lo mire antes."""
        w = self._wizard([
            ['A', 'ALBAÑILERÍA'],
            [1.0, 'Mampostería', 'm2', 100, 500.0, 50000.0],
            [2.0, 'Con unidad rara', 'bolsa', 10, 100.0, 1000.0],
        ])
        w.action_analizar()
        con_aviso = w.linea_ids.filtered('aviso')
        self.assertTrue(con_aviso, 'la unidad desconocida tiene que avisar')
        self.assertFalse(any(con_aviso.mapped('importar')),
                         'las filas con aviso llegan destildadas')
