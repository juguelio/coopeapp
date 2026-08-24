"""Wizard para cargar una foja de medición desde el cómputo y presupuesto.

Por qué es un wizard de dos pasos y no un botón de "importar":

Un cómputo trae la estructura que le dio quien lo armó. Sobre el archivo real
de Carriqueo, el parser encontró que los rubros de nivel 1 y sus subítems
traían importe los dos (sumarlos cuenta la obra dos veces), que los subítems
eran restos de una plantilla de agua y cloacas en una remodelación de oficinas,
que Excel había convertido "5.1" en la fecha 05/01/2023, y que la columna de
precio unitario traía 2.47e-08 en cinco rubros mientras la de importe tenía el
número bueno.

Ninguna de esas cuatro cosas la puede decidir un programa. Y equivocarse no es
gratis: la incidencia de cada ítem es la que después mueve el % de avance de la
obra y el aporte de cada socio. Por eso el wizard **muestra lo que entendió,
avisa lo que le resultó raro, y espera**.
"""

import base64
import io

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from . import foja_parser


class CoopFojaImport(models.TransientModel):
    _name = 'coop.foja.import'
    _description = 'Importar foja de medición desde cómputo (.xlsx)'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)])
    archivo = fields.Binary(string='Cómputo y presupuesto (.xlsx)',
                            required=True)
    nombre_archivo = fields.Char(string='Nombre del archivo')
    hoja = fields.Char(string='Solapa', readonly=True)
    hojas_disponibles = fields.Char(string='Solapas del archivo', readonly=True)
    nivel = fields.Integer(
        string='Nivel de numeración a importar', default=1,
        help='1 = los rubros (1.0, 2.0). 2 = los subítems (1.1, 1.2). '
             'Importar los dos cuenta la obra dos veces.')
    resumen = fields.Text(string='Qué se entendió', readonly=True)
    linea_ids = fields.One2many(
        'coop.foja.import.linea', 'wizard_id', string='Filas')
    analizado = fields.Boolean(default=False)
    reemplazar = fields.Boolean(
        string='Reemplazar la foja actual',
        help='Borra los ítems de foja de la obra que todavía no tengan '
             'avances cargados. Los que ya tienen avances nunca se borran.')

    # ── paso 1: leer y mostrar ───────────────────────────────────────
    def action_analizar(self):
        self.ensure_one()
        if not self.archivo:
            raise UserError(_('Subí el archivo primero.'))
        try:
            datos = foja_parser.parse_foja(
                io.BytesIO(base64.b64decode(self.archivo)))
        except Exception as e:  # archivo corrupto, no-xlsx, etc.
            raise UserError(_(
                'No se pudo leer el archivo: %s\n\n'
                'Tiene que ser un .xlsx (no .xls ni .pdf ni una foto de la '
                'planilla).') % e)
        if not datos['filas']:
            raise UserError(_(
                'Se leyó la solapa "%s" pero no se encontró ninguna fila de '
                'ítems.\n\nSolapas del archivo: %s'
            ) % (datos['hoja'], ', '.join(datos['hojas'])))

        nivel = self.nivel or datos.get('nivel_sugerido') or 1
        filas = foja_parser.filas_importables(datos, nivel=nivel)
        self.linea_ids.unlink()
        self.write({
            'hoja': datos['hoja'],
            'hojas_disponibles': ', '.join(datos['hojas']),
            'nivel': nivel,
            'analizado': True,
            'resumen': self._texto_resumen(datos, nivel, filas),
            'linea_ids': [(0, 0, {
                'fila': f['fila'], 'codigo': f['codigo'],
                'descripcion': f['descripcion'], 'uom': f['uom'],
                'cantidad': f['cantidad'],
                'precio_unitario': f['precio_unitario_final'],
                'aviso': ' · '.join(f['avisos']) or False,
                'importar': not f['avisos'],
            }) for f in filas],
        })
        return self._recargar()

    def _texto_resumen(self, datos, nivel, filas) -> str:
        L = []
        L.append('Solapa leída: %s   (encabezado en la fila %s)'
                 % (datos['hoja'], datos['encabezado_fila']))
        L.append('Filas leídas: %d' % len(datos['filas']))
        L.append('')
        L.append('Importes por nivel de numeración:')
        for n, d in sorted(datos['niveles'].items()):
            marca = '  ← estás importando este' if n == nivel else ''
            L.append('  nivel %d: %d ítems, $ %s%s'
                     % (n, d['n'], '{:,.2f}'.format(d['importe']), marca))
        if datos.get('total_declarado'):
            L.append('  total declarado en la planilla: $ %s'
                     % '{:,.2f}'.format(datos['total_declarado']))
        if datos.get('nivel_sugerido'):
            L.append('')
            L.append('Sugerencia: nivel %d — %s.'
                     % (datos['nivel_sugerido'],
                        datos.get('nivel_sugerido_motivo') or ''))
        total = sum(f['importe_final'] for f in filas)
        L.append('')
        L.append('A importar: %d ítems, $ %s'
                 % (len(filas), '{:,.2f}'.format(total)))
        con_aviso = sum(1 for f in filas if f['avisos'])
        if con_aviso:
            L.append('%d de esos ítems vienen con un aviso y quedaron '
                     'DESTILDADOS. Miralos antes de importar.' % con_aviso)
        if datos['avisos']:
            L.append('')
            L.append('Avisos del archivo:')
            for a in datos['avisos']:
                L.append('  · %s' % a)
        return '\n'.join(L)

    # ── paso 2: crear ────────────────────────────────────────────────
    def action_importar(self):
        self.ensure_one()
        if not self.analizado:
            raise UserError(_('Analizá el archivo antes de importar.'))
        lineas = self.linea_ids.filtered('importar')
        if not lineas:
            raise UserError(_('No hay ninguna fila tildada para importar.'))

        Item = self.env['coop.foja.item']
        if self.reemplazar:
            viejos = Item.search([('obra_id', '=', self.obra_id.id)])
            # Un ítem con avances cargados es trabajo que alguien ya midió:
            # borrarlo borra la producción de un socio. Nunca en silencio.
            con_avance = viejos.filtered(lambda i: i.avance_ids)
            if con_avance:
                raise UserError(_(
                    'No se puede reemplazar la foja: %d ítem(s) ya tienen '
                    'avances cargados y borrarlos borraría el trabajo medido '
                    'de los socios.\n\n%s\n\n'
                    'Importá sin reemplazar, o resolvé esos avances primero.'
                ) % (len(con_avance),
                     '\n'.join(' · %s %s' % (i.item, i.name)
                               for i in con_avance[:10])))
            viejos.unlink()

        existentes = {i.item: i for i in Item.search(
            [('obra_id', '=', self.obra_id.id)])}
        creados = actualizados = 0
        for l in lineas:
            vals = {
                'obra_id': self.obra_id.id, 'item': l.codigo,
                'name': l.descripcion, 'uom': l.uom,
                'cantidad': l.cantidad, 'precio_unitario': l.precio_unitario,
            }
            actual = existentes.get(l.codigo)
            if actual:
                actual.write(vals)
                actualizados += 1
            else:
                Item.create(vals)
                creados += 1

        self.resumen = (self.resumen or '') + (
            '\n\n✓ Importado: %d ítems nuevos, %d actualizados.'
            % (creados, actualizados))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.foja.item',
            'view_mode': 'list,form',
            'domain': [('obra_id', '=', self.obra_id.id)],
            'name': _('Foja de %s') % self.obra_id.name,
        }

    def action_cambiar_nivel(self):
        """Re-analiza con el nivel que eligió la persona."""
        self.ensure_one()
        return self.action_analizar()

    def _recargar(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'new',
            'name': _('Importar foja de medición'),
        }


