import io
import json
import urllib.parse
from datetime import timedelta

import xlsxwriter

from odoo import fields, http
from odoo.http import content_disposition, request

# Estados nativos de project.task que usa la hoja de ruta. Cerrar una tarea a
# mano la saca del camino crítico (ver coop_construction/project_project.py).
ESTADO_TERMINADA = '1_done'
ESTADO_EN_CURSO = '01_in_progress'


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
        n_relev = request.env['coop.relevamiento'].sudo().search_count(
            [('state', '=', 'cargado')])
        return request.render('coop_portal.admin_dashboard', {
            'member': member, 'resumenes': resumenes,
            'n_criticas': len(criticas), 'n_certs': n_certs, 'n_pedidos': n_pedidos,
            'n_relev': n_relev, 'creada': kw.get('creada'),
        })

    # ── nuevo trabajo (OT) + mandar a medir, desde el celular ────────
    @http.route('/app/admin/nuevo', type='http', auth='user', website=False)
    def ot_nueva(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        # solo socios que pueden ABRIR la app (tienen usuario): si no, el
        # relevamiento quedaría asignado a alguien que no puede cargarlo.
        socios = request.env['coop.member'].sudo().search(
            [('state', '=', 'active'),
             ('partner_id.user_ids', '!=', False)], order='name')
        return request.render('coop_portal.admin_ot_nueva', {
            'member': member, 'socios': socios,
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/nuevo/crear', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def ot_crear(self, cliente=None, telefono=None, ubicacion=None,
                 descripcion=None, relevador_id=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        cliente = (cliente or '').strip()
        if not cliente:
            return request.redirect('/app/admin/nuevo')
        Partner = request.env['res.partner'].sudo()
        tel = (telefono or '').strip()
        partner = Partner.search([('name', '=ilike', cliente)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': cliente, 'company_type': 'person',
                'phone': tel or False})
        elif tel and not partner.phone:
            partner.phone = tel
        vals = {
            'cliente_id': partner.id, 'administrador_id': member.id,
            'ubicacion': (ubicacion or '').strip() or False,
            'descripcion': (descripcion or '').strip() or False,
        }
        rel = None
        try:
            rel = int(relevador_id) if relevador_id else None
        except (TypeError, ValueError):
            rel = None
        if rel:
            relm = request.env['coop.member'].sudo().browse(rel).exists()
            # revalidar: el relevador tiene que poder abrir la app
            if not (relm and relm.partner_id.user_ids):
                rel = None
        if rel:
            vals['relevador_id'] = rel
        ot = request.env['coop.orden.trabajo'].sudo().create(vals)
        if rel:
            ot.action_a_relevamiento()
        return request.redirect('/app/admin?creada=1')

    # ── bandeja de relevamientos cargados (listos para presupuestar) ──
    @http.route('/app/admin/relevamientos', type='http', auth='user',
                website=False)
    def relevamientos(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        rels = request.env['coop.relevamiento'].sudo().search(
            [('state', '=', 'cargado')], order='fecha desc, id desc')
        return request.render('coop_portal.admin_relevamientos', {
            'member': member, 'rels': rels,
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/relevamiento/<int:rel_id>', type='http',
                auth='user', website=False)
    def relevamiento_detalle(self, rel_id, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        rel = request.env['coop.relevamiento'].sudo().browse(rel_id).exists()
        if not rel:
            return request.redirect('/app/admin/relevamientos')
        return request.render('coop_portal.admin_relevamiento_detalle', {
            'member': member, 'rel': rel,
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/relevamiento/validar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def relevamiento_validar(self, rel_id=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        try:
            rel = request.env['coop.relevamiento'].sudo().browse(
                int(rel_id)).exists() if rel_id else None
        except (TypeError, ValueError):
            rel = None
        if rel and rel.state == 'cargado':
            rel.action_validar()
        return request.redirect('/app/admin/relevamientos')

    # ── corralón: armar una orden directa, rápido (M8-4) ─────────────
    @http.route('/app/admin/corralon', type='http', auth='user', website=False)
    def corralon(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        return request.render('coop_portal.admin_corralon', {
            'member': member, 'obras': self._obras_activas(),
            'corralones': request.env['coop.corralon'].sudo().search(
                [('active', '=', True)], order='name'),
            'materiales': request.env['coop.material'].sudo().search(
                [('active', '=', True)], order='name'),
            'ordenes': request.env['coop.orden.corralon'].sudo().search(
                [], order='create_date desc', limit=10),
            'filas': range(6),
            'estado_labels': dict(request.env['coop.orden.corralon']
                                  ._fields['estado'].selection),
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/corralon/crear', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_crear(self, obra_id=None, **kw):
        """El admin elige obra + materiales; el OPTIMIZADOR (M2) asigna cada
        material a la fuente más barata (acopio congelado primero, compra al
        mejor precio después) y arma una orden por corralón con su ahorro."""
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists() if (obra_id or '').isdigit() else None
        if not obra:
            return request.redirect('/app/admin/corralon')
        Material = request.env['coop.material'].sudo()
        Pedido = request.env['coop.pedido.material'].sudo()
        pedidos = Pedido.browse()
        for i in range(6):
            if not kw.get('material_%d' % i):
                continue
            try:
                mat = Material.browse(int(kw['material_%d' % i])).exists()
                cant = float(str(kw.get('cantidad_%d' % i, '')).replace(',', '.'))
            except (TypeError, ValueError):
                continue
            if mat and cant > 0:
                pedidos |= Pedido.create({
                    'obra_id': obra.id, 'member_id': member.id,
                    'material_id': mat.id, 'uom': mat.uom, 'cantidad': cant,
                    'state': 'aceptado', 'revisado_por': member.id})
        if not pedidos:
            return request.redirect('/app/admin/corralon')
        res = request.env['coop.orden.corralon'].sudo().generar_desde_pedidos(
            obra, pedidos, creado_por=member)
        n_skip = len(res['skipped'])
        # borrado defensivo: cualquier pedido temporal que NO quedó ligado a una
        # orden (skipped o sin asignar) no debe quedar suelto en la bandeja del
        # coordinador (que filtra orden_id == False).
        huerfanos = pedidos.filtered(lambda p: not p.orden_id)
        if huerfanos:
            huerfanos.unlink()
        ids = ','.join(str(o.id) for o in res['ordenes'])
        return request.redirect(
            '/app/admin/corralon/resultado?ordenes=%s&skip=%d' % (ids, n_skip))

    @http.route('/app/admin/corralon/resultado', type='http', auth='user',
                website=False)
    def corralon_resultado(self, ordenes='', skip='0', **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        ids = [int(x) for x in (ordenes or '').split(',') if x.isdigit()]
        ords = request.env['coop.orden.corralon'].sudo().browse(ids).exists()
        data = []
        for o in ords:
            num = o.corralon_id.whatsapp_num or ''
            wa = ('https://wa.me/%s?text=%s' % (
                num, urllib.parse.quote(o.mensaje or ''))) if num else ''
            data.append({'orden': o, 'wa_url': wa})
        try:
            n_skip = int(skip or 0)
        except (TypeError, ValueError):
            n_skip = 0
        return request.render('coop_portal.admin_corralon_resultado', {
            'member': member, 'data': data, 'n_skip': n_skip,
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/corralon/<int:orden_id>', type='http',
                auth='user', website=False)
    def corralon_orden(self, orden_id, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        orden = request.env['coop.orden.corralon'].sudo().browse(
            orden_id).exists()
        if not orden:
            return request.redirect('/app/admin/corralon')
        num = orden.corralon_id.whatsapp_num or ''
        wa_url = ('https://wa.me/%s?text=%s' % (
            num, urllib.parse.quote(orden.mensaje or ''))) if num else ''
        return request.render('coop_portal.admin_corralon_orden', {
            'member': member, 'orden': orden, 'wa_url': wa_url,
            'estado_labels': dict(request.env['coop.orden.corralon']
                                  ._fields['estado'].selection),
            'nav_rol': 'admin', 'nav_activo': 'tablero',
        })

    @http.route('/app/admin/corralon/enviar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def corralon_enviar(self, orden_id=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        try:
            orden = request.env['coop.orden.corralon'].sudo().browse(
                int(orden_id)).exists() if orden_id else None
        except (TypeError, ValueError):
            orden = None
        if orden and orden.estado == 'borrador':
            orden.action_enviar()
        return request.redirect(
            '/app/admin/corralon/%d' % orden.id if orden
            else '/app/admin/corralon')

    # ── notas de obra (M8-2) ─────────────────────────────────────────
    @http.route('/app/admin/notas', type='http', auth='user', website=False)
    def notas(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Nota = request.env['coop.nota'].sudo()
        data = [{'obra': o, 'n': Nota.search_count([('obra_id', '=', o.id)])}
                for o in self._obras_activas()]
        return request.render('coop_portal.admin_notas', {
            'member': member, 'data': data,
            'nav_rol': 'admin', 'nav_activo': 'tablero'})

    @http.route('/app/admin/notas/<int:obra_id>', type='http', auth='user',
                website=False)
    def notas_obra(self, obra_id, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        obra = request.env['project.project'].sudo().browse(obra_id).exists()
        if not obra:
            return request.redirect('/app/admin/notas')
        notas = request.env['coop.nota'].sudo().search(
            [('obra_id', '=', obra.id)], order='create_date desc')
        return request.render('coop_portal.admin_notas_obra', {
            'member': member, 'obra': obra, 'notas': notas,
            'nav_rol': 'admin', 'nav_activo': 'tablero'})

    @http.route('/app/admin/notas/agregar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def notas_agregar(self, obra_id=None, texto=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        obra = request.env['project.project'].sudo().browse(
            int(obra_id)).exists() if (obra_id or '').isdigit() else None
        texto = (texto or '').strip()
        if obra and texto:
            request.env['coop.nota'].sudo().create({
                'obra_id': obra.id, 'texto': texto, 'member_id': member.id})
        return request.redirect(
            '/app/admin/notas/%d' % obra.id if obra else '/app/admin/notas')

    # ── hoja de ruta visual (Gantt CPM por oficio) — M9 ──────────────
    @http.route('/app/admin/ruta', type='http', auth='user', website=False)
    def ruta(self, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Task = request.env['project.task'].sudo()
        cat_labels = dict(Task._fields['categoria_tarea'].selection)
        data = []
        for o in self._obras_activas():
            tasks = Task.search([('project_id', '=', o.id)],
                                order='inicio_temprano, id')
            if tasks:
                data.append(self._gantt(o, tasks, cat_labels))
            else:
                data.append({'obra': o, 'empty': True})
        return request.render('coop_portal.admin_ruta', {
            'member': member, 'data': data, 'cat_labels': cat_labels,
            'nav_rol': 'admin', 'nav_activo': 'ruta',
        })

    @staticmethod
    def _short(s, n=24):
        s = s or 'Tarea'
        return s if len(s) <= n else s[:n - 1] + '…'

    def _gantt(self, obra, tasks, cat_labels):
        """Gantt CPM profesional: UNA fila por tarea, agrupadas por oficio.
        El nombre va en la columna izquierda (no se pisa), la barra en la línea
        de tiempo, la holgura como una barra fina, y SOLO los conectores que
        importan (camino crítico + cruce entre oficios). Toda la geometría se
        calcula acá; el template solo dibuja. `adj_json` alimenta el resaltado
        de cadena al tocar una tarea."""
        LANE_SHORT = {'excavacion': 'Excavación', 'estructura': 'Estructura',
                      'albanileria': 'Albañilería', 'electricidad': 'Eléctrica',
                      'sanitaria': 'Sanitaria', 'terminaciones': 'Terminaciones',
                      'otro': 'Otro'}
        order = {c: i for i, c in enumerate(
            ['excavacion', 'estructura', 'albanileria', 'electricidad',
             'sanitaria', 'terminaciones', 'otro'])}
        ts = sorted(tasks, key=lambda t: (
            order.get(t.categoria_tarea or 'otro', 99),
            t.inicio_temprano, t.id))
        ids = set(tasks.ids)
        max_day = max(1.0, max(
            t.inicio_temprano + t.duracion_dias + max(t.holgura, 0.0) for t in ts))
        W, LW, pad_r = 720.0, 150.0, 30.0
        x0 = LW + 4
        px = (W - x0 - pad_r) / max_day
        axis_h, group_h, row_h, bar_h = 28.0, 22.0, 30.0, 18.0
        xof = lambda d: round(x0 + d * px, 1)

        items, bars, midy, seps = [], [], {}, []
        y, last = axis_h, None
        for t in ts:
            of = t.categoria_tarea or 'otro'
            if of != last:
                if last is not None:
                    seps.append(round(y, 1))
                items.append({'g': True, 'y': round(y + 15, 1),
                              'label': LANE_SHORT.get(of, of)})
                y += group_h
                last = of
            by = y + (row_h - bar_h) / 2.0
            mid = round(by + bar_h / 2.0, 1)
            x = xof(t.inicio_temprano)
            w = max(t.duracion_dias * px, 4.0)
            hw = max(t.holgura, 0.0) * px
            term = t.esta_terminada
            crit = t.es_critica
            color = '#9aa3ad' if term else ('#e24b4a' if crit else '#1a7f4e')
            midy[t.id] = mid
            items.append({'g': False, 'name': self._short(t.name), 'cy': mid,
                          'ty': round(mid + 3.5, 1), 'tid': t.id,
                          'done': term, 'dot': color})
            bars.append({
                'tid': t.id, 'x': x, 'y': round(by, 1), 'w': round(w, 1),
                'h': bar_h, 'fill': color, 'done': term,
                'holg': hw > 0.5 and not term, 'hx': round(x + w, 1),
                'hw': round(hw, 1), 'hy': round(by + bar_h - 3, 1),
                'dlabel': ('%gd' % t.duracion_dias) if w >= 22 else '',
                'dx': round(x + w / 2.0, 1), 'dy': round(mid + 3, 1),
            })
            y += row_h
        svg_h = round(y + 8, 1)

        step = 5 if max_day <= 32 else (10 if max_day <= 80 else 20)
        axis, d = [], 0
        while d <= max_day + 0.001:
            axis.append({'x': xof(d), 'label': str(int(d))})
            d += step

        bx = {b['tid']: b for b in bars}
        conns, adj = [], {}
        for t in ts:
            adj.setdefault(t.id, {'p': [], 's': []})
            for dprec in t.depend_on_ids:
                if dprec.id not in ids:
                    continue
                adj.setdefault(t.id, {'p': [], 's': []})['p'].append(dprec.id)
                adj.setdefault(dprec.id, {'p': [], 's': []})['s'].append(t.id)
                cruza = (dprec.categoria_tarea or 'otro') != (t.categoria_tarea or 'otro')
                crit = t.es_critica and dprec.es_critica
                if not (cruza or crit):
                    continue
                pb, sb = bx[dprec.id], bx[t.id]
                x1, y1 = round(pb['x'] + pb['w'], 1), midy[dprec.id]
                x2, y2 = sb['x'], midy[t.id]
                xr = round(x1 + 6, 1)
                conns.append({
                    'from': dprec.id, 'to': t.id,
                    'd': 'M %s %s H %s V %s H %s' % (x1, y1, xr, y2, x2),
                    'color': '#c47f17' if cruza else '#b3261e',
                    'dash': '4 3' if cruza else '0',
                    'marker': 'url(#ga)' if cruza else 'url(#gc)',
                })

        cuello, best = '', 0
        for t in ts:
            if not t.es_critica:
                continue
            n = sum(1 for dprec in t.depend_on_ids if dprec.id in ids
                    and (dprec.categoria_tarea or 'otro') != (t.categoria_tarea or 'otro'))
            if n > best:
                best, cuello = n, t.name
        edit = [{
            'tk': t, 'cruce': t.depend_on_ids.filtered(
                lambda d: (d.categoria_tarea or 'otro')
                != (t.categoria_tarea or 'otro')).mapped('name'),
        } for t in ts]
        fin_real = max(t.inicio_temprano + t.duracion_dias for t in ts)
        return {
            'obra': obra, 'fin_obra': int(round(fin_real)),
            'n_criticas': sum(1 for t in ts if t.es_critica),
            'n_terminadas': sum(1 for t in ts if t.esta_terminada),
            'n_tareas': len(ts), 'cuello': cuello,
            'items': items, 'bars': bars, 'conns': conns, 'axis': axis,
            'seps': seps, 'svg_w': W, 'svg_h': svg_h, 'axis_h': axis_h,
            'lw': LW, 'adj_json': json.dumps(adj), 'edit': edit,
        }

    @http.route('/app/admin/ruta/editar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def ruta_editar(self, task_id, duracion=None, categoria=None, **kw):
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Task = request.env['project.task'].sudo()
        try:
            tk = Task.browse(int(task_id)).exists()
        except (TypeError, ValueError):
            return request.redirect('/app/admin/ruta')
        if tk and tk.project_id in self._obras_activas():
            vals = {}
            if duracion is not None:
                try:
                    vals['duracion_dias'] = max(
                        0.0, float(str(duracion).replace(',', '.')))
                except (TypeError, ValueError):
                    pass
            cats = dict(Task._fields['categoria_tarea'].selection)
            if categoria == '':
                vals['categoria_tarea'] = False
            elif categoria in cats:
                vals['categoria_tarea'] = categoria
            if vals:
                tk.write(vals)
                try:
                    tk.project_id.action_calcular_ruta_critica()
                except Exception:  # noqa: BLE001 — sin tareas o ciclo
                    pass
        return request.redirect('/app/admin/ruta')

    @http.route('/app/admin/ruta/terminar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def ruta_terminar(self, task_id, hecho='1', **kw):
        """Marca a mano una tarea de la hoja de ruta como terminada (o la
        reabre) y recalcula la ruta crítica para que el Gantt lo refleje."""
        member = self._member()
        if not self._es_admin(member):
            return request.redirect('/app')
        Task = request.env['project.task'].sudo()
        try:
            tk = Task.browse(int(task_id)).exists()
        except (TypeError, ValueError):
            return request.redirect('/app/admin/ruta')
        if tk and tk.project_id in self._obras_activas():
            tk.write({'state': ESTADO_TERMINADA if hecho == '1'
                      else ESTADO_EN_CURSO})
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

    @http.route('/app/admin/reportes/exportar', type='http', auth='user',
                website=False)
    def reportes_exportar(self, rango='mes', tipo=None, **kw):
        """Exporta la vista unificada a .xlsx para el contador/auditoría.

        Cierra la promesa del FAQ (/app/ayuda) de exportar desde la app. Sin
        destinatario cableado: el botón es la acción y el compartir lo resuelve
        el menú nativo del teléfono al descargar. El nombre del archivo lleva
        el período (y el tipo si hay filtro)."""
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
        registros = request.env['coop.operacion'].sudo().search(
            dominio, order='fecha desc')
        tipo_label = {'avance': 'Avance', 'pedido': 'Pedido de material',
                      'gasto': 'Gasto', 'incidente': 'Incidente'}
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('Operaciones')
        for c, h in enumerate(['Fecha', 'Tipo', 'Obra', 'Socio', 'Detalle',
                               'Monto ($)', 'Cantidad', 'Unidad']):
            ws.write(0, c, h)
        for r, o in enumerate(registros, start=1):
            ws.write(r, 0, o.fecha.strftime('%d/%m/%Y') if o.fecha else '')
            ws.write(r, 1, tipo_label.get(o.tipo, o.tipo or ''))
            ws.write(r, 2, o.obra_id.name or '')
            ws.write(r, 3, o.member_id.name or '')
            ws.write(r, 4, o.detalle or '')
            ws.write(r, 5, o.monto or 0.0)
            ws.write(r, 6, o.cantidad or 0.0)
            ws.write(r, 7, o.uom or '')
        wb.close()
        buf.seek(0)
        nombre = 'operaciones_%s%s_%s.xlsx' % (
            rango, ('_%s' % tipo) if tipo else '', hoy)
        return request.make_response(buf.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument'
             '.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(nombre)),
        ])
