import secrets
import string

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopMember(models.Model):
    _name = 'coop.member'
    _description = 'Socio Cooperativo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(string='Nombre completo', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Contacto', required=True, ondelete='restrict', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', ondelete='set null')
    dni = fields.Char(string='DNI', required=True, tracking=True)
    cuil = fields.Char(string='CUIL', tracking=True)
    date_birth = fields.Date(string='Fecha de nacimiento')
    phone = fields.Char(string='Teléfono / WhatsApp')
    email = fields.Char(string='Email')

    state = fields.Selection([
        ('prospect', 'Postulante'),
        ('active', 'Activo'),
        ('suspended', 'Suspendido'),
        ('leaving', 'En proceso de baja'),
        ('former', 'Ex socio'),
    ], string='Estado', default='prospect', required=True, tracking=True)

    date_admission = fields.Date(string='Fecha de ingreso', tracking=True)
    date_leaving = fields.Date(string='Fecha de baja', tracking=True)
    leaving_reason = fields.Selection([
        ('voluntary', 'Renuncia voluntaria'),
        ('expulsion', 'Expulsión por asamblea'),
        ('death', 'Fallecimiento'),
        ('other', 'Otro'),
    ], string='Motivo de baja', tracking=True)
    leaving_notes = fields.Text(string='Observaciones de baja')

    contribution_ids = fields.One2many('coop.contribution', 'member_id', string='Aportes')
    initial_contribution = fields.Monetary(string='Aporte inicial requerido', currency_field='currency_id', default=0.0)
    total_contributions = fields.Monetary(string='Total aportado', currency_field='currency_id', compute='_compute_totals', store=True)
    total_withdrawals = fields.Monetary(string='Total retirado', currency_field='currency_id', compute='_compute_totals', store=True)
    social_capital = fields.Monetary(string='Capital social', currency_field='currency_id', compute='_compute_totals', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    total_hours_worked = fields.Float(string='Horas trabajadas totales', compute='_compute_hours_stored', store=True)
    current_month_hours = fields.Float(string='Horas este mes', compute='_compute_hours_realtime')

    role = fields.Selection([
        ('worker', 'Operario'),
        ('board', 'Consejo de Administración'),
        ('syndic', 'Síndico'),
        ('manager', 'Administrador'),
    ], string='Rol', default='worker', required=True, tracking=True)

    is_board_member = fields.Boolean(string='Miembro del Consejo', compute='_compute_is_board', store=True)
    notes = fields.Html(string='Notas internas')

    _sql_constraints = [
        ('dni_unique', 'UNIQUE(dni)', 'Ya existe un socio con ese DNI.'),
        ('cuil_unique', 'UNIQUE(cuil)', 'Ya existe un socio con ese CUIL.'),
    ]

    @api.depends('contribution_ids', 'contribution_ids.amount', 'contribution_ids.type', 'contribution_ids.state')
    def _compute_totals(self):
        for member in self:
            confirmed = member.contribution_ids.filtered(lambda c: c.state == 'confirmed')
            member.total_contributions = sum(c.amount for c in confirmed if c.type == 'contribution')
            member.total_withdrawals = sum(c.amount for c in confirmed if c.type == 'withdrawal')
            member.social_capital = member.total_contributions - member.total_withdrawals

    @api.depends('employee_id')
    def _compute_hours_stored(self):
        for member in self:
            member.total_hours_worked = 0.0

    def _compute_hours_realtime(self):
        for member in self:
            member.current_month_hours = 0.0

    @api.depends('role')
    def _compute_is_board(self):
        for member in self:
            member.is_board_member = member.role in ('board', 'syndic', 'manager')

    @api.constrains('date_admission', 'date_leaving')
    def _check_dates(self):
        for member in self:
            if member.date_admission and member.date_leaving:
                if member.date_leaving < member.date_admission:
                    raise ValidationError(_('La fecha de baja no puede ser anterior a la fecha de ingreso.'))

    @api.constrains('state', 'date_admission')
    def _check_admission_date(self):
        for member in self:
            if member.state == 'active' and not member.date_admission:
                raise ValidationError(_('Un socio activo debe tener fecha de ingreso.'))

    def action_approve(self):
        for member in self:
            member.write({'state': 'active', 'date_admission': member.date_admission or fields.Date.today()})
            member.message_post(body=_('Socio aprobado y activado.'))

    def action_suspend(self):
        self.write({'state': 'suspended'})

    def action_start_leaving(self):
        self.write({'state': 'leaving'})

    def action_confirm_leaving(self):
        for member in self:
            member.write({'state': 'former', 'date_leaving': member.date_leaving or fields.Date.today()})

    def action_reactivate(self):
        self.write({'state': 'active', 'date_leaving': False})

    # ── Alta automática del acceso a la app (M7) ─────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        if not self.env.context.get('skip_portal_user'):
            for m in members:
                m._provision_portal_user()
        return members

    def _provision_portal_user(self):
        """Crea el acceso a la app del socio (usuario + rol + PIN) si todavía
        no tiene uno. Login = DNI; PIN inicial = los últimos 4 del DNI (el
        socio lo conoce; conviene que lo cambie). El teléfono del socio se
        copia al contacto para habilitar el login por teléfono+PIN."""
        self.ensure_one()
        partner = self.partner_id
        if not partner or not self.dni or partner.user_ids:
            return False
        if self.phone and not (partner.phone or partner.mobile):
            partner.phone = self.phone
        grupo_xmlid = {
            'syndic': 'coop_members.group_coop_syndic',
            'manager': 'coop_members.group_coop_manager',
        }.get(self.role, 'coop_members.group_coop_member')
        grupo = self.env.ref(grupo_xmlid, raise_if_not_found=False)
        interno = self.env.ref('base.group_user', raise_if_not_found=False)
        if not grupo or not interno:
            return False
        pwd = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(16))
        user = self.env['res.users'].sudo().with_context(
            no_reset_password=True).create({
                'name': self.name, 'login': self.dni,
                'partner_id': partner.id, 'password': pwd,
                'groups_id': [(6, 0, [interno.id, grupo.id])],
            })
        pin = ''.join(c for c in (self.dni or '') if c.isdigit())[-4:]
        if len(pin) == 4:
            user.set_coop_pin(pin)
        self.message_post(body=_(
            'Acceso a la app creado. Usuario: %s · PIN inicial: los últimos 4 '
            'dígitos del DNI (recomendá cambiarlo).') % self.dni)
        return user

    def action_dar_acceso_app(self):
        """Botón para (re)crear el acceso a la app a mano."""
        for m in self:
            m._provision_portal_user()
