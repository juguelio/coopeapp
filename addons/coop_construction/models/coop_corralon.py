import re

from odoo import models, fields, api

from .coop_pedido import UOM_COMPRA


class CoopCorralon(models.Model):
    _name = 'coop.corralon'
    _description = 'Corralón / proveedor de materiales'
    _order = 'name'

    name = fields.Char(string='Corralón', required=True,
                       help='Ej: Corralón Austral')
    telefono = fields.Char(
        string='WhatsApp / teléfono',
        help='Número con código de país, ej: 5492944123456. '
             'Se usa para mandar la orden por WhatsApp.')
    direccion = fields.Char(string='Dirección')
    nota = fields.Char(string='Nota')
    active = fields.Boolean(string='Activo', default=True)

    whatsapp_num = fields.Char(
        string='Número WhatsApp (normalizado)',
        compute='_compute_whatsapp_num', store=True,
        help='Solo dígitos, listo para wa.me')

    @api.depends('telefono')
    def _compute_whatsapp_num(self) -> None:
        for r in self:
            r.whatsapp_num = re.sub(r'\D', '', r.telefono or '')


ESTADOS_ORDEN = [
    ('borrador', 'Borrador'),
    ('enviada', 'Enviada'),
    ('confirmada', 'Confirmada'),
    ('entregada', 'Entregada'),
]


