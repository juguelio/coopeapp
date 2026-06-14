import hashlib

from odoo import models, fields, api


class CoopCertificado(models.Model):
    _name = 'coop.certificado'
    _description = 'Certificado de Avance de Obra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'obra_id, numero'

    name = fields.Char(string='Descripción', required=True, tracking=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict', tracking=True)
    numero = fields.Integer(string='N° certificado', required=True)
    date = fields.Date(
        string='Fecha de presentación', required=True,
        default=fields.Date.today, tracking=True)
    porcentaje_avance = fields.Float(
        string='Avance acumulado (%)', digits=(5, 2))
    monto_certificado = fields.Monetary(
        string='Monto del certificado', required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('presentado', 'Presentado'),
        ('aprobado', 'Aprobado'),
        ('cobrado', 'Cobrado'),
        ('rechazado', 'Rechazado'),
    ], string='Estado', default='borrador', required=True, tracking=True)
    notes = fields.Text(string='Observaciones')

    # ── Firma digital (interna, con hash) ────────────────────────────
    firmado = fields.Boolean(string='Firmado', readonly=True, copy=False)
    firmado_por_id = fields.Many2one(
        'coop.member', string='Firmado por', readonly=True, copy=False)
    fecha_firma = fields.Datetime(string='Fecha de firma', readonly=True, copy=False)
    hash_firma = fields.Char(string='Hash de la firma', readonly=True, copy=False)
    hash_actual = fields.Char(
        string='Hash actual', compute='_compute_hash_actual',
        help='Hash del contenido ahora; si difiere del firmado, el certificado fue alterado')
    firma_valida = fields.Boolean(
        string='Firma válida', compute='_compute_hash_actual',
        help='La firma es válida si el contenido no cambió desde que se firmó')

    def _contenido_para_hash(self):
        self.ensure_one()
        return '|'.join([
            str(self.obra_id.id), str(self.numero),
            '%.2f' % (self.porcentaje_avance or 0.0),
            '%.2f' % (self.monto_certificado or 0.0),
            str(self.date or ''),
        ])

    @api.depends('obra_id', 'numero', 'porcentaje_avance', 'monto_certificado',
                 'date', 'hash_firma')
    def _compute_hash_actual(self):
        for cert in self:
            actual = hashlib.sha256(
                cert._contenido_para_hash().encode('utf-8')).hexdigest()
            cert.hash_actual = actual
            cert.firma_valida = bool(cert.firmado) and cert.hash_firma == actual

    def action_firmar(self, member=None):
        """Firma el certificado: registra quién, cuándo y el hash del
        contenido. Si después alguien cambia un número, firma_valida pasa a
        False (se nota la alteración)."""
        for cert in self:
            firmante = member or self.env['coop.member'].search(
                [('partner_id.user_ids', 'in', [self.env.uid])], limit=1)
            cert.write({
                'firmado': True,
                'firmado_por_id': firmante.id if firmante else False,
                'fecha_firma': fields.Datetime.now(),
                'hash_firma': hashlib.sha256(
                    cert._contenido_para_hash().encode('utf-8')).hexdigest(),
            })

    _sql_constraints = [
        ('numero_obra_unique', 'UNIQUE(obra_id, numero)',
         'El número de certificado debe ser único por obra.'),
        ('monto_positivo', 'CHECK(monto_certificado > 0)',
         'El monto del certificado debe ser positivo.'),
        ('avance_rango',
         'CHECK(porcentaje_avance >= 0 AND porcentaje_avance <= 100)',
         'El porcentaje de avance debe estar entre 0 y 100.'),
    ]

    def action_presentar(self) -> None:
        self.write({'state': 'presentado'})

    def action_aprobar(self) -> None:
        self.write({'state': 'aprobado'})

    def action_cobrar(self) -> None:
        self.write({'state': 'cobrado'})

    def action_rechazar(self) -> None:
        self.write({'state': 'rechazado'})

    def action_borrador(self) -> None:
        self.filtered(lambda c: c.state == 'rechazado').write({'state': 'borrador'})
