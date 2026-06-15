from odoo import models, fields, api


class CoopActaFirma(models.Model):
    _name = 'coop.acta.firma'
    _description = 'Firma electrónica interna de un acta de asamblea'
    _order = 'create_date'

    assembly_id = fields.Many2one(
        'coop.assembly', string='Asamblea', required=True, ondelete='cascade')
    member_id = fields.Many2one(
        'coop.member', string='Firmante', required=True, ondelete='restrict')
    rol = fields.Selection([
        ('presidente', 'Presidente'),
        ('secretario', 'Secretario'),
        ('sindico', 'Síndico'),
    ], string='Rol', required=True)
    fecha = fields.Datetime(string='Firmado el', default=fields.Datetime.now,
                            readonly=True)
    hash_acta = fields.Char(
        string='Hash del acta', readonly=True,
        help='SHA-256 del texto del acta al momento de firmar.')
    firma_valida = fields.Boolean(
        string='Firma vigente', compute='_compute_firma_valida',
        help='Falsa si el acta cambió después de la firma.')

    _sql_constraints = [
        ('rol_unico_por_asamblea', 'UNIQUE(assembly_id, member_id, rol)',
         'Ese socio ya firmó esta acta con ese rol.'),
    ]

    @api.depends('hash_acta', 'assembly_id.acta_hash')
    def _compute_firma_valida(self) -> None:
        for r in self:
            r.firma_valida = bool(
                r.hash_acta and r.hash_acta == r.assembly_id.acta_hash)
