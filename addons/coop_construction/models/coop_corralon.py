import re

from odoo import models, fields, api


class CoopCorralon(models.Model):
    _name = 'coop.corralon'
    _description = 'Corralón / proveedor de materiales'
    _order = 'name'

    name = fields.Char(string='Corralón', required=True,
                       help='Ej: Corralón Austral')
    telefono = fields.Char(
        string='WhatsApp / teléfono',
        help='Número con código de país, ej: 5492944123456. '
             'Se usa para mandar la orden por WhatsApp.')
    direccion = fields.Char(string='Dirección')
    nota = fields.Char(string='Nota')
    active = fields.Boolean(string='Activo', default=True)

    whatsapp_num = fields.Char(
        string='Número WhatsApp (normalizado)',
        compute='_compute_whatsapp_num', store=True,
        help='Solo dígitos, listo para wa.me')

    @api.depends('telefono')
    def _compute_whatsapp_num(self) -> None:
        for r in self:
            r.whatsapp_num = re.sub(r'\D', '', r.telefono or '')


ESTADOS_ORDEN = [
    ('borrador', 'Borrador'),
    ('enviada', 'Enviada'),
    ('confirmada', 'Confirmada'),
    ('entregada', 'Entregada'),
]


class CoopOrdenCorralon(models.Model):
    _name = 'coop.orden.corralon'
    _description = 'Orden de materiales consolidada a un corralón'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Orden', compute='_compute_name', store=True)
    corralon_id = fields.Many2one(
        'coop.corralon', string='Corralón', required=True,
        ondelete='restrict', tracking=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict',
        tracking=True)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    pedido_ids = fields.One2many(
        'coop.pedido.material', 'orden_id', string='Pedidos consolidados')
    n_items = fields.Integer(
        string='Ítems', compute='_compute_n_items', store=True)
    estado = fields.Selection(
        ESTADOS_ORDEN, string='Estado', default='borrador',
        required=True, tracking=True)
    fecha_envio = fields.Datetime(string='Enviada el', readonly=True)
    fecha_entrega = fields.Datetime(string='Entregada el', readonly=True)
    importe_total = fields.Monetary(
        string='Importe de la orden',
        help='Costo total de la compra. Al marcar Entregada se imputa como '
             'gasto de Materiales en la etapa en curso de la obra.')
    mensaje = fields.Text(
        string='Mensaje al corralón', compute='_compute_mensaje',
        help='Texto que se manda por WhatsApp / SMS.')
    gasto_id = fields.Many2one(
        'coop.proyeccion.gasto', string='Gasto imputado', readonly=True,
        ondelete='set null')
    creado_por = fields.Many2one('coop.member', string='Armada por',
                                 readonly=True)

    @api.depends('corralon_id', 'obra_id')
    def _compute_name(self) -> None:
        for r in self:
            ref = 'OC%05d' % r.id if isinstance(r.id, int) else 'OC nueva'
            r.name = '%s — %s — %s' % (
                ref, r.corralon_id.name or '?', r.obra_id.name or '?')

    @api.depends('pedido_ids')
    def _compute_n_items(self) -> None:
        for r in self:
            r.n_items = len(r.pedido_ids)

    @api.depends('pedido_ids.cantidad', 'pedido_ids.name',
                 'corralon_id', 'obra_id')
    def _compute_mensaje(self) -> None:
        uom_labels = dict(
            self.env['coop.pedido.material']._fields['uom'].selection)
        for r in self:
            lineas = []
            for p in r.pedido_ids:
                mat = (p.material_id.name or p.descripcion_libre
                       or 'Material')
                unidad = uom_labels.get(p.uom, p.uom or '')
                lineas.append('• %g %s — %s' % (p.cantidad, unidad, mat))
            cuerpo = '\n'.join(lineas) or '(sin ítems)'
            r.mensaje = (
                'Hola %s! 👷 Pedido de materiales para la obra "%s":\n\n'
                '%s\n\n'
                'Por favor confirmar disponibilidad y precio. ¡Gracias!'
            ) % (r.corralon_id.name or '', r.obra_id.name or '', cuerpo)

    # ── transiciones de estado ───────────────────────────────────────
    def action_enviar(self) -> None:
        for r in self:
            if r.estado == 'borrador':
                r.write({'estado': 'enviada',
                         'fecha_envio': fields.Datetime.now()})

    def action_confirmar(self) -> None:
        for r in self:
            if r.estado in ('borrador', 'enviada'):
                r.estado = 'confirmada'

    def action_volver_borrador(self) -> None:
        for r in self:
            if r.estado != 'entregada':
                r.estado = 'borrador'

    def action_entregar(self) -> None:
        for r in self:
            if r.estado == 'entregada':
                continue
            r.write({'estado': 'entregada',
                     'fecha_entrega': fields.Datetime.now()})
            r._imputar_gasto()

    def _imputar_gasto(self) -> None:
        """Imputa el importe de la orden como gasto de Materiales en la
        etapa en curso de la obra. Idempotente: no duplica si ya hay gasto."""
        self.ensure_one()
        if self.gasto_id or not self.importe_total or self.importe_total <= 0:
            return
        # imputar solo a la etapa en curso (no a una cerrada ya certificada)
        etapa = self.env['coop.etapa'].search([
            ('obra_id', '=', self.obra_id.id),
            ('state', '=', 'en_curso'),
        ], limit=1)
        if not etapa:
            return
        gasto = self.env['coop.proyeccion.gasto'].create({
            'name': 'Orden %s (%d ítems)' % (
                self.corralon_id.name or 'corralón', self.n_items),
            'etapa_id': etapa.id,
            'rubro': 'materiales',
            'importe': self.importe_total,
            'state': 'pendiente',
            'observaciones': self.name,
        })
        self.gasto_id = gasto.id
