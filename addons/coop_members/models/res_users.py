import hashlib
import hmac
import os

from odoo import models, fields
from odoo.exceptions import AccessDenied


def _hash_pin(pin, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'),
                            bytes.fromhex(salt), 100000).hex()
    return '%s$%s' % (salt, h)


def _verify_pin(stored, pin):
    if not stored or '$' not in (stored or '') or not pin:
        return False
    salt, h = stored.split('$', 1)
    try:
        calc = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'),
                                   bytes.fromhex(salt), 100000).hex()
    except ValueError:
        return False
    return hmac.compare_digest(calc, h)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # PIN para login teléfono+PIN del portal (M7). Aditivo: NO toca el login
    # estándar de Odoo (email+password sigue funcionando igual).
    coop_pin_hash = fields.Char(string='PIN (hash)', copy=False, groups='base.group_system')
    coop_pin_intentos = fields.Integer(string='Intentos PIN fallidos',
                                       default=0, copy=False,
                                       groups='base.group_system')
    coop_pin_bloqueo = fields.Datetime(string='PIN bloqueado hasta', copy=False,
                                       groups='base.group_system')

    def create(self, vals_list):
        users = super().create(vals_list)
        action = self.env.ref(
            'coop_members.action_coop_member', raise_if_not_found=False,
        )
        if action:
            users.filtered(lambda u: not u.action_id).write(
                {'action_id': action.id}
            )
        return users

    def set_coop_pin(self, pin):
        """Define el PIN del usuario (hash). pin = string de 4-8 dígitos."""
        self.ensure_one()
        pin = (pin or '').strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            return False
        self.sudo().write({'coop_pin_hash': _hash_pin(pin),
                           'coop_pin_intentos': 0, 'coop_pin_bloqueo': False})
        return True

    def _verifica_pin(self, pin):
        self.ensure_one()
        return _verify_pin(self.sudo().coop_pin_hash, pin)

    def _check_credentials(self, credential, env):
        """Auth por PIN AISLADA del login estándar: el PIN solo se acepta cuando
        la credencial trae la clave 'coop_pin', que ÚNICAMENTE setea el flujo
        /app/ingresar. /web/login manda {login,password,type} sin esa clave →
        nunca acepta el PIN (no hay oráculo de brute-force en el backend).
        Además respeta el bloqueo por intentos en TODO punto de entrada."""
        if isinstance(credential, dict) and credential.get('coop_pin'):
            self.ensure_one()
            u = self.sudo()
            if u.coop_pin_bloqueo and u.coop_pin_bloqueo > fields.Datetime.now():
                raise AccessDenied()
            if self._verifica_pin(credential['coop_pin']):
                return {'uid': self.id, 'auth_method': 'password',
                        'mfa': 'default'}
            raise AccessDenied()
        return super()._check_credentials(credential, env)
