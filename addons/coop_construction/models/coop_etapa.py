from odoo import models, fields, api

RUBROS = [
    ('mano_obra', 'Mano de obra'),
    ('materiales', 'Materiales e insumos'),
    ('maquinarias', 'Maquinarias y Herramientas'),
    ('equipo_tecnico', 'Equipo Técnico'),
    ('gastos_operativos', 'Gastos Operativos'),
    ('gastos_administrativos', 'Gastos Administrativos'),
]


class CoopEtapa(models.Model):
    _name = 'coop.etapa'
    _description = 'Proyección de pagos por etapa de obra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'obra_id, numero'

    name = fields.Char(string='Etapa', required=True, tracking=True)
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict', tracking=True)
    numero = fields.Integer(string='N° de etapa', required=True, default=1)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    fecha_certificacion = fields.Date(
        string='Fecha de certificación', tracking=True,
        help='Fecha estimada de certificación de la etapa')
    meses_espera = fields.Integer(
        string='Meses de espera',
        help='Meses estimados entre certificación y cobro')
    state = fields.Selection([
        ('planificacion', 'Planificación'),
        ('en_curso', 'En curso'),
        ('cerrada', 'Cerrada'),
    ], string='Estado', default='planificacion', required=True, tracking=True)

    ingreso = fields.Monetary(
        string='Ingreso de la etapa', tracking=True,
        help='Monto que ingresa por la certificación de esta etapa')
    saldo_etapa_anterior = fields.Monetary(
        string='Saldo etapa anterior',
        help='Saldo en cuenta que queda de la etapa anterior')

    gasto_ids = fields.One2many(
        'coop.proyeccion.gasto', 'etapa_id', string='Gastos planificados')
    cuadrilla_ids = fields.One2many(
        'coop.etapa.cuadrilla', 'etapa_id', string='Cuadrilla')

    total_planificado = fields.Monetary(
        string='Gastos planificados', compute='_compute_totales', store=True)
    total_pagado = fields.Monetary(
        string='Pagado', compute='_compute_totales', store=True)
    saldo_sin_planificar = fields.Monetary(
        string='Saldo sin planificar', compute='_compute_totales', store=True,
        help='Ingreso + saldo anterior - gastos planificados')
    controlador = fields.Monetary(
        string='Controlador (diferencia)', compute='_compute_totales', store=True,
        help='Ingreso + saldo anterior - pagos efectuados: lo que debería haber en cuenta')
    total_cuadrilla = fields.Monetary(
        string='Mano de obra mensual (cuadrilla)',
        compute='_compute_total_cuadrilla', store=True)
    notes = fields.Text(string='Observaciones')

    _sql_constraints = [
        ('numero_obra_unique', 'UNIQUE(obra_id, numero)',
         'El número de etapa debe ser único por obra.'),
    ]

    @api.depends('ingreso', 'saldo_etapa_anterior',
                 'gasto_ids.importe', 'gasto_ids.state')
    def _compute_totales(self) -> None:
        for record in self:
            disponible = record.ingreso + record.saldo_etapa_anterior
            record.total_planificado = sum(record.gasto_ids.mapped('importe'))
            record.total_pagado = sum(
                record.gasto_ids.filtered(
                    lambda g: g.state == 'pagado').mapped('importe'))
            record.saldo_sin_planificar = disponible - record.total_planificado
            record.controlador = disponible - record.total_pagado

    @api.depends('cuadrilla_ids.subtotal')
    def _compute_total_cuadrilla(self) -> None:
        for record in self:
            record.total_cuadrilla = sum(record.cuadrilla_ids.mapped('subtotal'))

    def action_en_curso(self) -> None:
        self.write({'state': 'en_curso'})

    def action_cerrar(self) -> None:
        self.write({'state': 'cerrada'})

    def action_planificacion(self) -> None:
        self.write({'state': 'planificacion'})


class CoopProyeccionGasto(models.Model):
    _name = 'coop.proyeccion.gasto'
    _description = 'Gasto planificado de etapa'
    _order = 'etapa_id, id'

    name = fields.Char(string='Descripción', required=True)
    etapa_id = fields.Many2one(
        'coop.etapa', string='Etapa', required=True, ondelete='cascade')
    obra_id = fields.Many2one(
        related='etapa_id.obra_id', string='Obra', store=True, readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='etapa_id.currency_id',
        string='Moneda', store=True, readonly=True)
    periodo = fields.Char(
        string='Período / sector',
        help='Mes o sector de obra al que corresponde (ej: pasillo, planta baja)')
    rubro = fields.Selection(RUBROS, string='Rubro', required=True)
    importe = fields.Monetary(string='Importe', required=True)
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado'),
    ], string='Estado', default='pendiente', required=True)
    fecha_pago = fields.Date(string='Fecha de pago')
    presupuesto_confirmado = fields.Boolean(
        string='Presupuesto confirmado', default=False)
    observaciones = fields.Char(string='Observaciones')

    _sql_constraints = [
        ('importe_positivo', 'CHECK(importe > 0)',
         'El importe del gasto debe ser positivo.'),
    ]

    def action_pagar(self) -> None:
        self.write({'state': 'pagado', 'fecha_pago': fields.Date.today()})

    def action_pendiente(self) -> None:
        self.write({'state': 'pendiente', 'fecha_pago': False})


class CoopEtapaCuadrilla(models.Model):
    _name = 'coop.etapa.cuadrilla'
    _description = 'Cálculo de mano de obra por rol de cuadrilla'
    _order = 'etapa_id, id'

    etapa_id = fields.Many2one(
        'coop.etapa', string='Etapa', required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', related='etapa_id.currency_id',
        string='Moneda', store=True, readonly=True)
    rol = fields.Selection([
        ('coordinador', 'Coordinador'),
        ('oficial', 'Oficial'),
        ('medio_oficial', 'Medio oficial'),
        ('ayudante', 'Ayudante'),
        ('otro', 'Otro'),
    ], string='Rol', required=True)
    cantidad = fields.Integer(string='Cantidad', required=True, default=1)
    tarifa_diaria = fields.Monetary(string='Tarifa diaria', required=True)
    dias = fields.Float(string='Días', required=True, default=30.0)
    subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_subtotal', store=True)

    _sql_constraints = [
        ('cantidad_positiva', 'CHECK(cantidad > 0)',
         'La cantidad debe ser positiva.'),
    ]

    @api.depends('cantidad', 'tarifa_diaria', 'dias')
    def _compute_subtotal(self) -> None:
        for record in self:
            record.subtotal = record.cantidad * record.tarifa_diaria * record.dias