class CoopOrdenCorralon(models.Model):
    _name = 'coop.orden.corralon'
    _description = 'Orden de materiales consolidada a un corralón'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Orden', compute='_compute_name', store=True)
    corralon_id = fields.Many2one(
        'coop.corralon', string='Corralón', required=True,
        ondelete='restrict', tracking=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict',
        tracking=True)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    pedido_ids = fields.One2many(
        'coop.pedido.material', 'orden_id', string='Pedidos consolidados')
    linea_ids = fields.One2many(
        'coop.orden.corralon.linea', 'orden_id',
        string='Líneas (material → fuente)')
    n_items = fields.Integer(
        string='Ítems', compute='_compute_n_items', store=True)
    tipo = fields.Selection([
        ('retiro_acopio', 'Retiro de acopio'),
        ('compra', 'Compra directa'),
        ('mixta', 'Mixta (acopio + compra)'),
    ], string='Tipo', compute='_compute_tipo', store=True)
    acopio_id = fields.Many2one(
        'coop.acopio', string='Acopio del retiro', readonly=True,
        compute='_compute_acopio_id', store=True,
        help='Acopio del que se retira (si la orden tiene líneas de acopio).')
    total_lineas = fields.Monetary(
        string='Total optimizado', compute='_compute_total_lineas', store=True)
    ahorro_estimado = fields.Monetary(
        string='Ahorro estimado', compute='_compute_total_lineas', store=True,
        help='Suma del ahorro de cada línea vs comprar hoy al mejor precio.')
    estado = fields.Selection(
        ESTADOS_ORDEN, string='Estado', default='borrador',
        required=True, tracking=True)
    fecha_envio = fields.Datetime(string='Enviada el', readonly=True)
    fecha_entrega = fields.Datetime(string='Entregada el', readonly=True)
    importe_total = fields.Monetary(
        string='Importe de la orden',
        help='Costo total de la compra. Al marcar Entregada se imputa como '
             'gasto de Materiales en la etapa en curso de la obra.')
    mensaje = fields.Text(
        string='Mensaje al corralón', compute='_compute_mensaje',
        help='Texto que se manda por WhatsApp / SMS.')
    gasto_id = fields.Many2one(
        'coop.proyeccion.gasto', string='Gasto imputado', readonly=True,
        ondelete='set null')
    creado_por = fields.Many2one('coop.member', string='Armada por',
                                 readonly=True)

    @api.depends('corralon_id', 'obra_id')
    def _compute_name(self) -> None:
        for r in self:
            ref = 'OC%05d' % r.id if isinstance(r.id, int) else 'OC nueva'
            r.name = '%s — %s — %s' % (
                ref, r.corralon_id.name or '?', r.obra_id.name or '?')

    @api.depends('pedido_ids', 'linea_ids')
    def _compute_n_items(self) -> None:
        for r in self:
            r.n_items = len(r.linea_ids) or len(r.pedido_ids)

    @api.depends('linea_ids.fuente')
    def _compute_tipo(self) -> None:
        for r in self:
            fuentes = set(r.linea_ids.mapped('fuente'))
            if not fuentes:
                r.tipo = False
            elif fuentes == {'acopio'}:
                r.tipo = 'retiro_acopio'
            elif fuentes == {'compra'}:
                r.tipo = 'compra'
            else:
                r.tipo = 'mixta'

    @api.depends('linea_ids.subtotal', 'linea_ids.ahorro')
    def _compute_total_lineas(self) -> None:
        for r in self:
            r.total_lineas = sum(r.linea_ids.mapped('subtotal'))
            r.ahorro_estimado = sum(r.linea_ids.mapped('ahorro'))

    @api.depends('linea_ids.fuente', 'linea_ids.acopio_id')
    def _compute_acopio_id(self) -> None:
        for r in self:
            retiros = r.linea_ids.filtered(
                lambda ln: ln.fuente == 'acopio' and ln.acopio_id)
            r.acopio_id = retiros[:1].acopio_id.id if retiros else False

    @api.depends('pedido_ids.cantidad', 'pedido_ids.name',
                 'linea_ids.cantidad', 'linea_ids.material_id',
                 'linea_ids.fuente', 'corralon_id', 'obra_id')
    def _compute_mensaje(self) -> None:
        uom_labels = dict(UOM_COMPRA)
        for r in self:
            lineas = []
            if r.linea_ids:
                for ln in r.linea_ids:
                    mat = ln.material_id.name or 'Material'
                    unidad = uom_labels.get(ln.uom, ln.uom or '')
                    etiqueta = ' (de acopio)' if ln.fuente == 'acopio' else ''
                    lineas.append('• %g %s — %s%s' % (
                        ln.cantidad, unidad, mat, etiqueta))
            else:
                for p in r.pedido_ids:
                    mat = (p.material_id.name or p.descripcion_libre
                           or 'Material')
                    unidad = uom_labels.get(p.uom, p.uom or '')
                    lineas.append('• %g %s — %s' % (p.cantidad, unidad, mat))
            cuerpo = '\n'.join(lineas) or '(sin ítems)'
            r.mensaje = (
                'Hola %s! 👷 Pedido de materiales para la obra "%s":\n\n'
                '%s\n\n'
                'Por favor confirmar disponibilidad y precio. ¡Gracias!'
            ) % (r.corralon_id.name or '', r.obra_id.name or '', cuerpo)

    # ── transiciones de estado ───────────────────────────────────────
    def action_enviar(self) -> None:
        for r in self:
            if r.estado == 'borrador':
                r.write({'estado': 'enviada',
                         'fecha_envio': fields.Datetime.now()})

    def action_confirmar(self) -> None:
        for r in self:
            if r.estado in ('borrador', 'enviada'):
                r.estado = 'confirmada'

    def action_volver_borrador(self) -> None:
        for r in self:
            if r.estado != 'entregada':
                r.estado = 'borrador'

    def action_entregar(self) -> None:
        for r in self:
            if r.estado == 'entregada':
                continue
            r.write({'estado': 'entregada',
                     'fecha_entrega': fields.Datetime.now()})
            r._imputar_gasto()

    def _imputar_gasto(self) -> None:
        """Imputa el importe de la orden como gasto de Materiales en la
        etapa en curso de la obra. Idempotente: no duplica si ya hay gasto.
        Usa el importe cargado o, si no hay, el total optimizado de las líneas."""
        self.ensure_one()
        importe = self.importe_total or self.total_lineas
        if self.gasto_id or not importe or importe <= 0:
            return
        # imputar solo a la etapa en curso (no a una cerrada ya certificada)
        etapa = self.env['coop.etapa'].search([
            ('obra_id', '=', self.obra_id.id),
            ('state', '=', 'en_curso'),
        ], limit=1)
        if not etapa:
            return
        gasto = self.env['coop.proyeccion.gasto'].create({
            'name': 'Orden %s (%d ítems)' % (
                self.corralon_id.name or 'corralón', self.n_items),
            'etapa_id': etapa.id,
            'rubro': 'materiales',
            'importe': importe,
            'state': 'pendiente',
            'observaciones': self.name,
        })
        self.gasto_id = gasto.id

    # ── optimizador de compras ───────────────────────────────────────
    @api.model
    def _candidatos_material(self, obra, material, saldo_restante):
        """Fuentes posibles para un material en una obra, ordenadas por
        precio ascendente. Cada candidato:
        {tipo: 'acopio'|'compra', corralon, acopio, precio}.
        - acopio: el acopio ACTIVO por corralón (el más viejo vigente con
          saldo, regla de consumo cronológico) si tiene precio congelado.
        - compra: el precio actual más reciente por corralón."""
        candidatos = []
        acopios = self.env['coop.acopio'].search([
            ('obra_id', '=', obra.id), ('state', '=', 'vigente'),
        ], order='corralon_id, fecha, numero')
        activo_por_corr = {}
        for ac in acopios:
            saldo = saldo_restante.get(ac.id, ac.saldo)
            if ac.corralon_id.id not in activo_por_corr and saldo > 0:
                activo_por_corr[ac.corralon_id.id] = ac
        for ac in activo_por_corr.values():
            precio_rec = ac.precio_ids.filtered(
                lambda p: p.material_id.id == material.id)[:1]
            if precio_rec:
                candidatos.append({
                    'tipo': 'acopio', 'corralon': ac.corralon_id,
                    'acopio': ac, 'precio': precio_rec.precio_congelado})
        listas = self.env['coop.lista.precio'].search([
            ('material_id', '=', material.id),
        ], order='corralon_id, fecha desc')
        vistos = set()
        for lp in listas:
            if lp.corralon_id.id in vistos:
                continue
            vistos.add(lp.corralon_id.id)
            candidatos.append({
                'tipo': 'compra', 'corralon': lp.corralon_id,
                'acopio': False, 'precio': lp.precio})
        candidatos.sort(key=lambda c: (
            c['precio'], c['tipo'] != 'acopio', c['corralon'].name))
        return candidatos

    @api.model
    def generar_desde_pedidos(self, obra, pedidos, creado_por=False):
        """Optimizador: asigna cada pedido aceptado a la fuente de menor costo
        (acopio congelado primero, compra al mejor precio después) y arma una
        orden por corralón con sus líneas explicadas. Determinista.
        Asignación por línea completa (sin partir saldo): cada pedido va a la
        fuente más barata que lo cubre. Devuelve dict con ordenes y skipped."""
        Linea = self.env['coop.orden.corralon.linea']
        # saldo disponible por acopio, se va consumiendo dentro de la corrida
        saldo_restante = {
            ac.id: ac.saldo for ac in self.env['coop.acopio'].search([
                ('obra_id', '=', obra.id), ('state', '=', 'vigente')])}
        ordenes = {}   # corralon_id -> orden
        skipped = []
        for p in pedidos.sorted('id'):
            cand = self._candidatos_material(obra, p.material_id, saldo_restante)
            if not cand:
                skipped.append(p)
                continue
            # elegibles: compra (siempre) o acopio cuyo saldo cubre la línea
            elegibles = [
                c for c in cand
                if c['tipo'] == 'compra'
                or saldo_restante.get(c['acopio'].id, 0) >= p.cantidad * c['precio']]
            if not elegibles:
                skipped.append(p)
                continue
            best = elegibles[0]   # ya vienen ordenados por precio
            mejor_compra = min(
                [c['precio'] for c in cand if c['tipo'] == 'compra'],
                default=best['precio'])
            ahorro = max(0.0, mejor_compra - best['precio']) * p.cantidad
            razon = self._razon_linea(best, cand)
            corr = best['corralon']
            orden = ordenes.get(corr.id)
            if not orden:
                orden = self.create({
                    'corralon_id': corr.id, 'obra_id': obra.id,
                    'creado_por': creado_por and creado_por.id or False,
                })
                ordenes[corr.id] = orden
            if best['tipo'] == 'acopio':
                saldo_restante[best['acopio'].id] -= p.cantidad * best['precio']
            Linea.create({
                'orden_id': orden.id, 'pedido_id': p.id,
                'material_id': p.material_id.id, 'cantidad': p.cantidad,
                'uom': p.uom, 'fuente': best['tipo'],
                'acopio_id': best['acopio'] and best['acopio'].id or False,
                'precio_unitario': best['precio'], 'razon': razon,
                'ahorro': ahorro, 'asignacion_manual': False,
            })
            p.orden_id = orden.id
        for orden in ordenes.values():
            orden.importe_total = orden.total_lineas
        return {'ordenes': list(ordenes.values()), 'skipped': skipped}

    @api.model
    def _razon_linea(self, best, candidatos):
        def fmt(c):
            return '$%s (%s)' % ('{:,.0f}'.format(c['precio']).replace(',', '.'),
                                 c['corralon'].name)
        otros = [c for c in candidatos if c is not best][:2]
        cola = ' · vs ' + ', '.join(fmt(c) for c in otros) if otros else ''
        if best['tipo'] == 'acopio':
            return 'Acopio #%s congelado $%s%s' % (
                best['acopio'].numero,
                '{:,.0f}'.format(best['precio']).replace(',', '.'), cola)
        return 'Mejor precio actual $%s%s' % (
            '{:,.0f}'.format(best['precio']).replace(',', '.'), cola)


