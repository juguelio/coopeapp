from odoo import models, fields, tools


class CoopOperacion(models.Model):
    """Vista SQL de solo lectura que unifica todas las operaciones de la
    cooperativa (avances, pedidos, gastos, incidentes) para reportes y export.
    No tiene tabla propia (_auto = False): es un VIEW de Postgres."""
    _name = 'coop.operacion'
    _description = 'Operación (vista unificada para reportes)'
    _auto = False
    _order = 'fecha desc'

    fecha = fields.Date(string='Fecha', readonly=True)
    tipo = fields.Selection([
        ('avance', 'Avance'),
        ('pedido', 'Pedido de material'),
        ('gasto', 'Gasto'),
        ('incidente', 'Incidente'),
    ], string='Tipo', readonly=True)
    obra_id = fields.Many2one('project.project', string='Obra', readonly=True)
    member_id = fields.Many2one('coop.member', string='Socio', readonly=True)
    detalle = fields.Char(string='Detalle', readonly=True)
    monto = fields.Float(string='Monto', readonly=True)
    cantidad = fields.Float(string='Cantidad', readonly=True)
    uom = fields.Char(string='Unidad', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'coop_operacion')
        self.env.cr.execute("""
            CREATE VIEW coop_operacion AS (
                SELECT (10000000 + a.id) AS id,
                       'avance'::varchar AS tipo,
                       a.fecha AS fecha,
                       a.obra_id AS obra_id,
                       a.member_id AS member_id,
                       fi.name AS detalle,
                       0.0::double precision AS monto,
                       a.cantidad::double precision AS cantidad,
                       a.uom::varchar AS uom
                FROM coop_avance_medicion a
                JOIN coop_foja_item fi ON fi.id = a.foja_item_id
                WHERE a.state = 'validado'

                UNION ALL

                SELECT (20000000 + p.id),
                       'pedido'::varchar,
                       p.create_date::date,
                       p.obra_id,
                       p.member_id,
                       p.name,
                       0.0::double precision,
                       p.cantidad::double precision,
                       p.uom::varchar
                FROM coop_pedido_material p
                WHERE p.state = 'aceptado'

                UNION ALL

                SELECT (30000000 + g.id),
                       'gasto'::varchar,
                       g.fecha_pago,
                       g.obra_id,
                       NULL::integer,
                       g.name,
                       g.importe::double precision,
                       0.0::double precision,
                       NULL::varchar
                FROM coop_proyeccion_gasto g
                WHERE g.state = 'pagado'

                UNION ALL

                SELECT (40000000 + i.id),
                       'incidente'::varchar,
                       i.fecha,
                       i.obra_id,
                       i.reportado_por,
                       i.name,
                       COALESCE(i.valor_estimado, 0.0)::double precision,
                       i.cantidad::double precision,
                       NULL::varchar
                FROM coop_incidente i
            )
        """)
