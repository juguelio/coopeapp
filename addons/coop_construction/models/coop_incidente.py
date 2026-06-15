from odoo import models, fields, api

TIPOS_INCIDENTE = [
    ('rotura_herramienta', 'Rotura de herramienta'),
    ('perdida_herramienta', 'Pérdida de herramienta'),
    ('rotura_material', 'Rotura de material'),
    ('perdida_material', 'Pérdida de material'),
]


class CoopIncidente(models.Model):
    _name = 'coop.incidente'
    _description = 'Incidente: rotura o pérdida de herramienta o material'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Incidente', compute='_compute_name', store=True)
    tipo = fields.Selection(TIPOS_INCIDENTE, string='Tipo', required=True,
                            tracking=True)
    es_herramienta = fields.Boolean(compute='_compute_es_herramienta',
                                    store=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict')
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Herramienta', ondelete='set null')
    material_id = fields.Many2one(
        'coop.material', string='Material', ondelete='set null')
    cantidad = fields.Float(string='Cantidad', default=1.0)
    valor_estimado = fields.Monetary(
        string='Valor estimado de la merma',
        help='Se imputa como gasto de la etapa al resolver (sin culpa '
             'automática: es el registro del hecho).')
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id', store=True,
        string='Moneda', readonly=True)
    reportado_por = fields.Many2one(
        'coop.member', string='Reportado por', ondelete='restrict',
        default=lambda self: self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1))
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today)
    descripcion = fields.Text(string='Qué pasó')
    state = fields.Selection([
        ('reportado', 'Reportado'),
        ('revisado', 'Revisado'),
        ('resuelto', 'Resuelto'),
    ], string='Estado', default='reportado', required=True, tracking=True)
    gasto_id = fields.Many2one('coop.proyeccion.gasto', string='Merma imputada',
                               readonly=True, ondelete='set null')
    request_id = fields.Many2one('maintenance.request',
                                 string='Solicitud de reparación', readonly=True,
                                 ondelete='set null')

    @api.depends('tipo')
    def _compute_es_herramienta(self) -> None:
        for r in self:
            r.es_herramienta = r.tipo in (
                'rotura_herramienta', 'perdida_herramienta')

    @api.depends('tipo', 'equipment_id', 'material_id')
    def _compute_name(self) -> None:
        etiquetas = dict(TIPOS_INCIDENTE)
        for r in self:
            objeto = (r.equipment_id.name or r.material_id.name or '')
            r.name = '%s — %s' % (etiquetas.get(r.tipo, 'Incidente'), objeto)

    def action_revisar(self) -> None:
        for r in self:
            if r.state == 'reportado':
                r.state = 'revisado'

    def action_resolver(self) -> None:
        for r in self:
            if r.state == 'resuelto':
                continue
            r.state = 'resuelto'
            r._aplicar_efectos()

    def _aplicar_efectos(self) -> None:
        """Al resolver: actualiza el estado de la herramienta / crea la
        solicitud de reparación / imputa la merma de material. Idempotente."""
        self.ensure_one()
        if self.tipo == 'rotura_herramienta' and self.equipment_id:
            self.equipment_id.estado_coop = 'rota'
            if not self.request_id:
                self.request_id = self.env['maintenance.request'].create({
                    'name': 'Reparación — %s' % self.equipment_id.name,
                    'equipment_id': self.equipment_id.id,
                    'maintenance_type': 'corrective',
                }).id
        elif self.tipo == 'perdida_herramienta' and self.equipment_id:
            self.equipment_id.estado_coop = 'perdida'
        elif self.tipo in ('rotura_material', 'perdida_material'):
            if not self.gasto_id and self.valor_estimado > 0:
                etapa = self.env['coop.etapa'].search([
                    ('obra_id', '=', self.obra_id.id),
                    ('state', '=', 'en_curso')], limit=1)
                if etapa:
                    self.gasto_id = self.env['coop.proyeccion.gasto'].create({
                        'name': 'Merma: %s' % self.name,
                        'etapa_id': etapa.id, 'rubro': 'materiales',
                        'importe': self.valor_estimado, 'state': 'pendiente',
                        'observaciones': 'Incidente %s' % (
                            self.material_id.name or ''),
                    }).id
