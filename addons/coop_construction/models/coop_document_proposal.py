"""Propuestas documentales provenientes de Box.

Este modelo es el límite entre extracción y datos operativos. Una propuesta no
es una póliza: primero se revisa y recién una aprobación autenticada puede
crear registros en coop.poliza.
"""
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CoopDocumentProposal(models.Model):
    _name = 'coop.document.proposal'
    _description = 'Propuesta documental para revisión'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Propuesta', compute='_compute_name', store=True)
    state = fields.Selection([
        ('pending_review', 'Pendiente de revisión'),
        ('approved', 'Aprobada'),
        ('needs_correction', 'Pedir corrección'),
        ('rejected', 'Rechazada'),
        ('hold', 'En conflicto'),
    ], string='Estado', required=True, default='pending_review', index=True)

    # Fuente documental: no se pierde el vínculo con Box.
    source_file_name = fields.Char(string='Documento', required=True, readonly=True)
    box_file_id = fields.Char(string='Box file ID', required=True, readonly=True, index=True)
    box_version_id = fields.Char(string='Box version ID', required=True, readonly=True)
    source_sha256 = fields.Char(string='SHA-256', readonly=True)

    # Datos que la persona revisa.
    numero = fields.Char(string='Número de póliza', readonly=True)
    aseguradora = fields.Char(string='Aseguradora', readonly=True)
    obra_id = fields.Many2one('project.project', string='Obra', readonly=True)
    obra_nombre_extraido = fields.Char(string='Obra extraída', readonly=True)
    tipo = fields.Selection(related='poliza_id.tipo', string='Tipo', readonly=True)
    fecha_inicio = fields.Date(string='Vigente desde', readonly=True)
    fecha_fin = fields.Date(string='Vigente hasta', readonly=True)
    importe = fields.Float(string='Importe mensual', readonly=True)
    socios_extraidos = fields.Text(string='Socios extraídos', readonly=True)
    socios_pendientes = fields.Text(
        string='Socios sin vincular',
        readonly=True,
        help='Socios extraídos que no matchearon con el padrón al aprobar. '
             'Quedan pendientes de vincular a mano: no se adivinan.')
    campos_json = fields.Text(string='Campos extraídos (JSON)', readonly=True)

    # Auditoría de revisión/aprobación.
    reviewed_by_id = fields.Many2one('res.users', string='Revisado por', readonly=True)
    reviewed_at = fields.Datetime(string='Revisado el', readonly=True)
    approved_by_id = fields.Many2one('res.users', string='Aprobado por', readonly=True)
    approved_by_name = fields.Char(string='Nombre del aprobador', related='approved_by_id.name', readonly=True)
    approved_by_role = fields.Char(string='Rol del aprobador', readonly=True)
    approved_at = fields.Datetime(string='Aprobado el', readonly=True)
    decision_reason = fields.Text(string='Motivo de la decisión', readonly=True)

    poliza_id = fields.Many2one('coop.poliza', string='Póliza creada', readonly=True)

    _sql_constraints = [
        ('box_source_unique', 'unique(box_file_id, box_version_id)',
         'La misma versión de Box no puede generar dos propuestas.'),
    ]

    @api.depends('source_file_name', 'numero')
    def _compute_name(self):
        for record in self:
            record.name = '%s — %s' % (
                record.source_file_name or _('Documento'),
                record.numero or _('sin número'),
            )

    @api.model
    def create_from_ingestion(self, payload):
        """Persistir una propuesta extraída, sin aprobarla ni crear póliza."""
        source = payload.get('source') or {}
        proposal = payload.get('proposal') or {}
        required = ('file_id', 'version_id', 'file_name')
        missing = [key for key in required if not source.get(key)]
        if missing:
            raise ValidationError(_('Falta trazabilidad de Box: %s') % ', '.join(missing))
        existing = self.search([
            ('box_file_id', '=', str(source['file_id'])),
            ('box_version_id', '=', str(source['version_id'])),
        ], limit=1)
        if existing:
            return existing
        # El worker manda `status` (pending_review / needs_correction) y `conflicts`
        # (hold). El conflicto pesa más: si hay conflictos el estado es hold (póliza
        # vencida, nómina vacía...), sin importar el `status`. Si no hay conflictos,
        # se honra el status — esto habilita el caso "PDF ilegible -> needs_correction",
        # que hoy no existía porque el modelo ignoraba status.
        conflicts = payload.get('conflicts')
        estado_worker = proposal.get('status') or 'pending_review'
        if conflicts:
            state = 'hold'
        elif estado_worker in ('pending_review', 'needs_correction'):
            state = estado_worker
        else:
            state = 'hold'
        vals = {
            'source_file_name': source['file_name'],
            'box_file_id': str(source['file_id']),
            'box_version_id': str(source['version_id']),
            'source_sha256': source.get('sha256'),
            'numero': proposal.get('numero'),
            'aseguradora': proposal.get('aseguradora'),
            'obra_nombre_extraido': proposal.get('obra'),
            'fecha_inicio': proposal.get('fecha_inicio'),
            'fecha_fin': proposal.get('fecha_fin'),
            'importe': proposal.get('importe') or 0.0,
            'socios_extraidos': '\n'.join(proposal.get('socios') or []),
            'campos_json': json.dumps(proposal, ensure_ascii=False),
            'state': state,
        }
        if state == 'needs_correction' and proposal.get('reasons'):
            vals['decision_reason'] = '\n'.join(map(str, proposal['reasons']))
        return self.create(vals)

    def _approval_role(self):
        self.ensure_one()
        if self.env.user.has_group('coop_members.group_coop_manager'):
            return 'Administrador cooperativo'
        if self.env.user.has_group('coop_members.group_coop_coordinador'):
            return 'Coordinador'
        return 'Usuario CoopeApp autenticado'

    def action_approve(self):
        for record in self:
            if record.state != 'pending_review':
                raise UserError(_('Solo se puede aprobar una propuesta pendiente de revisión.'))
            if not record.obra_id:
                raise ValidationError(_('Antes de aprobar, asigná la propuesta a una obra.'))
            partner = self.env['res.partner'].search([
                ('name', '=', record.aseguradora),
            ], limit=1)
            if record.aseguradora and not partner:
                raise ValidationError(_(
                    'La aseguradora extraída no está vinculada a un contacto existente. '
                    'Vinculala antes de aprobar la propuesta.'))
            policy_vals = {
                'numero': record.numero or _('Sin número'),
                'sujeto': 'persona',
                'tipo': 'general',
                'aseguradora_id': partner.id if partner else False,
                'obra_id': record.obra_id.id,
                'fecha_inicio': record.fecha_inicio,
                'fecha_fin': record.fecha_fin,
            }
            policy = self.env['coop.poliza'].create(policy_vals)
            # Los socios extraídos pasan a la nómina SOLO cuando matchean
            # exacto contra el padrón. Lo que no matchea no cubre y queda
            # pendiente: nunca se adivina una persona para decir que está
            # cubierta (una afirmación así manda a alguien a un andamio).
            nomina_alta = record.fecha_inicio or fields.Date.context_today(self)
            pendientes = []
            for nombre in (record.socios_extraidos or '').splitlines():
                nombre = nombre.strip()
                if not nombre:
                    continue
                socio = self.env['coop.member'].sudo().search(
                    [('name', '=', nombre)], limit=1)
                if socio:
                    self.env['coop.poliza.nomina'].sudo().create({
                        'poliza_id': policy.id,
                        'member_id': socio.id,
                        'fecha_alta': nomina_alta,
                    })
                else:
                    pendientes.append(nombre)
            now = fields.Datetime.now()
            record.write({
                'state': 'approved',
                'poliza_id': policy.id,
                'socios_pendientes': '\n'.join(pendientes) or False,
                'reviewed_by_id': self.env.user.id,
                'reviewed_at': now,
                'approved_by_id': self.env.user.id,
                'approved_by_role': record._approval_role(),
                'approved_at': now,
                'decision_reason': _('Aprobación autenticada desde CoopeApp.'),
            })
        return True

    def action_request_correction(self):
        self.write({
            'state': 'needs_correction',
            'reviewed_by_id': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
            'decision_reason': _('Se solicitó corrección durante la revisión.'),
        })
        return True

    def action_reject(self):
        self.write({
            'state': 'rejected',
            'reviewed_by_id': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
            'decision_reason': _('Rechazada durante la revisión.'),
        })
        return True

    def action_reset_to_review(self):
        self.write({
            'state': 'pending_review',
            'decision_reason': False,
            'reviewed_by_id': False,
            'reviewed_at': False,
        })
        return True
