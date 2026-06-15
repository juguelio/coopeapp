from odoo import models, fields, api


ESTADOS_OT = [
    ('recibida', 'Recibida'),
    ('relevamiento', 'En relevamiento'),
    ('presupuestada', 'Presupuestada'),
    ('enviada', 'Enviada al cliente'),
    ('aprobada', 'Aprobada'),
    ('rechazada', 'Rechazada'),
    ('vencida', 'Vencida'),
]


class CoopOrdenTrabajo(models.Model):
    _name = 'coop.orden.trabajo'
    _description = 'Orden de trabajo (pipeline pre-obra)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_recepcion desc, id desc'

    name = fields.Char(string='N° de OT', required=True, copy=False,
                       default='Nueva', readonly=True)
    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, ondelete='restrict',
        tracking=True)
    descripcion = fields.Text(string='Descripción del trabajo', tracking=True)
    ubicacion = fields.Char(string='Ubicación')
    fecha_recepcion = fields.Date(
        string='Fecha de recepción', required=True,
        default=fields.Date.context_today, tracking=True)
    administrador_id = fields.Many2one(
        'coop.member', string='Administrador', ondelete='restrict',
        domain=[('state', '=', 'active')],
        default=lambda self: self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1))
    relevador_id = fields.Many2one(
        'coop.member', string='Relevador asignado', ondelete='restrict',
        domain=[('state', '=', 'active')], tracking=True)
    state = fields.Selection(
        ESTADOS_OT, string='Estado', default='recibida', required=True,
        tracking=True)
    etapa_memoria_ids = fields.One2many(
        'coop.ot.etapa', 'orden_id', string='Memoria descriptiva (etapas)')
    relevamiento_ids = fields.One2many(
        'coop.relevamiento', 'orden_id', string='Relevamientos')
    relevamiento_id = fields.Many2one(
        'coop.relevamiento', string='Relevamiento',
        compute='_compute_relevamiento')
    obra_id = fields.Many2one(
        'project.project', string='Obra generada', readonly=True,
        ondelete='set null')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'Nueva':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'coop.orden.trabajo') or 'Nueva'
        return super().create(vals_list)

    @api.depends('relevamiento_ids')
    def _compute_relevamiento(self) -> None:
        for r in self:
            r.relevamiento_id = r.relevamiento_ids[:1].id

    # ── transiciones básicas (presupuesto/obra se cablean en M3-3/M3-4) ──
    def action_a_relevamiento(self) -> None:
        """Pasa a relevamiento y crea el relevamiento para el relevador
        asignado (si todavía no hay uno)."""
        for r in self:
            if r.state != 'recibida':
                continue
            if not r.relevamiento_ids:
                self.env['coop.relevamiento'].create({
                    'orden_id': r.id, 'member_id': r.relevador_id.id or False,
                })
            r.state = 'relevamiento'

    def action_rechazar(self) -> None:
        self.write({'state': 'rechazada'})

    def action_vencer(self) -> None:
        self.write({'state': 'vencida'})

    def action_reabrir(self) -> None:
        self.write({'state': 'recibida'})


class CoopOtEtapa(models.Model):
    _name = 'coop.ot.etapa'
    _description = 'Etapa de la memoria descriptiva de una OT'
    _order = 'orden_id, secuencia, id'

    orden_id = fields.Many2one(
        'coop.orden.trabajo', string='Orden de trabajo', required=True,
        ondelete='cascade')
    secuencia = fields.Integer(string='Orden', default=10)
    name = fields.Char(string='Etapa', required=True)
    descripcion = fields.Text(string='Descripción')
    materiales = fields.Text(string='Materiales estimados')
    herramientas = fields.Text(string='Herramientas necesarias')
