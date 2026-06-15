from odoo import http
from odoo.http import request


class CoopPortalRelevamiento(http.Controller):
    """El socio relevador carga el relevamiento de una OT desde la app.
    Lecturas/escrituras con sudo tras verificar que el relevamiento es suyo
    (member_id == member), mismo patrón que el resto del portal."""

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid])], limit=1)

    @http.route('/app/relevar/<int:relevamiento_id>', type='http',
                auth='user', website=False)
    def relevar(self, relevamiento_id, **kw):
        member = self._member()
        rel = request.env['coop.relevamiento'].sudo().browse(
            relevamiento_id).exists()
        if not rel or not member or rel.member_id.id != member.id:
            return request.redirect('/app')
        return request.render('coop_portal.relevar', {
            'member': member, 'rel': rel, 'filas': range(6),
        })

    @http.route('/app/relevar/guardar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def relevar_guardar(self, relevamiento_id, observaciones=None, **kw):
        member = self._member()
        rel = request.env['coop.relevamiento'].sudo().browse(
            int(relevamiento_id)).exists()
        if not rel or not member or rel.member_id.id != member.id:
            return request.redirect('/app')
        Medida = request.env['coop.relevamiento.medida'].sudo()
        # limpiar medidas previas y recargar (la pantalla es la fuente)
        rel.medida_ids.unlink()
        for i in range(20):
            concepto = (kw.get('concepto_%d' % i) or '').strip()
            if not concepto:
                continue
            try:
                valor = float(str(kw.get('valor_%d' % i, '')).replace(',', '.'))
            except (TypeError, ValueError):
                valor = 0.0
            Medida.create({
                'relevamiento_id': rel.id, 'concepto': concepto,
                'valor': valor, 'unidad': (kw.get('unidad_%d' % i) or '').strip(),
            })
        rel.observaciones = observaciones or False
        if rel.state == 'pendiente':
            rel.action_cargado()
        return request.render('coop_portal.relevar_listo', {
            'member': member, 'rel': rel,
        })
