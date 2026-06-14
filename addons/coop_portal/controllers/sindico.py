from odoo import http
from odoo.http import request


class CoopPortalSindico(http.Controller):
    """Síndico en /app: panel de fiscalización (control distribuido, no
    eficiencia), pista de auditoría inmutable y firma de certificados con
    hash. Lectura total con sudo; la única escritura es firmar (verifica
    que el member es síndico)."""

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)

    def _es_sindico(self, member):
        return bool(member) and member.role == 'syndic'

    def _certs_a_firmar(self):
        return request.env['coop.certificado'].sudo().search([
            ('state', 'in', ['presentado', 'aprobado']),
            ('firmado', '=', False),
        ], order='date desc')

    # ── panel de control (home del síndico) ──────────────────────────
    @http.route('/app/control', type='http', auth='user', website=False)
    def control(self, **kw):
        member = self._member()
        if not self._es_sindico(member):
            return request.redirect('/app')
        certs = self._certs_a_firmar()
        asamblea = request.env['coop.assembly'].sudo().search(
            [('state', '=', 'open')], limit=1)
        obras = request.env['project.project'].sudo().search(
            [('is_coop_obra', '=', True), ('estado_obra', '=', 'activa')])
        # obras con controlador "en rojo" (controlador < 0 en su etapa en curso)
        en_rojo = 0
        for o in obras:
            et = request.env['coop.etapa'].sudo().search(
                [('obra_id', '=', o.id), ('state', '=', 'en_curso')], limit=1)
            if et and et.saldo_sin_planificar < 0:
                en_rojo += 1
        return request.render('coop_portal.sindico_control', {
            'member': member, 'n_certs': len(certs),
            'asamblea': asamblea, 'n_obras': len(obras), 'en_rojo': en_rojo,
        })

    # ── certificados a firmar ────────────────────────────────────────
    @http.route('/app/certificados', type='http', auth='user', website=False)
    def certificados(self, **kw):
        member = self._member()
        if not self._es_sindico(member):
            return request.redirect('/app')
        pendientes = self._certs_a_firmar()
        firmados = request.env['coop.certificado'].sudo().search(
            [('firmado', '=', True)], order='fecha_firma desc', limit=8)
        return request.render('coop_portal.sindico_certificados', {
            'member': member, 'pendientes': pendientes, 'firmados': firmados,
        })

    @http.route('/app/firmar', type='http', auth='user', website=False)
    def firmar_ver(self, cert_id, **kw):
        member = self._member()
        cert = request.env['coop.certificado'].sudo().browse(int(cert_id)).exists()
        if not self._es_sindico(member) or not cert or cert.firmado:
            return request.redirect('/app/certificados')
        return request.render('coop_portal.sindico_firmar', {
            'member': member, 'cert': cert,
        })

    @http.route('/app/firmar/confirmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def firmar_confirmar(self, cert_id, **kw):
        member = self._member()
        cert = request.env['coop.certificado'].sudo().browse(int(cert_id)).exists()
        if not self._es_sindico(member) or not cert or cert.firmado:
            return request.redirect('/app/certificados')
        cert.action_firmar(member=member)
        return request.render('coop_portal.sindico_firmado', {
            'member': member, 'cert': cert,
        })

    # ── pista de auditoría (operaciones recientes, inmutable) ─────────
    @http.route('/app/auditoria', type='http', auth='user', website=False)
    def auditoria(self, **kw):
        member = self._member()
        if not self._es_sindico(member):
            return request.redirect('/app')
        env = request.env
        ops = []
        for a in env['coop.avance.medicion'].sudo().search(
                [('state', '=', 'validado')], order='fecha desc', limit=15):
            ops.append({
                'fecha': a.fecha, 'tipo': 'Avance', 'icono': '✏️',
                'quien': a.member_id.name, 'obra': a.obra_id.name,
                'detalle': '%s — %g %s' % (
                    a.foja_item_id.name, a.cantidad,
                    dict(a._fields['uom'].selection).get(a.uom, a.uom)),
            })
        for p in env['coop.pedido.material'].sudo().search(
                [('state', 'in', ['aceptado', 'rechazado'])],
                order='create_date desc', limit=15):
            ops.append({
                'fecha': p.create_date.date() if p.create_date else False,
                'tipo': 'Pedido', 'icono': '🧱',
                'quien': p.member_id.name, 'obra': p.obra_id.name,
                'detalle': '%s (%s)' % (p.name, p.state),
            })
        for c in env['coop.certificado'].sudo().search(
                [('firmado', '=', True)], order='fecha_firma desc', limit=10):
            ops.append({
                'fecha': c.fecha_firma.date() if c.fecha_firma else False,
                'tipo': 'Firma', 'icono': '✍️',
                'quien': c.firmado_por_id.name, 'obra': c.obra_id.name,
                'detalle': 'Firmó %s · hash %s' % (
                    c.name, (c.hash_firma or '')[:8]),
            })
        ops = [o for o in ops if o['fecha']]
        ops.sort(key=lambda o: o['fecha'], reverse=True)
        return request.render('coop_portal.sindico_auditoria', {
            'member': member, 'ops': ops[:30],
        })
