from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopContribution(models.Model):
    _name = 'coop.contribution'
    _description = 'Aporte / Retiro de Capital Social'
    _inherit = ['mail.thread']
    _order = 'date desc'

    member_id = fields.Many2one(
        'coop.member',
        string='Socio',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    name = fields.Char(
        string='Referencia',
        required=True,
        tracking=True,
    )
    type = fields.Selection(
        selection=[
            ('contribution', 'Aporte'),
            ('withdrawal', 'Retiro'),
            ('return', 'Retorno de excedentes'),
            ('advance', 'Anticipo a cuenta'),
        ],
        string='Tipo',
        required=True,
        default='contribution',
        tracking=True,
    )
    amount = fields.Monetary(
        string='Monto',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('cancelled', 'Anulado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Asiento contable',
        ondelete='set null',
        readonly=True,
    )
    notes = fields.Text(
        string='Observaciones',
    )

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'El monto debe ser mayor a cero.'),
    ]

    @api.constrains('amount')
    def _check_withdrawal_amount(self):
        for contribution in self:
            if contribution.type == 'withdrawal' and contribution.state == 'confirmed':
                member = contribution.member_id
                current_capital = member.social_capital
                if contribution.amount > current_capital:
                    raise ValidationError(
                        _('El retiro de %s supera el capital social disponible (%s).')
                        % (contribution.amount, current_capital)
                    )

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        self.message_post(
            body=_('Aporte/Retiro confirmado.'),
            message_type='notification',
        )

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self.message_post(
            body=_('Aporte/Retiro anulado.'),
            message_type='notification',
        )

    def action_draft(self):
        self.write({'state': 'draft'})
