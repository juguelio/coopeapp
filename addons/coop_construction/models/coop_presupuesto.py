import re
from urllib.parse import quote

from odoo import models, fields, api
from odoo.exceptions import UserError

CATEGORIAS = [
    ('materiales', 'Materiales e insumos'),
    ('mano_obra', 'Mano de obra'),
    ('herramientas', 'Herramientas y equipos'),
    ('impositivos', 'Gastos impositivos'),
    ('administrativos', 'Gastos administrativos'),
    ('logistica', 'Logística'),
]

ALICUOTAS = [
    ('0', 'Exento / 0%'),
    ('10.5', '10,5%'),
    ('21', '21%'),
]


class CoopPresupuesto(models.Model):
    _name = 'coop.presupuesto'
    _description = 'Presupuesto de una orden de trabajo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    name = fields.Char(string='N° de presupuesto', required=True, copy=False,
                       default='Nuevo', readonly=True)
    orden_id = fields.Many2one(
        'coop.orden.trabajo', string='Orden de trabajo', required=True,
        ondelete='cascade', tracking=True)
    cliente_id = fields.Many2one(
        related='orden_id.cliente_id', string='Cliente', store=True,
        readonly=True)
    version = fields.Integer(string='Versión', default=1)
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today,
                        required=True)
    validez_dias = fields.Integer(
        string='Validez (días)', default=10,
        help='Con inflación conviene validez corta (7-10 días).')
    fecha_vencimiento = fields.Date(
        string='Vence', compute='_compute_vencimiento', store=True)
    tipo_factura = fields.Selection([
        ('A', 'Factura A (IVA discriminado)'),
        ('B', 'Factura B (IVA incluido)'),
    ], string='Tipo de comprobante', default='B', required=True, tracking=True,
        help='A: neto + IVA discriminado (responsable inscripto). '
             'B: IVA incluido en el precio (consumidor final). '
             'Recibo C/exento: pendiente de confirmar con el contador.')
    linea_ids = fields.One2many(
        'coop.presupuesto.linea', 'presupuesto_id', string='Líneas')
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('vencido', 'Vencido'),
    ], string='Estado', default='borrador', required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)

    neto = fields.Monetary(string='Neto', compute='_compute_totales', store=True)
    iva = fields.Monetary(string='IVA', compute='_compute_totales', store=True)
    total = fields.Monetary(string='Total', compute='_compute_totales',
                            store=True)
    mensaje = fields.Text(string='Mensaje al cliente', compute='_compute_mensaje')
    wa_url = fields.Char(string='WhatsApp', compute='_compute_mensaje')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'coop.presupuesto') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('fecha', 'validez_dias')
    def _compute_vencimiento(self) -> None:
        for r in self:
            r.fecha_vencimiento = (
                fields.Date.add(r.fecha, days=r.validez_dias)
                if r.fecha else False)

    @api.depends('linea_ids.cantidad', 'linea_ids.precio_unitario',
                 'linea_ids.iva_alicuota', 'tipo_factura')
    def _compute_totales(self) -> None:
        for r in self:
            neto = iva = total = 0.0
            for ln in r.linea_ids:
                base = ln.cantidad * ln.precio_unitario
                alic = float(ln.iva_alicuota or '0') / 100.0
                if r.tipo_factura == 'A':
                    # el precio cargado es neto, el IVA se suma
                    neto += base
                    iva += base * alic
                    total += base * (1 + alic)
                else:
                    # factura B: el precio ya incluye IVA
                    total += base
                    n = base / (1 + alic) if alic else base
                    neto += n
                    iva += base - n
            r.neto, r.iva, r.total = neto, iva, total

    @api.depends('total', 'fecha_vencimiento', 'name', 'cliente_id',
                 'cliente_id.phone', 'cliente_id.mobile')
    def _compute_mensaje(self) -> None:
        for r in self:
            total_txt = '{:,.0f}'.format(r.total).replace(',', '.')
            r.mensaje = (
                'Hola %s! Te paso el presupuesto %s por el trabajo solicitado.\n'
                'Total: $%s (IVA incluido).\n'
                'Válido hasta el %s.\n'
                'Cualquier duda quedo a disposición. ¡Gracias!'
            ) % (r.cliente_id.name or '', r.name or '', total_txt,
                 r.fecha_vencimiento and r.fecha_vencimiento.strftime('%d/%m/%Y') or '')
            num = re.sub(r'\D', '', r.cliente_id.phone or r.cliente_id.mobile or '')
            r.wa_url = ('https://wa.me/%s?text=%s' % (num, quote(r.mensaje))
                        ) if num else ''

    # ── transiciones ─────────────────────────────────────────────────
    def action_enviar(self) -> None:
        for r in self:
            if r.state in ('borrador',):
                r.state = 'enviado'
                if r.orden_id.state in ('recibida', 'relevamiento',
                                        'presupuestada'):
                    r.orden_id.state = 'enviada'

    def action_aprobar(self):
        """Aprueba el presupuesto y crea la OBRA con sus etapas desde la
        memoria descriptiva de la OT. Idempotente: si la OT ya tiene obra, no
        la recrea. Devuelve la acción para abrir la obra creada."""
        self.ensure_one()
        orden = self.orden_id
        # #2: si la OT ya tiene obra (un presupuesto anterior fue aprobado), no
        # crear otra ni dejar la obra con valores viejos en silencio. Para
        # renegociar, se ajusta la obra directamente.
        if orden.obra_id:
            raise UserError(
                'La OT %s ya tiene una obra creada por un presupuesto aprobado '
                '(%s). Si renegociaste, ajustá la obra directamente; no se '
                'aprueba un segundo presupuesto sobre la misma OT.'
                % (orden.name, orden.obra_id.name))
        self.state = 'aprobado'
        orden.state = 'aprobada'
        obra = self.env['project.project'].create({
            'name': '%s — %s' % (orden.name, orden.cliente_id.name or ''),
            'is_coop_obra': True,
            'obra_type': 'otro',
            'comitente_id': orden.cliente_id.id,
            'ubicacion': orden.ubicacion or False,
            'currency_id': self.currency_id.id,
            'monto_contrato': self.total,
            'estado_obra': 'planificacion',
        })
        # etapas desde la memoria descriptiva (orden estable por secuencia)
        etapas_vals = [
            {'obra_id': obra.id, 'numero': i, 'name': em.name,
             'state': 'planificacion'}
            for i, em in enumerate(
                orden.etapa_memoria_ids.sorted(lambda e: (e.secuencia, e.id)),
                start=1)
        ]
        # #4: si la OT no tiene memoria, la obra nace con una etapa por defecto
        # (no una obra vacía sin proyección).
        if not etapas_vals:
            etapas_vals = [{'obra_id': obra.id, 'numero': 1,
                            'name': 'Etapa 1', 'state': 'planificacion'}]
        self.env['coop.etapa'].create(etapas_vals)
        orden.obra_id = obra.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': orden.obra_id.id, 'view_mode': 'form',
            'target': 'current',
        }

    def action_rechazar(self) -> None:
        self.write({'state': 'rechazado'})

    def action_vencer(self) -> None:
        self.write({'state': 'vencido'})

    def action_borrador(self) -> None:
        self.write({'state': 'borrador'})


