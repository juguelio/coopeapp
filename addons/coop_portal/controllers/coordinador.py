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
        })

    @http.route('/app/pedidos/accion', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def pedidos_accion(self, pedido_id, accion, cantidad=None, **kw):
        member = self._member()
        pedido = request.env['coop.pedido.material'].sudo().browse(
            int(pedido_id)).exists()
        if pedido and self._coordina_obra(member, pedido.obra_id):
            if accion == 'aceptar':
                pedido.action_aceptar()
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
