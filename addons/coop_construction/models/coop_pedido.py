from odoo import models, fields, api

UOM_COMPRA = [
    ('bolsa', 'Bolsa'),
    ('m3', 'm³'),
    ('unidad', 'Unidad'),
    ('barra', 'Barra'),
    ('lata', 'Lata'),
    ('ml', 'Metro lineal'),
    ('m2', 'm²'),
    ('otro', 'Otro'),
]


class CoopMaterial(models.Model):
    _name = 'coop.material'
    _description = 'Catálogo de materiales (pedidos)'
    _order = 'name'

    name = fields.Char(string='Material', required=True,
                       help='Ej: Cemento, Ladrillo hueco, Pintura látex')
    code = fields.Char(string='Código')
    uom = fields.Selection(UOM_COMPRA, string='Unidad de compra', required=True)
    detalle = fields.Char(string='Detalle', help='Ej: bolsa 50kg, lata 20L')
    icono = fields.Char(string='Ícono', help='Emoji para la app, ej: 🪨')
    active = fields.Boolean(string='Activo', default=True)


class CoopPedidoMaterial(models.Model):
    _name = 'coop.pedido.material'
    _description = 'Pedido de material de un socio'
    _order = 'create_date desc'

    name = fields.Char(
        string='Pedido', compute='_compute_name', store=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict')
    member_id = fields.Many2one(
        'coop.member', string='Socio que pide', required=True,
        ondelete='restrict', domain=[('state', '=', 'active')],
        default=lambda self: self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1))
    material_id = fields.Many2one(
        'coop.material', string='Material', ondelete='restrict')
    descripcion_libre = fields.Char(
        string='Otro material',
        help='Si no está en el catálogo, lo escribís acá')
    uom = fields.Selection(UOM_COMPRA, string='Unidad', required=True,
                           default='unidad')
    cantidad = fields.Float(string='Cantidad', required=True, default=1.0)
    cantidad_original = fields.Float(
        string='Cantidad pedida (original)', readonly=True,
        help='Lo que pidió el socio, antes de que el coordinador corrija')
    nota = fields.Char(string='Nota / para qué')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ], string='Estado', default='pendiente', required=True)
    revisado_por = fields.Many2one(
        'coop.member', string='Revisado por', readonly=True)
    motivo_rechazo = fields.Char(string='Motivo del rechazo')

    _sql_constraints = [
        ('cantidad_positiva', 'CHECK(cantidad > 0)',
         'La cantidad debe ser positiva.'),
    ]

    @api.depends('material_id', 'descripcion_libre', 'cantidad', 'uom')
    def _compute_name(self) -> None:
        for r in self:
            mat = r.material_id.name or r.descripcion_libre or 'Material'
            unidad = dict(self._fields['uom'].selection).get(r.uom, r.uom)
            r.name = '%s — %g %s' % (mat, r.cantidad, unidad)

    @api.onchange('material_id')
    def _onchange_material(self) -> None:
        if self.material_id:
            self.uom = self.material_id.uom

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('cantidad_original', vals.get('cantidad', 0.0))
        return super().create(vals_list)

    def _revisor(self):
        return self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1)

    def action_aceptar(self) -> None:
        self.write({'state': 'aceptado', 'revisado_por': self._revisor().id})

    def action_rechazar(self, motivo=False) -> None:
        self.write({
            'state': 'rechazado', 'revisado_por': self._revisor().id,
            'motivo_rechazo': motivo or self.motivo_rechazo,
        })

    def action_corregir_cantidad(self, nueva) -> None:
        for r in self:
            r.write({'cantidad': nueva, 'state': 'aceptado',
                     'revisado_por': r._revisor().id})
