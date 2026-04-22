from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopAdvance(models.Model):
    _name = 'coop.advance'
    _description = 'Anticipo a Socio'
    _inherit = ['mail.thread']
    _order = 'date desc'

    name = fields.Char(string='Referencia', required=True, tracking=True)
    member_id = fields.Many2one('coop.member', string='Socio', required=True, ondelete='restrict', tracking=True)
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.today, tracking=True)
    reason = fields.Text(string='Motivo')
    state = fields.Selection([
        ('draft', 'Pendiente de aprobación'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('discounted', 'Descontado en liquidación'),
    ], string='Estado', default='draft', required=True, tracking=True)
    payroll_id = fields.Many2one('coop.payroll', string='Liquidación donde se descuenta', ondelete='set null')
    approved_by = fields.Many2one('res.users', string='Aprobado por', readonly=True)
    date_approved = fields.Date(string='Fecha de aprobación', readonly=True)

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'El monto del anticipo debe ser mayor a cero.'),
    ]

    def action_approve(self):
        for advance in self:
            advance.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'date_approved': fields.Date.today(),
            })
            advance.message_post(body=_('Anticipo aprobado por %s.') % self.env.user.name)

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.message_post(body=_('Anticipo rechazado.'))

    def action_draft(self):
        self.write({'state': 'draft'})
