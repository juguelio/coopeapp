from odoo import http
from odoo.http import request


class CoopPortalHerramientas(http.Controller):
    """Herramientas en /app: el coordinador lleva/devuelve herramientas de sus
    obras; cualquier socio reporta rotura/pérdida. Escrituras con sudo tras
    verificar pertenencia (coordina la obra / es socio de la obra)."""

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    def _obras_coordina(self, member):
        if not member:
            return request.env['project.project'].sudo()
        return request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('capataz_id', '=', member.id)])

    def _obras_socio(self, member):
        if not member:
            return request.env['project.project'].sudo()
        return request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('socio_obra_ids', 'in', member.ids)])

    # ── coordinador: herramientas de sus obras ───────────────────────
    @http.route('/app/herramientas', type='http', auth='user', website=False)
    def herramientas(self, **kw):
        member = self._member()
        obras = self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        Equipo = request.env['maintenance.equipment'].sudo()
        asignadas = request.env['coop.asignacion.herramienta'].sudo().search([
            ('obra_id', 'in', obras.ids), ('state', '=', 'en_obra')])
        disponibles = Equipo.search([('estado_coop', '=', 'disponible')])
        incidentes = request.env['coop.incidente'].sudo().search([
            ('obra_id', 'in', obras.ids), ('state', '!=', 'resuelto')],
            order='create_date desc')
        return request.render('coop_portal.herramientas', {
            'member': member, 'obras': obras, 'asignadas': asignadas,
            'disponibles': disponibles, 'incidentes': incidentes,
            'tipo_labels': dict(request.env['coop.incidente']
                                ._fields['tipo'].selection),
        })

    @http.route('/app/herramientas/llevar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def herramientas_llevar(self, equipment_id, obra_id, **kw):
        member = self._member()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        equipo = request.env['maintenance.equipment'].sudo().browse(
            int(equipment_id)).exists()
        if (obra and equipo and obra.capataz_id.id == member.id
                and equipo.estado_coop == 'disponible'):
            request.env['coop.asignacion.herramienta'].sudo().create({
                'equipment_id': equipo.id, 'obra_id': obra.id,
                'member_id': member.id})
        return request.redirect('/app/herramientas')

    @http.route('/app/herramientas/devolver', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def herramientas_devolver(self, asignacion_id, **kw):
        member = self._member()
        asig = request.env['coop.asignacion.herramienta'].sudo().browse(
            int(asignacion_id)).exists()
        if asig and asig.obra_id.capataz_id.id == member.id:
            asig.action_devolver()
        return request.redirect('/app/herramientas')

    # ── socio: reportar rotura / pérdida ─────────────────────────────
    @http.route('/app/reportar', type='http', auth='user', website=False)
    def reportar(self, obra_id=None, **kw):
        member = self._member()
        obras = self._obras_socio(member) | self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        obra = obras.filtered(lambda o: o.id == int(obra_id)) if obra_id else False
        obra = obra[:1] if obra else obras[:1]
        equipos = request.env['maintenance.equipment'].sudo().search(
            ['|', ('obra_id', '=', obra.id), ('estado_coop', '!=', 'disponible')])
        materiales = request.env['coop.material'].sudo().search(
            [('active', '=', True)], order='name')
        return request.render('coop_portal.reportar', {
            'member': member, 'obra': obra, 'obras': obras,
            'equipos': equipos, 'materiales': materiales,
        })

    @http.route('/app/reportar/guardar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def reportar_guardar(self, obra_id, tipo, equipment_id=None,
                         material_id=None, cantidad=None, valor=None,
                         descripcion=None, **kw):
        member = self._member()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        socio_obras = self._obras_socio(member) | self._obras_coordina(member)
        if not obra or obra not in socio_obras or tipo not in dict(
                request.env['coop.incidente']._fields['tipo'].selection):
            return request.redirect('/app')
        es_herr = tipo in ('rotura_herramienta', 'perdida_herramienta')
        vals = {
            'tipo': tipo, 'obra_id': obra.id, 'reportado_por': member.id,
            'descripcion': descripcion or False,
        }
        if es_herr and equipment_id:
            vals['equipment_id'] = int(equipment_id)
        elif not es_herr and material_id:
            vals['material_id'] = int(material_id)
            try:
                vals['cantidad'] = float(str(cantidad).replace(',', '.'))
            except (TypeError, ValueError):
                vals['cantidad'] = 1.0
            try:
                vals['valor_estimado'] = float(str(valor).replace(',', '.'))
            except (TypeError, ValueError):
                vals['valor_estimado'] = 0.0
        inc = request.env['coop.incidente'].sudo().create(vals)
        return request.render('coop_portal.reportar_listo', {
            'member': member, 'inc': inc})
