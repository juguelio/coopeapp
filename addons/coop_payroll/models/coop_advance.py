from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group('coop_members.group_coop_manager'):
            defaults = self.default_get(['state', 'payroll_id', 'approved_by', 'date_approved'])
            for vals in vals_list:
                values = dict(defaults, **vals)
                if values.get('state', 'draft') != 'draft' or any(
                    values.get(field) for field in ('payroll_id', 'approved_by', 'date_approved')
                ):
                    raise AccessError(_('Solo la administración puede aprobar o descontar anticipos.'))
        default_payroll = self.default_get(['payroll_id']).get('payroll_id')
        self._check_paid_payroll(self.env['coop.payroll'].browse([
            vals.get('payroll_id', default_payroll) for vals in vals_list
            if vals.get('payroll_id', default_payroll)
        ]))
        return super().create(vals_list)

    def _check_paid_payroll(self, payrolls):
        if payrolls.filtered(lambda p: p.state == 'paid'):
            raise ValidationError(_('No se pueden modificar anticipos de una liquidación pagada.'))

    def write(self, vals):
        payrolls = self.mapped('payroll_id')
        if vals.get('payroll_id'):
            payrolls |= self.env['coop.payroll'].browse(vals['payroll_id'])
        self._check_paid_payroll(payrolls)
        return super().write(vals)

    def unlink(self):
        self._check_paid_payroll(self.mapped('payroll_id'))
        return super().unlink()

    @api.constrains('member_id', 'payroll_id')
    def _check_payroll_member(self):
        for advance in self:
            if advance.payroll_id and advance.member_id != advance.payroll_id.member_id:
                raise ValidationError(_('El anticipo y la liquidación deben pertenecer al mismo socio.'))

    def action_approve(self):
        for advance in self:
            advance.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'date_approved': fields.Date.today(),
            })
            advance.sudo().message_post(author_id=self.env.user.partner_id.id, body=_('Anticipo aprobado por %s.') % self.env.user.name)

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.sudo().message_post(author_id=self.env.user.partner_id.id, body=_('Anticipo rechazado.'))

    def action_draft(self):
        self.write({'state': 'draft'})
