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
                if user.sudo().coop_pin_debe_cambiar:
                    return request.redirect('/app/cambiar-pin')
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

    # ── Cambio de PIN forzado en el primer ingreso ───────────────────
    @http.route('/app/cambiar-pin', type='http', auth='user', website=False)
    def cambiar_pin(self, **kw):
        return request.render('coop_portal.cambiar_pin', {'error': None})

    @http.route('/app/cambiar-pin/guardar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def cambiar_pin_guardar(self, pin=None, pin2=None, **kw):
        user = request.env.user
        nuevo = re.sub(r'\D', '', pin or '')
        rep = re.sub(r'\D', '', pin2 or '')
        if not (4 <= len(nuevo) <= 8):
            return request.render('coop_portal.cambiar_pin', {
                'error': 'El PIN tiene que ser de 4 a 8 números.'})
        if nuevo != rep:
            return request.render('coop_portal.cambiar_pin', {
                'error': 'Los dos PIN no coinciden. Volvé a escribirlos.'})
        # Que no deje el PIN inicial (los últimos 4 del DNI): si el nuevo
        # todavía valida contra el actual, pedimos uno distinto.
        if user.sudo()._verifica_pin(nuevo):
            return request.render('coop_portal.cambiar_pin', {
                'error': 'Elegí un PIN distinto al que tenías.'})
        user.sudo().set_coop_pin(nuevo, force_change=False)
        return request.redirect('/app')
