from odoo import models, fields, api


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # Extensiones cooperativas sobre el equipo nativo (= la herramienta).
    obra_id = fields.Many2one(
        'project.project', string='Obra actual',
        domain=[('is_coop_obra', '=', True)], ondelete='set null',
        help='Dónde está la herramienta ahora (la última asignación vigente).')
    coordinador_responsable_id = fields.Many2one(
        'coop.member', string='Coordinador responsable', ondelete='set null',
        domain=[('state', '=', 'active')])
    estado_coop = fields.Selection([
        ('disponible', 'Disponible'),
        ('en_obra', 'En obra'),
        ('en_service', 'En service'),
        ('rota', 'Rota'),
        ('perdida', 'Perdida'),
    ], string='Estado', default='disponible', required=True, tracking=True)
    valor_reposicion = fields.Monetary(string='Valor de reposición')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    codigo_etiqueta = fields.Char(string='Código de etiqueta')
    # service preventivo propio (en Odoo 18 maintenance.equipment ya no trae
    # 'period'/'next_action_date'; usamos campos propios autocontenidos).
    frecuencia_dias = fields.Integer(
        string='Frecuencia de service (días)',
        help='Cada cuántos días corresponde el mantenimiento preventivo.')
    proxima_revision = fields.Date(
        string='Próxima revisión',
        help='Fecha del próximo service. La app avisa si está vencida.')
    asignacion_ids = fields.One2many(
        'coop.asignacion.herramienta', 'equipment_id', string='Asignaciones')
    service_vencido = fields.Boolean(
        string='Service vencido', compute='_compute_service_vencido',
        search='_search_service_vencido')

    @api.depends('proxima_revision')
    def _compute_service_vencido(self) -> None:
        hoy = fields.Date.context_today(self)
        for r in self:
            r.service_vencido = bool(
                r.proxima_revision and r.proxima_revision < hoy)

    def _search_service_vencido(self, operator, value):
        hoy = fields.Date.context_today(self)
        vencidos = self.search([('proxima_revision', '<', hoy)])
        positivo = (operator == '=' and value) or (operator == '!=' and not value)
        return [('id', 'in' if positivo else 'not in', vencidos.ids)]


class CoopAsignacionHerramienta(models.Model):
    _name = 'coop.asignacion.herramienta'
    _description = 'Asignación de una herramienta a una obra'
    _order = 'fecha_retiro desc, id desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Herramienta', required=True,
        ondelete='cascade')
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='cascade')
    member_id = fields.Many2one(
        'coop.member', string='Quién la lleva', ondelete='restrict',
        domain=[('state', '=', 'active')])
    fecha_retiro = fields.Date(string='Retiro',
                               default=fields.Date.context_today, required=True)
    fecha_devolucion = fields.Date(string='Devolución', readonly=True)
    state = fields.Selection([
        ('en_obra', 'En obra'),
        ('devuelta', 'Devuelta'),
    ], string='Estado', default='en_obra', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        asignaciones = super().create(vals_list)
        for a in asignaciones:
            if a.state == 'en_obra' and a.equipment_id.estado_coop == 'disponible':
                a.equipment_id.write({
                    'estado_coop': 'en_obra', 'obra_id': a.obra_id.id})
        return asignaciones

    def action_devolver(self) -> None:
        for a in self:
            if a.state != 'en_obra':
                continue
            a.write({'state': 'devuelta',
                     'fecha_devolucion': fields.Date.context_today(self)})
            # si era la asignación vigente, la herramienta vuelve a disponible
            if a.equipment_id.estado_coop == 'en_obra':
                a.equipment_id.write({
                    'estado_coop': 'disponible', 'obra_id': False})
