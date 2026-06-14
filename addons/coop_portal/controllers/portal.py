from odoo import http
from odoo.http import request

MEDIDAS_TRABAJO = [
    ('jornal', 'Jornal diario', '📅'),
    ('hora', 'Horas trabajadas', '⏰'),
    ('tarea', 'Tarea completa', '✅'),
]


class CoopPortal(http.Controller):
    """App de socios: lectura con sudo() filtrado por pertenencia (los socios
    no tienen permisos sobre project.*), escritura siempre como el usuario
    (ACL + record rules mandan)."""

    # ── helpers ──────────────────────────────────────────────────────
    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    def _obras(self, member):
        return request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('socio_obra_ids', 'in', member.ids),
        ])

    def _obra_o_primera(self, member, obra_id):
        obras = self._obras(member)
        if obra_id:
            elegida = obras.filtered(lambda o: o.id == int(obra_id))
            if elegida:
                return elegida[0], obras
        return (obras[0] if obras else obras), obras

    def _render(self, template, valores):
        member = valores.get('member') or self._member()
        valores.setdefault('member', member)
        env = request.env
        valores.setdefault('uom_labels', dict(
            env['coop.foja.item']._fields['uom'].selection))
        valores.setdefault('medida_labels', dict(
            env['coop.avance.medicion']._fields['medida_trabajo'].selection))
        valores.setdefault('payroll_state_labels', dict(
            env['coop.payroll']._fields['state'].selection))
        valores.setdefault('etapa_state_labels', dict(
            env['coop.etapa']._fields['state'].selection))
        return request.render(template, valores)

    # ── inicio ───────────────────────────────────────────────────────
    @http.route('/app', type='http', auth='user', website=False)
    def home(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        # síndico y administrador tienen su propio panel
        if member.role == 'syndic':
            return request.redirect('/app/control')
        if member.role == 'manager':
            return request.redirect('/app/admin')
        obras = self._obras(member)
        avances = request.env['coop.avance.medicion'].sudo().search(
            [('member_id', '=', member.id)], order='fecha desc, id desc', limit=3)
        # ¿coordina obras? → accesos a sus bandejas
        obras_coord = request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('capataz_id', '=', member.id),
        ])
        n_validar = n_pedidos = n_corralon = 0
        if obras_coord:
            n_validar = request.env['coop.avance.medicion'].sudo().search_count([
                ('foja_item_id.obra_id', 'in', obras_coord.ids),
                ('state', '=', 'borrador')])
            n_pedidos = request.env['coop.pedido.material'].sudo().search_count([
                ('obra_id', 'in', obras_coord.ids), ('state', '=', 'pendiente')])
            n_corralon = request.env['coop.pedido.material'].sudo().search_count([
                ('obra_id', 'in', obras_coord.ids), ('state', '=', 'aceptado'),
                ('orden_id', '=', False)])
        # asamblea en curso (votación abierta)
        asamblea = request.env['coop.assembly'].sudo().search(
            [('state', '=', 'open')], order='date desc', limit=1)
        return self._render('coop_portal.home', {
            'member': member, 'obras': obras, 'avances': avances,
            'es_coordinador': bool(obras_coord),
            'n_validar': n_validar, 'n_pedidos': n_pedidos,
            'n_corralon': n_corralon,
            'asamblea': asamblea,
        })

    # ── cargar avance (wizard 3 pasos) ───────────────────────────────
    @http.route('/app/cargar', type='http', auth='user', website=False)
    def cargar_paso1(self, obra_id=None, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        obra, obras = self._obra_o_primera(member, obra_id)
        if not obra:
            return self._render('coop_portal.sin_obra', {'member': member})
        items = request.env['coop.foja.item'].sudo().search(
            [('obra_id', '=', obra.id)], order='item')
        return self._render('coop_portal.cargar_paso1', {
            'member': member, 'obra': obra, 'obras': obras, 'items': items,
        })

    @http.route('/app/cargar/cantidad', type='http', auth='user', website=False)
    def cargar_paso2(self, item_id, **kw):
        member = self._member()
        item = request.env['coop.foja.item'].sudo().browse(int(item_id)).exists()
        if not member or not item:
            return request.redirect('/app/cargar')
        return self._render('coop_portal.cargar_paso2', {
            'member': member, 'item': item,
        })

    @http.route('/app/cargar/trabajo', type='http', auth='user', website=False)
    def cargar_paso3(self, item_id, cantidad, **kw):
        member = self._member()
        item = request.env['coop.foja.item'].sudo().browse(int(item_id)).exists()
        cantidad = self._a_numero(cantidad)
        if not member or not item or cantidad <= 0:
            return request.redirect('/app/cargar')
        return self._render('coop_portal.cargar_paso3', {
            'member': member, 'item': item, 'cantidad': cantidad,
            'medidas': MEDIDAS_TRABAJO,
        })

    @http.route('/app/cargar/confirmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def cargar_confirmar(self, item_id, cantidad, medida_trabajo,
                         cantidad_trabajo, **kw):
        member = self._member()
        item = request.env['coop.foja.item'].sudo().browse(int(item_id)).exists()
        cantidad = self._a_numero(cantidad)
        trabajo = self._a_numero(cantidad_trabajo)
        if not member or not item or cantidad <= 0 or trabajo <= 0:
            return request.redirect('/app/cargar')
        if medida_trabajo not in [m[0] for m in MEDIDAS_TRABAJO]:
            return request.redirect('/app/cargar')
        # crear como usuario: la ACL y la record rule (propio + borrador) aplican
        avance = request.env['coop.avance.medicion'].create({
            'foja_item_id': item.id,
            'member_id': member.id,
            'cantidad': cantidad,
            'medida_trabajo': medida_trabajo,
            'cantidad_trabajo': trabajo,
        })
        return self._render('coop_portal.cargar_listo', {
            'member': member, 'avance': avance.sudo(), 'item': item,
        })

    # ── mi plata ─────────────────────────────────────────────────────
    @http.route('/app/plata', type='http', auth='user', website=False)
    def plata(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        payrolls = request.env['coop.payroll'].sudo().search(
            [('member_id', '=', member.id)], order='date_to desc', limit=6)
        validados = request.env['coop.avance.medicion'].sudo().search(
            [('member_id', '=', member.id), ('state', '=', 'validado')],
            order='fecha desc', limit=10)
        return self._render('coop_portal.plata', {
            'member': member, 'payrolls': payrolls, 'validados': validados,
        })

    # ── la obra (transparencia) ──────────────────────────────────────
    @http.route('/app/obra', type='http', auth='user', website=False)
    def obra(self, obra_id=None, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        obra, obras = self._obra_o_primera(member, obra_id)
        if not obra:
            return self._render('coop_portal.sin_obra', {'member': member})
        etapa = request.env['coop.etapa'].sudo().search(
            [('obra_id', '=', obra.id), ('state', '=', 'en_curso')], limit=1)
        if not etapa:
            etapa = request.env['coop.etapa'].sudo().search(
                [('obra_id', '=', obra.id)], order='numero desc', limit=1)
        # acopios vigentes de la obra (transparencia ACI: todos ven la plata
        # congelada que queda en cada corralón)
        acopios = request.env['coop.acopio'].sudo().search([
            ('obra_id', '=', obra.id), ('state', '=', 'vigente'),
        ], order='corralon_id, fecha')
        return self._render('coop_portal.obra', {
            'member': member, 'obra': obra, 'obras': obras, 'etapa': etapa,
            'acopios': acopios,
        })

    # ── util ─────────────────────────────────────────────────────────
    @staticmethod
    def _a_numero(valor):
        try:
            return float(str(valor).replace(',', '.'))
        except (TypeError, ValueError):
            return 0.0
