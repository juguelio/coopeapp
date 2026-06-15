import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

MESES_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


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
    point_ids = fields.One2many(
        'coop.assembly.point', 'assembly_id', string='Orden del día (puntos)')

    numero_acta = fields.Char(string='N° de acta', readonly=True, copy=False)
    acta_texto = fields.Text(string='Acta (texto legal)', copy=False)
    acta_hash = fields.Char(string='Hash del acta', compute='_compute_acta_hash',
                            store=True)
    firma_ids = fields.One2many(
        'coop.acta.firma', 'assembly_id', string='Firmas del acta')

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

    @api.depends('acta_texto')
    def _compute_acta_hash(self):
        for a in self:
            a.acta_hash = (hashlib.sha256(a.acta_texto.encode('utf-8'))
                           .hexdigest()) if a.acta_texto else False

    def _persona_con_dni(self, member):
        if not member:
            return '—'
        return '%s%s' % (member.name, ' DNI %s' % member.dni
                         if member.dni else '')

    def action_generate_minutes(self):
        """Genera el acta con el formato legal del libro (ley 20.337) a partir
        de los puntos del orden del día, presentes, autoridades y votaciones.
        Asigna el N° de acta por libro (asamblea / consejo) si no tiene."""
        for a in self:
            if not a.numero_acta:
                code = ('coop.assembly.acta.board'
                        if a.assembly_type == 'board'
                        else 'coop.assembly.acta.asamblea')
                a.numero_acta = self.env['ir.sequence'].next_by_code(code) or ''
            company = self.env.company
            organo = ('el Consejo de Administración'
                      if a.assembly_type == 'board'
                      else 'la Asamblea %s de socios' % (
                          'Extraordinaria' if a.assembly_type == 'extraordinary'
                          else 'Ordinaria'))
            fh = fields.Datetime.context_timestamp(a, a.date) if a.date else False
            dia = fh.day if fh else '—'
            mes = MESES_ES[fh.month] if fh else '—'
            anio = fh.year if fh else '—'
            hora = fh.strftime('%H:%M') if fh else '—'
            # cuerpo por punto
            cuerpos = []
            for p in a.point_ids.sorted('sequence'):
                txt = '%d) %s.' % (p.sequence, p.name)
                if p.resolucion:
                    txt += ' Resolución: %s' % p.resolucion
                if p.vote_id:
                    v = p.vote_id
                    txt += (' Votación: %d a favor, %d en contra, %d '
                            'abstenciones (%s).') % (
                        v.votes_yes, v.votes_no, v.votes_abstain,
                        'aprobada' if v.approved else 'rechazada')
                cuerpos.append(txt)
            orden = ' '.join(cuerpos) or 'No se trataron puntos.'
            acta = (
                'ACTA N° %s. En %s, a los %s días del mes de %s de %s, siendo '
                'las %s hs, en la sede de la %s, sita en %s, se reúne %s. '
                'Presidente: %s. Secretario: %s. Presentes: %d socios de %d '
                '(%.0f%%), con quórum suficiente conforme la ley 20.337 y el '
                'estatuto. ORDEN DEL DÍA: %s Sin más temas que tratar, siendo '
                'las %s hs se da por finalizada la reunión, firmando al pie los '
                'asistentes designados.'
            ) % (
                a.numero_acta or '—', company.city or 'San Martín de los Andes',
                dia, mes, anio, hora, company.name,
                company.street or 'su domicilio legal', organo,
                a._persona_con_dni(a.president_id),
                a._persona_con_dni(a.secretary_id),
                a.attendee_count, a.total_active_members, a.quorum_percentage,
                orden, hora,
            )
            a.acta_texto = acta
            a.message_post(body=_('Acta %s generada.') % (a.numero_acta or ''))

    def action_firmar(self, member, rol):
        """Registra la firma electrónica interna del acta (hash del texto
        al momento de firmar). Idempotente por (asamblea, socio, rol)."""
        self.ensure_one()
        if not self.acta_texto or not member or rol not in (
                'presidente', 'secretario', 'sindico'):
            return False
        existe = self.firma_ids.filtered(
            lambda f: f.member_id.id == member.id and f.rol == rol)
        if existe:
            existe.hash_acta = self.acta_hash  # re-firma sobre la versión actual
            return existe
        return self.env['coop.acta.firma'].create({
            'assembly_id': self.id, 'member_id': member.id, 'rol': rol,
            'hash_acta': self.acta_hash,
        })
