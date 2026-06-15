from odoo import models, fields, api


class CoopRelevamiento(models.Model):
    _name = 'coop.relevamiento'
    _description = 'Relevamiento en sitio de una orden de trabajo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Relevamiento', compute='_compute_name', store=True)
    orden_id = fields.Many2one(
        'coop.orden.trabajo', string='Orden de trabajo', required=True,
        ondelete='cascade')
    member_id = fields.Many2one(
        'coop.member', string='Relevador', ondelete='restrict',
        domain=[('state', '=', 'active')], tracking=True)
    fecha = fields.Date(string='Fecha del relevamiento',
                        default=fields.Date.context_today)
    observaciones = fields.Text(string='Observaciones')
    medida_ids = fields.One2many(
        'coop.relevamiento.medida', 'relevamiento_id', string='Medidas')
    n_medidas = fields.Integer(string='Medidas', compute='_compute_n_medidas')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('cargado', 'Cargado'),
        ('validado', 'Validado'),
    ], string='Estado', default='pendiente', required=True, tracking=True)

    @api.depends('orden_id.name')
    def _compute_name(self) -> None:
        for r in self:
            r.name = 'Relevamiento %s' % (r.orden_id.name or '')

    @api.depends('medida_ids')
    def _compute_n_medidas(self) -> None:
        for r in self:
            r.n_medidas = len(r.medida_ids)

    def action_validar(self) -> None:
        for r in self:
            if r.state == 'cargado':
                r.state = 'validado'

    def action_cargado(self) -> None:
        for r in self:
            if r.state == 'pendiente':
                r.state = 'cargado'

    def action_pendiente(self) -> None:
        self.write({'state': 'pendiente'})


class CoopRelevamientoMedida(models.Model):
    _name = 'coop.relevamiento.medida'
    _description = 'Medida tomada en un relevamiento'
    _order = 'relevamiento_id, id'

    relevamiento_id = fields.Many2one(
        'coop.relevamiento', string='Relevamiento', required=True,
        ondelete='cascade')
    concepto = fields.Char(string='Concepto', required=True,
                           help='Ej: frente, superficie a pintar, altura')
    valor = fields.Float(string='Valor')
    unidad = fields.Char(string='Unidad', help='Ej: ml, m², m³, u')
