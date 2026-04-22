from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_coop_member = fields.Boolean(
        string='Es socio cooperativo',
        default=False,
    )
    coop_member_id = fields.One2many(
        'coop.member',
        'partner_id',
        string='Ficha de socio',
    )
