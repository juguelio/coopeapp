from odoo import models, fields, api


class CoopAcopio(models.Model):
    _name = 'coop.acopio'
    _description = 'Acopio: plata con lista de precios congelada en un corralón'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # orden cronológico: el acopio más viejo se consume primero
    _order = 'corralon_id, fecha, numero'

    name = fields.Char(string='Acopio', compute='_compute_name', store=True)
    numero = fields.Char(string='N° de acopio', required=True,
                         help='Número de la carta de acopio, ej: 54073')
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict',
        tracking=True)
    corralon_id = fields.Many2one(
        'coop.corralon', string='Corralón', required=True,
        ondelete='restrict', tracking=True)
    fecha = fields.Date(string='Fecha del acopio', required=True,
                        default=fields.Date.context_today, tracking=True)
    monto_total = fields.Monetary(string='Monto entregado', required=True,
                                  tracking=True)
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id',
        string='Moneda', store=True, readonly=True)
    precio_ids = fields.One2many(
        'coop.acopio.precio', 'acopio_id', string='Lista de precios congelada')
    n_precios = fields.Integer(
        string='Materiales con precio', compute='_compute_n_precios')
    state = fields.Selection([
        ('vigente', 'Vigente'),
        ('agotado', 'Agotado'),
        ('cerrado', 'Cerrado'),
    ], string='Estado', default='vigente', required=True, tracking=True)

    consumido = fields.Monetary(
        string='Consumido', compute='_compute_saldo', store=True,
        help='Suma de los retiros valorizados a precio congelado.')
    saldo = fields.Monetary(
        string='Saldo disponible', compute='_compute_saldo', store=True,
        help='Monto entregado menos lo ya retirado a precio congelado.')
    pct_consumido = fields.Float(
        string='% consumido', compute='_compute_saldo', store=True)

    _sql_constraints = [
        ('numero_corralon_unique', 'UNIQUE(numero, corralon_id)',
         'Ya existe un acopio con ese número en ese corralón.'),
        ('monto_positivo', 'CHECK(monto_total > 0)',
         'El monto del acopio debe ser positivo.'),
    ]

    @api.depends('numero', 'corralon_id', 'obra_id')
    def _compute_name(self) -> None:
        for r in self:
            r.name = 'Acopio #%s — %s' % (
                r.numero or '?', r.corralon_id.name or '?')

    @api.depends('precio_ids')
    def _compute_n_precios(self) -> None:
        for r in self:
            r.n_precios = len(r.precio_ids)

    # NOTA: en M2 fase 1 el consumo es 0 (todavía no hay líneas de orden).
    # La fase 2 reescribe este compute para restar las líneas comprometidas.
    @api.depends('monto_total')
    def _compute_saldo(self) -> None:
        for r in self:
            r.consumido = 0.0
            r.saldo = r.monto_total
            r.pct_consumido = 0.0

    def action_cerrar(self) -> None:
        self.write({'state': 'cerrado'})

    def action_reabrir(self) -> None:
        self.write({'state': 'vigente'})


class CoopAcopioPrecio(models.Model):
    _name = 'coop.acopio.precio'
    _description = 'Precio congelado de un material en un acopio'
    _order = 'acopio_id, material_id'

    acopio_id = fields.Many2one(
        'coop.acopio', string='Acopio', required=True, ondelete='cascade')
    material_id = fields.Many2one(
        'coop.material', string='Material', required=True, ondelete='restrict')
    codigo_corralon = fields.Char(string='Código del corralón')
    precio_congelado = fields.Monetary(string='Precio congelado', required=True)
    currency_id = fields.Many2one(
        'res.currency', related='acopio_id.currency_id',
        string='Moneda', store=True, readonly=True)
    corralon_id = fields.Many2one(
        'coop.corralon', related='acopio_id.corralon_id', store=True,
        string='Corralón', readonly=True)

    _sql_constraints = [
        ('material_acopio_unique', 'UNIQUE(acopio_id, material_id)',
         'Ese material ya tiene precio congelado en este acopio.'),
        ('precio_positivo', 'CHECK(precio_congelado > 0)',
         'El precio congelado debe ser positivo.'),
    ]


class CoopListaPrecio(models.Model):
    _name = 'coop.lista.precio'
    _description = 'Precio actual de un material en un corralón (compra directa)'
    _order = 'corralon_id, material_id, fecha desc'

    corralon_id = fields.Many2one(
        'coop.corralon', string='Corralón', required=True, ondelete='cascade')
    material_id = fields.Many2one(
        'coop.material', string='Material', required=True, ondelete='restrict')
    precio = fields.Monetary(string='Precio actual', required=True)
    fecha = fields.Date(string='Fecha del precio', required=True,
                        default=fields.Date.context_today)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id)

    _sql_constraints = [
        ('precio_positivo', 'CHECK(precio > 0)',
         'El precio debe ser positivo.'),
    ]
