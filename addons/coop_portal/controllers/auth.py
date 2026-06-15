import re
from datetime import timedelta

from odoo import fields, http
from odoo.http import request


class CoopPortalAuth(http.Controller):
    """Login alternativo teléfono + PIN para socios (M7). Aditivo: el login
    estándar de Odoo (/web/login con email+password) sigue intacto. El PIN se
    valida vía el fallback de res.users._check_credentials."""

    @http.route('/app/ingresar', type='http', auth='public', website=False)
    def ingresar(self, **kw):
        if request.session.uid:
            return request.redirect('/app')
        return request.render('coop_portal.ingresar', {'error': None})

    @http.route('/app/ingresar/entrar', type='http', auth='public',
                website=False, methods=['POST'], csrf=True)
    def entrar(self, telefono=None, pin=None, **kw):
        num = re.sub(r'\D', '', telefono or '')
        member = request.env['coop.member'].sudo()
        if len(num) >= 6:
            member = member.search([
                '|', ('partner_id.phone', 'like', num[-8:]),
                     ('partner_id.mobile', 'like', num[-8:]),
                ('state', '=', 'active')], limit=1)
        user = member.partner_id.user_ids[:1] if member else \
            request.env['res.users'].sudo().browse()
        if user:
            if (user.coop_pin_bloqueo
                    and user.coop_pin_bloqueo > fields.Datetime.now()):
                return request.render('coop_portal.ingresar', {
                    'error': 'Demasiados intentos. Esperá unos minutos.'})
            try:
                request.session.authenticate(request.db, {
                    'login': user.login, 'password': pin or '',
                    'type': 'password'})
                user.sudo().write({'coop_pin_intentos': 0,
                                   'coop_pin_bloqueo': False})
                return request.redirect('/app')
            except Exception:  # noqa: BLE001 — PIN incorrecto
                intentos = user.coop_pin_intentos + 1
                vals = {'coop_pin_intentos': intentos}
                if intentos >= 5:
                    vals['coop_pin_bloqueo'] = (
                        fields.Datetime.now() + timedelta(minutes=15))
                    vals['coop_pin_intentos'] = 0
                user.sudo().write(vals)
        return request.render('coop_portal.ingresar', {
            'error': 'Teléfono o PIN incorrecto.'})
