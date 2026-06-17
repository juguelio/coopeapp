import re
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessDenied
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
        Member = request.env['coop.member'].sudo()
        member = Member.browse()
        if len(num) >= 6:
            tail = num[-8:]
            # pre-filtro SQL por los últimos 6 dígitos (casi siempre contiguos al
            # final), después match exacto por dígitos en Python → tolera
            # guiones/espacios SIN escanear toda la tabla de socios.
            suf = num[-6:]
            cand = Member.search([
                ('state', '=', 'active'),
                '|', ('partner_id.phone', 'like', suf),
                     ('partner_id.mobile', 'like', suf)],
                order='id', limit=50)
            member = next(
                (m for m in cand
                 if re.sub(r'\D', '', m.partner_id.phone or '')[-8:] == tail
                 or re.sub(r'\D', '', m.partner_id.mobile or '')[-8:] == tail),
                Member.browse())
        user = member.partner_id.user_ids[:1] if member else \
            request.env['res.users'].sudo().browse()
        pin = (pin or '').strip()
        if user and pin:
            if (user.coop_pin_bloqueo
                    and user.coop_pin_bloqueo > fields.Datetime.now()):
                return request.render('coop_portal.ingresar', {
                    'error': 'Demasiados intentos. Esperá unos minutos.'})
            try:
                # la clave 'coop_pin' activa la auth por PIN (aislada de
                # /web/login); sin ella el PIN no se acepta en ningún lado
                request.session.authenticate(request.db, {
                    'login': user.login, 'type': 'password', 'coop_pin': pin})
                user.sudo().write({'coop_pin_intentos': 0,
                                   'coop_pin_bloqueo': False})
                return request.redirect('/app')
            except AccessDenied:
                intentos = user.coop_pin_intentos + 1
                vals = {'coop_pin_intentos': intentos}
                if intentos >= 5:
                    vals['coop_pin_bloqueo'] = (
                        fields.Datetime.now() + timedelta(minutes=15))
                    vals['coop_pin_intentos'] = 0
                user.sudo().write(vals)
        return request.render('coop_portal.ingresar', {
            'error': 'Teléfono o PIN incorrecto.'})
