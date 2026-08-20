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
        n_validar = n_pedidos = n_corralon = n_otros = 0
        if obras_coord:
            n_validar = request.env['coop.avance.medicion'].sudo().search_count([
                ('foja_item_id.obra_id', 'in', obras_coord.ids),
                ('state', '=', 'borrador')])
            n_pedidos = request.env['coop.pedido.material'].sudo().search_count([
                ('obra_id', 'in', obras_coord.ids), ('state', '=', 'pendiente')])
            n_corralon = request.env['coop.pedido.material'].sudo().search_count([
                ('obra_id', 'in', obras_coord.ids), ('state', '=', 'aceptado'),
                ('orden_id', '=', False)])
            n_otros = request.env['coop.trabajo.otro'].sudo().search_count([
                ('obra_id', 'in', obras_coord.ids), ('state', '=', 'pendiente')])
        # asamblea en curso (votación abierta)
        asamblea = request.env['coop.assembly'].sudo().search(
            [('state', '=', 'open')], order='date desc', limit=1)
        # relevamiento asignado pendiente (el socio es relevador)
        relevamiento = request.env['coop.relevamiento'].sudo().search(
            [('member_id', '=', member.id), ('state', '=', 'pendiente')],
            order='create_date desc', limit=1)
        if obras_coord:
            return self._render('coop_portal.home_coordinador', {
                'member': member, 'obras_coord': obras_coord,
                'n_validar': n_validar, 'n_pedidos': n_pedidos,
                'n_corralon': n_corralon, 'n_otros': n_otros,
                'asamblea': asamblea,
                'relevamiento': relevamiento, 'nav_rol': 'coordinador',
            })
        return self._render('coop_portal.home', {
            'member': member, 'obras': obras, 'avances': avances,
            'es_coordinador': bool(obras_coord),
            'n_validar': n_validar, 'n_pedidos': n_pedidos,
            'n_corralon': n_corralon, 'n_otros': n_otros,
            'asamblea': asamblea, 'relevamiento': relevamiento,
        })

    # ── ayuda: preguntas frecuentes por rol ──────────────────────────
    @http.route('/app/ayuda', type='http', auth='user', website=False)
    def ayuda(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        if member.role == 'syndic':
            rol, nav_rol = 'sindico', 'sindico'
        elif member.role == 'manager':
            rol, nav_rol = 'admin', 'admin'
        elif request.env['project.project'].sudo().search_count([
                ('is_coop_obra', '=', True),
                ('estado_obra', 'in', ['planificacion', 'activa']),
                ('capataz_id', '=', member.id)]):
            rol, nav_rol = 'coordinador', 'coordinador'
        else:
            rol, nav_rol = 'socio', None
        return self._render('coop_portal.ayuda', {
            'member': member, 'rol': rol, 'nav_rol': nav_rol,
            'nav_activo': 'ayuda',
        })

    # ── mi aporte: producción + plata + transparencia del socio ──────
    @http.route('/app/aporte', type='http', auth='user', website=False)
    def aporte(self, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        Av = request.env['coop.avance.medicion'].sudo()
        val = Av.search([('member_id', '=', member.id), ('state', '=', 'validado')])
        borr = Av.search([('member_id', '=', member.id), ('state', '=', 'borrador')])
        # El trabajo cargado como "otro" no suma al avance físico (no tiene
        # unidad medible) pero SÍ a los jornales del socio: es lo que sostiene
        # que cargue lo que hizo aunque no estuviera previsto en la foja.
        Otro = request.env['coop.trabajo.otro']
        jornales = (sum(a.cantidad_trabajo for a in val if a.medida_trabajo == 'jornal')
                    + Otro.jornales_de(member, 'jornal'))
        horas = (sum(a.cantidad_trabajo for a in val if a.medida_trabajo == 'hora')
                 + Otro.jornales_de(member, 'hora'))
        tareas = (sum(a.cantidad_trabajo for a in val if a.medida_trabajo == 'tarea')
                  + Otro.jornales_de(member, 'tarea'))
        # Los rechazados van INCLUIDOS: si no, el socio no se entera de que le
        # rechazaron el trabajo ni lee el motivo, y el rechazo es justamente lo
        # que tiene que poder discutir.
        otros = Otro.sudo().search([
            ('member_id', '=', member.id),
        ], order='fecha desc', limit=8)
        # producción por ítem (validada) con su productividad
        porit = {}
        for a in val:
            it = a.foja_item_id
            d = porit.setdefault(it.id, {
                'name': it.name, 'uom': a.uom, 'cant': 0.0, 'jor': 0.0,
                'itemcant': it.cantidad, 'inc': it.incidencia})
            d['cant'] += a.cantidad
            if a.medida_trabajo == 'jornal':
                d['jor'] += a.cantidad_trabajo
        # aporte al avance de la obra: su producción ponderada por incidencia,
        # acotada por ítem (no puede aportar más que el 100% del ítem).
        aporte = 0.0
        for d in porit.values():
            if d['itemcant']:
                aporte += min(d['cant'] / d['itemcant'], 1.0) * d['inc']
            d['prod'] = round(d['cant'] / d['jor'], 1) if d['jor'] else 0.0
            d['cant'] = round(d['cant'], 1)
        items = sorted(porit.values(), key=lambda d: -d['cant'])
        # Plata en TRES estados. Antes eran dos y la producción validada
        # quedaba invisible: al validarla salía de "en camino" y no aparecía en
        # ningún lado hasta que se liquidaba. El socio con 10 m² certificados
        # leía "En camino $ 0". Y lo que el coordinador certifica desde
        # /app/otros nace directamente en 'validado', así que nunca pasaba por
        # el único estado que se mostraba.
        cobrado = sum(request.env['coop.payroll'].sudo().search(
            [('member_id', '=', member.id), ('state', '=', 'paid')]).mapped('net_amount'))
        esperando_validacion = sum(
            a.cantidad * a.foja_item_id.precio_unitario for a in borr)
        esperando_liquidacion = sum(
            a.cantidad * a.foja_item_id.precio_unitario for a in val)
        tot = cobrado + esperando_validacion + esperando_liquidacion
        pct = lambda x: round(x / tot * 100, 0) if tot else 0
        return self._render('coop_portal.mi_aporte', {
            'member': member, 'items': items[:8],
            'jornales': jornales, 'horas': horas, 'tareas': tareas,
            'aporte': round(aporte, 1), 'cobrado': cobrado,
            'esperando_validacion': esperando_validacion,
            'esperando_liquidacion': esperando_liquidacion,
            'n_borrador': len(borr), 'n_validado': len(val), 'otros': otros,
            'cobrado_pct': pct(cobrado),
            'val_pct': pct(esperando_validacion),
            'liq_pct': pct(esperando_liquidacion),
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

    # ── cargar "otro": trabajo que no entra en ningún ítem de la foja ──
    @http.route('/app/cargar/otro', type='http', auth='user', website=False)
    def cargar_otro(self, obra_id=None, **kw):
        member = self._member()
        if not member:
            return request.render('coop_portal.sin_socio')
        obra, obras = self._obra_o_primera(member, obra_id)
        if not obra:
            return self._render('coop_portal.sin_obra', {'member': member})
        return self._render('coop_portal.cargar_otro', {
            'member': member, 'obra': obra, 'medidas': MEDIDAS_TRABAJO,
            'error': None,
        })

    @http.route('/app/cargar/otro/confirmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def cargar_otro_confirmar(self, obra_id, descripcion, medida_trabajo,
                              cantidad_trabajo, foto=None, **kw):
        member = self._member()
        obra, _obras = self._obra_o_primera(member, obra_id)
        texto = (descripcion or '').strip()
        trabajo = self._a_numero(cantidad_trabajo)
        if not member or not obra or not texto or trabajo <= 0:
            return request.redirect('/app/cargar')
        if medida_trabajo not in [m[0] for m in MEDIDAS_TRABAJO]:
            return request.redirect('/app/cargar')
        # crear como usuario: la ACL y la record rule (propio + pendiente) aplican
        trabajo_otro = request.env['coop.trabajo.otro'].create({
            'obra_id': obra.id,
            'member_id': member.id,
            'descripcion': texto,
            'medida_trabajo': medida_trabajo,
            'cantidad_trabajo': trabajo,
        })
        # La foto es opcional: si falla, el trabajo YA quedó cargado y no se
        # pierde. Se avisa en la pantalla de confirmación en vez de tirar todo.
        aviso_foto = trabajo_otro.sudo().guardar_foto(foto)
        return self._render('coop_portal.cargar_otro_listo', {
            'member': member, 'trabajo': trabajo_otro.sudo(), 'obra': obra,
            'aviso_foto': aviso_foto,
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
