from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


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
        ('prestada_externo', 'Prestada afuera'),
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
    # `tipo` existe porque una herramienta sale de dos maneras distintas y
    # antes solo se podia registrar una. Prestarsela al equipo de arquitectos
    # exigia elegir una obra propia y un socio activo: no se podia anotar, asi
    # que no se anotaba, y la herramienta figuraba 'disponible' mientras estaba
    # en la camioneta de otro.
    tipo = fields.Selection([
        ('obra', 'A una obra'),
        ('externo', 'Prestada afuera'),
    ], string='Tipo de salida', default='obra', required=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra',
        domain=[('is_coop_obra', '=', True)], ondelete='cascade',
        help='Obligatoria si la salida es a una obra. En un prestamo externo '
             'es opcional: sirve para saber a raiz de que obra se presto.')
    member_id = fields.Many2one(
        'coop.member', string='Quién la lleva', ondelete='restrict',
        domain=[('state', '=', 'active')],
        help='El socio que la retira. En un prestamo externo es quien la '
             'entrego, no quien la tiene.')
    # Los tres datos que faltaban para poder reclamar: a quien, como ubicarlo,
    # y con que identificarlo si hay que ir mas lejos que un llamado.
    prestado_a = fields.Char(
        string='Se la llevó', help='Nombre de la persona o del estudio.')
    prestado_tel = fields.Char(string='Teléfono')
    prestado_doc = fields.Char(string='DNI / CUIT')
    fecha_retiro = fields.Date(string='Retiro',
                               default=fields.Date.context_today, required=True)
    fecha_devolucion_prevista = fields.Date(
        string='Devuelve el',
        help='Sin esto nunca se puede decir "vencida", solo "prestada".')
    fecha_devolucion = fields.Date(string='Devolución', readonly=True)
    state = fields.Selection([
        ('en_obra', 'En obra'),
        ('prestada', 'Prestada afuera'),
        ('devuelta', 'Devuelta'),
    ], string='Estado', default='en_obra', required=True)
    dias_afuera = fields.Integer(
        string='Días afuera', compute='_compute_dias_afuera')
    vencida = fields.Boolean(
        string='Vencida', compute='_compute_vencida',
        search='_search_vencida')

    @api.depends('fecha_retiro', 'fecha_devolucion', 'state')
    def _compute_dias_afuera(self) -> None:
        hoy = fields.Date.context_today(self)
        for a in self:
            if not a.fecha_retiro:
                a.dias_afuera = 0
                continue
            # una devuelta sin fecha de devolución no debería existir, pero
            # si existe se cuenta hasta hoy antes que romper la pantalla
            hasta = (a.fecha_devolucion
                     if a.state == 'devuelta' and a.fecha_devolucion else hoy)
            a.dias_afuera = (hasta - a.fecha_retiro).days

    @api.depends('fecha_devolucion_prevista', 'state')
    def _compute_vencida(self) -> None:
        hoy = fields.Date.context_today(self)
        for a in self:
            a.vencida = bool(
                a.state != 'devuelta' and a.fecha_devolucion_prevista
                and a.fecha_devolucion_prevista < hoy)

    def _search_vencida(self, operator, value):
        hoy = fields.Date.context_today(self)
        vencidas = self.search([
            ('state', '!=', 'devuelta'),
            ('fecha_devolucion_prevista', '<', hoy)])
        positivo = (operator == '=' and value) or (operator == '!=' and not value)
        return [('id', 'in' if positivo else 'not in', vencidas.ids)]

    @api.constrains('tipo', 'obra_id', 'prestado_a')
    def _check_destino(self) -> None:
        """Una salida sin destino es exactamente el agujero que abrimos al
        sacarle el required a obra_id. Cerrarlo por constraint, no por buena
        voluntad del formulario."""
        for a in self:
            if a.tipo == 'obra' and not a.obra_id:
                raise ValidationError(_(
                    'Una salida a obra necesita la obra.'))
            if a.tipo == 'externo' and not (a.prestado_a or '').strip():
                raise ValidationError(_(
                    'Un préstamo afuera necesita saber quién se la llevó. '
                    'Si no queda registrado a quién reclamarle, es lo mismo '
                    'que no anotarlo.'))

    @api.model_create_multi
    def create(self, vals_list):
        # `state` sigue al tipo salvo que se pida otra cosa explícitamente. Sin
        # esto, crear un préstamo externo con el state por defecto ('en_obra')
        # marcaría la herramienta como si estuviera en una obra que no existe.
        for vals in vals_list:
            if vals.get('tipo') == 'externo' and not vals.get('state'):
                vals['state'] = 'prestada'
        asignaciones = super().create(vals_list)
        for a in asignaciones:
            if a.equipment_id.estado_coop != 'disponible':
                continue
            if a.state == 'en_obra':
                a.equipment_id.write({
                    'estado_coop': 'en_obra', 'obra_id': a.obra_id.id})
            elif a.state == 'prestada':
                # obra_id acompaña al préstamo solo si se declaró: la
                # herramienta no está en esa obra, salió a raíz de ella.
                a.equipment_id.write({'estado_coop': 'prestada_externo'})
        return asignaciones

    def action_devolver(self) -> None:
        for a in self:
            if a.state not in ('en_obra', 'prestada'):
                continue
            a.write({'state': 'devuelta',
                     'fecha_devolucion': fields.Date.context_today(self)})
            # si era la salida vigente, la herramienta vuelve a disponible
            if a.equipment_id.estado_coop in ('en_obra', 'prestada_externo'):
                a.equipment_id.write({
                    'estado_coop': 'disponible', 'obra_id': False})
