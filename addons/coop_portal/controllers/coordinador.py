from urllib.parse import quote

from odoo import http
from odoo.http import request


class CoopPortalCoordinador(http.Controller):
    """Coordinador en /app: valida avances y gestiona pedidos de SUS obras
    (las que coordina = capataz_id). La autorización se verifica en el
    controller (el member es capataz de la obra del registro) y la escritura
    va con sudo(). Deuda: cuando exista group_coop_coordinador, mover a
    record rule. El socio también pide materiales desde acá."""

    # ── helpers ──────────────────────────────────────────────────────
    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    def _obras_coordina(self, member):
        if not member:
            return request.env['project.project'].sudo()
        return request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('capataz_id', '=', member.id),
        ])

    def _coordina_obra(self, member, obra):
        return bool(obra) and obra.capataz_id.id == member.id

    def _corralones(self):
        return request.env['coop.corralon'].sudo().search(
            [('active', '=', True)], order='name')

    # ── bandeja de avances a validar ─────────────────────────────────
    @http.route('/app/validar', type='http', auth='user', website=False)
    def validar(self, **kw):
        member = self._member()
        obras = self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        avances = request.env['coop.avance.medicion'].sudo().search([
            ('foja_item_id.obra_id', 'in', obras.ids),
            ('state', '=', 'borrador'),
        ], order='fecha desc')
        return request.render('coop_portal.coord_validar', {
            'member': member, 'avances': avances,
            'uom_labels': dict(request.env['coop.foja.item']
                               ._fields['uom'].selection),
            'medida_labels': dict(request.env['coop.avance.medicion']
                                  ._fields['medida_trabajo'].selection),
        })

    @http.route('/app/validar/accion', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def validar_accion(self, avance_id, accion, **kw):
        member = self._member()
        avance = request.env['coop.avance.medicion'].sudo().browse(
            int(avance_id)).exists()
        if avance and self._coordina_obra(member, avance.foja_item_id.obra_id):
            if accion == 'validar':
                avance.action_validar()
            elif accion == 'rechazar':
                avance.action_borrador()  # vuelve al socio; queda registro
        return request.redirect('/app/validar')

    # ── bandeja de pedidos ───────────────────────────────────────────
    @http.route('/app/pedidos', type='http', auth='user', website=False)
    def pedidos(self, **kw):
        member = self._member()
        obras = self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        pedidos = request.env['coop.pedido.material'].sudo().search([
            ('obra_id', 'in', obras.ids), ('state', '=', 'pendiente'),
        ], order='create_date desc')
        return request.render('coop_portal.coord_pedidos', {
            'member': member, 'pedidos': pedidos,
            'corralones': self._corralones(),
        })

    @http.route('/app/pedidos/accion', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def pedidos_accion(self, pedido_id, accion, cantidad=None,
                       corralon_id=None, **kw):
        member = self._member()
        pedido = request.env['coop.pedido.material'].sudo().browse(
            int(pedido_id)).exists()
        if pedido and self._coordina_obra(member, pedido.obra_id):
            if accion == 'aceptar':
                pedido.action_aceptar()
                if corralon_id:
                    pedido.corralon_id = int(corralon_id)
            elif accion == 'rechazar':
                pedido.action_rechazar()
            elif accion == 'corregir':
                try:
                    nueva = float(str(cantidad).replace(',', '.'))
                except (TypeError, ValueError):
                    nueva = 0.0
                if nueva > 0:
                    pedido.action_corregir_cantidad(nueva)
        return request.redirect('/app/pedidos')

    # ── consolidar pedidos → orden al corralón ───────────────────────
    @http.route('/app/corralon', type='http', auth='user', website=False)
    def corralon(self, **kw):
        member = self._member()
        obras = self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        Pedido = request.env['coop.pedido.material'].sudo()
        # aceptados y todavía sin orden
        sin_orden = Pedido.search([
            ('obra_id', 'in', obras.ids), ('state', '=', 'aceptado'),
            ('orden_id', '=', False),
        ], order='obra_id, corralon_id')
        sin_corralon = sin_orden.filtered(lambda p: not p.corralon_id)
        # agrupar los que ya tienen corralón por (obra, corralón)
        grupos = {}
        for p in sin_orden.filtered(lambda p: p.corralon_id):
            grupos.setdefault((p.obra_id, p.corralon_id), request.env[
                'coop.pedido.material'].sudo())
            grupos[(p.obra_id, p.corralon_id)] |= p
        grupos_list = [
            {'obra': o, 'corralon': c, 'pedidos': peds}
            for (o, c), peds in grupos.items()
        ]
        # órdenes ya armadas de sus obras
        ordenes = request.env['coop.orden.corralon'].sudo().search(
            [('obra_id', 'in', obras.ids)], order='create_date desc', limit=20)
        ahorro_borrador = sum(ordenes.filtered(
            lambda o: o.estado == 'borrador').mapped('ahorro_estimado'))
        return request.render('coop_portal.coord_corralon', {
            'member': member, 'sin_corralon': sin_corralon,
            'grupos': grupos_list, 'ordenes': ordenes,
            'corralones': self._corralones(),
            'n_optimizables': len(sin_orden),
            'ahorro_borrador': ahorro_borrador,
            'estado_labels': dict(request.env['coop.orden.corralon']
                                  ._fields['estado'].selection),
        })

    @http.route('/app/corralon/optimizar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_optimizar(self, **kw):
        member = self._member()
        obras = self._obras_coordina(member)
        if not obras:
            return request.redirect('/app')
        Orden = request.env['coop.orden.corralon'].sudo()
        Pedido = request.env['coop.pedido.material'].sudo()
        # optimizar por obra (los acopios y precios son por obra)
        for obra in obras:
            pedidos = Pedido.search([
                ('obra_id', '=', obra.id), ('state', '=', 'aceptado'),
                ('orden_id', '=', False),
            ])
            if pedidos:
                Orden.generar_desde_pedidos(obra, pedidos, creado_por=member)
        return request.redirect('/app/corralon')

    @http.route('/app/corralon/asignar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_asignar(self, pedido_id, corralon_id, **kw):
        member = self._member()
        pedido = request.env['coop.pedido.material'].sudo().browse(
            int(pedido_id)).exists()
        if (pedido and corralon_id
                and self._coordina_obra(member, pedido.obra_id)):
            pedido.corralon_id = int(corralon_id)
        return request.redirect('/app/corralon')

    @http.route('/app/corralon/armar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_armar(self, obra_id, corralon_id, **kw):
        member = self._member()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        if not obra or not self._coordina_obra(member, obra):
            return request.redirect('/app/corralon')
        pedidos = request.env['coop.pedido.material'].sudo().search([
            ('obra_id', '=', obra.id), ('corralon_id', '=', int(corralon_id)),
            ('state', '=', 'aceptado'), ('orden_id', '=', False),
        ])
        if not pedidos:
            return request.redirect('/app/corralon')
        orden = request.env['coop.orden.corralon'].sudo().create({
            'corralon_id': int(corralon_id), 'obra_id': obra.id,
            'creado_por': member.id,
        })
        pedidos.write({'orden_id': orden.id})
        return request.redirect('/app/corralon/orden/%d' % orden.id)

    @http.route('/app/corralon/orden/<int:orden_id>', type='http',
                auth='user', website=False)
    def corralon_orden(self, orden_id, **kw):
        member = self._member()
        orden = request.env['coop.orden.corralon'].sudo().browse(
            orden_id).exists()
        if not orden or not self._coordina_obra(member, orden.obra_id):
            return request.redirect('/app/corralon')
        num = orden.corralon_id.whatsapp_num or ''
        texto = quote(orden.mensaje or '')
        wa_url = ('https://wa.me/%s?text=%s' % (num, texto)) if num else ''
        sms_url = 'sms:%s?body=%s' % (num, texto)
        # para el override: candidatos por línea con el costo de cada alternativa
        Orden = request.env['coop.orden.corralon'].sudo()
        saldo = {ac.id: ac.saldo for ac in request.env['coop.acopio'].sudo()
                 .search([('obra_id', '=', orden.obra_id.id),
                          ('state', '=', 'vigente')])}
        lineas_data = []
        for ln in orden.linea_ids:
            cand = Orden._candidatos_material(orden.obra_id, ln.material_id, saldo)
            opciones = []
            for c in cand:
                actual = (c['corralon'].id == orden.corralon_id.id
                          and c['tipo'] == ln.fuente)
                opciones.append({
                    'corralon': c['corralon'], 'tipo': c['tipo'],
                    'precio': c['precio'],
                    'delta': (c['precio'] - ln.precio_unitario) * ln.cantidad,
                    'actual': actual,
                })
            lineas_data.append({'linea': ln, 'opciones': opciones})
        return request.render('coop_portal.coord_orden', {
            'member': member, 'orden': orden,
            'wa_url': wa_url, 'sms_url': sms_url, 'lineas_data': lineas_data,
            'estado_labels': dict(request.env['coop.orden.corralon']
                                  ._fields['estado'].selection),
        })

    @http.route('/app/corralon/linea/reasignar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_linea_reasignar(self, linea_id, opcion, **kw):
        member = self._member()
        Linea = request.env['coop.orden.corralon.linea'].sudo()
        Orden = request.env['coop.orden.corralon'].sudo()
        ln = Linea.browse(int(linea_id)).exists()
        if not ln or not self._coordina_obra(member, ln.obra_id):
            return request.redirect('/app/corralon')
        try:
            corralon_id, tipo = str(opcion).split(':')
        except ValueError:
            return request.redirect('/app/corralon/orden/%d' % ln.orden_id.id)
        orden_orig = ln.orden_id
        if orden_orig.estado != 'borrador':
            return request.redirect('/app/corralon/orden/%d' % orden_orig.id)
        # recalcular el candidato elegido server-side (no confiar en el precio)
        saldo = {ac.id: ac.saldo for ac in request.env['coop.acopio'].sudo()
                 .search([('obra_id', '=', ln.obra_id.id),
                          ('state', '=', 'vigente')])}
        cand = Orden._candidatos_material(ln.obra_id, ln.material_id, saldo)
        elegido = next((c for c in cand
                        if c['corralon'].id == int(corralon_id)
                        and c['tipo'] == tipo), False)
        if not elegido:
            return request.redirect('/app/corralon/orden/%d' % orden_orig.id)
        destino = orden_orig
        if elegido['corralon'].id != orden_orig.corralon_id.id:
            destino = Orden.search([
                ('corralon_id', '=', elegido['corralon'].id),
                ('obra_id', '=', ln.obra_id.id), ('estado', '=', 'borrador'),
            ], limit=1) or Orden.create({
                'corralon_id': elegido['corralon'].id,
                'obra_id': ln.obra_id.id, 'creado_por': member.id})
        ln.write({
            'orden_id': destino.id, 'fuente': elegido['tipo'],
            'acopio_id': elegido['acopio'] and elegido['acopio'].id or False,
            'precio_unitario': elegido['precio'], 'asignacion_manual': True,
            'razon': 'Elegido a mano por el coordinador',
        })
        # actualizar importes y limpiar orden origen si quedó vacía
        for o in (orden_orig, destino):
            o.importe_total = o.total_lineas
        if orden_orig.id != destino.id and not orden_orig.linea_ids:
            orden_orig.pedido_ids.write({'orden_id': destino.id})
            orden_orig.unlink()
        return request.redirect('/app/corralon/orden/%d' % destino.id)

    @http.route('/app/corralon/orden/accion', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_orden_accion(self, orden_id, accion, importe=None, **kw):
        member = self._member()
        orden = request.env['coop.orden.corralon'].sudo().browse(
            int(orden_id)).exists()
        if not orden or not self._coordina_obra(member, orden.obra_id):
            return request.redirect('/app/corralon')
        if accion == 'enviar':
            orden.action_enviar()
        elif accion == 'confirmar':
            orden.action_confirmar()
        elif accion == 'entregar':
            try:
                monto = float(str(importe).replace(',', '.'))
            except (TypeError, ValueError):
                monto = 0.0
            # exigir importe > 0: entregada es terminal e imputa el gasto;
            # sin importe no se puede re-imputar después
            if monto > 0:
                orden.importe_total = monto
                orden.action_entregar()
        elif accion == 'borrador':
            orden.action_volver_borrador()
        return request.redirect('/app/corralon/orden/%d' % orden.id)

    # ── socio: pedir materiales ──────────────────────────────────────
    @http.route('/app/pedir', type='http', auth='user', website=False)
    def pedir_paso1(self, obra_id=None, **kw):
        member = self._member()
        if not member:
            return request.redirect('/app')
        obras = request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('socio_obra_ids', 'in', member.ids),
        ])
        if not obras:
            return request.redirect('/app/obra')
        obra = obras.filtered(lambda o: o.id == int(obra_id)) if obra_id else False
        obra = obra[0] if obra else obras[0]
        materiales = request.env['coop.material'].sudo().search(
            [('active', '=', True)], order='name')
        return request.render('coop_portal.pedir_paso1', {
            'member': member, 'obra': obra, 'materiales': materiales,
        })

    @http.route('/app/pedir/cantidad', type='http', auth='user', website=False)
    def pedir_paso2(self, obra_id, material_id, **kw):
        member = self._member()
        material = request.env['coop.material'].sudo().browse(
            int(material_id)).exists()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        if not member or not material or not obra:
            return request.redirect('/app/pedir')
        return request.render('coop_portal.pedir_paso2', {
            'member': member, 'obra': obra, 'material': material,
            'uom_compra_labels': dict(request.env['coop.material']
                                      ._fields['uom'].selection),
        })

    @http.route('/app/pedir/confirmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def pedir_confirmar(self, obra_id, material_id, cantidad, nota=None, **kw):
        member = self._member()
        material = request.env['coop.material'].sudo().browse(
            int(material_id)).exists()
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists()
        try:
            cant = float(str(cantidad).replace(',', '.'))
        except (TypeError, ValueError):
            cant = 0.0
        if not member or not material or not obra or cant <= 0:
            return request.redirect('/app/pedir')
        # crear como el usuario: la record rule (propio + pendiente) aplica
        pedido = request.env['coop.pedido.material'].create({
            'obra_id': obra.id, 'member_id': member.id,
            'material_id': material.id, 'uom': material.uom,
            'cantidad': cant, 'nota': nota or False,
        })
        return request.render('coop_portal.pedir_listo', {
            'member': member, 'pedido': pedido.sudo(), 'material': material,
        })
