from datetime import timedelta

from odoo import fields, http
from odoo.http import request


class CoopPortalAdmin(http.Controller):
    """Administrador en /app: máxima información, cero operativa (no valida
    avances). Tablero multi-obra, ruta crítica de toda la cartera y reportes.
    Todo lectura con sudo (el admin ve todo). rol = member.role == 'manager'."""

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)

    def _es_admin(self, member):
        return bool(member) and member.role == 'manager'

    def _obras_activas(self):
        return request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
        ], order='name')

    def _resumen_obra(self, obra):
        etapa = request.env['coop.etapa'].sudo().search(
            [('obra_id', '=', obra.id), ('state', '=', 'en_curso')], limit=1)
        return {
            'obra': obra,
            'avance': obra.avance_fisico,
            'coord': obra.capataz_id.name or '—',
            'saldo': etapa.saldo_sin_planificar if etapa else 0.0,
            'controlador': etapa.controlador if etapa else 0.0,
            'tiene_etapa': bool(etapa),
        }

    # ── tablero ──────────────────────────────────────────────────────
    @http.route('/app/admin', type='http', auth='user', website=False)
    def dashboard(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        obras = self._obras_activas()
        resumenes = [self._resumen_obra(o) for o in obras]
        # ruta crítica: tareas críticas de toda la cartera
        criticas = request.env['project.task'].sudo().search([
            ('project_id', 'in', obras.ids), ('es_critica', '=', True),
        ], order='fin_temprano')
        n_certs = request.env['coop.certificado'].sudo().search_count(
            [('state', 'in', ['presentado', 'aprobado']), ('firmado', '=', False)])
        n_pedidos = request.env['coop.pedido.material'].sudo().search_count(
            [('state', '=', 'pendiente')])
        return request.render('coop_portal.admin_dashboard', {
            'member': member, 'resumenes': resumenes,
            'n_criticas': len(criticas), 'n_certs': n_certs, 'n_pedidos': n_pedidos,
        })

    # ── ruta crítica multi-obra ──────────────────────────────────────
    @http.route('/app/admin/ruta', type='http', auth='user', website=False)
    def ruta(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        obras = self._obras_activas()
        data = []
        for o in obras:
            criticas = request.env['project.task'].sudo().search([
                ('project_id', '=', o.id), ('es_critica', '=', True),
            ], order='fin_temprano')
            data.append({'obra': o, 'criticas': criticas})
        return request.render('coop_portal.admin_ruta', {
            'member': member, 'data': data,
            'cat_labels': dict(
                request.env['project.task']._fields['categoria_tarea'].selection),
        })

    # ── reportes con rango de fechas ─────────────────────────────────
    @http.route('/app/admin/reportes', type='http', auth='user', website=False)
    def reportes(self, rango='mes', **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        hoy = fields.Date.context_today(request.env['coop.member'].sudo())
        desde = {
            'hoy': hoy,
            'semana': hoy - timedelta(days=7),
            'mes': hoy - timedelta(days=30),
        }.get(rango, hoy - timedelta(days=30))

        env = request.env
        ops, total_gasto, total_m2 = [], 0.0, 0.0
        for a in env['coop.avance.medicion'].sudo().search([
                ('state', '=', 'validado'), ('fecha', '>=', desde)],
                order='fecha desc'):
            if a.uom == 'm2':
                total_m2 += a.cantidad
            ops.append({'fecha': a.fecha, 'icono': '✏️', 'quien': a.member_id.name,
                        'obra': a.obra_id.name,
                        'detalle': '%s — %g %s' % (
                            a.foja_item_id.name, a.cantidad,
                            dict(a._fields['uom'].selection).get(a.uom, a.uom))})
        for p in env['coop.pedido.material'].sudo().search([
                ('state', '=', 'aceptado'),
                ('create_date', '>=', fields.Datetime.to_string(desde))],
                order='create_date desc'):
            ops.append({'fecha': p.create_date.date(), 'icono': '🧱',
                        'quien': p.member_id.name, 'obra': p.obra_id.name,
                        'detalle': p.name})
        for g in env['coop.proyeccion.gasto'].sudo().search([
                ('state', '=', 'pagado'),
                ('fecha_pago', '>=', desde)], order='fecha_pago desc'):
            total_gasto += g.importe
            ops.append({'fecha': g.fecha_pago, 'icono': '💸',
                        'quien': '—', 'obra': g.obra_id.name,
                        'detalle': '%s · $ %s' % (
                            g.name, '{:,.0f}'.format(g.importe).replace(',', '.'))})
        ops = [o for o in ops if o['fecha']]
        ops.sort(key=lambda o: o['fecha'], reverse=True)
        return request.render('coop_portal.admin_reportes', {
            'member': member, 'ops': ops[:40], 'rango': rango,
            'n_ops': len(ops), 'total_gasto': total_gasto, 'total_m2': total_m2,
        })
