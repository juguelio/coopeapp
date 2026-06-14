from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopAssembly(models.Model):
    _name = 'coop.assembly'
    _description = 'Asamblea Cooperativa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Título', required=True, tracking=True)
    assembly_type = fields.Selection([
        ('ordinary', 'Ordinaria'),
        ('extraordinary', 'Extraordinaria'),
        ('board', 'Reunión de Consejo'),
    ], string='Tipo', required=True, default='ordinary', tracking=True)

    state = fields.Selection([
        ('draft', 'Convocada'),
        ('open', 'En curso'),
        ('closed', 'Cerrada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft', required=True, tracking=True)

    date = fields.Datetime(string='Fecha y hora', required=True, tracking=True)
    location = fields.Char(string='Lugar', tracking=True)
    quorum_required = fields.Integer(string='Quórum requerido (%)', default=50)

    agenda = fields.Html(string='Orden del día')
    minutes = fields.Html(string='Acta')

    attendee_ids = fields.Many2many(
        'coop.member',
        'assembly_attendee_rel',
        'assembly_id',
        'member_id',
        string='Socios presentes',
        domain=[('state', '=', 'active')],
    )
    attendee_count = fields.Integer(
        string='Presentes',
        compute='_compute_quorum',
    )
    total_active_members = fields.Integer(
        string='Total socios activos',
        compute='_compute_quorum',
    )
    quorum_reached = fields.Boolean(
        string='Quórum alcanzado',
        compute='_compute_quorum',
    )
    quorum_percentage = fields.Float(
        string='% de asistencia',
        compute='_compute_quorum',
    )

    vote_ids = fields.One2many('coop.vote', 'assembly_id', string='Votaciones')
    vote_count = fields.Integer(string='Votaciones', compute='_compute_vote_count')

    president_id = fields.Many2one('coop.member', string='Presidente de asamblea')
    secretary_id = fields.Many2one('coop.member', string='Secretario de actas')

    notes = fields.Text(string='Notas internas')

    @api.depends('attendee_ids')
    def _compute_quorum(self):
        for assembly in self:
            total = self.env['coop.member'].search_count([('state', '=', 'active')])
            present = len(assembly.attendee_ids)
            assembly.attendee_count = present
            assembly.total_active_members = total
            assembly.quorum_percentage = (present / total * 100) if total > 0 else 0
            assembly.quorum_reached = assembly.quorum_percentage >= assembly.quorum_required

    @api.depends('vote_ids')
    def _compute_vote_count(self):
        for assembly in self:
            assembly.vote_count = len(assembly.vote_ids)

    def action_open(self):
        for assembly in self:
            if not assembly.quorum_reached:
                raise ValidationError(
                    _('No se alcanzó el quórum requerido (%s%%). Asistencia actual: %s%%')
                    % (assembly.quorum_required, round(assembly.quorum_percentage, 1))
                )
            assembly.write({'state': 'open'})
            assembly.message_post(body=_('Asamblea iniciada. Quórum alcanzado.'))

    def action_close(self):
        for assembly in self:
            assembly.write({'state': 'closed'})
            assembly.message_post(body=_('Asamblea cerrada. Acta generada.'))

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_generate_minutes(self):
        for assembly in self:
            votes_summary = ''
            for vote in assembly.vote_ids:
                votes_summary += f'<p><b>{vote.name}:</b> {vote.result_summary}</p>'

            minutes = f"""
<h2>{assembly.name}</h2>
<p><b>Tipo:</b> {dict(assembly._fields['assembly_type'].selection).get(assembly.assembly_type)}</p>
<p><b>Fecha:</b> {assembly.date}</p>
<p><b>Lugar:</b> {assembly.location or 'No especificado'}</p>
<p><b>Socios presentes:</b> {assembly.attendee_count} de {assembly.total_active_members} ({round(assembly.quorum_percentage, 1)}%)</p>
<p><b>Presidente:</b> {assembly.president_id.name if assembly.president_id else '-'}</p>
<p><b>Secretario:</b> {assembly.secretary_id.name if assembly.secretary_id else '-'}</p>
<h3>Votaciones</h3>
{votes_summary or '<p>No hubo votaciones.</p>'}
<h3>Cierre</h3>
<p>Sin más temas que tratar, se da por finalizada la asamblea.</p>
"""
            assembly.write({'minutes': minutes})
            assembly.message_post(body=_('Acta generada automáticamente.'))
