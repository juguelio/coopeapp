from odoo import api, fields, models


class CoopContrato(models.Model):
    """El contrato con el comitente: archivo Y fuente.

    Corte de Germán (25/08): del contrato salen **monto total, condiciones y
    fechas**. Los montos de certificación NO — siguen saliendo del avance real
    medido (`coop.foja.item` / `coop.certificado`). Este modelo no toca la
    certificación.

    Timing (Germán, 28/08): *"arreglamos de palabra, empezamos la obra y luego
    acomodamos los contratos"*. El papel llega DESPUÉS de la obra, no antes.
    Por eso `fecha_inicio` / `fecha_fin` son las fechas **de palabra**
    (operativas): existen desde el día 1 y son las que alimentan el CPM y el
    `atraso_dias` de la obra. Cuando después llega el contrato firmado, sus
    fechas se cargan aparte (`fecha_inicio_firmado` / `fecha_fin_firmado`) y
    solo RECONCILIAN: si divergen, se muestra (`fechas_divergen`), nunca se
    pisa lo acordado de palabra.

    La firma del comitente está BLOQUEADA hasta que Juan defina qué significa
    (papel + hash / token al mail / declaración del coordinador). Por ahora el
    contrato se carga con `estado='firmado'` y se adjunta el papel.
    """
    _name = 'coop.contrato'
    _description = 'Contrato de obra con el comitente'
    _inherit = ['mail.thread']
    _order = 'fecha_inicio desc, id desc'

    name = fields.Char(
        string='Identificación', required=True, tracking=True,
        help='N° de contrato, expediente o una referencia para ubicarlo.')
    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='cascade', tracking=True)
    comitente_id = fields.Many2one(
        'res.partner', string='Comitente', required=True, ondelete='restrict',
        tracking=True)
    estado = fields.Selection(
        [('palabra', 'De palabra'), ('firmado', 'Firmado')],
        string='Estado', default='palabra', required=True, tracking=True,
        help='"De palabra": lo acordado antes de empezar la obra, es lo que '
             'manda para el CPM y el atraso. "Firmado": ya llegó el papel y se '
             'cargaron sus fechas para reconciliar.')
    monto_total = fields.Monetary(
        string='Monto total del contrato', currency_field='currency_id',
        tracking=True,
        help='Lo pactado. NO alimenta la certificación: los certificados '
             'siguen saliendo del avance real medido.')
    currency_id = fields.Many2one(
        'res.currency', related='obra_id.currency_id', store=True,
        readonly=True)
    condiciones = fields.Text(string='Condiciones')
    fecha_inicio = fields.Date(
        string='Inicio (de palabra)', required=True, tracking=True,
        help='Fecha operativa acordada de palabra. Alimenta el CPM y el '
             'atraso de la obra. La fecha del papel firmado NO la pisa.')
    fecha_fin = fields.Date(
        string='Fin (de palabra)', required=True, tracking=True,
        help='Fecha operativa acordada de palabra. Alimenta el CPM y el '
             'atraso de la obra. La fecha del papel firmado NO la pisa.')
    fecha_inicio_firmado = fields.Date(
        string='Inicio (papel firmado)', tracking=True,
        help='Fecha que dice el contrato en papel. Rastro de auditoría: '
             'nunca pisa la fecha de palabra.')
    fecha_fin_firmado = fields.Date(
        string='Fin (papel firmado)', tracking=True,
        help='Fecha que dice el contrato en papel. Rastro de auditoría: '
             'nunca pisa la fecha de palabra.')
    fechas_divergen = fields.Boolean(
        string='Las fechas del papel divergen',
        compute='_compute_fechas_divergen',
        help='El papel firmado tiene fechas distintas a las acordadas de '
             'palabra. Se muestra para que alguien lo revise; no cambia el '
             'atraso, que sigue contra las fechas de palabra.')
    documento = fields.Binary(string='Documento del contrato', attachment=True)
    documento_filename = fields.Char(string='Nombre del archivo')

    _sql_constraints = [
        ('fechas_coherentes', 'CHECK(fecha_fin >= fecha_inicio)',
         'El fin contractual no puede ser anterior al inicio.'),
        ('fechas_firmado_coherentes',
         'CHECK(fecha_fin_firmado IS NULL OR fecha_inicio_firmado IS NULL '
         'OR fecha_fin_firmado >= fecha_inicio_firmado)',
         'El fin del papel firmado no puede ser anterior al inicio.'),
    ]

    @api.depends('estado', 'fecha_inicio', 'fecha_fin',
                 'fecha_inicio_firmado', 'fecha_fin_firmado')
    def _compute_fechas_divergen(self) -> None:
        for contrato in self:
            contrato.fechas_divergen = bool(
                contrato.estado == 'firmado' and (
                    (contrato.fecha_inicio_firmado
                     and contrato.fecha_inicio_firmado != contrato.fecha_inicio)
                    or (contrato.fecha_fin_firmado
                        and contrato.fecha_fin_firmado != contrato.fecha_fin)))