class CoopOrdenCorralonLinea(models.Model):
    _name = 'coop.orden.corralon.linea'
    _description = 'Línea de orden al corralón (material asignado a una fuente)'
    _order = 'orden_id, id'

    orden_id = fields.Many2one(
        'coop.orden.corralon', string='Orden', required=True,
        ondelete='cascade')
    obra_id = fields.Many2one(
        related='orden_id.obra_id', store=True, string='Obra', readonly=True)
    pedido_id = fields.Many2one(
        'coop.pedido.material', string='Pedido origen', ondelete='set null')
    material_id = fields.Many2one(
        'coop.material', string='Material', required=True, ondelete='restrict')
    cantidad = fields.Float(string='Cantidad', required=True, default=1.0)
    uom = fields.Selection(UOM_COMPRA, string='Unidad', default='unidad')
    fuente = fields.Selection([
        ('acopio', 'Acopio congelado'),
        ('compra', 'Compra directa'),
    ], string='Fuente', required=True, default='compra')
    acopio_id = fields.Many2one(
        'coop.acopio', string='Acopio', ondelete='set null',
        help='Acopio del que se retira (si la fuente es acopio).')
    precio_unitario = fields.Monetary(string='Precio aplicado')
    subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(
        'res.currency', related='orden_id.currency_id', store=True,
        string='Moneda', readonly=True)
    razon = fields.Char(string='Por qué esta fuente')
    ahorro = fields.Monetary(string='Ahorro estimado')
    asignacion_manual = fields.Boolean(
        string='Asignación manual', default=False,
        help='El coordinador pisó la decisión del optimizador.')

    @api.depends('cantidad', 'precio_unitario')
    def _compute_subtotal(self) -> None:
        for r in self:
            r.subtotal = r.cantidad * r.precio_unitario
