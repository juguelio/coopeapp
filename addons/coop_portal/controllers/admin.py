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

    # ── ruta crítica multi-obra, editable por oficio (carriles) ──────
    @http.route('/app/admin/ruta', type='http', auth='user', website=False)
    def ruta(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Task = request.env['project.task'].sudo()
        data = []
        for o in self._obras_activas():
            tasks = Task.search(
                [('project_id', '=', o.id)], order='categoria_tarea, fin_temprano')
            carriles = {}
            for tk in tasks:
                # aviso anti-cadena-falsa: dependencia con OTRO oficio
                cruces = tk.depend_on_ids.filtered(
                    lambda d: d.categoria_tarea and tk.categoria_tarea
                    and d.categoria_tarea != tk.categoria_tarea)
                carriles.setdefault(tk.categoria_tarea or 'otro', []).append({
                    'tk': tk, 'cruce': cruces.mapped('name')})
            carriles_list = [{
                'oficio': k, 'items': v,
                'dur': sum(i['tk'].duracion_dias for i in v),
                'criticas': sum(1 for i in v if i['tk'].es_critica),
            } for k, v in carriles.items()]
            data.append({'obra': o, 'carriles': carriles_list,
                         'fin_obra': max(tasks.mapped('fin_temprano') or [0.0])})
        return request.render('coop_portal.admin_ruta', {
            'member': member, 'data': data,
            'cat_labels': dict(
                Task._fields['categoria_tarea'].selection),
        })

    @http.route('/app/admin/ruta/editar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def ruta_editar(self, task_id, duracion=None, categoria=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Task = request.env['project.task'].sudo()
        tk = Task.browse(int(task_id)).exists()
        if tk and tk.project_id in self._obras_activas():
            vals = {}
            if duracion is not None:
                try:
                    vals['duracion_dias'] = max(
                        0.0, float(str(duracion).replace(',', '.')))
                except (TypeError, ValueError):
                    pass
            cats = dict(Task._fields['categoria_tarea'].selection)
            if categoria in cats:
                vals['categoria_tarea'] = categoria
            if vals:
                tk.write(vals)
                try:
                    tk.project_id.action_calcular_ruta_critica()
                except Exception:  # noqa: BLE001 — sin tareas o ciclo
                    pass
        return request.redirect('/app/admin/ruta')

    # ── reportes: sobre la vista unificada coop.operacion (M6) ───────
    @http.route('/app/admin/reportes', type='http', auth='user', website=False)
    def reportes(self, rango='mes', tipo=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        hoy = fields.Date.context_today(request.env['coop.member'].sudo())
        desde = {
            'hoy': hoy, 'semana': hoy - timedelta(days=7),
            'mes': hoy - timedelta(days=30),
        }.get(rango, hoy - timedelta(days=30))
        dominio = [('fecha', '>=', desde)]
        if tipo in ('avance', 'pedido', 'gasto', 'incidente'):
            dominio.append(('tipo', '=', tipo))
        iconos = {'avance': '✏️', 'pedido': '🧱', 'gasto': '💸',
                  'incidente': '⚠️'}
        registros = request.env['coop.operacion'].sudo().search(
            dominio, order='fecha desc')
        ops, total_gasto, total_m2 = [], 0.0, 0.0
        for o in registros:
            if o.tipo == 'gasto':
                total_gasto += o.monto
            if o.uom == 'm2':
                total_m2 += o.cantidad
            detalle = o.detalle or ''
            if o.tipo == 'gasto' and o.monto:
                detalle += ' · $ %s' % '{:,.0f}'.format(o.monto).replace(',', '.')
            elif o.cantidad and o.uom:
                detalle += ' — %g %s' % (o.cantidad, o.uom)
            ops.append({'fecha': o.fecha, 'icono': iconos.get(o.tipo, '•'),
                        'quien': o.member_id.name or '—',
                        'obra': o.obra_id.name or '—', 'detalle': detalle})
        return request.render('coop_portal.admin_reportes', {
            'member': member, 'ops': ops[:40], 'rango': rango, 'tipo': tipo,
            'n_ops': len(ops), 'total_gasto': total_gasto, 'total_m2': total_m2,
        })
