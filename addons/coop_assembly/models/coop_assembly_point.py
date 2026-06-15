from odoo import models, fields


class CoopAssemblyPoint(models.Model):
    _name = 'coop.assembly.point'
    _description = 'Punto del orden del día de una asamblea'
    _order = 'assembly_id, sequence, id'

    assembly_id = fields.Many2one(
        'coop.assembly', string='Asamblea', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Orden', default=10)
    name = fields.Char(string='Tema', required=True)
    descripcion = fields.Text(string='Descripción')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_debate', 'En debate'),
        ('resuelto', 'Resuelto'),
    ], string='Estado', default='pendiente', required=True)
    vote_id = fields.Many2one(
        'coop.vote', string='Votación', ondelete='set null',
        help='Si el punto se vota, la votación asociada (coop.vote).')
    resolucion = fields.Text(
        string='Resolución',
        help='Lo que quedó decidido (lo redacta el secretario).')

    def action_debate(self) -> None:
        for r in self:
            if r.state == 'pendiente':
                r.state = 'en_debate'

    def action_resolver(self) -> None:
        for r in self:
            r.state = 'resuelto'

    def action_pendiente(self) -> None:
        self.write({'state': 'pendiente'})
