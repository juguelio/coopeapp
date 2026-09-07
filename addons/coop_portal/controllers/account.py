from odoo import http
from odoo.http import request


class CoopPortalAccount(http.Controller):
    @staticmethod
    def _member():
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    @staticmethod
    def _nav_role(member):
        if member.role == 'syndic':
            return 'sindico'
        if member.role == 'manager':
            return 'admin'
        if request.env['project.project'].sudo().search_count([
                ('is_coop_obra', '=', True),
                ('estado_obra', 'in', ['planificacion', 'activa']),
                ('capataz_id', '=', member.id)]):
            return 'coordinador'
        return None

    @http.route('/app/cuenta', type='http', auth='user', website=False)
    def cuenta(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        role_labels = {
            'worker': 'Socio / operario',
            'coordinator': 'Coordinador',
            'syndic': 'Síndico',
            'manager': 'Administrador',
            'board': 'Consejo',
        }
        ui_mode = 'cartel' if member.role == 'worker' else 'obra'
        return request.render('coop_portal.cuenta', {
            'member': member,
            'rol_label': role_labels.get(member.role, 'Integrante'),
            'nav_rol': self._nav_role(member),
            'nav_activo': 'cuenta',
            'ui_mode': ui_mode,
        })