class CoopPresupuestoLinea(models.Model):
    _name = 'coop.presupuesto.linea'
    _description = 'Línea de presupuesto'
    _order = 'presupuesto_id, categoria, id'

    presupuesto_id = fields.Many2one(
        'coop.presupuesto', string='Presupuesto', required=True,
        ondelete='cascade')
    categoria = fields.Selection(CATEGORIAS, string='Categoría', required=True,
                                 default='materiales')
    name = fields.Char(string='Detalle', required=True)
    material_id = fields.Many2one(
        'coop.material', string='Material (opcional)', ondelete='set null')
    cantidad = fields.Float(string='Cantidad', default=1.0)
    precio_unitario = fields.Monetary(string='Precio unitario')
    iva_alicuota = fields.Selection(ALICUOTAS, string='IVA', default='21')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal',
                               store=True)
    currency_id = fields.Many2one(
        'res.currency', related='presupuesto_id.currency_id', store=True,
        string='Moneda', readonly=True)

    @api.depends('cantidad', 'precio_unitario')
    def _compute_subtotal(self) -> None:
        for r in self:
            r.subtotal = r.cantidad * r.precio_unitario

    @api.onchange('material_id')
    def _onchange_material(self) -> None:
        if self.material_id and not self.name:
            self.name = self.material_id.name
