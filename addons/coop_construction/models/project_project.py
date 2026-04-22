from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_coop_obra = fields.Boolean(string='Es obra cooperativa', default=False)
    obra_type = fields.Selection([
        ('vivienda', 'Vivienda'),
        ('infraestructura', 'Infraestructura'),
        ('industrial', 'Industrial'),
        ('vial', 'Vial'),
        ('otro', 'Otro'),
    ], string='Tipo de obra')
    comitente_id = fields.Many2one(
        'res.partner', string='Comitente', ondelete='restrict')
    numero_expediente = fields.Char(string='N° expediente / contrato')
    monto_contrato = fields.Monetary(string='Monto del contrato')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    ubicacion = fields.Char(string='Ubicación de la obra')
    director_id = fields.Many2one(
        'coop.member', string='Director de obra', ondelete='restrict',
        domain=[('state', '=', 'active')])
    capataz_id = fields.Many2one(
        'coop.member', string='Capataz principal', ondelete='restrict',
        domain=[('state', '=', 'active')])
    socio_obra_ids = fields.Many2many(
        'coop.member', 'project_coop_member_rel', 'project_id', 'member_id',
        string='Plantel asignado', domain=[('state', '=', 'active')])
    estado_obra = fields.Selection([
        ('planificacion', 'Planificación'),
        ('activa', 'Activa'),
        ('suspendida', 'Suspendida'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado de obra', default='planificacion', tracking=True)
    hour_rate = fields.Monetary(
        string='Tarifa horaria (obra)', currency_field='currency_id',
        help='Tarifa por hora negociada con el comitente para esta obra')
    obra_work_entry_ids = fields.One2many(
        'coop.work.entry', 'obra_id', string='Entradas de trabajo de obra')
    costo_mano_obra = fields.Monetary(
        string='Costo mano de obra', compute='_compute_costo_mano_obra',
        currency_field='currency_id', store=True)
    certificado_ids = fields.One2many(
        'coop.certificado', 'obra_id', string='Certificados')
    certificado_count = fields.Integer(
        string='Certificados', compute='_compute_certificado_count')
    total_certificado = fields.Monetary(
        string='Total certificado', compute='_compute_total_certificado',
        currency_field='currency_id', store=True)

    @api.depends('obra_work_entry_ids.hours', 'hour_rate')
    def _compute_costo_mano_obra(self) -> None:
        for record in self:
            total_hours = sum(record.obra_work_entry_ids.mapped('hours'))
            record.costo_mano_obra = total_hours * (record.hour_rate or 0.0)

    @api.depends('certificado_ids')
    def _compute_certificado_count(self) -> None:
        for record in self:
            record.certificado_count = len(record.certificado_ids)

    @api.depends('certificado_ids.monto_certificado', 'certificado_ids.state')
    def _compute_total_certificado(self) -> None:
        for record in self:
            cobrados = record.certificado_ids.filtered(
                lambda c: c.state in ('aprobado', 'cobrado'))
            record.total_certificado = sum(cobrados.mapped('monto_certificado'))

    def action_open_certificados(self) -> dict:
        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificados',
            'res_model': 'coop.certificado',
            'view_mode': 'list,form',
            'domain': [('obra_id', '=', self.id)],
            'context': {'default_obra_id': self.id},
        }
