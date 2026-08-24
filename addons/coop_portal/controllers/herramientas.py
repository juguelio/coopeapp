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
        Asig = request.env['coop.asignacion.herramienta'].sudo()
        asignadas = Asig.search([
            ('obra_id', 'in', obras.ids), ('state', '=', 'en_obra')])
        # Los préstamos externos NO se filtran por obra: la herramienta puede
        # haber salido sin obra asociada, y justamente esas son las que se
        # pierden. Se listan las que prestó este coordinador o que salieron a
        # raíz de una obra suya. Más viejo primero: lo que más urge reclamar.
        prestadas = Asig.search([
            ('state', '=', 'prestada'),
            '|', ('obra_id', 'in', obras.ids), ('member_id', '=', member.id),
        ], order='fecha_retiro asc')
        disponibles = Equipo.search([('estado_coop', '=', 'disponible')])
        incidentes = request.env['coop.incidente'].sudo().search([
            ('obra_id', 'in', obras.ids), ('state', '!=', 'resuelto')],
            order='create_date desc')
        return request.render('coop_portal.herramientas', {
            'member': member, 'obras': obras, 'asignadas': asignadas,
            'prestadas': prestadas,
            'disponibles': disponibles, 'incidentes': incidentes,
            'tipo_labels': dict(request.env['coop.incidente']
                                ._fields['tipo'].selection),
        })

    @http.route('/app/herramientas/prestar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def herramientas_prestar(self, equipment_id, prestado_a, prestado_tel=None,
                             prestado_doc=None, fecha_devolucion_prevista=None,
                             obra_id=None, **kw):
        """Prestar una herramienta a alguien de afuera de la cooperativa.

        Existe porque antes no se podía: la asignación exigía una obra propia y
        un socio activo, así que el préstamo al equipo de arquitectos no tenía
        dónde anotarse. La herramienta no se pierde por desprolijidad: se
        pierde porque prestarla bien llevaba más trabajo que prestarla mal.
        """
        member = self._member()
        obras = self._obras_coordina(member)
        equipo = request.env['maintenance.equipment'].sudo().browse(
            int(equipment_id)).exists()
        # sin member/equipo, o sin obras que coordine, no compara .id
        # (mismo patrón anti-bypass False == False del resto del módulo)
        if not member or not equipo or not obras:
            return request.redirect('/app')
        if not (prestado_a or '').strip():
            return request.redirect('/app/herramientas')
        if equipo.estado_coop != 'disponible':
            return request.redirect('/app/herramientas')
        # la obra es opcional, pero si viene tiene que ser una que coordina
        obra = obras.filtered(lambda o: o.id == int(obra_id)) if obra_id else False
        request.env['coop.asignacion.herramienta'].sudo().create({
            'equipment_id': equipo.id,
            'tipo': 'externo',
            'obra_id': obra.id if obra else False,
            'member_id': member.id,
            'prestado_a': prestado_a.strip(),
            'prestado_tel': (prestado_tel or '').strip() or False,
            'prestado_doc': (prestado_doc or '').strip() or False,
            'fecha_devolucion_prevista': fecha_devolucion_prevista or False,
        })
        return request.redirect('/app/herramientas')

    @http.route('/app/herramientas/llevar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def herramientas_llevar(self, equipment_id, obra_id, **kw):
        member = self._member()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        equipo = request.env['maintenance.equipment'].sudo().browse(
            int(equipment_id)).exists()
        # guardas explícitas: sin member/obra/equipo, o sin capataz, no se
        # compara .id (evita el bypass False == False)
        if not member or not obra or not equipo:
            return request.redirect('/app')
        if (obra.capataz_id and obra.capataz_id.id == member.id
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
        if not member or not asig:
            return request.redirect('/app')
        # Un préstamo externo puede no tener obra: entonces lo devuelve quien
        # lo prestó. Con obra, manda el capataz, como siempre.
        capataz = asig.obra_id.capataz_id
        autorizado = bool(
            (capataz and capataz.id == member.id)
            or (asig.tipo == 'externo' and asig.member_id
                and asig.member_id.id == member.id))
        if autorizado:
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
