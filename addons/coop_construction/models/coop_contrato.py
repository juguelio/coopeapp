from odoo import fields, models


class CoopContrato(models.Model):
    """El contrato con el comitente: archivo Y fuente.

    Corte de Germán (25/08): del contrato salen **monto total, condiciones y
    fechas**. Los montos de certificación NO — siguen saliendo del avance real
    medido (`coop.foja.item` / `coop.certificado`). Este modelo no toca la
    certificación.

    Su valor concreto: la obra no tenía ninguna fecha. Con `fecha_inicio` y
    `fecha_fin` acá, la ruta crítica pasa de "termina el día 26" a «6 días
    tarde contra el contrato» (ver `project.project.atraso_dias`).

    La firma del comitente está BLOQUEADA hasta que Juan defina qué significa
    (papel + hash / token al mail / declaración del coordinador). Por ahora el
    contrato se carga y se adjunta, sin firma.
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
        string='Inicio contractual', required=True, tracking=True)
    fecha_fin = fields.Date(
        string='Fin contractual', required=True, tracking=True)
    documento = fields.Binary(string='Documento del contrato', attachment=True)
    documento_filename = fields.Char(string='Nombre del archivo')

    _sql_constraints = [
        ('fechas_coherentes', 'CHECK(fecha_fin >= fecha_inicio)',
         'El fin contractual no puede ser anterior al inicio.'),
    ]
