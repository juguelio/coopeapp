from odoo import http
from odoo.http import request


class CoopPortalSeguros(http.Controller):
    """Seguros en /app: la pantalla que hace visible el cruce.

    Solo lectura, para todos los roles (transparencia ACI: ver qué cobertura
    falta es de todos, no solo de administración). No carga nada; carga la hace
    Yamila en el backoffice. Acá se ve el resultado de
    project.project.cobertura_faltante(): quién está sin cobertura, qué
    requisitos no se cumplen, y qué arranques están autorizados por excepción.
    """

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    def _nav_rol(self, member):
        if member.role == 'syndic':
            return 'sindico'
        if member.role == 'manager':
            return 'admin'
        es_capataz = request.env['project.project'].sudo().search_count(
            [('capataz_id', '=', member.id)])
        return 'coordinador' if es_capataz else None

    @http.route('/app/seguros', type='http', auth='user', website=False)
    def seguros(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')

        problemas = request.env['project.project'].sudo().cruce_diario_cobertura()
        # El cruce ya trae los tres tipos: 'sin_cobertura', 'requisito' y
        # 'excepcion'. Se separan las excepciones (autorizadas, informativas)
        # de lo que de verdad falta.
        faltantes = [p for p in problemas if p['tipo'] != 'excepcion']
        excepciones = [p for p in problemas if p['tipo'] == 'excepcion']

        return request.render('coop_portal.seguros', {
            'member': member,
            'nav_rol': self._nav_rol(member),
            'faltantes': faltantes,
            'excepciones': excepciones,
        })
