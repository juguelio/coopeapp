from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopMemberPinWizard(models.TransientModel):
    _name = 'coop.member.pin.wizard'
    _description = 'Asistente para definir el PIN de un socio'

    member_id = fields.Many2one('coop.member', string='Socio', required=True,
                                ondelete='cascade')
    pin = fields.Char(string='Nuevo PIN', required=True,
                      help='4 a 8 dígitos. Es la clave que el socio usa para '
                           'entrar a la app con su teléfono.')

    @api.constrains('pin')
    def _check_pin(self):
        for wiz in self:
            pin = (wiz.pin or '').strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 8):
                raise ValidationError(_(
                    'El PIN tiene que ser de 4 a 8 dígitos numéricos.'))

    def action_set_pin(self):
        self.ensure_one()
        user = self.member_id.app_user_id
        if not user:
            raise ValidationError(_(
                'El socio no tiene acceso a la app. Primero usá '
                '"Dar acceso a la app".'))
        if not user.sudo().set_coop_pin((self.pin or '').strip()):
            raise ValidationError(_(
                'El PIN tiene que ser de 4 a 8 dígitos numéricos.'))
        self.member_id.message_post(body=_('PIN cambiado a mano.'))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('PIN actualizado'),
                       'message': _('El nuevo PIN quedó guardado.'),
                       'type': 'success', 'sticky': False},
        }
