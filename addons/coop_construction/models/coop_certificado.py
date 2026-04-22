from odoo import models, fields


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
