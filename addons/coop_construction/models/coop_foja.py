from odoo import models, fields, api

UOM_FISICA = [
    ('m2', 'm²'),
    ('m3', 'm³'),
    ('ml', 'ml'),
    ('u', 'Unidad'),
    ('gl', 'Global'),
    ('kg', 'kg'),
    ('otro', 'Otro'),
]

MEDIDA_TRABAJO = [
    ('jornal', 'Jornal diario'),
    ('hora', 'Hora trabajada'),
    ('tarea', 'Tarea realizada'),
]


class CoopUnidadProduccion(models.Model):
    _name = 'coop.unidad.produccion'
    _description = 'Unidad de producción (catálogo de ítems con precio)'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True,
                       help='Ej: Pintura, Pintura en altura, Excavación')
    code = fields.Char(string='Código')
    uom = fields.Selection(UOM_FISICA, string='Unidad de medida', required=True)
    precio_referencia = fields.Monetary(
        string='Precio de referencia',
        help='Precio unitario de referencia; cada obra puede ajustarlo en su foja')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    descripcion = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)


class CoopFojaItem(models.Model):
    _name = 'coop.foja.item'
    _description = 'Ítem de foja de medición'
    _order = 'obra_id, item'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict')
    etapa_id = fields.Many2one(
        'coop.etapa', string='Etapa', ondelete='set null',
        domain="[('obra_id', '=', obra_id)]")
    task_id = fields.Many2one(
        'project.task', string='Tarea (Gantt)', ondelete='set null',
        domain="[('project_id', '=', obra_id)]")
    item = fields.Char(string='Ítem', required=True, help='Ej: 1.0, 2.3')
    name = fields.Char(string='Descripción', required=True)
    unidad_produccion_id = fields.Many2one(
        'coop.unidad.produccion', string='Unidad de producción',
        ondelete='restrict')
    uom = fields.Selection(UOM_FISICA, string='U.', required=True)
    cantidad = fields.Float(string='Cantidad', required=True, default=1.0)
    precio_unitario = fields.Monetary(string='Precio unitario', required=True)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    precio_total = fields.Monetary(
        string='Precio total', compute='_compute_precio_total', store=True)
    incidencia = fields.Float(
        string='Incidencia %', compute='_compute_incidencia', store=True,
        digits=(7, 4), help='Peso del ítem sobre el total de la foja de la obra')
    avance_ids = fields.One2many(
        'coop.avance.medicion', 'foja_item_id', string='Avances')
    cantidad_ejecutada = fields.Float(
        string='Ejecutado', compute='_compute_avance', store=True,
        help='Suma de avances validados')
    avance_pct = fields.Float(
        string='Avance %', compute='_compute_avance', store=True, digits=(5, 2))
    aporte_pct = fields.Float(
        string='Aporte al avance de obra %', compute='_compute_avance',
        store=True, digits=(7, 4),
        help='Avance del ítem ponderado por su incidencia')

    _sql_constraints = [
        ('cantidad_positiva', 'CHECK(cantidad > 0)',
         'La cantidad prevista debe ser positiva.'),
    ]

    @api.depends('cantidad', 'precio_unitario')
    def _compute_precio_total(self) -> None:
        for record in self:
            record.precio_total = record.cantidad * record.precio_unitario

    @api.depends('precio_total', 'obra_id.foja_item_ids.precio_total')
    def _compute_incidencia(self) -> None:
        for record in self:
            total_obra = sum(record.obra_id.foja_item_ids.mapped('precio_total'))
            record.incidencia = (
                record.precio_total / total_obra * 100 if total_obra else 0.0)

    @api.depends('avance_ids.cantidad', 'avance_ids.state',
                 'cantidad', 'incidencia')
    def _compute_avance(self) -> None:
        for record in self:
            validados = record.avance_ids.filtered(
                lambda a: a.state == 'validado')
            record.cantidad_ejecutada = sum(validados.mapped('cantidad'))
            record.avance_pct = min(
                record.cantidad_ejecutada / record.cantidad * 100
                if record.cantidad else 0.0, 100.0)
            record.aporte_pct = record.incidencia * record.avance_pct / 100

    @api.onchange('unidad_produccion_id')
    def _onchange_unidad_produccion(self) -> None:
        if self.unidad_produccion_id:
            self.uom = self.unidad_produccion_id.uom
            if self.unidad_produccion_id.precio_referencia:
                self.precio_unitario = self.unidad_produccion_id.precio_referencia
            if not self.name:
                self.name = self.unidad_produccion_id.name


class CoopAvanceMedicion(models.Model):
    _name = 'coop.avance.medicion'
    _description = 'Avance de medición registrado por un socio'
    _order = 'fecha desc, id desc'

    foja_item_id = fields.Many2one(
        'coop.foja.item', string='Ítem de foja', required=True,
        ondelete='restrict')
    obra_id = fields.Many2one(
        related='foja_item_id.obra_id', string='Obra', store=True,
        readonly=True)
    uom = fields.Selection(
        related='foja_item_id.uom', string='U.', store=True, readonly=True)
    member_id = fields.Many2one(
        'coop.member', string='Socio', required=True, ondelete='restrict',
        domain=[('state', '=', 'active')],
        default=lambda self: self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1))
    fecha = fields.Date(
        string='Fecha', required=True, default=fields.Date.today)
    cantidad = fields.Float(
        string='Cantidad producida', required=True,
        help='En la unidad de medida del ítem (m², ml, unidades…)')
    medida_trabajo = fields.Selection(
        MEDIDA_TRABAJO, string='Medido por', required=True, default='jornal')
    cantidad_trabajo = fields.Float(
        string='Trabajo insumido', required=True, default=1.0,
        help='Jornales, horas o tareas según la unidad de medida elegida')
    productividad = fields.Float(
        string='Productividad', compute='_compute_productividad', store=True,
        digits=(12, 2),
        help='Cantidad producida por jornal / hora / tarea')
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('validado', 'Validado'),
    ], string='Estado', default='borrador', required=True)
    observaciones = fields.Char(string='Observaciones')

    _sql_constraints = [
        ('cantidad_positiva', 'CHECK(cantidad > 0)',
         'La cantidad producida debe ser positiva.'),
        ('trabajo_positivo', 'CHECK(cantidad_trabajo > 0)',
         'El trabajo insumido debe ser positivo.'),
    ]

    @api.depends('cantidad', 'cantidad_trabajo')
    def _compute_productividad(self) -> None:
        for record in self:
            record.productividad = (
                record.cantidad / record.cantidad_trabajo
                if record.cantidad_trabajo else 0.0)

    def action_validar(self) -> None:
        self.write({'state': 'validado'})

    def action_borrador(self) -> None:
        self.write({'state': 'borrador'})