class CoopFojaImportLinea(models.TransientModel):
    _name = 'coop.foja.import.linea'
    _description = 'Fila leída del cómputo, antes de confirmar'
    _order = 'fila'

    wizard_id = fields.Many2one('coop.foja.import', ondelete='cascade')
    importar = fields.Boolean(string='Importar', default=True)
    fila = fields.Integer(string='Fila del Excel', readonly=True)
    codigo = fields.Char(string='Ítem')
    descripcion = fields.Char(string='Descripción')
    uom = fields.Selection(
        [('m2', 'm²'), ('m3', 'm³'), ('ml', 'ml'), ('u', 'Unidad'),
         ('gl', 'Global'), ('kg', 'kg'), ('otro', 'Otro')], string='U.')
    cantidad = fields.Float(string='Cantidad')
    precio_unitario = fields.Monetary(string='Precio unitario')
    currency_id = fields.Many2one(
        'res.currency', related='wizard_id.obra_id.currency_id', readonly=True)
    importe = fields.Monetary(string='Importe', compute='_compute_importe')
    aviso = fields.Char(string='⚠ Revisá', readonly=True)

    @api.depends('cantidad', 'precio_unitario')
    def _compute_importe(self) -> None:
        for l in self:
            l.importe = l.cantidad * l.precio_unitario
